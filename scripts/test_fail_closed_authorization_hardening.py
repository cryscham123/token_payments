from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiAuthContext, HttpRouter, StoreCatalogApi, StoreOwnerInventoryApi  # noqa: E402
from token_payments.api import register_store_catalog_routes, register_store_owner_inventory_routes  # noqa: E402
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.contexts.inventory.application import StoreOwnerInventoryCommandResult  # noqa: E402
from token_payments.contexts.inventory.application import StoreOwnerInventoryCommandStatus  # noqa: E402
from token_payments.contexts.inventory.domain import ProductInventory, Quantity  # noqa: E402
from token_payments.contexts.store_catalog.application import StoreCatalogApplicationService  # noqa: E402
from token_payments.contexts.store_catalog.domain import StoreMembership, StoreMembershipRole  # noqa: E402
from token_payments.shared.domain import CommandId, ProductId, StoreId, UserId  # noqa: E402

from _store_catalog_test_support import (  # noqa: E402
    OTHER_ID,
    OWNER_ID,
    OWNER_WALLET,
    PRODUCT_ID,
    STORE_ID,
    FakeStoreCatalogRepository,
    FixedIdGenerator,
    auth,
    decode,
    json_body,
    price_payload,
)


NOW = datetime(2026, 5, 22, 4, 0, tzinfo=UTC)
VARIANT_ID = "var_ledger_mug_default"


def test_inventory_write_requires_scope_even_for_canonical_owner() -> None:
    router = _inventory_router(
        auth_context=ApiAuthContext(
            user_id=str(OWNER_ID),
            role=UserRole.STORE_OWNER.value,
            scopes=(),
            session_id="session-owner-without-scope",
        ),
        query=CanonicalInventoryQuery({(STORE_ID, OWNER_ID): "OWNER"}),
    )

    response = router.handle(
        "POST",
        _variant_inventory_path("intake"),
        headers={"Content-Type": "application/json", "Idempotency-Key": "fail-closed-no-scope"},
        body=_json_body({"quantity": 1, "reason": "missing write scope"}),
        received_at=NOW,
    )

    assert response.status_code == 403
    assert _json(response.body)["error"]["code"] == "STORE_OWNER_INVENTORY_FORBIDDEN"


def test_inventory_write_requires_canonical_store_membership_when_scope_is_present() -> None:
    stale_projection_query = LegacyOwnerOnlyInventoryQuery(
        stale_projection_roles={(STORE_ID, OWNER_ID): "OWNER"},
        owner_fallback={STORE_ID: OWNER_ID},
    )
    router = _inventory_router(
        auth_context=ApiAuthContext(
            user_id=str(OWNER_ID),
            role=UserRole.STORE_OWNER.value,
            scopes=("inventory:write",),
            session_id="session-stale-projection",
        ),
        query=stale_projection_query,
    )

    response = router.handle(
        "POST",
        _variant_inventory_path("intake"),
        headers={"Content-Type": "application/json", "Idempotency-Key": "fail-closed-stale-projection"},
        body=_json_body({"quantity": 1, "reason": "stale projection must not authorize"}),
        received_at=NOW,
    )

    assert response.status_code == 403
    assert _json(response.body)["error"]["code"] == "STORE_OWNER_STORE_FORBIDDEN"
    assert stale_projection_query.owner_fallback_calls == 0


def test_inventory_write_allows_owner_or_manager_only_with_scope_and_canonical_membership() -> None:
    for role in ("OWNER", "MANAGER"):
        handler = CapturingInventoryHandler()
        router = _inventory_router(
            auth_context=ApiAuthContext(
                user_id=str(OWNER_ID),
                role=UserRole.CUSTOMER.value,
                scopes=("inventory:write",),
                session_id=f"session-{role.lower()}",
            ),
            query=CanonicalInventoryQuery({(STORE_ID, OWNER_ID): role}),
            handler=handler,
        )

        response = router.handle(
            "POST",
            _variant_inventory_path("intake"),
            headers={"Content-Type": "application/json", "Idempotency-Key": f"inventory-{role.lower()}-allowed"},
            body=_json_body({"quantity": 2, "reason": f"{role.lower()} stock intake"}),
            received_at=NOW,
        )

        assert response.status_code == 202
        assert handler.actor_store_roles == [role]


def test_inventory_write_rejects_revoked_canonical_membership() -> None:
    router = _inventory_router(
        auth_context=ApiAuthContext(
            user_id=str(OWNER_ID),
            role=UserRole.CUSTOMER.value,
            scopes=("inventory:write",),
            session_id="session-revoked",
        ),
        query=CanonicalInventoryQuery({(STORE_ID, OWNER_ID): None}),
    )

    response = router.handle(
        "POST",
        _variant_inventory_path("intake"),
        headers={"Content-Type": "application/json", "Idempotency-Key": "fail-closed-revoked"},
        body=_json_body({"quantity": 1, "reason": "revoked member"}),
        received_at=NOW,
    )

    assert response.status_code == 403
    assert _json(response.body)["error"]["code"] == "STORE_OWNER_STORE_FORBIDDEN"


def test_product_registration_requires_api_scope_and_service_membership_check() -> None:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    repository.seed_store(owner_id=OWNER_ID)

    no_scope = _catalog_router(repository, auth(OWNER_ID, UserRole.CUSTOMER, scopes=())).handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-no-scope"},
        body=_product_body(),
        received_at=NOW,
    )

    repository.memberships[(STORE_ID, OWNER_ID)] = StoreMembership(
        STORE_ID,
        OWNER_ID,
        StoreMembershipRole.OWNER,
        active=False,
    )
    revoked_member = _catalog_router(
        repository,
        auth(OWNER_ID, UserRole.CUSTOMER, scopes=("product:write",)),
    ).handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-revoked-member"},
        body=_product_body(),
        received_at=NOW,
    )

    assert no_scope.status_code == 403
    assert decode(no_scope.body)["error"]["message"] == "product:write permission is required"
    assert revoked_member.status_code == 403
    assert decode(revoked_member.body)["error"]["code"] == "STORE_OWNER_STORE_FORBIDDEN"


def _inventory_router(
    *,
    auth_context: ApiAuthContext,
    query: "CanonicalInventoryQuery",
    handler: "CapturingInventoryHandler | None" = None,
) -> HttpRouter:
    router = HttpRouter(auth_context_factory=lambda _request: auth_context, allow_dev_auth_headers=False)
    register_store_owner_inventory_routes(
        router,
        StoreOwnerInventoryApi(query=query, command_handler=handler or CapturingInventoryHandler()),
    )
    return router


def _catalog_router(repository: FakeStoreCatalogRepository, auth_context: ApiAuthContext) -> HttpRouter:
    service = StoreCatalogApplicationService(repository=repository, user_id_generator=FixedIdGenerator(str(OTHER_ID)))
    router = HttpRouter(auth_context_factory=lambda _request: auth_context, allow_dev_auth_headers=False)
    register_store_catalog_routes(router, StoreCatalogApi(service, id_generator=FixedIdGenerator(str(PRODUCT_ID))))
    return router


def _product_body() -> bytes:
    return json_body({"name": "Ledger Mug", "price": price_payload(), "initialTotalStock": 10})


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _variant_inventory_path(action: str) -> str:
    return f"/store-owner/stores/{STORE_ID}/inventory/{PRODUCT_ID}/variants/{VARIANT_ID}/{action}"


def _json(body: bytes) -> dict[str, Any]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


class CanonicalInventoryQuery:
    def __init__(
        self,
        canonical_roles: dict[tuple[StoreId, UserId], str | None],
        *,
        stale_projection_roles: dict[tuple[StoreId, UserId], str] | None = None,
        owner_fallback: dict[StoreId, UserId] | None = None,
    ) -> None:
        self.canonical_roles = canonical_roles
        self.stale_projection_roles = stale_projection_roles or {}
        self.owner_fallback = owner_fallback or {}
        self.owner_fallback_calls = 0

    def list_inventory(self, store_id: StoreId | None = None):
        return ()

    def list_inventory_for_owner(self, owner_user_id: UserId, store_id: StoreId | None = None):
        return ()

    def list_inventory_for_member(self, owner_user_id: UserId, store_id: StoreId | None = None):
        return ()

    def owner_for_store(self, store_id: StoreId) -> UserId | None:
        self.owner_fallback_calls += 1
        return self.owner_fallback.get(store_id)

    def store_role_for_user(self, store_id: StoreId, user_id: UserId) -> str | None:
        return self.canonical_roles.get((store_id, user_id))

    def projection_role_for_user(self, store_id: StoreId, user_id: UserId) -> str | None:
        return self.stale_projection_roles.get((store_id, user_id))


class LegacyOwnerOnlyInventoryQuery:
    def __init__(
        self,
        *,
        stale_projection_roles: dict[tuple[StoreId, UserId], str],
        owner_fallback: dict[StoreId, UserId],
    ) -> None:
        self.stale_projection_roles = stale_projection_roles
        self.owner_fallback = owner_fallback
        self.owner_fallback_calls = 0

    def list_inventory(self, store_id: StoreId | None = None):
        return ()

    def list_inventory_for_owner(self, owner_user_id: UserId, store_id: StoreId | None = None):
        return ()

    def owner_for_store(self, store_id: StoreId) -> UserId | None:
        self.owner_fallback_calls += 1
        return self.owner_fallback.get(store_id)

    def projection_role_for_user(self, store_id: StoreId, user_id: UserId) -> str | None:
        return self.stale_projection_roles.get((store_id, user_id))


class CapturingInventoryHandler:
    def __init__(self) -> None:
        self.actor_store_roles: list[str | None] = []
        self.inventory = ProductInventory(
            product_id=PRODUCT_ID,
            store_id=STORE_ID,
            available_stock=Quantity(5),
            reserved_stock=Quantity(0),
            total_stock=Quantity(5),
            public_variant_id=VARIANT_ID,
        )

    def increase_stock(self, command: Any) -> StoreOwnerInventoryCommandResult:
        self.actor_store_roles.append(command.actor_store_role)
        self.inventory = self.inventory.increase_stock(command.quantity)
        return StoreOwnerInventoryCommandResult(
            command_id=CommandId(str(command.command_id)),
            store_id=STORE_ID,
            product_id=PRODUCT_ID,
            status=StoreOwnerInventoryCommandStatus.ACCEPTED,
            inventory=self.inventory,
        )

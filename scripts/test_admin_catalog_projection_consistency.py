from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiAuthContext, HttpRouter, StoreOwnerInventoryApi, register_store_owner_inventory_routes  # noqa: E402
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.contexts.inventory.application import InventoryAuditRecord, StoreOwnerInventoryCommandHandler  # noqa: E402
from token_payments.contexts.inventory.domain import ProductInventory, Quantity  # noqa: E402
from token_payments.shared.domain import CommandId, ProcessedCommand, ProductId, StoreId, UserId  # noqa: E402

from _store_catalog_test_support import (  # noqa: E402
    ADMIN_ID,
    CUSTOMER_ID,
    OWNER_ID,
    OWNER_WALLET,
    PRODUCT_ID,
    STORE_ID,
    FakeStoreCatalogRepository,
    auth,
    catalog_router,
    decode,
    json_body,
    price_payload,
    FixedIdGenerator,
)


NOW = datetime(2026, 5, 20, 1, 30, tzinfo=UTC)
VARIANT_ID = "var_ledger_mug_default"


def test_admin_mutations_require_server_side_admin_claim_and_idempotency_key() -> None:
    repository = FakeStoreCatalogRepository()
    body = json_body({"walletAddress": str(OWNER_WALLET), "actorRole": "ADMIN"})

    no_session = catalog_router(repository, None).handle(
        "POST",
        "/admin/store-users",
        headers={"Content-Type": "application/json"},
        body=body,
        received_at=NOW,
    )
    customer = catalog_router(repository, auth(CUSTOMER_ID, UserRole.CUSTOMER)).handle(
        "POST",
        "/admin/store-users",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-body-role-is-ignored"},
        body=body,
        received_at=NOW,
    )
    admin_without_key = catalog_router(repository, auth(ADMIN_ID, UserRole.ADMIN)).handle(
        "POST",
        "/admin/store-users",
        headers={"Content-Type": "application/json"},
        body=body,
        received_at=NOW,
    )

    assert decode(no_session.body)["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert decode(customer.body)["error"]["code"] == "ADMIN_REQUIRED"
    assert decode(admin_without_key.body)["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_same_idempotency_key_does_not_duplicate_user_store_product_projection_or_audit() -> None:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    repository.seed_store(owner_id=OWNER_ID)
    router = catalog_router(repository, auth(OWNER_ID, UserRole.CUSTOMER), id_generator=FixedIdGenerator(str(PRODUCT_ID)))
    body = json_body(
        {
            "name": "Ledger Mug",
            "price": price_payload(),
            "initialTotalStock": 25,
            "active": True,
        }
    )

    first = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "projection-idem-001", "X-Request-Id": "req-projection-1"},
        body=body,
        received_at=NOW,
    )
    duplicate = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "projection-idem-001", "X-Request-Id": "req-projection-1"},
        body=body,
        received_at=NOW,
    )
    conflict = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "projection-idem-001", "X-Request-Id": "req-projection-conflict"},
        body=json_body(
            {
                "name": "Changed Mug",
                "price": price_payload(),
                "initialTotalStock": 25,
                "active": True,
            }
        ),
        received_at=NOW,
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert conflict.status_code == 409
    assert len(repository.products) == 1
    assert len(repository.order_products) == 1
    assert len(repository.store_approval_products) == 1
    assert len(repository.inventory) == 1
    assert len(repository.audit_records) == 1


def test_customer_role_store_member_can_mutate_inventory_and_audit_records_store_role() -> None:
    inventory_repository = FakeInventoryRepository(_inventory())
    audit_records: list[InventoryAuditRecord] = []
    handler = StoreOwnerInventoryCommandHandler(
        inventory_repository=inventory_repository,
        processed_commands=FakeProcessedCommandRepository(),
        audit_repository=FakeInventoryAuditRepository(audit_records),
    )
    router = HttpRouter(
        auth_context_factory=lambda _request: ApiAuthContext(
            user_id=str(OWNER_ID),
            role=UserRole.CUSTOMER.value,
            scopes=("inventory:write",),
            session_id="session-cookie",
        ),
        allow_dev_auth_headers=False,
    )
    register_store_owner_inventory_routes(
        router,
        StoreOwnerInventoryApi(
            query=MembershipInventoryQuery({(STORE_ID, OWNER_ID): "OWNER"}),
            command_handler=handler,
        ),
    )

    response = router.handle(
        "POST",
        _variant_inventory_path("intake"),
        headers={"Content-Type": "application/json", "Idempotency-Key": "customer-owner-stock-001", "X-Request-Id": "req-customer-owner-stock"},
        body=_json_body({"quantity": 3, "reason": "owner intake"}),
        received_at=NOW,
    )

    assert response.status_code == 202
    assert audit_records == [
        InventoryAuditRecord(
            actor_user_id=OWNER_ID,
            actor_role=UserRole.CUSTOMER,
            store_id=STORE_ID,
            product_id=PRODUCT_ID,
            action="increaseStock",
            before_available_stock=5,
            before_reserved_stock=0,
            before_total_stock=5,
            before_sale_status="ACTIVE",
            after_available_stock=8,
            after_reserved_stock=0,
            after_total_stock=8,
            after_sale_status="ACTIVE",
            reason="owner intake",
            request_id="req-customer-owner-stock",
            idempotency_key="customer-owner-stock-001",
            recorded_at=NOW,
            actor_store_role="OWNER",
            public_variant_id=VARIANT_ID,
        )
    ]


def test_projection_validation_happens_before_partial_writes_for_missing_or_invalid_store() -> None:
    repository = FakeStoreCatalogRepository()
    router = catalog_router(repository, auth(OWNER_ID, UserRole.CUSTOMER))

    response = router.handle(
        "POST",
        "/merchant/stores/st_missing_store/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "missing-store-product-001"},
        body=json_body(
            {
                "name": "Ledger Mug",
                "price": price_payload(),
                "initialTotalStock": 25,
                "active": True,
            }
        ),
        received_at=NOW,
    )

    assert response.status_code == 404
    assert repository.products == {}
    assert repository.order_products == {}
    assert repository.store_approval_products == {}
    assert repository.inventory == {}


def _inventory() -> ProductInventory:
    return ProductInventory(
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        available_stock=Quantity(5),
        reserved_stock=Quantity(0),
        total_stock=Quantity(5),
        public_variant_id=VARIANT_ID,
    )


def _variant_inventory_path(action: str) -> str:
    return f"/store-owner/stores/{STORE_ID}/inventory/{PRODUCT_ID}/variants/{VARIANT_ID}/{action}"


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


class MembershipInventoryQuery:
    def __init__(self, roles: dict[tuple[StoreId, UserId], str]) -> None:
        self.roles = roles

    def list_inventory(self, store_id: StoreId | None = None):
        return ()

    def list_inventory_for_owner(self, owner_user_id: UserId, store_id: StoreId | None = None):
        return ()

    def list_inventory_for_member(self, owner_user_id: UserId, store_id: StoreId | None = None):
        return ()

    def owner_for_store(self, store_id: StoreId) -> UserId | None:
        return OWNER_ID

    def store_role_for_user(self, store_id: StoreId, user_id: UserId) -> str | None:
        return self.roles.get((store_id, user_id))


class FakeInventoryRepository:
    def __init__(self, inventory: ProductInventory) -> None:
        self.inventory = inventory

    def get(self, product_id: ProductId, store_id: StoreId, public_variant_id: str | None = None) -> ProductInventory | None:
        return self.inventory if (product_id, store_id) == (PRODUCT_ID, STORE_ID) else None

    def save(self, inventory: ProductInventory) -> None:
        self.inventory = inventory


class FakeProcessedCommandRepository:
    def __init__(self) -> None:
        self.processed: set[tuple[str, str]] = set()

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return (handler, str(command_id)) in self.processed

    def record(self, processed_command: ProcessedCommand) -> None:
        self.processed.add(processed_command.idempotency_key)


class FakeInventoryAuditRepository:
    def __init__(self, records: list[InventoryAuditRecord]) -> None:
        self.records = records

    def record(self, audit_record: InventoryAuditRecord) -> str | None:
        self.records.append(audit_record)
        return f"audit-{len(self.records)}"

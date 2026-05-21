from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    STORE_OWNER_INVENTORY_HTTP_ROUTES,
    ApiAuthContext,
    HttpRouter,
    StoreOwnerInventoryApi,
    http_route_manifest,
    register_store_owner_inventory_routes,
)
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.contexts.inventory.application import InventorySnapshot  # noqa: E402
from token_payments.contexts.inventory.domain import InventorySaleStatus  # noqa: E402
from token_payments.shared.domain import ProductId, StoreId, UserId  # noqa: E402


NOW = datetime(2026, 5, 18, 1, 15, tzinfo=UTC)
OWNER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8101")
OTHER_OWNER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8102")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8103")
OTHER_STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8104")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8105")


def test_store_owner_inventory_route_manifest_exposes_query_endpoint() -> None:
    spec = STORE_OWNER_INVENTORY_HTTP_ROUTES["list_inventory"]

    assert spec.method == "GET"
    assert spec.path == "/store-owner/inventory"
    assert spec.operation_id == "listStoreOwnerInventory"
    assert {
        "method": "GET",
        "path": "/store-owner/inventory",
        "operationId": "listStoreOwnerInventory",
    } in http_route_manifest()


def test_store_owner_can_query_only_owned_store_inventory_from_cookie_auth_context() -> None:
    query = FakeInventoryQuery(
        snapshots=(
            _snapshot(store_id=STORE_ID, product_id=PRODUCT_ID),
            _snapshot(store_id=OTHER_STORE_ID, product_id=PRODUCT_ID),
        ),
        owners={STORE_ID: OWNER_ID, OTHER_STORE_ID: OTHER_OWNER_ID},
    )
    response = _router(query, _auth(OWNER_ID, UserRole.STORE_OWNER)).handle(
        "GET",
        "/store-owner/inventory",
        query={"storeId": str(STORE_ID)},
        headers={"X-Request-Id": "req-owner-inventory"},
        received_at=NOW,
    )

    payload = _json(response.body)

    assert response.status_code == 200
    assert query.owner_queries == [(OWNER_ID, STORE_ID)]
    assert payload["inventory"] == [
        {
            "storeId": str(STORE_ID),
            "productId": str(PRODUCT_ID),
            "availableStock": 8,
            "reservedStock": 2,
            "soldStock": 3,
            "confirmedStock": 3,
            "totalStock": 10,
            "saleStatus": "ACTIVE",
            "updatedAt": NOW.isoformat(),
        }
    ]


def test_admin_can_query_all_inventory_or_filter_by_store() -> None:
    query = FakeInventoryQuery(
        snapshots=(
            _snapshot(store_id=STORE_ID, product_id=PRODUCT_ID),
            _snapshot(store_id=OTHER_STORE_ID, product_id=PRODUCT_ID, sale_status=InventorySaleStatus.PAUSED),
        ),
        owners={STORE_ID: OWNER_ID, OTHER_STORE_ID: OTHER_OWNER_ID},
    )
    router = _router(query, _auth(UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8106"), UserRole.ADMIN))

    all_response = router.handle("GET", "/store-owner/inventory", headers={"X-Request-Id": "req-admin-all"})
    filtered_response = router.handle(
        "GET",
        "/store-owner/inventory",
        query={"storeId": str(OTHER_STORE_ID)},
        headers={"X-Request-Id": "req-admin-filter"},
    )

    assert all_response.status_code == 200
    assert len(_json(all_response.body)["inventory"]) == 2
    assert filtered_response.status_code == 200
    assert [item["storeId"] for item in _json(filtered_response.body)["inventory"]] == [str(OTHER_STORE_ID)]
    assert query.admin_queries == [None, OTHER_STORE_ID]


def test_customer_and_unauthenticated_requests_are_denied() -> None:
    query = FakeInventoryQuery(snapshots=(_snapshot(store_id=STORE_ID, product_id=PRODUCT_ID),), owners={STORE_ID: OWNER_ID})

    customer = _router(query, _auth(OWNER_ID, UserRole.CUSTOMER)).handle("GET", "/store-owner/inventory")
    unauthenticated = _router(query, None).handle("GET", "/store-owner/inventory")

    assert customer.status_code == 403
    assert _json(customer.body)["error"]["code"] == "STORE_OWNER_INVENTORY_FORBIDDEN"
    assert unauthenticated.status_code == 401
    assert _json(unauthenticated.body)["error"]["code"] == "AUTHENTICATION_REQUIRED"


def _router(query: "FakeInventoryQuery", auth_context: ApiAuthContext | None) -> HttpRouter:
    router = HttpRouter(auth_context_factory=lambda _request: auth_context, allow_dev_auth_headers=False)
    register_store_owner_inventory_routes(router, StoreOwnerInventoryApi(query=query, command_handler=None))
    return router


def _auth(user_id: UserId, role: UserRole) -> ApiAuthContext:
    scopes = {
        UserRole.STORE_OWNER: ("inventory:read",),
        UserRole.ADMIN: ("inventory:read:any",),
    }.get(role, ())
    return ApiAuthContext(user_id=str(user_id), role=role.value, scopes=scopes, session_id="session-cookie")


def _snapshot(
    *,
    store_id: StoreId,
    product_id: ProductId,
    sale_status: InventorySaleStatus = InventorySaleStatus.ACTIVE,
) -> InventorySnapshot:
    return InventorySnapshot(
        store_id=store_id,
        product_id=product_id,
        available_stock=8,
        reserved_stock=2,
        confirmed_stock=3,
        total_stock=10,
        sale_status=sale_status,
        updated_at=NOW,
    )


def _json(body: bytes) -> dict[str, object]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


class FakeInventoryQuery:
    def __init__(self, *, snapshots: tuple[InventorySnapshot, ...], owners: dict[StoreId, UserId]) -> None:
        self.snapshots = snapshots
        self.owners = owners
        self.owner_queries: list[tuple[UserId, StoreId | None]] = []
        self.admin_queries: list[StoreId | None] = []

    def list_inventory(self, store_id: StoreId | None = None) -> tuple[InventorySnapshot, ...]:
        self.admin_queries.append(store_id)
        return tuple(snapshot for snapshot in self.snapshots if store_id is None or snapshot.store_id == store_id)

    def list_inventory_for_owner(
        self,
        owner_user_id: UserId,
        store_id: StoreId | None = None,
    ) -> tuple[InventorySnapshot, ...]:
        self.owner_queries.append((owner_user_id, store_id))
        return tuple(
            snapshot
            for snapshot in self.snapshots
            if self.owners.get(snapshot.store_id) == owner_user_id
            and (store_id is None or snapshot.store_id == store_id)
        )

    def owner_for_store(self, store_id: StoreId) -> UserId | None:
        return self.owners.get(store_id)

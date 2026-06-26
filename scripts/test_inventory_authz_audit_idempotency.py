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
from token_payments.contexts.inventory.application import (  # noqa: E402
    InventoryAuditRecord,
    StoreOwnerInventoryCommandHandler,
)
from token_payments.contexts.inventory.domain import ProductInventory, Quantity  # noqa: E402
from token_payments.shared.domain import CommandId, ProcessedCommand, ProductId, StoreId, UserId  # noqa: E402


NOW = datetime(2026, 5, 18, 1, 45, tzinfo=UTC)
OWNER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8301")
ADMIN_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8302")
CUSTOMER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8303")
OTHER_OWNER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8304")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8305")
OTHER_STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8306")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8307")
VARIANT_ID = "var_ledger_hoodie_l"


def test_store_owner_can_mutate_only_owned_store_and_denied_attempt_has_no_audit() -> None:
    fixture = ApiFixture(_auth(OWNER_ID, UserRole.STORE_OWNER))

    own = fixture.post_intake(STORE_ID, "stock-intake-own-001")
    other = fixture.post_intake(OTHER_STORE_ID, "stock-intake-other-001")

    assert own.status_code == 202
    assert other.status_code == 403
    assert _json(other.body)["error"]["code"] == "STORE_OWNER_STORE_FORBIDDEN"
    assert [record.store_id for record in fixture.audit_records] == [STORE_ID]


def test_admin_can_mutate_any_store_and_audit_preserves_actor_role() -> None:
    fixture = ApiFixture(_auth(ADMIN_ID, UserRole.ADMIN))

    response = fixture.post_intake(OTHER_STORE_ID, "stock-intake-admin-001")

    assert response.status_code == 202
    assert fixture.audit_records[-1].actor_user_id == ADMIN_ID
    assert fixture.audit_records[-1].actor_role == UserRole.ADMIN
    assert fixture.audit_records[-1].store_id == OTHER_STORE_ID


def test_customer_mutation_is_forbidden_before_handler_or_audit() -> None:
    fixture = ApiFixture(_auth(CUSTOMER_ID, UserRole.CUSTOMER))

    response = fixture.post_intake(STORE_ID, "stock-intake-customer-001")

    assert response.status_code == 403
    assert _json(response.body)["error"]["code"] == "STORE_OWNER_INVENTORY_FORBIDDEN"
    assert fixture.audit_records == []
    assert fixture.inventory_repository.saved == []


def test_inventory_mutation_audit_records_before_after_reason_request_and_idempotency_key() -> None:
    fixture = ApiFixture(_auth(OWNER_ID, UserRole.STORE_OWNER))

    response = fixture.post_intake(STORE_ID, "stock-intake-audit-001")

    assert response.status_code == 202
    assert fixture.audit_records == [
        InventoryAuditRecord(
            actor_user_id=OWNER_ID,
            actor_role=UserRole.STORE_OWNER,
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
            reason="warehouse intake",
            request_id="req-stock-intake-audit-001",
            idempotency_key="stock-intake-audit-001",
            recorded_at=NOW,
            actor_store_role="OWNER",
            public_variant_id=VARIANT_ID,
        )
    ]


def test_duplicate_idempotency_key_returns_duplicate_without_extra_audit_or_outbox() -> None:
    fixture = ApiFixture(_auth(OWNER_ID, UserRole.STORE_OWNER))

    first = fixture.post_intake(STORE_ID, "stock-intake-duplicate-001")
    duplicate = fixture.post_intake(STORE_ID, "stock-intake-duplicate-001")

    assert first.status_code == 202
    assert duplicate.status_code == 202
    assert _json(first.body)["status"] == "accepted"
    assert _json(duplicate.body)["status"] == "duplicate"
    assert len(fixture.audit_records) == 1
    assert len(fixture.inventory_repository.saved) == 1


class ApiFixture:
    def __init__(self, auth_context: ApiAuthContext) -> None:
        self.inventory_repository = FakeInventoryRepository(
            (
                _inventory(STORE_ID, available=5),
                _inventory(OTHER_STORE_ID, available=7),
            )
        )
        self.processed_commands = FakeProcessedCommandRepository()
        self.audit_records: list[InventoryAuditRecord] = []
        self.handler = StoreOwnerInventoryCommandHandler(
            inventory_repository=self.inventory_repository,
            processed_commands=self.processed_commands,
            audit_repository=FakeInventoryAuditRepository(self.audit_records),
        )
        query = FakeInventoryQuery(owners={STORE_ID: OWNER_ID, OTHER_STORE_ID: OTHER_OWNER_ID})
        self.router = HttpRouter(
            auth_context_factory=lambda _request: auth_context,
            allow_dev_auth_headers=False,
        )
        register_store_owner_inventory_routes(
            self.router,
            StoreOwnerInventoryApi(query=query, command_handler=self.handler),
        )

    def post_intake(self, store_id: StoreId, idempotency_key: str):
        return self.router.handle(
            "POST",
            f"/store-owner/stores/{store_id}/inventory/{PRODUCT_ID}/variants/{VARIANT_ID}/intake",
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
                "X-Request-Id": f"req-{idempotency_key}",
            },
            body=_json_body({"quantity": 3, "reason": "warehouse intake"}),
            received_at=NOW,
        )


def _auth(user_id: UserId, role: UserRole) -> ApiAuthContext:
    scopes = {
        UserRole.ADMIN: ("inventory:read:any", "inventory:write:any"),
        UserRole.STORE_OWNER: ("inventory:read", "inventory:write"),
        UserRole.CUSTOMER: (),
    }[role]
    return ApiAuthContext(user_id=str(user_id), role=role.value, session_id="session-cookie", scopes=scopes)


def _inventory(store_id: StoreId, *, available: int) -> ProductInventory:
    return ProductInventory(
        product_id=PRODUCT_ID,
        store_id=store_id,
        available_stock=Quantity(available),
        reserved_stock=Quantity(0),
        total_stock=Quantity(available),
        public_variant_id=VARIANT_ID,
    )


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json(body: bytes) -> dict[str, Any]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


class FakeInventoryRepository:
    def __init__(self, inventories: tuple[ProductInventory, ...]) -> None:
        self.inventories = {(inventory.product_id, inventory.store_id): inventory for inventory in inventories}
        self.saved: list[ProductInventory] = []

    def get(self, product_id: ProductId, store_id: StoreId, public_variant_id: str | None = None) -> ProductInventory | None:
        return self.inventories.get((product_id, store_id))

    def save(self, inventory: ProductInventory) -> None:
        self.saved.append(inventory)
        self.inventories[(inventory.product_id, inventory.store_id)] = inventory


class FakeProcessedCommandRepository:
    def __init__(self) -> None:
        self.existing: set[tuple[str, str]] = set()
        self.records: list[ProcessedCommand] = []

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return (handler, str(command_id)) in self.existing

    def record(self, processed_command: ProcessedCommand) -> None:
        self.records.append(processed_command)
        self.existing.add(processed_command.idempotency_key)


class FakeInventoryAuditRepository:
    def __init__(self, records: list[InventoryAuditRecord]) -> None:
        self.records = records

    def record(self, audit_record: InventoryAuditRecord) -> str | None:
        self.records.append(audit_record)
        return f"audit-{len(self.records)}"


class FakeInventoryQuery:
    def __init__(self, *, owners: dict[StoreId, UserId]) -> None:
        self.owners = owners

    def list_inventory(self, store_id: StoreId | None = None):
        return ()

    def list_inventory_for_owner(self, owner_user_id: UserId, store_id: StoreId | None = None):
        return ()

    def owner_for_store(self, store_id: StoreId) -> UserId | None:
        return self.owners.get(store_id)

    def store_role_for_user(self, store_id: StoreId, user_id: UserId) -> str | None:
        return "OWNER" if self.owners.get(store_id) == user_id else None

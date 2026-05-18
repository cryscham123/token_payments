from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.contexts.inventory.application import (  # noqa: E402
    InventoryAuditRecord,
    PauseProductSalesCommand,
    ResumeProductSalesCommand,
    StoreOwnerCorrectStockCommand,
    StoreOwnerIncreaseStockCommand,
    StoreOwnerInventoryCommandHandler,
    StoreOwnerInventoryCommandStatus,
)
from token_payments.contexts.inventory.domain import (  # noqa: E402
    InventorySaleStatus,
    ProductInventory,
    Quantity,
)
from token_payments.shared.domain import (  # noqa: E402
    CommandId,
    IdempotencyDecision,
    ProductId,
    OrderId,
    StoreId,
    UserId,
)


NOW = datetime(2026, 5, 18, 1, 0, tzinfo=UTC)
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8001")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8002")
ACTOR_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8003")
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc8004")


def test_stock_intake_command_increases_total_and_available_stock_with_audit() -> None:
    fixture = HandlerFixture(_inventory(available=5))

    result = fixture.handler.increase_stock(_increase_command(quantity=7))

    assert result.status == StoreOwnerInventoryCommandStatus.ACCEPTED
    assert result.inventory is not None
    assert result.inventory.available_stock == Quantity(12)
    assert result.inventory.total_stock == Quantity(12)
    assert fixture.inventory_repository.saved == [result.inventory]
    assert fixture.audit_records == [
        InventoryAuditRecord(
            actor_user_id=ACTOR_ID,
            actor_role=UserRole.STORE_OWNER,
            store_id=STORE_ID,
            product_id=PRODUCT_ID,
            action="increaseStock",
            before_available_stock=5,
            before_reserved_stock=0,
            before_total_stock=5,
            before_sale_status=InventorySaleStatus.ACTIVE,
            after_available_stock=12,
            after_reserved_stock=0,
            after_total_stock=12,
            after_sale_status=InventorySaleStatus.ACTIVE,
            reason="warehouse intake",
            request_id="req-stock-increase",
            idempotency_key="stock-intake-001",
            recorded_at=NOW,
        )
    ]


def test_stock_correction_rejects_target_total_below_reserved_stock_without_side_effects() -> None:
    reserved = _inventory(available=7).reserve_inventory(ORDER_ID, Quantity(4))
    fixture = HandlerFixture(reserved)

    result = fixture.handler.correct_stock(_correct_command(target_total_stock=2))

    assert result.status == StoreOwnerInventoryCommandStatus.REJECTED
    assert result.rejection_reason == "STOCK_BELOW_RESERVED"
    assert result.inventory is None
    assert fixture.inventory_repository.saved == []
    assert fixture.audit_records == []
    assert fixture.processed_commands.records == []


def test_sale_pause_and_resume_change_new_order_availability_without_releasing_reservations() -> None:
    inventory = _inventory(available=8).reserve_inventory(ORDER_ID, Quantity(2))
    fixture = HandlerFixture(inventory)

    paused = fixture.handler.pause_sales(_pause_command())
    resumed = fixture.handler.resume_sales(_resume_command())

    assert paused.inventory is not None
    assert paused.inventory.sale_status == InventorySaleStatus.PAUSED
    assert paused.inventory.available_for_new_orders is False
    assert paused.inventory.reserved_stock == Quantity(2)
    assert resumed.inventory is not None
    assert resumed.inventory.sale_status == InventorySaleStatus.ACTIVE
    assert resumed.inventory.available_for_new_orders is True
    assert resumed.inventory.reserved_stock == Quantity(2)


def test_store_owner_mutation_commands_require_common_audit_fields() -> None:
    required = {"command_id", "store_id", "product_id", "actor_user_id", "reason", "requested_at"}

    for command_type in (
        StoreOwnerIncreaseStockCommand,
        StoreOwnerCorrectStockCommand,
        PauseProductSalesCommand,
        ResumeProductSalesCommand,
    ):
        assert required <= set(command_type.__dataclass_fields__)

    with pytest.raises(ValueError, match="reason"):
        _increase_command(quantity=1, reason=" ")


def test_command_result_distinguishes_accepted_rejected_and_duplicate_statuses() -> None:
    accepted = HandlerFixture(_inventory(available=5)).handler.increase_stock(_increase_command(quantity=1))
    rejected = HandlerFixture(None).handler.increase_stock(_increase_command(quantity=1))
    duplicate_fixture = HandlerFixture(
        _inventory(available=5),
        processed={(StoreOwnerInventoryCommandHandler.HANDLER_NAME, "stock-intake-001")},
    )
    duplicate = duplicate_fixture.handler.increase_stock(_increase_command(quantity=1))

    assert accepted.status == StoreOwnerInventoryCommandStatus.ACCEPTED
    assert rejected.status == StoreOwnerInventoryCommandStatus.REJECTED
    assert rejected.rejection_reason == "INVENTORY_NOT_FOUND"
    assert duplicate.status == StoreOwnerInventoryCommandStatus.DUPLICATE
    assert duplicate.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert duplicate_fixture.inventory_repository.saved == []
    assert duplicate_fixture.audit_records == []


def _increase_command(*, quantity: int, reason: str = "warehouse intake") -> StoreOwnerIncreaseStockCommand:
    return StoreOwnerIncreaseStockCommand(
        command_id=CommandId("stock-intake-001"),
        store_id=STORE_ID,
        product_id=PRODUCT_ID,
        actor_user_id=ACTOR_ID,
        actor_role=UserRole.STORE_OWNER,
        quantity=Quantity(quantity),
        reason=reason,
        requested_at=NOW,
        request_id="req-stock-increase",
    )


def _correct_command(*, target_total_stock: int) -> StoreOwnerCorrectStockCommand:
    return StoreOwnerCorrectStockCommand(
        command_id=CommandId("stock-correction-001"),
        store_id=STORE_ID,
        product_id=PRODUCT_ID,
        actor_user_id=ACTOR_ID,
        actor_role=UserRole.STORE_OWNER,
        target_total_stock=target_total_stock,
        reason="cycle count",
        requested_at=NOW,
        request_id="req-stock-correction",
    )


def _pause_command() -> PauseProductSalesCommand:
    return PauseProductSalesCommand(
        command_id=CommandId("sale-pause-001"),
        store_id=STORE_ID,
        product_id=PRODUCT_ID,
        actor_user_id=ACTOR_ID,
        actor_role=UserRole.STORE_OWNER,
        reason="supplier hold",
        requested_at=NOW,
        request_id="req-sale-pause",
    )


def _resume_command() -> ResumeProductSalesCommand:
    return ResumeProductSalesCommand(
        command_id=CommandId("sale-resume-001"),
        store_id=STORE_ID,
        product_id=PRODUCT_ID,
        actor_user_id=ACTOR_ID,
        actor_role=UserRole.STORE_OWNER,
        reason="supplier released hold",
        requested_at=NOW,
        request_id="req-sale-resume",
    )


def _inventory(*, available: int) -> ProductInventory:
    return ProductInventory(
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        available_stock=Quantity(available),
        reserved_stock=Quantity(0),
        total_stock=Quantity(available),
    )


class HandlerFixture:
    def __init__(
        self,
        inventory: ProductInventory | None,
        *,
        processed: set[tuple[str, str]] | None = None,
    ) -> None:
        self.inventory_repository = FakeInventoryRepository(inventory)
        self.processed_commands = FakeProcessedCommandRepository(processed)
        self.audit_records: list[InventoryAuditRecord] = []
        self.handler = StoreOwnerInventoryCommandHandler(
            inventory_repository=self.inventory_repository,
            processed_commands=self.processed_commands,
            audit_repository=FakeInventoryAuditRepository(self.audit_records),
        )


class FakeInventoryRepository:
    def __init__(self, inventory: ProductInventory | None) -> None:
        self.inventories: dict[tuple[ProductId, StoreId], ProductInventory] = {}
        if inventory is not None:
            self.inventories[(inventory.product_id, inventory.store_id)] = inventory
        self.saved: list[ProductInventory] = []

    def get(self, product_id: ProductId, store_id: StoreId) -> ProductInventory | None:
        return self.inventories.get((product_id, store_id))

    def save(self, inventory: ProductInventory) -> None:
        self.saved.append(inventory)
        self.inventories[(inventory.product_id, inventory.store_id)] = inventory


class FakeProcessedCommandRepository:
    def __init__(self, existing: set[tuple[str, str]] | None = None) -> None:
        self.existing = existing or set()
        self.records = []

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return (handler, str(command_id)) in self.existing

    def record(self, processed_command) -> None:
        self.records.append(processed_command)
        self.existing.add(processed_command.idempotency_key)


class FakeInventoryAuditRepository:
    def __init__(self, records: list[InventoryAuditRecord]) -> None:
        self.records = records

    def record(self, audit_record: InventoryAuditRecord) -> str | None:
        self.records.append(audit_record)
        return f"audit-{len(self.records)}"

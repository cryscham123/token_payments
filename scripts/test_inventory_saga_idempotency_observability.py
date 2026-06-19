from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.inventory.adapter import PostgresInventoryRepository  # noqa: E402
from token_payments.contexts.inventory.application import (  # noqa: E402
    ConfirmInventoryCommand,
    InventoryCommandHandler,
    InventoryCommandRejected,
    InventoryCommandStatus,
    ReleaseInventoryCommand,
    ReserveInventoryCommand,
)
from token_payments.contexts.inventory.domain import (  # noqa: E402
    ProductInventory,
    Quantity,
    ReservationStatus,
)
from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CommandId,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxMessage,
    ProcessedCommand,
    ProductId,
    StoreId,
    default_public_variant_id,
)


NOW = datetime(2026, 5, 18, 2, 30, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c51")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c52")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c53")


def test_reserve_then_confirm_keeps_stock_counters_consistent_and_observable() -> None:
    fixture = HandlerFixture(_inventory(available=10))

    reserved = fixture.handler.reserve_inventory(_reserve_command(quantity=4))
    confirmed = fixture.handler.confirm_inventory(_confirm_command())

    assert reserved.inventory is not None
    assert reserved.inventory.available_stock == Quantity(6)
    assert reserved.inventory.reserved_stock == Quantity(4)
    assert reserved.inventory.total_stock == Quantity(10)
    assert confirmed.inventory is not None
    assert confirmed.inventory.available_stock == Quantity(6)
    assert confirmed.inventory.reserved_stock == Quantity(0)
    assert confirmed.inventory.total_stock == Quantity(6)
    assert confirmed.inventory.reservations[0].status == ReservationStatus.CONFIRMED

    confirm_payload = fixture.outbox_messages.saved[-1].payload
    assert confirm_payload["eventName"] == "InventoryConfirmedEvent"
    assert confirm_payload["reservationStatus"] == ReservationStatus.CONFIRMED.value
    assert confirm_payload["availableStock"] == 6
    assert confirm_payload["reservedStock"] == 0
    assert confirm_payload["totalStock"] == 6


def test_reserve_then_release_blocks_later_confirm() -> None:
    fixture = HandlerFixture(_inventory(available=10))

    fixture.handler.reserve_inventory(_reserve_command(quantity=2))
    released = fixture.handler.release_inventory(_release_command())

    assert released.inventory is not None
    assert released.inventory.available_stock == Quantity(10)
    assert released.inventory.reserved_stock == Quantity(0)
    assert released.inventory.total_stock == Quantity(10)
    assert released.inventory.reservations[0].status == ReservationStatus.CANCELLED

    with pytest.raises(InventoryCommandRejected):
        fixture.handler.confirm_inventory(_confirm_command(command_suffix="confirm-after-release"))


def test_duplicate_confirm_command_does_not_mutate_inventory_or_create_outbox() -> None:
    fixture = HandlerFixture(_inventory(available=10))

    fixture.handler.reserve_inventory(_reserve_command(quantity=1))
    first = fixture.handler.confirm_inventory(_confirm_command())
    before_outbox = len(fixture.outbox_messages.saved)
    duplicate = fixture.handler.confirm_inventory(_confirm_command())

    assert first.status == InventoryCommandStatus.CONFIRMED
    assert duplicate.status == InventoryCommandStatus.DUPLICATE_IGNORED
    assert duplicate.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert len(fixture.outbox_messages.saved) == before_outbox
    assert duplicate.inventory is None
    assert duplicate.outbox_message is None


def test_repository_roundtrip_preserves_confirmed_and_cancelled_reservation_statuses() -> None:
    connection = FakePostgresConnection()
    repository = PostgresInventoryRepository(connection)
    base = replace(_inventory(available=10), public_variant_id=default_public_variant_id(PRODUCT_ID))
    confirmed = base.reserve_inventory(ORDER_ID, Quantity(3)).confirm_reservation(ORDER_ID)
    released = confirmed.reserve_inventory(_other_order_id(), Quantity(2)).release_reservation(_other_order_id())

    repository.save(released)
    loaded = repository.get(PRODUCT_ID, STORE_ID)

    assert loaded == released
    assert loaded is not None
    assert loaded.available_stock == Quantity(7)
    assert loaded.reserved_stock == Quantity(0)
    assert loaded.total_stock == Quantity(7)
    assert [reservation.status for reservation in loaded.reservations] == [
        ReservationStatus.CONFIRMED,
        ReservationStatus.CANCELLED,
    ]


def test_release_and_confirm_outbox_payloads_distinguish_reservation_states() -> None:
    fixture = HandlerFixture(_inventory(available=10))

    fixture.handler.reserve_inventory(_reserve_command(quantity=2))
    fixture.handler.release_inventory(_release_command())
    release_payload = fixture.outbox_messages.saved[-1].payload

    assert release_payload["eventName"] == "InventoryReleasedEvent"
    assert release_payload["reservationStatus"] == ReservationStatus.CANCELLED.value
    assert release_payload["availableStock"] == 10
    assert release_payload["reservedStock"] == 0
    assert release_payload["totalStock"] == 10
    assert release_payload["correlationId"] == str(ORDER_ID)
    assert release_payload["causationId"] == str(_command_id(CheckoutCommandName.RELEASE_INVENTORY))


def _reserve_command(quantity: int) -> ReserveInventoryCommand:
    return ReserveInventoryCommand(
        command_id=_command_id(CheckoutCommandName.RESERVE_INVENTORY),
        order_id=ORDER_ID,
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        quantity=Quantity(quantity),
        requested_at=NOW,
        event_message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c61"),
    )


def _release_command() -> ReleaseInventoryCommand:
    return ReleaseInventoryCommand(
        command_id=_command_id(CheckoutCommandName.RELEASE_INVENTORY),
        order_id=ORDER_ID,
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        requested_at=NOW,
        event_message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c62"),
    )


def _confirm_command(command_suffix: str | None = None) -> ConfirmInventoryCommand:
    command_id = (
        CommandId(f"{ORDER_ID}:{command_suffix}")
        if command_suffix is not None
        else _command_id(CheckoutCommandName.CONFIRM_INVENTORY)
    )
    return ConfirmInventoryCommand(
        command_id=command_id,
        order_id=ORDER_ID,
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        requested_at=NOW,
        event_message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c63"),
    )


def _command_id(name: CheckoutCommandName) -> CommandId:
    return CommandId.for_order_action(ORDER_ID, name)


def _other_order_id() -> OrderId:
    return OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c54")


def _inventory(available: int) -> ProductInventory:
    return ProductInventory(
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        available_stock=Quantity(available),
        reserved_stock=Quantity(0),
        total_stock=Quantity(available),
    )


class HandlerFixture:
    def __init__(self, inventory: ProductInventory) -> None:
        self.inventory_repository = FakeInventoryRepository(inventory)
        self.processed_commands = FakeProcessedCommandRepository()
        self.outbox_messages = FakeOutboxMessageRepository()
        self.handler = InventoryCommandHandler(
            self.inventory_repository,
            self.processed_commands,
            self.outbox_messages,
        )


class FakeInventoryRepository:
    def __init__(self, inventory: ProductInventory | None) -> None:
        self.inventories: dict[tuple[ProductId, StoreId, str | None], ProductInventory] = {}
        if inventory is not None:
            self.inventories[(inventory.product_id, inventory.store_id, inventory.public_variant_id)] = inventory

    def get(self, product_id: ProductId, store_id: StoreId, public_variant_id: str | None = None) -> ProductInventory | None:
        return self.inventories.get((product_id, store_id, public_variant_id))

    def save(self, inventory: ProductInventory) -> None:
        self.inventories[(inventory.product_id, inventory.store_id, inventory.public_variant_id)] = inventory


class FakeProcessedCommandRepository:
    def __init__(self) -> None:
        self.existing: set[tuple[str, str]] = set()
        self.records: list[ProcessedCommand] = []

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return (handler, str(command_id)) in self.existing

    def record(self, processed_command: ProcessedCommand) -> IdempotencyDecision:
        self.records.append(processed_command)
        self.existing.add(processed_command.idempotency_key)
        return IdempotencyDecision.PROCESS


class FakeOutboxMessageRepository:
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)


@dataclass(frozen=True)
class ExecutedStatement:
    sql: str
    params: Mapping[str, Any]


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class FakePostgresConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []
        self.product_variant_inventory: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.inventory_reservations: dict[str, dict[str, Any]] = {}

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> FakeResult:
        params = dict(params or {})
        self.statements.append(ExecutedStatement(sql=sql, params=params))
        normalized = " ".join(sql.lower().split())
        if "insert into product_variant_inventory" in normalized:
            self.product_variant_inventory[
                (str(params["product_id"]), str(params["store_id"]), str(params["public_variant_id"]))
            ] = params
            return FakeResult()
        if "insert into inventory_reservations" in normalized:
            self.inventory_reservations[str(params["reservation_id"])] = params
            return FakeResult()
        if "delete from inventory_reservations" in normalized:
            return FakeResult()
        if "from product_variant_inventory" in normalized and "select" in normalized:
            row = self.product_variant_inventory.get(
                (str(params["product_id"]), str(params["store_id"]), str(params["public_variant_id"]))
            )
            return FakeResult([dict(row)] if row is not None else [])
        if "from inventory_reservations" in normalized and "select" in normalized:
            requested_variant = params.get("public_variant_id")
            rows = [
                dict(row)
                for row in self.inventory_reservations.values()
                if row["product_id"] == str(params["product_id"])
                and row["store_id"] == str(params["store_id"])
                and row.get("public_variant_id") == requested_variant
            ]
            rows.sort(key=lambda row: (row["created_at"], row["reservation_id"]))
            return FakeResult(rows)
        raise AssertionError(f"unexpected SQL: {sql}")

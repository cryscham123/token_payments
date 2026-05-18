from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.inventory.application import (  # noqa: E402
    ConfirmInventoryCommand,
    InventoryCommandHandler,
    InventoryCommandRejected,
    InventoryCommandStatus,
)
from token_payments.contexts.inventory.domain import ProductInventory, Quantity, ReservationStatus  # noqa: E402
from token_payments.shared.adapter import MessageTopicResolver  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    ProcessedCommand,
    ProductId,
    StoreId,
)


NOW = datetime(2026, 5, 18, 1, 0, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
COMMAND_ID = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.CONFIRM_INVENTORY)
EVENT_MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")


def test_confirm_inventory_command_validates_required_contract_fields() -> None:
    command = _confirm_command()

    assert command.command_id == COMMAND_ID
    assert command.order_id == ORDER_ID
    assert command.product_id == PRODUCT_ID
    assert command.store_id == STORE_ID
    assert command.requested_at == NOW
    assert command.causation_id == "order-approved-message"
    assert command.event_message_id == EVENT_MESSAGE_ID


@pytest.mark.parametrize(
    ("field_name", "override", "message"),
    [
        ("command_id", "not-a-command-id", "ConfirmInventoryCommand.command_id must be a CommandId"),
        ("order_id", "not-an-order-id", "ConfirmInventoryCommand.order_id must be an OrderId"),
        ("product_id", "not-a-product-id", "ConfirmInventoryCommand.product_id must be a ProductId"),
        ("store_id", "not-a-store-id", "ConfirmInventoryCommand.store_id must be a StoreId"),
        (
            "requested_at",
            datetime(2026, 5, 18, 1, 0),
            "ConfirmInventoryCommand.requested_at must be timezone-aware",
        ),
        ("causation_id", "   ", "ConfirmInventoryCommand.causation_id must be a non-empty string"),
        ("event_message_id", "not-a-message-id", "ConfirmInventoryCommand.event_message_id must be a MessageId"),
    ],
)
def test_confirm_inventory_command_rejects_invalid_fields(
    field_name: str,
    override: object,
    message: str,
) -> None:
    values: dict[str, object] = {
        "command_id": COMMAND_ID,
        "order_id": ORDER_ID,
        "product_id": PRODUCT_ID,
        "store_id": STORE_ID,
        "requested_at": NOW,
        "causation_id": "order-approved-message",
        "event_message_id": EVENT_MESSAGE_ID,
    }
    values[field_name] = override

    with pytest.raises(ValueError, match=message):
        ConfirmInventoryCommand(**values)  # type: ignore[arg-type]


def test_confirm_reservation_consumes_reserved_stock_marks_confirmed_and_is_idempotent() -> None:
    reserved = _reserved_inventory(quantity=3)

    confirmed = reserved.confirm_reservation(ORDER_ID)
    confirmed_again = confirmed.confirm_reservation(ORDER_ID)

    assert confirmed.available_stock == Quantity(7)
    assert confirmed.reserved_stock == Quantity(0)
    assert confirmed.total_stock == Quantity(7)
    assert confirmed.reservations[0].status == ReservationStatus.CONFIRMED
    assert confirmed_again == confirmed


def test_cancelled_reservation_cannot_be_confirmed() -> None:
    cancelled = _reserved_inventory(quantity=3).release_reservation(ORDER_ID)

    with pytest.raises(ValueError, match="cancelled inventory reservations cannot be confirmed"):
        cancelled.confirm_reservation(ORDER_ID)


def test_confirm_inventory_handler_records_inventory_confirmed_event_contract() -> None:
    inventory_repository = FakeInventoryRepository(_reserved_inventory(quantity=3))
    processed_commands = FakeProcessedCommandRepository()
    outbox_messages = FakeOutboxMessageRepository()
    handler = InventoryCommandHandler(inventory_repository, processed_commands, outbox_messages)

    result = handler.confirm_inventory(_confirm_command())

    assert result.status == InventoryCommandStatus.CONFIRMED
    assert result.inventory is not None
    assert result.inventory.available_stock == Quantity(7)
    assert result.inventory.reserved_stock == Quantity(0)
    assert result.inventory.total_stock == Quantity(7)
    assert inventory_repository.saved == [result.inventory]

    outbox = outbox_messages.saved[0]
    assert outbox.kind == OutboxMessageKind.EVENT
    assert outbox.name == CheckoutEventName.INVENTORY_CONFIRMED.value
    assert outbox.topic == "inventory.events"
    assert outbox.key == str(ORDER_ID)
    assert outbox.identity == str(EVENT_MESSAGE_ID)
    assert outbox.headers["correlationId"] == str(ORDER_ID)
    assert outbox.headers["causationId"] == str(COMMAND_ID)
    assert outbox.headers["sourceCausationId"] == "order-approved-message"
    assert outbox.payload == {
        "eventName": CheckoutEventName.INVENTORY_CONFIRMED.value,
        "orderId": str(ORDER_ID),
        "productId": str(PRODUCT_ID),
        "storeId": str(STORE_ID),
        "availableStock": 7,
        "reservedStock": 0,
        "totalStock": 7,
        "occurredAt": NOW.isoformat(),
        "correlationId": str(ORDER_ID),
        "causationId": str(COMMAND_ID),
        "reservationId": outbox.payload["reservationId"],
        "reservedQuantity": 3,
        "reservationStatus": ReservationStatus.CONFIRMED.value,
    }
    assert processed_commands.records == [
        ProcessedCommand.record(
            command_id=COMMAND_ID,
            handler=InventoryCommandHandler.HANDLER_NAME,
            processed_at=NOW,
            order_id=ORDER_ID,
        )
    ]


def test_confirm_inventory_rejects_missing_reservation_without_side_effects() -> None:
    inventory_repository = FakeInventoryRepository(_inventory(available=10))
    processed_commands = FakeProcessedCommandRepository()
    outbox_messages = FakeOutboxMessageRepository()
    handler = InventoryCommandHandler(inventory_repository, processed_commands, outbox_messages)

    with pytest.raises(InventoryCommandRejected):
        handler.confirm_inventory(_confirm_command())

    assert inventory_repository.saved == []
    assert outbox_messages.saved == []
    assert processed_commands.records == []


def test_shared_topic_resolver_maps_inventory_confirm_command_and_event() -> None:
    resolver = MessageTopicResolver.default()

    assert resolver.topic_for(CheckoutCommandName.CONFIRM_INVENTORY) == "inventory.commands"
    assert resolver.topic_for(CheckoutEventName.INVENTORY_CONFIRMED) == "inventory.events"


def _confirm_command() -> ConfirmInventoryCommand:
    return ConfirmInventoryCommand(
        command_id=COMMAND_ID,
        order_id=ORDER_ID,
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        requested_at=NOW,
        causation_id="order-approved-message",
        event_message_id=EVENT_MESSAGE_ID,
    )


def _inventory(available: int) -> ProductInventory:
    return ProductInventory(
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        available_stock=Quantity(available),
        reserved_stock=Quantity(0),
        total_stock=Quantity(available),
    )


def _reserved_inventory(quantity: int) -> ProductInventory:
    return _inventory(available=10).reserve_inventory(ORDER_ID, Quantity(quantity))


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
        self.records: list[ProcessedCommand] = []

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return (handler, str(command_id)) in self.existing

    def record(self, processed_command: ProcessedCommand) -> None:
        self.records.append(processed_command)
        self.existing.add(processed_command.idempotency_key)


class FakeOutboxMessageRepository:
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)

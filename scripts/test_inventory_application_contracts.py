from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import get_type_hints

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.inventory.application import (  # noqa: E402
    ConfirmInventoryCommand,
    InventoryCommandHandler,
    InventoryCommandRejected,
    InventoryCommandRejectionReason,
    InventoryCommandStatus,
    InventoryRepository,
    OutboxMessageRepository,
    ProcessedCommandRepository,
    ReleaseInventoryCommand,
    ReserveInventoryCommand,
)
from token_payments.contexts.inventory.domain import ProductInventory, Quantity  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    ProcessedCommand,
    ProductId,
    StoreId,
)


NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
COMMAND_ID = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.RESERVE_INVENTORY)
EVENT_MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")


def test_reserve_inventory_command_saves_inventory_outbox_and_processed_command() -> None:
    inventory_repository = FakeInventoryRepository(_inventory(available=10))
    processed_commands = FakeProcessedCommandRepository()
    outbox_messages = FakeOutboxMessageRepository()
    handler = InventoryCommandHandler(inventory_repository, processed_commands, outbox_messages)

    result = handler.reserve_inventory(_reserve_command(quantity=3))

    assert result.status == InventoryCommandStatus.RESERVED
    assert result.duplicate_decision is None
    assert result.inventory is not None
    assert result.inventory.available_stock == Quantity(7)
    assert result.inventory.reserved_stock == Quantity(3)

    assert inventory_repository.saved == [result.inventory]
    assert len(outbox_messages.saved) == 1
    outbox = outbox_messages.saved[0]
    assert outbox.kind == OutboxMessageKind.EVENT
    assert outbox.name == CheckoutEventName.INVENTORY_RESERVED.value
    assert outbox.topic == "inventory.events"
    assert outbox.key == str(ORDER_ID)
    assert outbox.identity == str(EVENT_MESSAGE_ID)
    assert outbox.headers["correlationId"] == str(ORDER_ID)
    assert outbox.headers["causationId"] == str(COMMAND_ID)
    assert outbox.payload["orderId"] == str(ORDER_ID)
    assert outbox.payload["productId"] == str(PRODUCT_ID)
    assert outbox.payload["storeId"] == str(STORE_ID)
    assert outbox.payload["reservedQuantity"] == 3
    assert outbox.payload["availableStock"] == 7
    assert outbox.payload["reservedStock"] == 3
    assert outbox.payload["totalStock"] == 10
    assert outbox.payload["occurredAt"] == NOW.isoformat()

    assert processed_commands.records == [
        ProcessedCommand.record(
            command_id=COMMAND_ID,
            handler=InventoryCommandHandler.HANDLER_NAME,
            processed_at=NOW,
            order_id=ORDER_ID,
        )
    ]


def test_reserve_inventory_command_rejects_insufficient_stock_without_side_effects() -> None:
    inventory_repository = FakeInventoryRepository(_inventory(available=2))
    processed_commands = FakeProcessedCommandRepository()
    outbox_messages = FakeOutboxMessageRepository()
    handler = InventoryCommandHandler(inventory_repository, processed_commands, outbox_messages)

    with pytest.raises(InventoryCommandRejected) as exc:
        handler.reserve_inventory(_reserve_command(quantity=3))

    assert exc.value.reason == InventoryCommandRejectionReason.INSUFFICIENT_STOCK
    assert exc.value.command_id == COMMAND_ID
    assert exc.value.order_id == ORDER_ID
    assert inventory_repository.saved == []
    assert outbox_messages.saved == []
    assert processed_commands.records == []


def test_duplicate_command_is_explicitly_ignored_before_loading_or_saving_inventory() -> None:
    inventory_repository = FakeInventoryRepository(_inventory(available=10))
    processed_commands = FakeProcessedCommandRepository(
        existing={(InventoryCommandHandler.HANDLER_NAME, str(COMMAND_ID))}
    )
    outbox_messages = FakeOutboxMessageRepository()
    handler = InventoryCommandHandler(inventory_repository, processed_commands, outbox_messages)

    result = handler.reserve_inventory(_reserve_command(quantity=3))

    assert result.status == InventoryCommandStatus.DUPLICATE_IGNORED
    assert result.inventory is None
    assert result.outbox_message is None
    assert result.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert inventory_repository.get_calls == []
    assert inventory_repository.saved == []
    assert outbox_messages.saved == []
    assert processed_commands.records == []


def test_inventory_application_public_contracts_are_protocols_and_exports() -> None:
    import token_payments.contexts.inventory.application as application

    for port in (InventoryRepository, ProcessedCommandRepository, OutboxMessageRepository):
        assert getattr(port, "_is_protocol", False), f"{port.__name__} must be a Protocol"

    hints = get_type_hints(InventoryRepository.get)
    assert hints["return"] == ProductInventory | None

    assert {
        "ConfirmInventoryCommand",
        "InventoryCommandHandler",
        "InventoryCommandRejected",
        "InventoryCommandRejectionReason",
        "InventoryCommandStatus",
        "InventoryRepository",
        "OutboxMessageRepository",
        "ProcessedCommandRepository",
        "ReleaseInventoryCommand",
        "ReserveInventoryCommand",
    } <= set(application.__all__)


def test_inventory_application_does_not_import_external_adapters_or_clients() -> None:
    forbidden_roots = {
        "blockchain",
        "kafka",
        "metamask",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }

    for path in (ROOT / "app/token_payments/contexts/inventory/application").glob("**/*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        assert imports.isdisjoint(forbidden_roots), f"{path} imports adapter dependency: {imports}"


def _reserve_command(quantity: int) -> ReserveInventoryCommand:
    return ReserveInventoryCommand(
        command_id=COMMAND_ID,
        order_id=ORDER_ID,
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        quantity=Quantity(quantity),
        requested_at=NOW,
        causation_id="order-created-message",
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


class FakeInventoryRepository:
    def __init__(self, inventory: ProductInventory | None) -> None:
        self.inventories: dict[tuple[ProductId, StoreId], ProductInventory] = {}
        if inventory is not None:
            self.inventories[(inventory.product_id, inventory.store_id)] = inventory
        self.get_calls: list[tuple[ProductId, StoreId]] = []
        self.saved: list[ProductInventory] = []

    def get(self, product_id: ProductId, store_id: StoreId) -> ProductInventory | None:
        self.get_calls.append((product_id, store_id))
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

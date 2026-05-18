from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.inventory.adapter.kafka import InventoryKafkaCommandListener  # noqa: E402
from token_payments.contexts.inventory.application import ConfirmInventoryCommand  # noqa: E402
from token_payments.shared.adapter import MessageTopicResolver  # noqa: E402
from token_payments.shared.adapter.kafka import KafkaInboundMessage, MalformedKafkaMessage  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    IdempotencyDecision,
    MessageId,
    OrderId,
    ProcessedCommand,
    ProductId,
    StoreId,
)


NOW = datetime(2026, 5, 18, 2, 0, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c41")
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c42")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c43")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c44")
COMMAND_ID = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.CONFIRM_INVENTORY)


def test_inventory_listener_deserializes_confirm_command_and_dispatches_handler() -> None:
    handler = FakeInventoryCommandHandler()
    listener = InventoryKafkaCommandListener(
        command_handler=handler,
        processed_commands=FakeProcessedCommandRepository(),
    )

    result = listener.handle(
        _command_message(
            CheckoutCommandName.CONFIRM_INVENTORY,
            COMMAND_ID,
            {
                "productId": str(PRODUCT_ID),
                "storeId": str(STORE_ID),
                "requestedAt": NOW.isoformat(),
            },
        )
    )

    assert result.duplicate_decision is None
    assert result.command_id == COMMAND_ID
    command = handler.confirm_calls[0]
    assert isinstance(command, ConfirmInventoryCommand)
    assert command.command_id == COMMAND_ID
    assert command.order_id == ORDER_ID
    assert command.product_id == PRODUCT_ID
    assert command.store_id == STORE_ID
    assert command.requested_at == NOW
    assert command.causation_id == str(MESSAGE_ID)


def test_malformed_confirm_payload_raises_bounded_listener_error_before_dispatch() -> None:
    handler = FakeInventoryCommandHandler()
    listener = InventoryKafkaCommandListener(
        command_handler=handler,
        processed_commands=FakeProcessedCommandRepository(),
    )

    with pytest.raises(MalformedKafkaMessage, match="productId"):
        listener.handle(
            _command_message(
                CheckoutCommandName.CONFIRM_INVENTORY,
                COMMAND_ID,
                {
                    "storeId": str(STORE_ID),
                    "requestedAt": NOW.isoformat(),
                },
            )
        )

    assert handler.confirm_calls == []


def test_processed_confirm_command_duplicate_is_idempotent_before_handler_side_effects() -> None:
    processed = FakeProcessedCommandRepository(
        existing={(FakeInventoryCommandHandler.HANDLER_NAME, str(COMMAND_ID))}
    )
    handler = FakeInventoryCommandHandler()
    listener = InventoryKafkaCommandListener(command_handler=handler, processed_commands=processed)

    result = listener.handle(
        _command_message(
            CheckoutCommandName.CONFIRM_INVENTORY,
            COMMAND_ID,
            {
                "productId": str(PRODUCT_ID),
                "storeId": str(STORE_ID),
                "requestedAt": NOW.isoformat(),
            },
        )
    )

    assert result.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert handler.confirm_calls == []
    assert processed.records == []


def test_topic_resolver_exposes_confirm_command_and_event_topics() -> None:
    resolver = MessageTopicResolver.default()

    assert resolver.topic_for(CheckoutCommandName.CONFIRM_INVENTORY) == "inventory.commands"
    assert resolver.topic_for(CheckoutEventName.INVENTORY_CONFIRMED) == "inventory.events"


def test_live_worker_registry_includes_inventory_confirm_command_listener_without_starting_loops() -> None:
    from token_payments.runtime import describe_live_worker_registry

    registry = describe_live_worker_registry()
    inventory_worker = next(worker for worker in registry["workers"] if worker["name"] == "inventory-command-listener")

    assert registry["longRunning"] is False
    assert registry["serverStarted"] is False
    assert registry["externalConnectionsOpened"] is False
    assert inventory_worker["topic"] == "inventory.commands"
    assert inventory_worker["listener"] == (
        "token_payments.contexts.inventory.adapter.kafka.InventoryKafkaCommandListener"
    )
    assert set(inventory_worker["messageNames"]) == {
        CheckoutCommandName.RESERVE_INVENTORY.value,
        CheckoutCommandName.RELEASE_INVENTORY.value,
        CheckoutCommandName.CONFIRM_INVENTORY.value,
    }


def _command_message(
    name: CheckoutCommandName,
    command_id: CommandId,
    extra_payload: Mapping[str, Any],
) -> KafkaInboundMessage:
    return KafkaInboundMessage(
        topic="inventory.commands",
        key=str(ORDER_ID),
        value=json.dumps(
            {
                "commandName": name.value,
                "commandId": str(command_id),
                "orderId": str(ORDER_ID),
                **extra_payload,
            }
        ),
        headers={
            "command_id": str(command_id),
            "correlation_id": str(ORDER_ID),
            "causation_id": str(MESSAGE_ID),
        },
    )


class FakeHandlerResult:
    def __init__(self, command_id: CommandId, order_id: OrderId) -> None:
        self.command_id = command_id
        self.order_id = order_id


class FakeInventoryCommandHandler:
    HANDLER_NAME = "inventory-command-handler"

    def __init__(self) -> None:
        self.confirm_calls: list[ConfirmInventoryCommand] = []

    def confirm_inventory(self, command: ConfirmInventoryCommand) -> FakeHandlerResult:
        self.confirm_calls.append(command)
        return FakeHandlerResult(command.command_id, command.order_id)


class FakeProcessedCommandRepository:
    def __init__(self, existing: set[tuple[str, str]] | None = None) -> None:
        self.existing = existing or set()
        self.records: list[ProcessedCommand] = []

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return (handler, str(command_id)) in self.existing

    def record(self, processed_command: ProcessedCommand) -> IdempotencyDecision:
        self.records.append(processed_command)
        self.existing.add(processed_command.idempotency_key)
        return IdempotencyDecision.PROCESS

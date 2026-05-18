from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.checkout.adapter.kafka import CheckoutKafkaEventListener  # noqa: E402
from token_payments.contexts.checkout.application import CheckoutProcessManager  # noqa: E402
from token_payments.shared.adapter.kafka import KafkaInboundMessage  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxMessage,
    ProcessedMessage,
    ProductId,
    StoreId,
)


NOW = datetime(2026, 5, 18, 1, 30, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c31")
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c32")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c33")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c34")


def test_order_approved_event_decides_deterministic_confirm_inventory_command() -> None:
    commands = CheckoutProcessManager().handle(_process_event(CheckoutEventName.ORDER_APPROVED))

    assert [command.name for command in commands] == [CheckoutCommandName.CONFIRM_INVENTORY]
    assert [str(command.command_id) for command in commands] == [
        f"{ORDER_ID}:ConfirmInventoryCommand",
    ]


def test_failure_and_rejection_events_still_release_reserved_inventory() -> None:
    manager = CheckoutProcessManager()

    assert [command.name for command in manager.handle(_process_event(CheckoutEventName.ORDER_REJECTED))] == [
        CheckoutCommandName.REFUND_PAYMENT,
        CheckoutCommandName.RELEASE_INVENTORY,
        CheckoutCommandName.CANCEL_ORDER,
    ]
    for event_name in (CheckoutEventName.PAYMENT_FAILED, CheckoutEventName.PAYMENT_EXPIRED):
        assert [command.name for command in manager.handle(_process_event(event_name))] == [
            CheckoutCommandName.RELEASE_INVENTORY,
            CheckoutCommandName.CANCEL_ORDER,
        ]


def test_terminal_order_cancelled_event_does_not_emit_confirm_inventory() -> None:
    assert CheckoutProcessManager().handle(_process_event(CheckoutEventName.ORDER_CANCELLED)) == ()
    assert CheckoutProcessManager().handle(_process_event(CheckoutEventName.INVENTORY_CONFIRMED)) == ()


def test_checkout_listener_writes_confirm_inventory_payload_for_order_approved_event() -> None:
    outbox_messages = FakeOutboxMessageRepository()
    listener = CheckoutKafkaEventListener(
        process_manager=CheckoutProcessManager(),
        processed_messages=FakeProcessedMessageRepository(),
        outbox_messages=outbox_messages,
    )

    result = listener.handle(
        _event_message(
            CheckoutEventName.ORDER_APPROVED,
            {
                "storeId": str(STORE_ID),
                "productIds": [str(PRODUCT_ID)],
                "approvalStatus": "APPROVED",
            },
        )
    )

    assert result.duplicate_decision is None
    assert len(outbox_messages.saved) == 1
    confirm = outbox_messages.saved[0]
    assert confirm.name == CheckoutCommandName.CONFIRM_INVENTORY.value
    assert confirm.topic == "inventory.commands"
    assert confirm.identity == str(CommandId.for_order_action(ORDER_ID, CheckoutCommandName.CONFIRM_INVENTORY))
    assert confirm.payload["commandName"] == CheckoutCommandName.CONFIRM_INVENTORY.value
    assert confirm.payload["commandId"] == confirm.identity
    assert confirm.payload["orderId"] == str(ORDER_ID)
    assert confirm.payload["storeId"] == str(STORE_ID)
    assert confirm.payload["productId"] == str(PRODUCT_ID)
    assert confirm.payload["sourceEventName"] == CheckoutEventName.ORDER_APPROVED.value


def test_duplicate_order_approved_message_is_ignored_before_confirm_command_side_effects() -> None:
    processed = FakeProcessedMessageRepository(
        existing={(CheckoutKafkaEventListener.CONSUMER_NAME, str(MESSAGE_ID))}
    )
    outbox_messages = FakeOutboxMessageRepository()
    listener = CheckoutKafkaEventListener(
        process_manager=CheckoutProcessManager(),
        processed_messages=processed,
        outbox_messages=outbox_messages,
    )

    result = listener.handle(_event_message(CheckoutEventName.ORDER_APPROVED, {"storeId": str(STORE_ID)}))

    assert result.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert outbox_messages.saved == []
    assert processed.records == []


def _process_event(name: CheckoutEventName):
    from token_payments.contexts.checkout.application import CheckoutProcessEvent
    from token_payments.shared.domain import EventMetadata

    return CheckoutProcessEvent(
        metadata=EventMetadata(
            message_id=MESSAGE_ID,
            name=name,
            aggregate_id=str(ORDER_ID),
            occurred_at=NOW,
            correlation_id=str(ORDER_ID),
        ),
        order_id=ORDER_ID,
    )


def _event_message(name: CheckoutEventName, extra_payload: Mapping[str, Any]) -> KafkaInboundMessage:
    return KafkaInboundMessage(
        topic="checkout.events",
        key=str(ORDER_ID),
        value=json.dumps(
            {
                "eventName": name.value,
                "orderId": str(ORDER_ID),
                "occurredAt": NOW.isoformat(),
                **extra_payload,
            }
        ),
        headers={
            "message_id": str(MESSAGE_ID),
            "correlation_id": str(ORDER_ID),
            "causation_id": "upstream-command",
        },
    )


class FakeProcessedMessageRepository:
    def __init__(self, existing: set[tuple[str, str]] | None = None) -> None:
        self.existing = existing or set()
        self.records: list[ProcessedMessage] = []

    def was_processed(self, message_id: MessageId, consumer: str) -> bool:
        return (consumer, str(message_id)) in self.existing

    def record(self, processed_message: ProcessedMessage) -> IdempotencyDecision:
        self.records.append(processed_message)
        self.existing.add(processed_message.idempotency_key)
        return IdempotencyDecision.PROCESS


class FakeOutboxMessageRepository:
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)

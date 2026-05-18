from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    CommandMetadata,
    EventMetadata,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxPublishStatus,
    ProcessedCommand,
    ProcessedMessage,
)


def test_checkout_message_names_cover_process_manager_sequence() -> None:
    assert {event.value for event in CheckoutEventName} == {
        "OrderCreatedEvent",
        "InventoryReservedEvent",
        "InventoryConfirmedEvent",
        "PaymentConfirmedEvent",
        "PaymentFailedEvent",
        "PaymentExpiredEvent",
        "OrderApprovedEvent",
        "OrderRejectedEvent",
        "OrderCancelledEvent",
    }
    assert {command.value for command in CheckoutCommandName} == {
        "ReserveInventoryCommand",
        "InitiatePaymentCommand",
        "RequestStoreApprovalCommand",
        "ConfirmInventoryCommand",
        "ReleaseInventoryCommand",
        "RefundPaymentCommand",
        "CancelOrderCommand",
    }


def test_event_metadata_carries_message_identity_and_correlation() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    event = EventMetadata(
        message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"),
        name=CheckoutEventName.ORDER_CREATED,
        aggregate_id="order-123",
        occurred_at=now,
        correlation_id="checkout-123",
        causation_id="api-request-123",
    )

    assert event.message_id == MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
    assert event.name == CheckoutEventName.ORDER_CREATED
    assert event.occurred_at == now
    assert event.correlation_id == "checkout-123"


def test_compensation_command_id_is_deterministic_from_order_and_action() -> None:
    order_id = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")

    release_1 = CommandId.for_order_action(order_id, CheckoutCommandName.RELEASE_INVENTORY)
    release_2 = CommandId.for_order_action(order_id, "ReleaseInventoryCommand")
    cancel = CommandId.for_order_action(order_id, CheckoutCommandName.CANCEL_ORDER)

    assert release_1 == release_2
    assert release_1.value == f"{order_id}:ReleaseInventoryCommand"
    assert cancel.value == f"{order_id}:CancelOrderCommand"
    assert release_1 != cancel


def test_command_metadata_uses_deterministic_command_id() -> None:
    order_id = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
    command_id = CommandId.for_order_action(order_id, CheckoutCommandName.REFUND_PAYMENT)

    command = CommandMetadata(
        command_id=command_id,
        name=CheckoutCommandName.REFUND_PAYMENT,
        aggregate_id=str(order_id),
        issued_at=datetime(2026, 5, 9, 12, 1, tzinfo=UTC),
        correlation_id=str(order_id),
        causation_id="PaymentConfirmedEvent",
    )

    assert command.command_id == command_id
    assert command.name == CheckoutCommandName.REFUND_PAYMENT
    assert command.aggregate_id == str(order_id)


def test_outbox_message_publish_status_transitions_are_explicit() -> None:
    outbox = OutboxMessage.record_event(
        metadata=EventMetadata(
            message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"),
            name=CheckoutEventName.PAYMENT_CONFIRMED,
            aggregate_id="payment-123",
            occurred_at=datetime(2026, 5, 9, 12, 2, tzinfo=UTC),
            correlation_id="order-123",
        ),
        topic="payment.events",
        key="order-123",
        payload={"orderId": "order-123"},
    )

    assert outbox.status == OutboxPublishStatus.READY

    publishing = outbox.mark_publishing()
    assert publishing.status == OutboxPublishStatus.PUBLISHING
    assert outbox.status == OutboxPublishStatus.READY

    published_at = datetime(2026, 5, 9, 12, 3, tzinfo=UTC)
    published = publishing.mark_published(published_at=published_at)
    assert published.status == OutboxPublishStatus.PUBLISHED
    assert published.published_at == published_at

    with pytest.raises(ValueError):
        published.mark_publishing()


def test_outbox_message_failure_can_be_retried_without_using_harness_statuses() -> None:
    outbox = OutboxMessage.record_command(
        metadata=CommandMetadata(
            command_id=CommandId.for_order_action(
                OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"),
                CheckoutCommandName.CANCEL_ORDER,
            ),
            name=CheckoutCommandName.CANCEL_ORDER,
            aggregate_id="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21",
            issued_at=datetime(2026, 5, 9, 12, 4, tzinfo=UTC),
            correlation_id="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21",
        ),
        topic="order.commands",
        key="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21",
        payload={"reason": "payment-expired"},
    )

    failed = outbox.mark_failed("broker unavailable")
    retrying = failed.mark_publishing()

    assert failed.status == OutboxPublishStatus.FAILED
    assert failed.failure_count == 1
    assert failed.last_error == "broker unavailable"
    assert retrying.status == OutboxPublishStatus.PUBLISHING
    assert {status.value for status in OutboxPublishStatus}.isdisjoint(
        {"pending", "completed", "error", "blocked"}
    )


def test_processed_models_define_idempotent_ignore_keys() -> None:
    message_id = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
    order_id = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
    processed_message = ProcessedMessage.record(
        message_id=message_id,
        consumer="checkout-process-manager",
        order_id=order_id,
        processed_at=datetime(2026, 5, 9, 12, 5, tzinfo=UTC),
    )
    processed_command = ProcessedCommand.record(
        command_id=CommandId.for_order_action(order_id, CheckoutCommandName.RELEASE_INVENTORY),
        handler="inventory-command-handler",
        order_id=order_id,
        processed_at=datetime(2026, 5, 9, 12, 6, tzinfo=UTC),
    )

    assert processed_message.idempotency_key == ("checkout-process-manager", str(message_id))
    assert processed_message.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert processed_command.idempotency_key == (
        "inventory-command-handler",
        f"{order_id}:ReleaseInventoryCommand",
    )
    assert processed_command.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE


def test_messaging_contracts_do_not_import_adapters_or_brokers() -> None:
    forbidden_roots = {
        "blockchain",
        "kafka",
        "metamask",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }
    path = ROOT / "app/token_payments/shared/domain/messaging.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    assert imports.isdisjoint(forbidden_roots), f"{path} imports adapter dependency: {imports}"

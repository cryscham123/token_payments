from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    OperatorActionResultStatus,
    OperatorCancelOrderActionExecutor,
    OperatorClaims,
)
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.contexts.order.application import (  # noqa: E402
    CancelOrderCommand,
    OrderCommandRejected,
    OrderCommandRejectionReason,
    OrderCommandResult,
    OrderCommandStatus,
)
from token_payments.shared.domain import CheckoutCommandName, CommandId, MessageId, OrderId  # noqa: E402


NOW = datetime(2026, 5, 11, 7, 20, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7a11")
REQUEST_ID = "req-operator-cancel-1"
EVENT_MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7a12")
IDEMPOTENCY_KEY = "operator-cancel-order-explicit-key"


def test_admin_cancel_order_action_builds_command_with_explicit_idempotency_key() -> None:
    handler = RecordingOrderCommandHandler(OrderCommandStatus.CANCELLED)
    audit = RecordingOperatorActionAuditRepository()
    executor = OperatorCancelOrderActionExecutor(command_handler=handler, audit_repository=audit)

    result = executor.cancel_order(
        actor=_admin(),
        order_id=ORDER_ID,
        reason="support confirmed payment timeout",
        request_id=REQUEST_ID,
        requested_at=NOW,
        idempotency_key=IDEMPOTENCY_KEY,
        event_message_id=EVENT_MESSAGE_ID,
    )

    command = handler.calls[0]
    assert isinstance(command, CancelOrderCommand)
    assert command.command_id == CommandId(IDEMPOTENCY_KEY)
    assert command.order_id == ORDER_ID
    assert command.reason == "support confirmed payment timeout"
    assert command.requested_at == NOW
    assert command.causation_id == REQUEST_ID
    assert command.event_message_id == EVENT_MESSAGE_ID

    assert result.status is OperatorActionResultStatus.ACCEPTED
    assert result.command_id == IDEMPOTENCY_KEY
    assert result.message_id == str(EVENT_MESSAGE_ID)
    assert result.idempotency_key == IDEMPOTENCY_KEY
    assert result.details["handlerStatus"] == OrderCommandStatus.CANCELLED.value
    assert result.audit_id == "audit-1"
    assert audit.records[0].outcome is OperatorActionResultStatus.ACCEPTED


def test_cancel_order_action_without_idempotency_key_uses_stable_default_keys() -> None:
    handler = RecordingOrderCommandHandler(OrderCommandStatus.CANCELLED)
    executor = OperatorCancelOrderActionExecutor(command_handler=handler)

    result = executor.cancel_order(
        actor=_admin(),
        order_id=str(ORDER_ID),
        reason="manual cancellation after customer request",
        request_id=REQUEST_ID,
        requested_at=NOW,
    )

    command = handler.calls[0]
    expected_command_id = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.CANCEL_ORDER)
    assert command.command_id == expected_command_id
    assert command.causation_id == REQUEST_ID
    assert isinstance(command.event_message_id, MessageId)
    assert result.command_id == str(expected_command_id)
    assert result.message_id == str(command.event_message_id)
    assert result.idempotency_key == f"operator:cancelOrder:{ORDER_ID}:{REQUEST_ID}"


@pytest.mark.parametrize(
    ("handler_status", "action_status"),
    [
        (OrderCommandStatus.CANCELLED, OperatorActionResultStatus.ACCEPTED),
        (OrderCommandStatus.ALREADY_CANCELLED, OperatorActionResultStatus.ACCEPTED),
        (OrderCommandStatus.DUPLICATE_IGNORED, OperatorActionResultStatus.DUPLICATE),
    ],
)
def test_cancel_order_action_preserves_handler_status_in_operator_payload(
    handler_status: OrderCommandStatus,
    action_status: OperatorActionResultStatus,
) -> None:
    audit = RecordingOperatorActionAuditRepository()
    executor = OperatorCancelOrderActionExecutor(
        command_handler=RecordingOrderCommandHandler(handler_status),
        audit_repository=audit,
    )

    result = executor.cancel_order(
        actor=_admin(),
        order_id=ORDER_ID,
        reason="operator requested cancellation",
        request_id=REQUEST_ID,
        requested_at=NOW,
        event_message_id=EVENT_MESSAGE_ID,
    )

    assert result.status is action_status
    assert result.details["handlerStatus"] == handler_status.value
    assert result.details["orderId"] == str(ORDER_ID)
    assert audit.records[0].outcome is action_status


@pytest.mark.parametrize(
    "rejection_reason",
    [OrderCommandRejectionReason.ORDER_NOT_FOUND, OrderCommandRejectionReason.INVALID_STATE],
)
def test_cancel_order_action_converts_handler_rejections_to_rejected_result(
    rejection_reason: OrderCommandRejectionReason,
) -> None:
    rejection = OrderCommandRejected(
        reason=rejection_reason,
        command_id=CommandId.for_order_action(ORDER_ID, CheckoutCommandName.CANCEL_ORDER),
        order_id=ORDER_ID,
        message=f"handler rejected with {rejection_reason.value}",
    )
    handler = RecordingOrderCommandHandler(rejection)
    audit = RecordingOperatorActionAuditRepository()
    executor = OperatorCancelOrderActionExecutor(command_handler=handler, audit_repository=audit)

    result = executor.cancel_order(
        actor=_admin(),
        order_id=ORDER_ID,
        reason="operator requested cancellation",
        request_id=REQUEST_ID,
        requested_at=NOW,
        event_message_id=EVENT_MESSAGE_ID,
    )

    assert result.status is OperatorActionResultStatus.REJECTED
    assert result.details["rejectionReason"] == rejection_reason.value
    assert result.details["orderId"] == str(ORDER_ID)
    assert "handler rejected" in result.summary
    assert audit.records[0].outcome is OperatorActionResultStatus.REJECTED


def test_cancel_order_action_rejects_non_admin_without_calling_handler() -> None:
    handler = RecordingOrderCommandHandler(OrderCommandStatus.CANCELLED)
    audit = RecordingOperatorActionAuditRepository()
    executor = OperatorCancelOrderActionExecutor(command_handler=handler, audit_repository=audit)

    result = executor.cancel_order(
        actor=OperatorClaims(user_id="customer-1", role=UserRole.CUSTOMER),
        order_id=ORDER_ID,
        reason="attempted unauthorized cancellation",
        request_id=REQUEST_ID,
        requested_at=NOW,
        event_message_id=EVENT_MESSAGE_ID,
    )

    assert handler.calls == []
    assert result.status is OperatorActionResultStatus.REJECTED
    assert result.details["errorCode"] == "OPERATOR_FORBIDDEN"
    assert result.summary == "operator:action permission is required to execute cancelOrder"
    assert audit.records[0].outcome is OperatorActionResultStatus.REJECTED


def _admin() -> OperatorClaims:
    return OperatorClaims(user_id="operator-1", role=UserRole.ADMIN, scopes=("operator:action",))


class RecordingOrderCommandHandler:
    def __init__(self, outcome: OrderCommandStatus | OrderCommandRejected) -> None:
        self.outcome = outcome
        self.calls: list[CancelOrderCommand] = []

    def cancel_order(self, command: CancelOrderCommand) -> OrderCommandResult:
        self.calls.append(command)
        if isinstance(self.outcome, OrderCommandRejected):
            raise self.outcome
        return OrderCommandResult(command_id=command.command_id, order_id=command.order_id, status=self.outcome)


class RecordingOperatorActionAuditRepository:
    def __init__(self) -> None:
        self.records = []

    def record(self, audit_record):
        self.records.append(audit_record)
        return f"audit-{len(self.records)}"

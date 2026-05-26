from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    OperatorActionResultStatus,
    OperatorClaims,
    OperatorMessageReplayRequest,
    OperatorOutboxActionExecutor,
    OperatorOutboxActionPortResult,
    OperatorOutboxActionStatus,
    OperatorOutboxRetryRequest,
)
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.shared.domain import OutboxMessageKind  # noqa: E402


NOW = datetime(2026, 5, 11, 8, 15, tzinfo=UTC)
REQUEST_ID = "req-operator-outbox-action-1"
OUTBOX_MESSAGE_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc8a21"
COMMAND_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc8a11:ReleaseInventoryCommand"
RETRY_IDEMPOTENCY_KEY = "operator:retryOutboxMessage:018f33aa-9e6d-73d8-9dc3-47d6cdcc8a21"
REPLAY_IDEMPOTENCY_KEY = "operator:replayMessage:018f33aa-9e6d-73d8-9dc3-47d6cdcc8a11"


def test_retry_outbox_message_action_calls_retry_port_and_records_audit_payload() -> None:
    retry_port = RecordingRetryPort(OperatorOutboxActionStatus.RETRYABLE)
    audit = RecordingOperatorActionAuditRepository()
    executor = OperatorOutboxActionExecutor(
        retry_port=retry_port,
        replay_port=RecordingReplayPort(OperatorOutboxActionStatus.RECORDED),
        audit_repository=audit,
    )

    result = executor.retry_outbox_message(
        actor=_admin(),
        message_kind=OutboxMessageKind.EVENT,
        message_identity=OUTBOX_MESSAGE_ID,
        reason="broker outage resolved; publish failed OrderCreated event again",
        request_id=REQUEST_ID,
        requested_at=NOW,
        idempotency_key=RETRY_IDEMPOTENCY_KEY,
    )

    request = retry_port.requests[0]
    assert isinstance(request, OperatorOutboxRetryRequest)
    assert request.message_kind is OutboxMessageKind.EVENT
    assert request.message_identity == OUTBOX_MESSAGE_ID
    assert request.reason == "broker outage resolved; publish failed OrderCreated event again"
    assert request.actor == _admin()
    assert request.request_id == REQUEST_ID
    assert request.idempotency_key == RETRY_IDEMPOTENCY_KEY
    assert request.requested_at == NOW

    assert result.status is OperatorActionResultStatus.ACCEPTED
    assert result.message_id == OUTBOX_MESSAGE_ID
    assert result.audit_id == "audit-1"
    assert result.details["outboxActionStatus"] == OperatorOutboxActionStatus.RETRYABLE.value
    assert result.details["messageKind"] == OutboxMessageKind.EVENT.value
    assert result.details["messageIdentity"] == OUTBOX_MESSAGE_ID
    assert result.details["requestId"] == REQUEST_ID
    assert result.details["actor"] == {
        "userId": "operator-1",
        "groupId": None,
        "scopes": ["operator:action", "outbox:retry"],
    }
    assert result.details["reason"] == "broker outage resolved; publish failed OrderCreated event again"

    audit_record = audit.records[0]
    assert audit_record.target.to_payload() == {"kind": "outboxMessage", "id": OUTBOX_MESSAGE_ID}
    assert audit_record.request_id == REQUEST_ID
    assert audit_record.actor == _admin()
    assert audit_record.reason == "broker outage resolved; publish failed OrderCreated event again"
    assert audit_record.outcome is OperatorActionResultStatus.ACCEPTED


def test_replay_message_action_records_replay_request_without_idempotency_deletes() -> None:
    replay_port = RecordingReplayPort(OperatorOutboxActionStatus.RECORDED)
    executor = OperatorOutboxActionExecutor(
        retry_port=RecordingRetryPort(OperatorOutboxActionStatus.RETRYABLE),
        replay_port=replay_port,
        audit_repository=RecordingOperatorActionAuditRepository(),
    )

    result = executor.replay_message(
        actor=_admin(),
        message_kind="COMMAND",
        message_identity=COMMAND_ID,
        reason="handler bug fixed; replay original ReleaseInventory command intent",
        request_id=REQUEST_ID,
        requested_at=NOW,
        idempotency_key=REPLAY_IDEMPOTENCY_KEY,
    )

    request = replay_port.requests[0]
    assert isinstance(request, OperatorMessageReplayRequest)
    assert request.message_kind is OutboxMessageKind.COMMAND
    assert request.message_identity == COMMAND_ID
    assert request.reason == "handler bug fixed; replay original ReleaseInventory command intent"
    assert replay_port.deleted_processed_messages == []
    assert replay_port.deleted_processed_commands == []

    assert result.status is OperatorActionResultStatus.ACCEPTED
    assert result.message_id == COMMAND_ID
    assert result.details["outboxActionStatus"] == OperatorOutboxActionStatus.RECORDED.value
    assert result.details["messageKind"] == OutboxMessageKind.COMMAND.value
    assert result.details["messageIdentity"] == COMMAND_ID
    assert result.details["requestId"] == REQUEST_ID
    assert result.details["idempotencyRecordsDeleted"] is False


@pytest.mark.parametrize(
    ("method_name", "port_status", "expected_action_status"),
    [
        ("retry_outbox_message", OperatorOutboxActionStatus.DUPLICATE_IGNORED, OperatorActionResultStatus.DUPLICATE),
        ("replay_message", OperatorOutboxActionStatus.DUPLICATE_IGNORED, OperatorActionResultStatus.DUPLICATE),
    ],
)
def test_retry_and_replay_duplicate_idempotency_keys_return_duplicate_ignored_results(
    method_name: str,
    port_status: OperatorOutboxActionStatus,
    expected_action_status: OperatorActionResultStatus,
) -> None:
    executor = OperatorOutboxActionExecutor(
        retry_port=RecordingRetryPort(port_status),
        replay_port=RecordingReplayPort(port_status),
        audit_repository=RecordingOperatorActionAuditRepository(),
    )

    result = getattr(executor, method_name)(
        actor=_admin(),
        message_kind=OutboxMessageKind.EVENT,
        message_identity=OUTBOX_MESSAGE_ID,
        reason="same operator action was already requested",
        request_id=REQUEST_ID,
        requested_at=NOW,
        idempotency_key=RETRY_IDEMPOTENCY_KEY,
    )

    assert result.status is expected_action_status
    assert result.details["outboxActionStatus"] == OperatorOutboxActionStatus.DUPLICATE_IGNORED.value
    assert result.details["duplicateDecision"] == OperatorOutboxActionStatus.DUPLICATE_IGNORED.value
    assert result.summary == "Duplicate operator outbox action ignored for idempotency key."
    assert result.audit_id == "audit-1"


@pytest.mark.parametrize(
    ("method_name", "message_kind", "message_identity", "reason", "invalid_field"),
    [
        ("retry_outbox_message", "INVALID", OUTBOX_MESSAGE_ID, "retry after broker recovery", "messageKind"),
        ("replay_message", OutboxMessageKind.EVENT, " ", "replay original event", "messageIdentity"),
        ("retry_outbox_message", OutboxMessageKind.EVENT, OUTBOX_MESSAGE_ID, " ", "reason"),
    ],
)
def test_retry_replay_reject_invalid_inputs_without_calling_ports(
    method_name: str,
    message_kind: OutboxMessageKind | str,
    message_identity: str,
    reason: str,
    invalid_field: str,
) -> None:
    retry_port = RecordingRetryPort(OperatorOutboxActionStatus.RETRYABLE)
    replay_port = RecordingReplayPort(OperatorOutboxActionStatus.RECORDED)
    executor = OperatorOutboxActionExecutor(
        retry_port=retry_port,
        replay_port=replay_port,
        audit_repository=RecordingOperatorActionAuditRepository(),
    )

    result = getattr(executor, method_name)(
        actor=_admin(),
        message_kind=message_kind,
        message_identity=message_identity,
        reason=reason,
        request_id=REQUEST_ID,
        requested_at=NOW,
        idempotency_key=RETRY_IDEMPOTENCY_KEY,
    )

    assert retry_port.requests == []
    assert replay_port.requests == []
    assert result.status is OperatorActionResultStatus.REJECTED
    assert result.details["errorCode"] == "OPERATOR_ACTION_VALIDATION_FAILED"
    assert result.details["invalidField"] == invalid_field
    assert result.details["requestId"] == REQUEST_ID
    assert result.summary.startswith("Invalid operator outbox action request:")


def test_retry_outbox_action_rejects_missing_outbox_retry_permission_without_calling_retry_port() -> None:
    retry_port = RecordingRetryPort(OperatorOutboxActionStatus.RETRYABLE)
    executor = OperatorOutboxActionExecutor(
        retry_port=retry_port,
        replay_port=RecordingReplayPort(OperatorOutboxActionStatus.RECORDED),
        audit_repository=RecordingOperatorActionAuditRepository(),
    )

    result = executor.retry_outbox_message(
        actor=OperatorClaims(user_id="customer-1", role=UserRole.CUSTOMER, scopes=("operator:action",)),
        message_kind=OutboxMessageKind.EVENT,
        message_identity=OUTBOX_MESSAGE_ID,
        reason="customer attempted retry",
        request_id=REQUEST_ID,
        requested_at=NOW,
        idempotency_key=RETRY_IDEMPOTENCY_KEY,
    )

    assert retry_port.requests == []
    assert result.status is OperatorActionResultStatus.REJECTED
    assert result.summary == "operator:action and outbox:retry permissions are required to execute retryOutboxMessage"
    assert result.details["errorCode"] == "OPERATOR_FORBIDDEN"
    assert result.details["messageIdentity"] == OUTBOX_MESSAGE_ID


def _admin() -> OperatorClaims:
    return OperatorClaims(user_id="operator-1", role=UserRole.ADMIN, scopes=("operator:action", "outbox:retry"))


class RecordingRetryPort:
    def __init__(self, status: OperatorOutboxActionStatus) -> None:
        self.status = status
        self.requests: list[OperatorOutboxRetryRequest] = []

    def request_retry(self, request: OperatorOutboxRetryRequest) -> OperatorOutboxActionPortResult:
        self.requests.append(request)
        return OperatorOutboxActionPortResult(
            status=self.status,
            message_kind=request.message_kind,
            message_identity=request.message_identity,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            summary=_summary_for(self.status),
        )


class RecordingReplayPort:
    def __init__(self, status: OperatorOutboxActionStatus) -> None:
        self.status = status
        self.requests: list[OperatorMessageReplayRequest] = []
        self.deleted_processed_messages: list[str] = []
        self.deleted_processed_commands: list[str] = []

    def request_replay(self, request: OperatorMessageReplayRequest) -> OperatorOutboxActionPortResult:
        self.requests.append(request)
        return OperatorOutboxActionPortResult(
            status=self.status,
            message_kind=request.message_kind,
            message_identity=request.message_identity,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            summary=_summary_for(self.status),
        )

    def delete_processed_message(self, message_id: str) -> None:
        self.deleted_processed_messages.append(message_id)

    def delete_processed_command(self, command_id: str) -> None:
        self.deleted_processed_commands.append(command_id)


class RecordingOperatorActionAuditRepository:
    def __init__(self) -> None:
        self.records = []

    def record(self, audit_record):
        self.records.append(audit_record)
        return f"audit-{len(self.records)}"


def _summary_for(status: OperatorOutboxActionStatus) -> str:
    if status is OperatorOutboxActionStatus.DUPLICATE_IGNORED:
        return "Duplicate operator outbox action ignored for idempotency key."
    if status is OperatorOutboxActionStatus.RETRYABLE:
        return "Outbox message retry request recorded and message is retryable."
    return "Message replay request recorded."

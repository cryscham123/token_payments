"""Framework-neutral operator action command, result, audit, and policy contracts."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import math
from types import MappingProxyType
from typing import Any, Mapping, Protocol
from uuid import UUID

from token_payments.contexts.auth.domain import UserRole
from token_payments.contexts.order.application import (
    CancelOrderCommand,
    OrderCommandRejected,
    OrderCommandResult,
    OrderCommandStatus,
)
from token_payments.shared.domain import CheckoutCommandName, CommandId, MessageId, OrderId, OutboxMessageKind

from .contracts import JsonValue
from .operator import OperatorClaims


class OperatorActionName(StrEnum):
    CANCEL_ORDER = "cancelOrder"
    RETRY_OUTBOX_MESSAGE = "retryOutboxMessage"
    REPLAY_MESSAGE = "replayMessage"


class OperatorActionTargetKind(StrEnum):
    ORDER = "order"
    OUTBOX_MESSAGE = "outboxMessage"
    MESSAGE = "message"


class OperatorActionResultStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class OperatorOutboxActionStatus(StrEnum):
    RECORDED = "RECORDED"
    RETRYABLE = "RETRYABLE"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class OperatorActionTarget:
    kind: OperatorActionTargetKind | str
    id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OperatorActionTargetKind):
            object.__setattr__(
                self,
                "kind",
                OperatorActionTargetKind(_require_text(str(self.kind), "OperatorActionTarget.kind")),
            )
        object.__setattr__(self, "id", _require_text(self.id, "OperatorActionTarget.id"))

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "kind": self.kind.value,
            "id": self.id,
        }


@dataclass(frozen=True)
class OperatorActionCommand:
    action: OperatorActionName | str
    target: OperatorActionTarget
    actor: OperatorClaims
    request_id: str
    idempotency_key: str
    reason: str
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", _coerce_action(self.action, "OperatorActionCommand.action"))
        if not isinstance(self.target, OperatorActionTarget):
            raise ValueError("OperatorActionCommand.target must be an OperatorActionTarget")
        if not isinstance(self.actor, OperatorClaims):
            raise ValueError("OperatorActionCommand.actor must be an OperatorClaims")
        object.__setattr__(self, "request_id", _require_text(self.request_id, "OperatorActionCommand.request_id"))
        object.__setattr__(
            self,
            "idempotency_key",
            _require_text(self.idempotency_key, "OperatorActionCommand.idempotency_key"),
        )
        object.__setattr__(self, "reason", _require_text(self.reason, "OperatorActionCommand.reason"))
        object.__setattr__(
            self,
            "requested_at",
            _require_aware_datetime(self.requested_at, "OperatorActionCommand.requested_at"),
        )
        object.__setattr__(
            self,
            "parameters",
            MappingProxyType(_to_json_safe_mapping(self.parameters, "OperatorActionCommand.parameters")),
        )
        _validate_action_target(self.action, self.target)


@dataclass(frozen=True)
class OperatorActionResult:
    status: OperatorActionResultStatus | str
    action: OperatorActionName | str
    target: OperatorActionTarget
    idempotency_key: str
    summary: str
    command_id: str | None = None
    message_id: str | None = None
    audit_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.status, OperatorActionResultStatus):
            object.__setattr__(
                self,
                "status",
                OperatorActionResultStatus(_require_text(str(self.status), "OperatorActionResult.status")),
            )
        object.__setattr__(self, "action", _coerce_action(self.action, "OperatorActionResult.action"))
        if not isinstance(self.target, OperatorActionTarget):
            raise ValueError("OperatorActionResult.target must be an OperatorActionTarget")
        object.__setattr__(
            self,
            "idempotency_key",
            _require_text(self.idempotency_key, "OperatorActionResult.idempotency_key"),
        )
        object.__setattr__(self, "summary", _require_text(self.summary, "OperatorActionResult.summary"))
        if self.command_id is not None:
            object.__setattr__(self, "command_id", _require_text(self.command_id, "OperatorActionResult.command_id"))
        if self.message_id is not None:
            object.__setattr__(self, "message_id", _require_text(self.message_id, "OperatorActionResult.message_id"))
        if self.audit_id is not None:
            object.__setattr__(self, "audit_id", _require_text(self.audit_id, "OperatorActionResult.audit_id"))
        object.__setattr__(
            self,
            "details",
            MappingProxyType(_to_json_safe_mapping(self.details, "OperatorActionResult.details")),
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "action": self.action.value,
            "status": self.status.value,
            "target": self.target.to_payload(),
            "idempotencyKey": self.idempotency_key,
            "commandId": self.command_id,
            "messageId": self.message_id,
            "auditId": self.audit_id,
            "summary": self.summary,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class OperatorActionAuditRecord:
    actor: OperatorClaims
    action: OperatorActionName | str
    target: OperatorActionTarget
    idempotency_key: str
    request_id: str
    outcome: OperatorActionResultStatus | str
    reason: str
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.actor, OperatorClaims):
            raise ValueError("OperatorActionAuditRecord.actor must be an OperatorClaims")
        object.__setattr__(self, "action", _coerce_action(self.action, "OperatorActionAuditRecord.action"))
        if not isinstance(self.target, OperatorActionTarget):
            raise ValueError("OperatorActionAuditRecord.target must be an OperatorActionTarget")
        object.__setattr__(
            self,
            "idempotency_key",
            _require_text(self.idempotency_key, "OperatorActionAuditRecord.idempotency_key"),
        )
        object.__setattr__(self, "request_id", _require_text(self.request_id, "OperatorActionAuditRecord.request_id"))
        if not isinstance(self.outcome, OperatorActionResultStatus):
            object.__setattr__(
                self,
                "outcome",
                OperatorActionResultStatus(_require_text(str(self.outcome), "OperatorActionAuditRecord.outcome")),
            )
        object.__setattr__(self, "reason", _require_text(self.reason, "OperatorActionAuditRecord.reason"))
        object.__setattr__(
            self,
            "recorded_at",
            _require_aware_datetime(self.recorded_at, "OperatorActionAuditRecord.recorded_at"),
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "actor": {
                "userId": self.actor.user_id,
                "role": self.actor.role.value if isinstance(self.actor.role, UserRole) else self.actor.role,
                "scopes": list(self.actor.scopes),
            },
            "action": self.action.value,
            "target": self.target.to_payload(),
            "idempotencyKey": self.idempotency_key,
            "requestId": self.request_id,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "recordedAt": self.recorded_at.isoformat(),
        }


class OperatorActionPolicy(Protocol):
    def can_execute_action(self, claims: OperatorClaims, action: OperatorActionName | str) -> bool:
        ...


class AdminRoleOperatorActionPolicy:
    """Action policy that requires an ADMIN role and is separate from read-only observability policy."""

    def can_execute_action(self, claims: OperatorClaims, action: OperatorActionName | str) -> bool:
        _coerce_action(action, "action")
        return claims.role is UserRole.ADMIN


class CancelOrderCommandHandler(Protocol):
    def cancel_order(self, command: CancelOrderCommand) -> OrderCommandResult:
        ...


class OperatorActionAuditRepository(Protocol):
    def record(self, audit_record: OperatorActionAuditRecord) -> str | None:
        ...


@dataclass(frozen=True)
class OperatorOutboxRetryRequest:
    message_kind: OutboxMessageKind | str
    message_identity: str
    reason: str
    actor: OperatorClaims
    request_id: str
    idempotency_key: str
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "message_kind",
            _coerce_outbox_message_kind(self.message_kind, "OperatorOutboxRetryRequest.message_kind"),
        )
        object.__setattr__(
            self,
            "message_identity",
            _require_text(self.message_identity, "OperatorOutboxRetryRequest.message_identity"),
        )
        object.__setattr__(self, "reason", _require_text(self.reason, "OperatorOutboxRetryRequest.reason"))
        if not isinstance(self.actor, OperatorClaims):
            raise ValueError("OperatorOutboxRetryRequest.actor must be an OperatorClaims")
        object.__setattr__(
            self,
            "request_id",
            _require_text(self.request_id, "OperatorOutboxRetryRequest.request_id"),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _require_text(self.idempotency_key, "OperatorOutboxRetryRequest.idempotency_key"),
        )
        object.__setattr__(
            self,
            "requested_at",
            _require_aware_datetime(self.requested_at, "OperatorOutboxRetryRequest.requested_at"),
        )


@dataclass(frozen=True)
class OperatorMessageReplayRequest:
    message_kind: OutboxMessageKind | str
    message_identity: str
    reason: str
    actor: OperatorClaims
    request_id: str
    idempotency_key: str
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "message_kind",
            _coerce_outbox_message_kind(self.message_kind, "OperatorMessageReplayRequest.message_kind"),
        )
        object.__setattr__(
            self,
            "message_identity",
            _require_text(self.message_identity, "OperatorMessageReplayRequest.message_identity"),
        )
        object.__setattr__(self, "reason", _require_text(self.reason, "OperatorMessageReplayRequest.reason"))
        if not isinstance(self.actor, OperatorClaims):
            raise ValueError("OperatorMessageReplayRequest.actor must be an OperatorClaims")
        object.__setattr__(
            self,
            "request_id",
            _require_text(self.request_id, "OperatorMessageReplayRequest.request_id"),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _require_text(self.idempotency_key, "OperatorMessageReplayRequest.idempotency_key"),
        )
        object.__setattr__(
            self,
            "requested_at",
            _require_aware_datetime(self.requested_at, "OperatorMessageReplayRequest.requested_at"),
        )


@dataclass(frozen=True)
class OperatorOutboxActionPortResult:
    status: OperatorOutboxActionStatus | str
    message_kind: OutboxMessageKind | str
    message_identity: str
    request_id: str
    idempotency_key: str
    summary: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.status, OperatorOutboxActionStatus):
            object.__setattr__(
                self,
                "status",
                OperatorOutboxActionStatus(
                    _require_text(str(self.status), "OperatorOutboxActionPortResult.status")
                ),
            )
        object.__setattr__(
            self,
            "message_kind",
            _coerce_outbox_message_kind(self.message_kind, "OperatorOutboxActionPortResult.message_kind"),
        )
        object.__setattr__(
            self,
            "message_identity",
            _require_text(self.message_identity, "OperatorOutboxActionPortResult.message_identity"),
        )
        object.__setattr__(
            self,
            "request_id",
            _require_text(self.request_id, "OperatorOutboxActionPortResult.request_id"),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _require_text(self.idempotency_key, "OperatorOutboxActionPortResult.idempotency_key"),
        )
        object.__setattr__(
            self,
            "summary",
            _require_text(self.summary, "OperatorOutboxActionPortResult.summary"),
        )
        object.__setattr__(
            self,
            "details",
            MappingProxyType(_to_json_safe_mapping(self.details, "OperatorOutboxActionPortResult.details")),
        )


class OperatorOutboxRetryPort(Protocol):
    def request_retry(self, request: OperatorOutboxRetryRequest) -> OperatorOutboxActionPortResult:
        ...


class OperatorMessageReplayPort(Protocol):
    def request_replay(self, request: OperatorMessageReplayRequest) -> OperatorOutboxActionPortResult:
        ...


class OperatorCancelOrderActionExecutor:
    """Runtime-neutral operator action executor for manual order cancellation."""

    def __init__(
        self,
        command_handler: CancelOrderCommandHandler,
        *,
        policy: OperatorActionPolicy | None = None,
        audit_repository: OperatorActionAuditRepository | None = None,
    ) -> None:
        self._command_handler = command_handler
        self._policy = policy or AdminRoleOperatorActionPolicy()
        self._audit_repository = audit_repository

    def cancel_order(
        self,
        *,
        actor: OperatorClaims,
        order_id: OrderId | str,
        reason: str,
        request_id: str,
        requested_at: datetime | None = None,
        idempotency_key: str | None = None,
        event_message_id: MessageId | str | None = None,
    ) -> OperatorActionResult:
        if not isinstance(actor, OperatorClaims):
            raise ValueError("OperatorCancelOrderActionExecutor.actor must be an OperatorClaims")

        requested_time = _require_aware_datetime(
            requested_at or datetime.now(UTC),
            "OperatorCancelOrderActionExecutor.requested_at",
        )
        order_id_value = _coerce_order_id(order_id)
        action_command = OperatorActionCommand(
            action=OperatorActionName.CANCEL_ORDER,
            target=OperatorActionTarget(OperatorActionTargetKind.ORDER, str(order_id_value)),
            actor=actor,
            request_id=request_id,
            idempotency_key=_cancel_order_idempotency_key(order_id_value, request_id, idempotency_key),
            reason=reason,
            requested_at=requested_time,
        )
        cancel_command = CancelOrderCommand(
            command_id=_cancel_order_command_id(order_id_value, idempotency_key),
            order_id=order_id_value,
            reason=action_command.reason,
            requested_at=requested_time,
            causation_id=action_command.request_id,
            event_message_id=_coerce_message_id(event_message_id) if event_message_id is not None else MessageId.new(),
        )
        return self._execute(action_command, cancel_command)

    def _execute(self, action_command: OperatorActionCommand, cancel_command: CancelOrderCommand) -> OperatorActionResult:
        if not self._policy.can_execute_action(action_command.actor, action_command.action):
            return self._rejected_result(
                action_command,
                cancel_command,
                summary="operator ADMIN role is required to execute cancelOrder",
                details={"errorCode": "OPERATOR_FORBIDDEN", "orderId": str(cancel_command.order_id)},
            )

        try:
            handler_result = self._command_handler.cancel_order(cancel_command)
        except OrderCommandRejected as exc:
            return self._rejected_result(
                action_command,
                cancel_command,
                summary=str(exc),
                details={
                    "rejectionReason": exc.reason.value,
                    "orderId": str(exc.order_id),
                    "reason": action_command.reason,
                },
            )

        status = _operator_status_for_order_command(handler_result.status)
        summary = f"{handler_result.status.value} for order {handler_result.order_id}."
        details: dict[str, Any] = {
            "handlerStatus": handler_result.status.value,
            "orderId": str(handler_result.order_id),
            "reason": action_command.reason,
        }
        if handler_result.duplicate_decision is not None:
            details["duplicateDecision"] = handler_result.duplicate_decision.value

        audit_id = self._record_audit(action_command, status, summary)
        return OperatorActionResult(
            status=status,
            action=action_command.action,
            target=action_command.target,
            idempotency_key=action_command.idempotency_key,
            command_id=str(cancel_command.command_id),
            message_id=str(cancel_command.event_message_id),
            audit_id=audit_id,
            summary=summary,
            details=details,
        )

    def _rejected_result(
        self,
        action_command: OperatorActionCommand,
        cancel_command: CancelOrderCommand,
        *,
        summary: str,
        details: Mapping[str, Any],
    ) -> OperatorActionResult:
        audit_id = self._record_audit(action_command, OperatorActionResultStatus.REJECTED, summary)
        return OperatorActionResult(
            status=OperatorActionResultStatus.REJECTED,
            action=action_command.action,
            target=action_command.target,
            idempotency_key=action_command.idempotency_key,
            command_id=str(cancel_command.command_id),
            message_id=str(cancel_command.event_message_id),
            audit_id=audit_id,
            summary=summary,
            details=details,
        )

    def _record_audit(
        self,
        action_command: OperatorActionCommand,
        outcome: OperatorActionResultStatus,
        reason: str,
    ) -> str | None:
        if self._audit_repository is None:
            return None

        audit_id = self._audit_repository.record(
            OperatorActionAuditRecord(
                actor=action_command.actor,
                action=action_command.action,
                target=action_command.target,
                idempotency_key=action_command.idempotency_key,
                request_id=action_command.request_id,
                outcome=outcome,
                reason=reason,
                recorded_at=action_command.requested_at,
            )
        )
        if audit_id is None:
            return None
        return _require_text(str(audit_id), "OperatorActionAuditRepository.record")


class OperatorOutboxActionExecutor:
    """Runtime-neutral operator actions for outbox retry and message replay intents."""

    def __init__(
        self,
        retry_port: OperatorOutboxRetryPort,
        replay_port: OperatorMessageReplayPort,
        *,
        policy: OperatorActionPolicy | None = None,
        audit_repository: OperatorActionAuditRepository | None = None,
    ) -> None:
        self._retry_port = retry_port
        self._replay_port = replay_port
        self._policy = policy or AdminRoleOperatorActionPolicy()
        self._audit_repository = audit_repository

    def retry_outbox_message(
        self,
        *,
        actor: OperatorClaims,
        message_kind: OutboxMessageKind | str,
        message_identity: str,
        reason: str,
        request_id: str,
        requested_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> OperatorActionResult:
        requested_time = _require_aware_datetime(
            requested_at or datetime.now(UTC),
            "OperatorOutboxActionExecutor.requested_at",
        )
        validation_error = _validate_outbox_action_input(
            message_kind=message_kind,
            message_identity=message_identity,
            reason=reason,
        )
        if validation_error is not None:
            return self._validation_rejected_result(
                action=OperatorActionName.RETRY_OUTBOX_MESSAGE,
                target_kind=OperatorActionTargetKind.OUTBOX_MESSAGE,
                actor=actor,
                message_kind=message_kind,
                message_identity=message_identity,
                reason=reason,
                request_id=request_id,
                requested_at=requested_time,
                idempotency_key=idempotency_key,
                invalid_field=validation_error[0],
                validation_message=validation_error[1],
            )

        action_command = _build_outbox_action_command(
            action=OperatorActionName.RETRY_OUTBOX_MESSAGE,
            target_kind=OperatorActionTargetKind.OUTBOX_MESSAGE,
            actor=actor,
            message_kind=message_kind,
            message_identity=message_identity,
            reason=reason,
            request_id=request_id,
            requested_at=requested_time,
            idempotency_key=idempotency_key,
        )
        retry_request = OperatorOutboxRetryRequest(
            message_kind=message_kind,
            message_identity=message_identity,
            reason=action_command.reason,
            actor=actor,
            request_id=action_command.request_id,
            idempotency_key=action_command.idempotency_key,
            requested_at=requested_time,
        )
        if not self._policy.can_execute_action(action_command.actor, action_command.action):
            return self._forbidden_result(action_command, retry_request.message_kind, retry_request.message_identity)

        return self._execute(action_command, self._retry_port.request_retry(retry_request))

    def replay_message(
        self,
        *,
        actor: OperatorClaims,
        message_kind: OutboxMessageKind | str,
        message_identity: str,
        reason: str,
        request_id: str,
        requested_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> OperatorActionResult:
        requested_time = _require_aware_datetime(
            requested_at or datetime.now(UTC),
            "OperatorOutboxActionExecutor.requested_at",
        )
        validation_error = _validate_outbox_action_input(
            message_kind=message_kind,
            message_identity=message_identity,
            reason=reason,
        )
        if validation_error is not None:
            return self._validation_rejected_result(
                action=OperatorActionName.REPLAY_MESSAGE,
                target_kind=OperatorActionTargetKind.MESSAGE,
                actor=actor,
                message_kind=message_kind,
                message_identity=message_identity,
                reason=reason,
                request_id=request_id,
                requested_at=requested_time,
                idempotency_key=idempotency_key,
                invalid_field=validation_error[0],
                validation_message=validation_error[1],
            )

        action_command = _build_outbox_action_command(
            action=OperatorActionName.REPLAY_MESSAGE,
            target_kind=OperatorActionTargetKind.MESSAGE,
            actor=actor,
            message_kind=message_kind,
            message_identity=message_identity,
            reason=reason,
            request_id=request_id,
            requested_at=requested_time,
            idempotency_key=idempotency_key,
        )
        replay_request = OperatorMessageReplayRequest(
            message_kind=message_kind,
            message_identity=message_identity,
            reason=action_command.reason,
            actor=actor,
            request_id=action_command.request_id,
            idempotency_key=action_command.idempotency_key,
            requested_at=requested_time,
        )
        if not self._policy.can_execute_action(action_command.actor, action_command.action):
            return self._forbidden_result(action_command, replay_request.message_kind, replay_request.message_identity)

        return self._execute(
            action_command,
            self._replay_port.request_replay(replay_request),
            idempotency_records_deleted=False,
        )

    def _execute(
        self,
        action_command: OperatorActionCommand,
        port_result: OperatorOutboxActionPortResult,
        *,
        idempotency_records_deleted: bool | None = None,
    ) -> OperatorActionResult:
        status = _operator_status_for_outbox_action(port_result.status)
        details: dict[str, Any] = {
            "outboxActionStatus": port_result.status.value,
            "messageKind": port_result.message_kind.value,
            "messageIdentity": port_result.message_identity,
            "requestId": port_result.request_id,
            "actor": _operator_actor_payload(action_command.actor),
            "reason": action_command.reason,
        }
        if port_result.status is OperatorOutboxActionStatus.DUPLICATE_IGNORED:
            details["duplicateDecision"] = OperatorOutboxActionStatus.DUPLICATE_IGNORED.value
        details.update(port_result.details)
        if idempotency_records_deleted is not None:
            details["idempotencyRecordsDeleted"] = idempotency_records_deleted

        audit_id = self._record_audit(action_command, status, action_command.reason)
        return OperatorActionResult(
            status=status,
            action=action_command.action,
            target=action_command.target,
            idempotency_key=action_command.idempotency_key,
            message_id=port_result.message_identity,
            audit_id=audit_id,
            summary=port_result.summary,
            details=details,
        )

    def _forbidden_result(
        self,
        action_command: OperatorActionCommand,
        message_kind: OutboxMessageKind,
        message_identity: str,
    ) -> OperatorActionResult:
        return self._rejected_result(
            action_command,
            summary=f"operator ADMIN role is required to execute {action_command.action.value}",
            details={
                "errorCode": "OPERATOR_FORBIDDEN",
                "messageKind": message_kind.value,
                "messageIdentity": message_identity,
                "requestId": action_command.request_id,
                "actor": _operator_actor_payload(action_command.actor),
                "reason": action_command.reason,
            },
        )

    def _validation_rejected_result(
        self,
        *,
        action: OperatorActionName,
        target_kind: OperatorActionTargetKind,
        actor: OperatorClaims,
        message_kind: OutboxMessageKind | str,
        message_identity: str,
        reason: str,
        request_id: str,
        requested_at: datetime,
        idempotency_key: str | None,
        invalid_field: str,
        validation_message: str,
    ) -> OperatorActionResult:
        target = OperatorActionTarget(target_kind, _safe_target_id(message_identity))
        summary = f"Invalid operator outbox action request: {validation_message}."
        safe_request_id = _safe_text(request_id) or "<missing-request-id>"
        safe_reason = _safe_text(reason) or summary
        safe_message_kind = _safe_text(_safe_message_kind_text(message_kind)) or "<invalid-kind>"
        safe_idempotency_key = _safe_text(idempotency_key) or _outbox_action_idempotency_key(
            action,
            safe_message_kind,
            target.id,
            safe_request_id,
            None,
        )
        details = {
            "errorCode": "OPERATOR_ACTION_VALIDATION_FAILED",
            "invalidField": invalid_field,
            "validationError": validation_message,
            "messageKind": safe_message_kind,
            "messageIdentity": message_identity,
            "requestId": safe_request_id,
            "actor": _operator_actor_payload(actor) if isinstance(actor, OperatorClaims) else None,
            "reason": reason,
        }
        audit_id = self._record_audit(
            OperatorActionCommand(
                action=action,
                target=target,
                actor=actor,
                request_id=safe_request_id,
                idempotency_key=safe_idempotency_key,
                reason=safe_reason,
                requested_at=requested_at,
                parameters={"messageKind": safe_message_kind},
            ),
            OperatorActionResultStatus.REJECTED,
            safe_reason,
        )
        return OperatorActionResult(
            status=OperatorActionResultStatus.REJECTED,
            action=action,
            target=target,
            idempotency_key=safe_idempotency_key,
            message_id=_safe_text(message_identity),
            audit_id=audit_id,
            summary=summary,
            details=details,
        )

    def _rejected_result(
        self,
        action_command: OperatorActionCommand,
        *,
        summary: str,
        details: Mapping[str, Any],
    ) -> OperatorActionResult:
        audit_id = self._record_audit(action_command, OperatorActionResultStatus.REJECTED, action_command.reason)
        return OperatorActionResult(
            status=OperatorActionResultStatus.REJECTED,
            action=action_command.action,
            target=action_command.target,
            idempotency_key=action_command.idempotency_key,
            message_id=action_command.target.id,
            audit_id=audit_id,
            summary=summary,
            details=details,
        )

    def _record_audit(
        self,
        action_command: OperatorActionCommand,
        outcome: OperatorActionResultStatus,
        reason: str,
    ) -> str | None:
        if self._audit_repository is None:
            return None

        audit_id = self._audit_repository.record(
            OperatorActionAuditRecord(
                actor=action_command.actor,
                action=action_command.action,
                target=action_command.target,
                idempotency_key=action_command.idempotency_key,
                request_id=action_command.request_id,
                outcome=outcome,
                reason=reason,
                recorded_at=action_command.requested_at,
            )
        )
        if audit_id is None:
            return None
        return _require_text(str(audit_id), "OperatorActionAuditRepository.record")


def _validate_action_target(action: OperatorActionName, target: OperatorActionTarget) -> None:
    expected = {
        OperatorActionName.CANCEL_ORDER: OperatorActionTargetKind.ORDER,
        OperatorActionName.RETRY_OUTBOX_MESSAGE: OperatorActionTargetKind.OUTBOX_MESSAGE,
        OperatorActionName.REPLAY_MESSAGE: OperatorActionTargetKind.MESSAGE,
    }[action]
    if target.kind is not expected:
        raise ValueError(f"{action.value} targets must be {expected.value}")


def _coerce_action(value: OperatorActionName | str, field_name: str) -> OperatorActionName:
    if isinstance(value, OperatorActionName):
        return value
    return OperatorActionName(_require_text(str(value), field_name))


def _coerce_order_id(value: OrderId | str) -> OrderId:
    return value if isinstance(value, OrderId) else OrderId(value)


def _coerce_message_id(value: MessageId | str) -> MessageId:
    return value if isinstance(value, MessageId) else MessageId(value)


def _coerce_outbox_message_kind(value: OutboxMessageKind | str, field_name: str) -> OutboxMessageKind:
    if isinstance(value, OutboxMessageKind):
        return value
    return OutboxMessageKind(_require_text(str(value), field_name))


def _cancel_order_idempotency_key(order_id: OrderId, request_id: str, idempotency_key: str | None) -> str:
    if idempotency_key is not None:
        return _require_text(idempotency_key, "OperatorCancelOrderActionExecutor.idempotency_key")
    return f"operator:cancelOrder:{order_id}:{_require_text(request_id, 'OperatorCancelOrderActionExecutor.request_id')}"


def _cancel_order_command_id(order_id: OrderId, idempotency_key: str | None) -> CommandId:
    if idempotency_key is not None:
        return CommandId(_require_text(idempotency_key, "OperatorCancelOrderActionExecutor.idempotency_key"))
    return CommandId.for_order_action(order_id, CheckoutCommandName.CANCEL_ORDER)


def _operator_status_for_order_command(status: OrderCommandStatus) -> OperatorActionResultStatus:
    if status is OrderCommandStatus.DUPLICATE_IGNORED:
        return OperatorActionResultStatus.DUPLICATE
    return OperatorActionResultStatus.ACCEPTED


def _operator_status_for_outbox_action(status: OperatorOutboxActionStatus) -> OperatorActionResultStatus:
    if status is OperatorOutboxActionStatus.DUPLICATE_IGNORED:
        return OperatorActionResultStatus.DUPLICATE
    if status is OperatorOutboxActionStatus.REJECTED:
        return OperatorActionResultStatus.REJECTED
    return OperatorActionResultStatus.ACCEPTED


def _build_outbox_action_command(
    *,
    action: OperatorActionName,
    target_kind: OperatorActionTargetKind,
    actor: OperatorClaims,
    message_kind: OutboxMessageKind | str,
    message_identity: str,
    reason: str,
    request_id: str,
    requested_at: datetime,
    idempotency_key: str | None,
) -> OperatorActionCommand:
    kind = _coerce_outbox_message_kind(message_kind, "message_kind")
    return OperatorActionCommand(
        action=action,
        target=OperatorActionTarget(target_kind, _require_text(message_identity, "message_identity")),
        actor=actor,
        request_id=request_id,
        idempotency_key=_outbox_action_idempotency_key(action, kind.value, message_identity, request_id, idempotency_key),
        reason=reason,
        requested_at=requested_at,
        parameters={"messageKind": kind.value},
    )


def _outbox_action_idempotency_key(
    action: OperatorActionName,
    message_kind: str,
    message_identity: str,
    request_id: str,
    idempotency_key: str | None,
) -> str:
    if idempotency_key is not None:
        return _require_text(idempotency_key, "OperatorOutboxActionExecutor.idempotency_key")
    return (
        f"operator:{action.value}:{_require_text(message_kind, 'message_kind')}:"
        f"{_require_text(message_identity, 'message_identity')}:"
        f"{_require_text(request_id, 'OperatorOutboxActionExecutor.request_id')}"
    )


def _validate_outbox_action_input(
    *,
    message_kind: OutboxMessageKind | str,
    message_identity: str,
    reason: str,
) -> tuple[str, str] | None:
    try:
        _coerce_outbox_message_kind(message_kind, "messageKind")
    except ValueError as exc:
        return ("messageKind", str(exc))
    if _safe_text(message_identity) is None:
        return ("messageIdentity", "messageIdentity must be a non-empty string")
    if _safe_text(reason) is None:
        return ("reason", "reason must be a non-empty string")
    return None


def _operator_actor_payload(actor: OperatorClaims) -> dict[str, JsonValue]:
    return {
        "userId": actor.user_id,
        "role": actor.role.value if isinstance(actor.role, UserRole) else actor.role,
        "scopes": list(actor.scopes),
    }


def _safe_message_kind_text(value: OutboxMessageKind | str) -> str:
    return value.value if isinstance(value, OutboxMessageKind) else str(value)


def _safe_target_id(value: str) -> str:
    return _safe_text(value) or "<empty>"


def _safe_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _to_json_safe_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    output: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        try:
            output[key] = _to_json_safe(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must contain only JSON-safe values") from exc
    return output


def _to_json_safe(value: Any) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON payload floats must be finite")
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _require_aware_datetime(value, "JSON payload datetime").isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return _to_json_safe_mapping(value, "JSON payload mapping")
    if isinstance(value, tuple | list):
        return [_to_json_safe(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _to_json_safe(getattr(value, field.name)) for field in fields(value)}
    raise TypeError(f"{type(value).__name__} is not JSON payload serializable")


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


__all__ = [
    "AdminRoleOperatorActionPolicy",
    "CancelOrderCommandHandler",
    "OperatorActionAuditRepository",
    "OperatorActionAuditRecord",
    "OperatorActionCommand",
    "OperatorActionName",
    "OperatorActionPolicy",
    "OperatorActionResult",
    "OperatorActionResultStatus",
    "OperatorActionTarget",
    "OperatorActionTargetKind",
    "OperatorCancelOrderActionExecutor",
    "OperatorMessageReplayPort",
    "OperatorMessageReplayRequest",
    "OperatorOutboxActionExecutor",
    "OperatorOutboxActionPortResult",
    "OperatorOutboxActionStatus",
    "OperatorOutboxRetryPort",
    "OperatorOutboxRetryRequest",
]

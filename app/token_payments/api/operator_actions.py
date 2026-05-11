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
from token_payments.shared.domain import CheckoutCommandName, CommandId, MessageId, OrderId

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
]

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
    "OperatorActionAuditRecord",
    "OperatorActionCommand",
    "OperatorActionName",
    "OperatorActionPolicy",
    "OperatorActionResult",
    "OperatorActionResultStatus",
    "OperatorActionTarget",
    "OperatorActionTargetKind",
]

"""Framework-free runtime contracts for API and worker composition."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable
from uuid import UUID


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


@runtime_checkable
class Clock(Protocol):
    """Clock port used by runtime wiring and tests."""

    def now(self) -> datetime:
        """Return the current timezone-aware time."""


@runtime_checkable
class IdGenerator(Protocol):
    """ID generator port used by runtime/API adapters."""

    def new_id(self) -> str:
        """Return a new externally safe identifier string."""


@dataclass(frozen=True)
class WorkerLoopOptions:
    """Shared worker loop timing and batch controls."""

    batch_size: int = 100
    poll_interval_seconds: float = 1.0
    receipt_poll_interval_seconds: float = 5.0

    def __post_init__(self) -> None:
        if isinstance(self.batch_size, bool) or not isinstance(self.batch_size, int) or self.batch_size <= 0:
            raise ValueError("WorkerLoopOptions.batch_size must be a positive integer")
        object.__setattr__(
            self,
            "poll_interval_seconds",
            _require_positive_float(
                self.poll_interval_seconds,
                "WorkerLoopOptions.poll_interval_seconds",
            ),
        )
        object.__setattr__(
            self,
            "receipt_poll_interval_seconds",
            _require_positive_float(
                self.receipt_poll_interval_seconds,
                "WorkerLoopOptions.receipt_poll_interval_seconds",
            ),
        )


class HealthState(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class HealthStatus:
    """JSON-safe health value for runtime probes and command output."""

    component: str
    state: HealthState
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "component", _require_text(self.component, "HealthStatus.component"))
        if not isinstance(self.state, HealthState):
            object.__setattr__(self, "state", HealthState(str(self.state)))
        object.__setattr__(self, "checked_at", _require_aware_datetime(self.checked_at, "HealthStatus.checked_at"))
        if not isinstance(self.details, Mapping):
            raise ValueError("HealthStatus.details must be a mapping")
        object.__setattr__(self, "details", MappingProxyType(_to_json_safe_mapping(self.details)))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "component": self.component,
            "state": self.state.value,
            "checkedAt": self.checked_at.isoformat(),
            "details": dict(self.details),
        }


class CommandDispatchStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class CommandDispatchResult:
    """Result returned by runtime command dispatch without binding to a CLI framework."""

    command: str
    status: CommandDispatchStatus
    summary: str
    exit_code: int
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _require_text(self.command, "CommandDispatchResult.command"))
        object.__setattr__(self, "summary", _require_text(self.summary, "CommandDispatchResult.summary"))
        if not isinstance(self.status, CommandDispatchStatus):
            object.__setattr__(self, "status", CommandDispatchStatus(str(self.status)))
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int) or self.exit_code < 0:
            raise ValueError("CommandDispatchResult.exit_code must be a non-negative integer")
        if not isinstance(self.details, Mapping):
            raise ValueError("CommandDispatchResult.details must be a mapping")
        object.__setattr__(self, "details", MappingProxyType(_to_json_safe_mapping(self.details)))

    @classmethod
    def succeeded(
        cls,
        *,
        command: str,
        summary: str,
        details: Mapping[str, Any] | None = None,
    ) -> "CommandDispatchResult":
        return cls(
            command=command,
            status=CommandDispatchStatus.SUCCEEDED,
            summary=summary,
            exit_code=0,
            details=details or {},
        )

    @classmethod
    def failed(
        cls,
        *,
        command: str,
        summary: str,
        exit_code: int = 1,
        details: Mapping[str, Any] | None = None,
    ) -> "CommandDispatchResult":
        return cls(
            command=command,
            status=CommandDispatchStatus.FAILED,
            summary=summary,
            exit_code=exit_code,
            details=details or {},
        )

    @property
    def success(self) -> bool:
        return self.status is CommandDispatchStatus.SUCCEEDED and self.exit_code == 0

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "command": self.command,
            "status": self.status.value,
            "summary": self.summary,
            "exitCode": self.exit_code,
            "details": dict(self.details),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)


@runtime_checkable
class RuntimeContainer(Protocol):
    """Composition root contract used by CLI, API, and worker entrypoints."""

    @property
    def config(self) -> Any:
        """Return the runtime configuration object."""

    def health(self) -> HealthStatus:
        """Return runtime health without touching live infrastructure."""

    def dispatch_command(self, command: str) -> CommandDispatchResult:
        """Dispatch a runtime command without starting services implicitly."""


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _require_positive_float(value: float | int, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{field_name} must be a positive number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return normalized


def _to_json_safe_mapping(value: Mapping[str, Any]) -> dict[str, JsonValue]:
    return {key: _to_json_safe(item) for key, item in value.items()}


def _to_json_safe(value: Any) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON floats must be finite")
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _require_aware_datetime(value, "JSON datetime").isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, HealthStatus):
        return value.to_dict()
    if isinstance(value, Mapping):
        output: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON mapping keys must be strings")
            output[key] = _to_json_safe(item)
        return output
    if isinstance(value, tuple | list):
        return [_to_json_safe(item) for item in value]
    raise TypeError(f"{type(value).__name__} is not JSON serializable")

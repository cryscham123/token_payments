"""Deterministic smoke scenario contracts for integration readiness."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import math
from types import MappingProxyType
from typing import Any, Callable, Mapping
from uuid import UUID


SMOKE_CONTRACT = "CommandDispatchResult.details.smoke"
UNKNOWN_SMOKE_SCENARIO_ERROR = "UNKNOWN_SMOKE_SCENARIO"
AVAILABLE_SMOKE_SCENARIOS = ("happy-path-checkout", "compensation-checkout", "compose-readiness")

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
SmokeRunner = Callable[[], "SmokeScenarioResult"]


class SmokeStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class SmokeResult:
    status: SmokeStatus | str
    summary: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _coerce_status(self.status))
        object.__setattr__(self, "summary", _require_text(self.summary, "SmokeResult.summary"))
        object.__setattr__(self, "details", MappingProxyType(_to_json_safe_mapping(self.details)))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "status": self.status.value,
            "summary": self.summary,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class SmokeStep:
    name: str
    result: SmokeResult

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_text(self.name, "SmokeStep.name"))
        if not isinstance(self.result, SmokeResult):
            raise ValueError("SmokeStep.result must be a SmokeResult")

    def to_dict(self) -> dict[str, JsonValue]:
        return {"name": self.name} | self.result.to_dict()


@dataclass(frozen=True)
class SmokeScenarioResult:
    scenario: str
    result: SmokeResult
    steps: tuple[SmokeStep, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario", _require_text(self.scenario, "SmokeScenarioResult.scenario"))
        if not isinstance(self.result, SmokeResult):
            raise ValueError("SmokeScenarioResult.result must be a SmokeResult")
        object.__setattr__(self, "steps", tuple(self.steps))
        if not all(isinstance(step, SmokeStep) for step in self.steps):
            raise ValueError("SmokeScenarioResult.steps must contain only SmokeStep values")
        object.__setattr__(self, "details", MappingProxyType(_to_json_safe_mapping(self.details)))

    @property
    def status(self) -> SmokeStatus:
        return self.result.status

    @property
    def summary(self) -> str:
        return self.result.summary

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "contract": SMOKE_CONTRACT,
            "scenario": self.scenario,
            "status": self.status.value,
            "summary": self.summary,
            "steps": [step.to_dict() for step in self.steps],
            "details": dict(self.details),
        }


class UnknownSmokeScenario(ValueError):
    """Raised when a smoke scenario selector is not known."""

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        super().__init__(f"unknown smoke scenario: {scenario}")

    def to_error(self) -> dict[str, JsonValue]:
        return {
            "code": UNKNOWN_SMOKE_SCENARIO_ERROR,
            "scenario": self.scenario,
            "availableScenarios": list(AVAILABLE_SMOKE_SCENARIOS),
        }


_SMOKE_RUNNERS: Mapping[str, SmokeRunner] = MappingProxyType({})


def describe_smoke_registry() -> dict[str, JsonValue]:
    return {
        "contract": SMOKE_CONTRACT,
        "availableScenarios": list(AVAILABLE_SMOKE_SCENARIOS),
        "runnerCount": len(_SMOKE_RUNNERS),
    }


def run_smoke_scenario(scenario: str) -> SmokeScenarioResult:
    normalized = _normalize_scenario(scenario)
    if normalized not in AVAILABLE_SMOKE_SCENARIOS:
        raise UnknownSmokeScenario(normalized)

    runner = _SMOKE_RUNNERS.get(normalized)
    if runner is None:
        return SmokeScenarioResult(
            scenario=normalized,
            result=SmokeResult(
                status=SmokeStatus.SKIPPED,
                summary="smoke scenario runner is reserved but not implemented",
            ),
            details={
                "runnerImplemented": False,
                "availableScenarios": AVAILABLE_SMOKE_SCENARIOS,
            },
        )
    return runner()


def _normalize_scenario(scenario: str) -> str:
    return _require_text(scenario, "scenario").lower()


def _coerce_status(value: SmokeStatus | str) -> SmokeStatus:
    if isinstance(value, SmokeStatus):
        return value
    try:
        return SmokeStatus(str(value))
    except ValueError as exc:
        raise ValueError("SmokeResult.status must be one of passed, failed, skipped") from exc


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _to_json_safe_mapping(value: Mapping[str, Any]) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError("details must be a mapping")
    output: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("JSON mapping keys must be strings")
        output[key] = _to_json_safe(item)
    return output


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
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("JSON datetime must be timezone-aware")
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return _to_json_safe_mapping(value)
    if isinstance(value, tuple | list):
        return [_to_json_safe(item) for item in value]
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "AVAILABLE_SMOKE_SCENARIOS",
    "SMOKE_CONTRACT",
    "UNKNOWN_SMOKE_SCENARIO_ERROR",
    "JsonValue",
    "SmokeResult",
    "SmokeScenarioResult",
    "SmokeStatus",
    "SmokeStep",
    "UnknownSmokeScenario",
    "describe_smoke_registry",
    "run_smoke_scenario",
]

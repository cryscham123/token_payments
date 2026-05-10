"""Environment-backed runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping, Self

from .contracts import WorkerLoopOptions


@dataclass(frozen=True)
class RuntimeConfig:
    """API and worker runtime settings parsed from environment variables."""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    request_timeout_seconds: float = 30.0
    worker_batch_size: int = 100
    worker_poll_interval_seconds: float = 1.0
    receipt_poll_interval_seconds: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "api_host", _require_text(self.api_host, "RUNTIME_API_HOST"))
        object.__setattr__(self, "api_port", _require_port(self.api_port, "RUNTIME_API_PORT"))
        object.__setattr__(
            self,
            "request_timeout_seconds",
            _require_positive_number(self.request_timeout_seconds, "RUNTIME_REQUEST_TIMEOUT_SECONDS"),
        )
        object.__setattr__(
            self,
            "worker_batch_size",
            _require_positive_int(self.worker_batch_size, "RUNTIME_WORKER_BATCH_SIZE"),
        )
        object.__setattr__(
            self,
            "worker_poll_interval_seconds",
            _require_positive_number(
                self.worker_poll_interval_seconds,
                "RUNTIME_WORKER_POLL_INTERVAL_SECONDS",
            ),
        )
        object.__setattr__(
            self,
            "receipt_poll_interval_seconds",
            _require_positive_number(
                self.receipt_poll_interval_seconds,
                "RUNTIME_RECEIPT_POLL_INTERVAL_SECONDS",
            ),
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        source = os.environ if env is None else env
        return cls(
            api_host=source.get("RUNTIME_API_HOST", cls.api_host),
            api_port=_parse_int(source, "RUNTIME_API_PORT", cls.api_port),
            request_timeout_seconds=_parse_float(
                source,
                "RUNTIME_REQUEST_TIMEOUT_SECONDS",
                cls.request_timeout_seconds,
            ),
            worker_batch_size=_parse_int(source, "RUNTIME_WORKER_BATCH_SIZE", cls.worker_batch_size),
            worker_poll_interval_seconds=_parse_float(
                source,
                "RUNTIME_WORKER_POLL_INTERVAL_SECONDS",
                cls.worker_poll_interval_seconds,
            ),
            receipt_poll_interval_seconds=_parse_float(
                source,
                "RUNTIME_RECEIPT_POLL_INTERVAL_SECONDS",
                cls.receipt_poll_interval_seconds,
            ),
        )

    def worker_loop_options(self) -> WorkerLoopOptions:
        return WorkerLoopOptions(
            batch_size=self.worker_batch_size,
            poll_interval_seconds=self.worker_poll_interval_seconds,
            receipt_poll_interval_seconds=self.receipt_poll_interval_seconds,
        )

    def to_dict(self) -> dict[str, str | int | float]:
        return {
            "apiHost": self.api_host,
            "apiPort": self.api_port,
            "requestTimeoutSeconds": self.request_timeout_seconds,
            "workerBatchSize": self.worker_batch_size,
            "workerPollIntervalSeconds": self.worker_poll_interval_seconds,
            "receiptPollIntervalSeconds": self.receipt_poll_interval_seconds,
        }


def _parse_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _parse_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number") from exc


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_port(value: int, field_name: str) -> int:
    port = _require_positive_int(value, field_name)
    if port > 65535:
        raise ValueError(f"{field_name} must be between 1 and 65535")
    return port


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_positive_number(value: float | int, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or float(value) <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return float(value)

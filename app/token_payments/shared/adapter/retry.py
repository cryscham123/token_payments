"""Retry/backoff configuration shared by infrastructure adapters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryBackoffConfig:
    max_attempts: int = 5
    initial_delay_seconds: float = 0.5
    multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    jitter_ratio: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int) or self.max_attempts <= 0:
            raise ValueError("RetryBackoffConfig.max_attempts must be a positive integer")
        _validate_positive_number(self.initial_delay_seconds, "RetryBackoffConfig.initial_delay_seconds")
        _validate_positive_number(self.multiplier, "RetryBackoffConfig.multiplier")
        _validate_positive_number(self.max_delay_seconds, "RetryBackoffConfig.max_delay_seconds")
        if self.multiplier < 1:
            raise ValueError("RetryBackoffConfig.multiplier must be greater than or equal to 1")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("RetryBackoffConfig.max_delay_seconds must not be less than initial_delay_seconds")
        if (
            isinstance(self.jitter_ratio, bool)
            or not isinstance(self.jitter_ratio, int | float)
            or self.jitter_ratio < 0
            or self.jitter_ratio > 1
        ):
            raise ValueError("RetryBackoffConfig.jitter_ratio must be between 0 and 1")

        object.__setattr__(self, "initial_delay_seconds", float(self.initial_delay_seconds))
        object.__setattr__(self, "multiplier", float(self.multiplier))
        object.__setattr__(self, "max_delay_seconds", float(self.max_delay_seconds))
        object.__setattr__(self, "jitter_ratio", float(self.jitter_ratio))

    def delay_for_attempt(self, attempt: int) -> float:
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt <= 0:
            raise ValueError("attempt must be a positive 1-based integer")
        delay = self.initial_delay_seconds * (self.multiplier ** (attempt - 1))
        return min(delay, self.max_delay_seconds)

    def should_retry(self, failure_count: int) -> bool:
        if isinstance(failure_count, bool) or not isinstance(failure_count, int) or failure_count < 0:
            raise ValueError("failure_count must be a non-negative integer")
        return failure_count < self.max_attempts


def _validate_positive_number(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ValueError(f"{field_name} must be a positive number")

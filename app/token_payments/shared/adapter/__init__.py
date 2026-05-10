"""Shared adapter boundary contracts.

This package is intentionally limited to infrastructure-facing contracts.
Domain and application layers must not import from it.
"""

from .messaging import DEFAULT_COMMAND_TOPICS, DEFAULT_EVENT_TOPICS, JsonMessageSerializer, MessageTopicResolver
from .outbox_relay import OutboxRelay, OutboxRelayFailure, OutboxRelayRepository, OutboxRelayResult
from .retry import RetryBackoffConfig
from .transactions import TransactionBoundary, TransactionalSession

__all__ = [
    "DEFAULT_COMMAND_TOPICS",
    "DEFAULT_EVENT_TOPICS",
    "JsonMessageSerializer",
    "MessageTopicResolver",
    "OutboxRelay",
    "OutboxRelayFailure",
    "OutboxRelayRepository",
    "OutboxRelayResult",
    "RetryBackoffConfig",
    "TransactionBoundary",
    "TransactionalSession",
]

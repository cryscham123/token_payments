"""PostgreSQL repository adapters for shared outbox/idempotency tables."""

from .idempotency import PostgresProcessedCommandRepository, PostgresProcessedMessageRepository
from .outbox import PostgresOutboxMessageRepository
from .protocols import PostgresConnection

__all__ = [
    "PostgresConnection",
    "PostgresOutboxMessageRepository",
    "PostgresProcessedCommandRepository",
    "PostgresProcessedMessageRepository",
]


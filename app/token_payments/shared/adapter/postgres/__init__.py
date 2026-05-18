"""PostgreSQL repository adapters for shared outbox/idempotency tables."""

from .idempotency import PostgresProcessedCommandRepository, PostgresProcessedMessageRepository
from .outbox import PostgresOutboxMessageRepository
from .protocols import PostgresConnection
from .schema import POSTGRES_SCHEMA_COMPATIBILITY_SQL, ensure_postgres_schema_compatibility

__all__ = [
    "PostgresConnection",
    "PostgresOutboxMessageRepository",
    "PostgresProcessedCommandRepository",
    "PostgresProcessedMessageRepository",
    "POSTGRES_SCHEMA_COMPATIBILITY_SQL",
    "ensure_postgres_schema_compatibility",
]

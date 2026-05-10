"""Store approval adapter layer."""

from .postgres import PostgresOrderDetailRepository, PostgresStoreRepository

__all__ = [
    "PostgresOrderDetailRepository",
    "PostgresStoreRepository",
]

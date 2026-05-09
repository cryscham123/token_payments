"""Application port contracts for the store approval bounded context."""

from __future__ import annotations

from typing import Protocol

from token_payments.contexts.store_approval.domain import OrderDetail, Store
from token_payments.shared.domain import CommandId, OrderId, OutboxMessage, ProcessedCommand, StoreId


class StoreRepository(Protocol):
    def get(self, store_id: StoreId) -> Store | None:
        ...


class OrderDetailRepository(Protocol):
    def get(self, order_id: OrderId) -> OrderDetail | None:
        ...

    def save(self, order_detail: OrderDetail) -> None:
        ...


class ProcessedCommandRepository(Protocol):
    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        ...

    def record(self, processed_command: ProcessedCommand) -> None:
        ...


class OutboxMessageRepository(Protocol):
    def save(self, message: OutboxMessage) -> None:
        ...

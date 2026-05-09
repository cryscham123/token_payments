"""Application port contracts for the inventory bounded context."""

from __future__ import annotations

from typing import Protocol

from token_payments.contexts.inventory.domain import ProductInventory
from token_payments.shared.domain import CommandId, OutboxMessage, ProcessedCommand, ProductId, StoreId


class InventoryRepository(Protocol):
    def get(self, product_id: ProductId, store_id: StoreId) -> ProductInventory | None:
        ...

    def save(self, inventory: ProductInventory) -> None:
        ...


class ProcessedCommandRepository(Protocol):
    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        ...

    def record(self, processed_command: ProcessedCommand) -> None:
        ...


class OutboxMessageRepository(Protocol):
    def save(self, message: OutboxMessage) -> None:
        ...

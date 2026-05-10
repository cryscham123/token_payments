"""Application port contracts for the order bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from token_payments.contexts.order.domain import Customer, Order, Store
from token_payments.shared.domain import Crypto, OutboxMessage, StoreId, UserId

from .commands import CreateOrderCommand


@dataclass(frozen=True)
class OrderCreationResult:
    order: Order
    total_amount: Crypto
    outbox_message: OutboxMessage


class OrderUseCase(Protocol):
    def createOrder(self, command: CreateOrderCommand) -> OrderCreationResult:
        ...


class CustomerRepository(Protocol):
    def get_by_user_id(self, user_id: UserId) -> Customer | None:
        ...


class StoreRepository(Protocol):
    def get(self, store_id: StoreId) -> Store | None:
        ...


class OrderRepository(Protocol):
    def save(self, order: Order) -> None:
        ...


class OutboxMessageRepository(Protocol):
    def save(self, message: OutboxMessage) -> None:
        ...

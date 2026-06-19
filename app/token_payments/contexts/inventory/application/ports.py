"""Application port contracts for the inventory bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from token_payments.contexts.inventory.domain import InventorySaleStatus, ProductInventory
from token_payments.shared.domain import CommandId, OutboxMessage, ProcessedCommand, ProductId, StoreId, UserId


@dataclass(frozen=True)
class InventorySnapshot:
    store_id: StoreId
    product_id: ProductId
    available_stock: int
    reserved_stock: int
    confirmed_stock: int
    total_stock: int
    sale_status: InventorySaleStatus | str
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.store_id, StoreId):
            raise ValueError("InventorySnapshot.store_id must be a StoreId")
        if not isinstance(self.product_id, ProductId):
            raise ValueError("InventorySnapshot.product_id must be a ProductId")
        object.__setattr__(self, "available_stock", _non_negative_int(self.available_stock, "available_stock"))
        object.__setattr__(self, "reserved_stock", _non_negative_int(self.reserved_stock, "reserved_stock"))
        object.__setattr__(self, "confirmed_stock", _non_negative_int(self.confirmed_stock, "confirmed_stock"))
        object.__setattr__(self, "total_stock", _non_negative_int(self.total_stock, "total_stock"))
        object.__setattr__(self, "sale_status", _sale_status(self.sale_status))
        object.__setattr__(self, "updated_at", _aware_datetime(self.updated_at, "updated_at"))


@dataclass(frozen=True)
class InventoryAuditRecord:
    actor_user_id: UserId
    actor_role: str
    store_id: StoreId
    product_id: ProductId
    action: str
    before_available_stock: int
    before_reserved_stock: int
    before_total_stock: int
    before_sale_status: InventorySaleStatus | str
    after_available_stock: int
    after_reserved_stock: int
    after_total_stock: int
    after_sale_status: InventorySaleStatus | str
    reason: str
    request_id: str
    idempotency_key: str
    recorded_at: datetime
    actor_store_role: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.actor_user_id, UserId):
            raise ValueError("InventoryAuditRecord.actor_user_id must be a UserId")
        object.__setattr__(self, "actor_role", _text(str(self.actor_role), "actor_role"))
        if not isinstance(self.store_id, StoreId):
            raise ValueError("InventoryAuditRecord.store_id must be a StoreId")
        if not isinstance(self.product_id, ProductId):
            raise ValueError("InventoryAuditRecord.product_id must be a ProductId")
        object.__setattr__(self, "action", _text(self.action, "action"))
        for field_name in (
            "before_available_stock",
            "before_reserved_stock",
            "before_total_stock",
            "after_available_stock",
            "after_reserved_stock",
            "after_total_stock",
        ):
            object.__setattr__(self, field_name, _non_negative_int(getattr(self, field_name), field_name))
        object.__setattr__(self, "before_sale_status", _sale_status(self.before_sale_status))
        object.__setattr__(self, "after_sale_status", _sale_status(self.after_sale_status))
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        object.__setattr__(self, "idempotency_key", _text(self.idempotency_key, "idempotency_key"))
        object.__setattr__(self, "recorded_at", _aware_datetime(self.recorded_at, "recorded_at"))
        if self.actor_store_role is not None:
            object.__setattr__(self, "actor_store_role", _text(self.actor_store_role, "actor_store_role"))


class InventoryRepository(Protocol):
    def get(self, product_id: ProductId, store_id: StoreId, public_variant_id: str | None = None) -> ProductInventory | None:
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


class InventoryQueryRepository(Protocol):
    def list_inventory(self, store_id: StoreId | None = None) -> tuple[InventorySnapshot, ...]:
        ...

    def list_inventory_for_owner(
        self,
        owner_user_id: UserId,
        store_id: StoreId | None = None,
    ) -> tuple[InventorySnapshot, ...]:
        ...

    def owner_for_store(self, store_id: StoreId) -> UserId | None:
        ...

    def store_role_for_user(self, store_id: StoreId, user_id: UserId) -> str | None:
        ...


class InventoryAuditRepository(Protocol):
    def record(self, audit_record: InventoryAuditRecord) -> str | None:
        ...


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _sale_status(value: InventorySaleStatus | str) -> InventorySaleStatus:
    if isinstance(value, InventorySaleStatus):
        return value
    return InventorySaleStatus(_text(str(value), "sale_status"))

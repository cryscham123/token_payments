"""Store catalog application port contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping, Protocol

from token_payments.contexts.auth.domain import User
from token_payments.contexts.store_catalog.domain import (
    PublicProductId,
    PublicStoreId,
    StoreMembership,
    StoreMembershipRole,
    StoreProduct,
    StoreProfile,
)
from token_payments.shared.domain import ProductId, StoreId, UserId, WalletAddress


class StoreCatalogCommandStatus(StrEnum):
    COMPLETED = "completed"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    REJECTED = "rejected"


@dataclass(frozen=True)
class StoreCatalogCommandResult:
    status: StoreCatalogCommandStatus
    payload: Mapping[str, Any]
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, StoreCatalogCommandStatus):
            object.__setattr__(self, "status", StoreCatalogCommandStatus(str(self.status)))
        if not isinstance(self.payload, Mapping):
            raise ValueError("StoreCatalogCommandResult.payload must be a mapping")
        if self.rejection_reason is not None:
            object.__setattr__(self, "rejection_reason", _text(self.rejection_reason, "rejection_reason"))


@dataclass(frozen=True)
class CatalogIdempotencyRecord:
    handler: str
    idempotency_key: str
    payload_hash: str
    response_payload: Mapping[str, Any]
    recorded_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "handler", _text(self.handler, "handler"))
        object.__setattr__(self, "idempotency_key", _text(self.idempotency_key, "idempotency_key"))
        object.__setattr__(self, "payload_hash", _text(self.payload_hash, "payload_hash"))
        if not isinstance(self.response_payload, Mapping):
            raise ValueError("CatalogIdempotencyRecord.response_payload must be a mapping")
        if not isinstance(self.recorded_at, datetime) or self.recorded_at.tzinfo is None:
            raise ValueError("CatalogIdempotencyRecord.recorded_at must be timezone-aware")


@dataclass(frozen=True)
class CatalogAuditRecord:
    actor_user_id: UserId
    action: str
    store_id: StoreId | None
    product_id: ProductId | None
    target_user_id: UserId | None
    request_id: str
    idempotency_key: str
    before: Mapping[str, Any]
    after: Mapping[str, Any]
    recorded_at: datetime
    group_id: str | None = None
    permission: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.actor_user_id, UserId):
            raise ValueError("CatalogAuditRecord.actor_user_id must be a UserId")
        object.__setattr__(self, "action", _text(self.action, "action"))
        if self.store_id is not None and not isinstance(self.store_id, StoreId):
            raise ValueError("CatalogAuditRecord.store_id must be a StoreId or None")
        if self.product_id is not None and not isinstance(self.product_id, ProductId):
            raise ValueError("CatalogAuditRecord.product_id must be a ProductId or None")
        if self.target_user_id is not None and not isinstance(self.target_user_id, UserId):
            raise ValueError("CatalogAuditRecord.target_user_id must be a UserId or None")
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        object.__setattr__(self, "idempotency_key", _text(self.idempotency_key, "idempotency_key"))
        if not isinstance(self.before, Mapping) or not isinstance(self.after, Mapping):
            raise ValueError("CatalogAuditRecord before/after must be mappings")
        if not isinstance(self.recorded_at, datetime) or self.recorded_at.tzinfo is None:
            raise ValueError("CatalogAuditRecord.recorded_at must be timezone-aware")
        for field_name in ("group_id", "permission", "resource_type", "resource_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(str(value), field_name))


class CatalogWriteRepository(Protocol):
    def get_idempotency_record(self, handler: str, idempotency_key: str) -> CatalogIdempotencyRecord | None:
        ...

    def save_idempotency_record(self, record: CatalogIdempotencyRecord) -> None:
        ...

    def get_user_by_wallet(self, wallet: WalletAddress) -> User | None:
        ...

    def get_user_by_id(self, user_id: UserId) -> User | None:
        ...

    def save_user(self, user: User) -> None:
        ...

    def get_store(self, store_id: StoreId) -> StoreProfile | None:
        ...

    def get_store_by_public_id(self, public_store_id: PublicStoreId) -> StoreProfile | None:
        ...

    def list_stores_for_member(self, user_id: UserId) -> tuple[StoreProfile, ...]:
        ...

    def save_store(self, store: StoreProfile) -> None:
        ...

    def save_order_store_projection(self, store: StoreProfile) -> None:
        ...

    def save_store_approval_store_projection(self, store: StoreProfile) -> None:
        ...

    def get_membership(self, store_id: StoreId, user_id: UserId) -> StoreMembership | None:
        ...

    def save_membership(self, membership: StoreMembership) -> None:
        ...

    def get_store_role(self, store_id: StoreId, user_id: UserId) -> StoreMembershipRole | None:
        ...

    def get_product(self, store_id: StoreId, product_id: ProductId) -> StoreProduct | None:
        ...

    def get_product_by_public_id(self, store_id: StoreId, public_product_id: PublicProductId) -> StoreProduct | None:
        ...

    def save_product(self, product: StoreProduct) -> None:
        ...

    def save_order_product_projection(self, product: StoreProduct) -> None:
        ...

    def save_store_approval_product_projection(self, product: StoreProduct) -> None:
        ...

    def save_inventory_projection(self, product: StoreProduct, initial_total_stock: int) -> None:
        ...

    def record_audit(self, record: CatalogAuditRecord) -> str | None:
        ...


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()

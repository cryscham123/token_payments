"""Store catalog application port contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping, Protocol

from token_payments.contexts.store_catalog.domain import (
    ProductOption,
    ProductOptionValue,
    ProductVariant,
    PublicProductId,
    PublicStoreId,
    PublicVariantId,
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
class CatalogUserRecord:
    user_id: UserId
    primary_wallet: WalletAddress
    role: str = "CUSTOMER"
    active: bool = True
    last_login_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("CatalogUserRecord.user_id must be a UserId")
        if not isinstance(self.primary_wallet, WalletAddress):
            raise ValueError("CatalogUserRecord.primary_wallet must be a WalletAddress")
        object.__setattr__(self, "role", _text(str(self.role), "role"))
        if not isinstance(self.active, bool):
            raise ValueError("CatalogUserRecord.active must be a bool")
        if self.last_login_at is not None and (
            not isinstance(self.last_login_at, datetime) or self.last_login_at.tzinfo is None
        ):
            raise ValueError("CatalogUserRecord.last_login_at must be timezone-aware or None")


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


@dataclass(frozen=True)
class ProductAssetRecord:
    store_id: StoreId
    public_store_id: PublicStoreId
    media_ref: str
    asset_type: str
    file_name: str
    content_type: str
    size_bytes: int
    content_sha256: str
    content: bytes
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.store_id, StoreId):
            raise ValueError("ProductAssetRecord.store_id must be a StoreId")
        if not isinstance(self.public_store_id, PublicStoreId):
            raise ValueError("ProductAssetRecord.public_store_id must be a PublicStoreId")
        object.__setattr__(self, "media_ref", _text(self.media_ref, "media_ref"))
        object.__setattr__(self, "asset_type", _text(self.asset_type, "asset_type"))
        object.__setattr__(self, "file_name", _text(self.file_name, "file_name"))
        object.__setattr__(self, "content_type", _text(self.content_type, "content_type"))
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 1:
            raise ValueError("ProductAssetRecord.size_bytes must be a positive integer")
        object.__setattr__(self, "content_sha256", _text(self.content_sha256, "content_sha256"))
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("ProductAssetRecord.content must be non-empty bytes")
        if not isinstance(self.created_at, datetime) or self.created_at.tzinfo is None:
            raise ValueError("ProductAssetRecord.created_at must be timezone-aware")


class CatalogWriteRepository(Protocol):
    def get_idempotency_record(self, handler: str, idempotency_key: str) -> CatalogIdempotencyRecord | None:
        ...

    def save_idempotency_record(self, record: CatalogIdempotencyRecord) -> None:
        ...

    def get_user_by_wallet(self, wallet: WalletAddress) -> CatalogUserRecord | None:
        ...

    def get_user_by_id(self, user_id: UserId) -> CatalogUserRecord | None:
        ...

    def save_user(self, user: CatalogUserRecord) -> None:
        ...

    def get_store(self, store_id: StoreId) -> StoreProfile | None:
        ...

    def get_store_by_public_id(self, public_store_id: PublicStoreId) -> StoreProfile | None:
        ...

    def get_store_by_display_name(self, display_name: str) -> StoreProfile | None:
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

    def save_product_asset(self, asset: ProductAssetRecord) -> None:
        ...

    def get_product_asset(self, media_ref: str) -> ProductAssetRecord | None:
        ...

    def replace_product_options(
        self,
        store_id: StoreId,
        product_id: ProductId,
        options: tuple[ProductOption, ...],
        option_values: Mapping[str, tuple[ProductOptionValue, ...]],
    ) -> None:
        ...

    def replace_product_variants(
        self,
        store_id: StoreId,
        product_id: ProductId,
        variants: tuple[ProductVariant, ...],
    ) -> None:
        ...

    def save_variant_inventory_projection(
        self,
        product: StoreProduct,
        public_variant_id: PublicVariantId,
        initial_total_stock: int,
    ) -> None:
        ...

    def record_audit(self, record: CatalogAuditRecord) -> str | None:
        ...


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()

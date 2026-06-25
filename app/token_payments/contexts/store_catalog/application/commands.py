"""Input DTOs for canonical store catalog provisioning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from token_payments.contexts.store_catalog.domain import (
    ProductStatus,
    ProductVisibility,
    PublicProductId,
    PublicStoreId,
    StoreMembershipRole,
)
from token_payments.shared.domain import CommandId, Money, ProductId, StoreId, UserId, WalletAddress


@dataclass(frozen=True)
class CreateOrReuseStoreUserCommand:
    command_id: CommandId
    wallet_address: WalletAddress
    requested_at: datetime
    request_id: str
    payload_hash: str

    def __post_init__(self) -> None:
        _validate_common(self)
        if not isinstance(self.wallet_address, WalletAddress):
            raise ValueError("CreateOrReuseStoreUserCommand.wallet_address must be a WalletAddress")


@dataclass(frozen=True)
class CreateStoreCommand:
    command_id: CommandId
    actor_user_id: UserId
    store_id: StoreId
    owner_user_id: UserId
    store_wallet: WalletAddress
    supported_chain_ids: tuple[int, ...]
    active: bool
    requested_at: datetime
    request_id: str
    payload_hash: str
    public_store_id: PublicStoreId | None = None
    display_name: str = "Untitled Store"
    description: str | None = None
    support_email: str | None = None
    support_email_public: bool = False
    business_registration_label: str | None = None

    def __post_init__(self) -> None:
        _validate_common(self)
        if not isinstance(self.actor_user_id, UserId):
            raise ValueError("CreateStoreCommand.actor_user_id must be a UserId")
        if not isinstance(self.store_id, StoreId):
            raise ValueError("CreateStoreCommand.store_id must be a StoreId")
        if self.public_store_id is not None and not isinstance(self.public_store_id, PublicStoreId):
            object.__setattr__(self, "public_store_id", PublicStoreId(str(self.public_store_id)))
        if not isinstance(self.owner_user_id, UserId):
            raise ValueError("CreateStoreCommand.owner_user_id must be a UserId")
        if not isinstance(self.store_wallet, WalletAddress):
            raise ValueError("CreateStoreCommand.store_wallet must be a WalletAddress")
        object.__setattr__(
            self,
            "supported_chain_ids",
            tuple(_positive_int(chain_id, "supported_chain_ids") for chain_id in self.supported_chain_ids),
        )
        if not self.supported_chain_ids:
            raise ValueError("CreateStoreCommand.supported_chain_ids must not be empty")
        if not isinstance(self.active, bool):
            raise ValueError("CreateStoreCommand.active must be a bool")
        object.__setattr__(self, "display_name", _text(self.display_name, "display_name"))
        if self.description is not None:
            object.__setattr__(self, "description", _text(self.description, "description"))
        if self.support_email is not None:
            object.__setattr__(self, "support_email", _text(self.support_email, "support_email"))
        if not isinstance(self.support_email_public, bool):
            raise ValueError("CreateStoreCommand.support_email_public must be a bool")
        if self.business_registration_label is not None:
            object.__setattr__(
                self,
                "business_registration_label",
                _text(self.business_registration_label, "business_registration_label"),
            )


@dataclass(frozen=True)
class GetStoreProfileQuery:
    public_store_id: PublicStoreId

    def __post_init__(self) -> None:
        if not isinstance(self.public_store_id, PublicStoreId):
            object.__setattr__(self, "public_store_id", PublicStoreId(str(self.public_store_id)))


@dataclass(frozen=True)
class ListMerchantStoresQuery:
    actor_user_id: UserId

    def __post_init__(self) -> None:
        if not isinstance(self.actor_user_id, UserId):
            raise ValueError("ListMerchantStoresQuery.actor_user_id must be a UserId")


@dataclass(frozen=True)
class UpdateStoreProfileCommand:
    command_id: CommandId
    actor_user_id: UserId
    public_store_id: PublicStoreId
    display_name: str | None
    description: str | None
    support_email: str | None
    support_email_public: bool | None
    business_registration_label: str | None
    platform_override: bool
    requested_at: datetime
    request_id: str
    payload_hash: str
    supported_chain_ids: tuple[int, ...] | None = None
    supported_payment_asset_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _validate_common(self)
        if not isinstance(self.actor_user_id, UserId):
            raise ValueError("UpdateStoreProfileCommand.actor_user_id must be a UserId")
        if not isinstance(self.public_store_id, PublicStoreId):
            object.__setattr__(self, "public_store_id", PublicStoreId(str(self.public_store_id)))
        for field_name in ("display_name", "description", "support_email", "business_registration_label"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(value, field_name))
        if self.support_email_public is not None and not isinstance(self.support_email_public, bool):
            raise ValueError("UpdateStoreProfileCommand.support_email_public must be a bool")
        if not isinstance(self.platform_override, bool):
            raise ValueError("UpdateStoreProfileCommand.platform_override must be a bool")
        if self.supported_chain_ids is not None:
            if not isinstance(self.supported_chain_ids, tuple):
                raise ValueError("UpdateStoreProfileCommand.supported_chain_ids must be a tuple of ints")
            for chain_id in self.supported_chain_ids:
                if not isinstance(chain_id, int) or chain_id <= 0:
                    raise ValueError("supported_chain_ids must contain positive integers")
        if self.supported_payment_asset_ids is not None:
            if not isinstance(self.supported_payment_asset_ids, tuple):
                raise ValueError("UpdateStoreProfileCommand.supported_payment_asset_ids must be a tuple of strings")
            for asset_id in self.supported_payment_asset_ids:
                if not isinstance(asset_id, str) or not asset_id.strip():
                    raise ValueError("supported_payment_asset_ids must contain non-empty strings")


@dataclass(frozen=True)
class GrantStoreMembershipCommand:
    command_id: CommandId
    actor_user_id: UserId
    store_id: StoreId
    user_id: UserId
    role: StoreMembershipRole
    active: bool
    requested_at: datetime
    request_id: str
    payload_hash: str

    def __post_init__(self) -> None:
        _validate_common(self)
        for field_name in ("actor_user_id", "store_id", "user_id"):
            expected = UserId if field_name != "store_id" else StoreId
            if not isinstance(getattr(self, field_name), expected):
                raise ValueError(f"GrantStoreMembershipCommand.{field_name} must be a {expected.__name__}")
        if not isinstance(self.role, StoreMembershipRole):
            object.__setattr__(self, "role", StoreMembershipRole(_text(str(self.role), "role")))
        if not isinstance(self.active, bool):
            raise ValueError("GrantStoreMembershipCommand.active must be a bool")


@dataclass(frozen=True)
class RegisterStoreProductCommand:
    command_id: CommandId
    actor_user_id: UserId
    public_store_id: PublicStoreId
    product_id: ProductId
    title: str
    price: Money
    initial_total_stock: int
    requested_at: datetime
    request_id: str
    payload_hash: str
    public_product_id: PublicProductId | None = None
    description: str | None = None
    category: str | None = None
    tags: tuple[str, ...] = ()
    media: tuple[str, ...] = ()
    attributes: Mapping[str, object] | None = None
    status: ProductStatus | str = ProductStatus.ACTIVE
    visibility: ProductVisibility | str = ProductVisibility.PUBLIC
    active: bool = True
    platform_override: bool = False

    def __post_init__(self) -> None:
        _validate_common(self)
        if not isinstance(self.actor_user_id, UserId):
            raise ValueError("RegisterStoreProductCommand.actor_user_id must be a UserId")
        if not isinstance(self.public_store_id, PublicStoreId):
            object.__setattr__(self, "public_store_id", PublicStoreId(str(self.public_store_id)))
        if not isinstance(self.product_id, ProductId):
            raise ValueError("RegisterStoreProductCommand.product_id must be a ProductId")
        if self.public_product_id is not None and not isinstance(self.public_product_id, PublicProductId):
            object.__setattr__(self, "public_product_id", PublicProductId(str(self.public_product_id)))
        object.__setattr__(self, "title", _text(self.title, "RegisterStoreProductCommand.title"))
        if not isinstance(self.price, Money):
            raise ValueError("RegisterStoreProductCommand.price must be a Money")
        if isinstance(self.initial_total_stock, bool) or not isinstance(self.initial_total_stock, int) or self.initial_total_stock < 0:
            raise ValueError("RegisterStoreProductCommand.initial_total_stock must be a non-negative integer")
        if not isinstance(self.active, bool):
            raise ValueError("RegisterStoreProductCommand.active must be a bool")
        if not isinstance(self.platform_override, bool):
            raise ValueError("RegisterStoreProductCommand.platform_override must be a bool")
        for field_name in ("description", "category"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(value, field_name))
        object.__setattr__(self, "tags", _text_tuple(self.tags, "tags"))
        object.__setattr__(self, "media", _text_tuple(self.media, "media"))
        if self.attributes is not None and not isinstance(self.attributes, Mapping):
            raise ValueError("RegisterStoreProductCommand.attributes must be an object")
        if not isinstance(self.status, ProductStatus):
            object.__setattr__(self, "status", ProductStatus(_text(str(self.status), "status")))
        if not isinstance(self.visibility, ProductVisibility):
            object.__setattr__(self, "visibility", ProductVisibility(_text(str(self.visibility), "visibility")))


@dataclass(frozen=True)
class UpdateStoreProductCommand:
    command_id: CommandId
    actor_user_id: UserId
    public_store_id: PublicStoreId
    public_product_id: PublicProductId
    title: str | None
    description: str | None
    category: str | None
    tags: tuple[str, ...] | None
    media: tuple[str, ...] | None
    attributes: Mapping[str, object] | None
    status: ProductStatus | str | None
    visibility: ProductVisibility | str | None
    requested_at: datetime
    request_id: str
    payload_hash: str
    price: Money | None = None
    platform_override: bool = False

    def __post_init__(self) -> None:
        _validate_common(self)
        if not isinstance(self.actor_user_id, UserId):
            raise ValueError("UpdateStoreProductCommand.actor_user_id must be a UserId")
        if not isinstance(self.public_store_id, PublicStoreId):
            object.__setattr__(self, "public_store_id", PublicStoreId(str(self.public_store_id)))
        if not isinstance(self.public_product_id, PublicProductId):
            object.__setattr__(self, "public_product_id", PublicProductId(str(self.public_product_id)))
        for field_name in ("title", "description", "category"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _text(value, field_name))
        if self.tags is not None:
            object.__setattr__(self, "tags", _text_tuple(self.tags, "tags"))
        if self.media is not None:
            object.__setattr__(self, "media", _text_tuple(self.media, "media"))
        if self.attributes is not None and not isinstance(self.attributes, Mapping):
            raise ValueError("UpdateStoreProductCommand.attributes must be an object")
        if self.status is not None and not isinstance(self.status, ProductStatus):
            object.__setattr__(self, "status", ProductStatus(_text(str(self.status), "status")))
        if self.visibility is not None and not isinstance(self.visibility, ProductVisibility):
            object.__setattr__(self, "visibility", ProductVisibility(_text(str(self.visibility), "visibility")))
        if self.price is not None and not isinstance(self.price, Money):
            raise ValueError("UpdateStoreProductCommand.price must be a Money")
        if not isinstance(self.platform_override, bool):
            raise ValueError("UpdateStoreProductCommand.platform_override must be a bool")


def _validate_common(command: object) -> None:
    if not isinstance(getattr(command, "command_id"), CommandId):
        raise ValueError(f"{type(command).__name__}.command_id must be a CommandId")
    if not isinstance(getattr(command, "requested_at"), datetime) or getattr(command, "requested_at").tzinfo is None:
        raise ValueError(f"{type(command).__name__}.requested_at must be timezone-aware")
    object.__setattr__(command, "request_id", _text(getattr(command, "request_id"), "request_id"))
    object.__setattr__(command, "payload_hash", _text(getattr(command, "payload_hash"), "payload_hash"))


def payload_hash(payload: Mapping[str, object]) -> str:
    import hashlib
    import json

    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must contain positive integers")
    return value


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _text_tuple(values: tuple[str, ...] | list[str], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple | list):
        raise ValueError(f"{field_name} must be an array")
    return tuple(_text(value, field_name) for value in values)

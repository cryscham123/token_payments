"""Canonical store ownership, business profile, and minimal catalog domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
import math
import re
from types import MappingProxyType
import unicodedata
from typing import Any, Mapping, Self
from uuid import UUID

from token_payments.contexts.auth.domain import GroupId
from token_payments.shared.domain import Crypto, ProductId, StoreId, UserId, WalletAddress


_PUBLIC_STORE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{7,63}$")
_PUBLIC_PRODUCT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{7,63}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_OBJECT_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_LOG_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@")


class StoreMembershipRole(StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"


class StoreStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class ProductStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class ProductVisibility(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


@dataclass(frozen=True)
class PublicStoreId:
    value: str

    def __post_init__(self) -> None:
        value = _public_store_id(self.value, "PublicStoreId.value")
        object.__setattr__(self, "value", value)

    @classmethod
    def for_store_id(cls, store_id: StoreId) -> Self:
        if not isinstance(store_id, StoreId):
            raise ValueError("PublicStoreId.for_store_id store_id must be a StoreId")
        digest = hashlib.blake2s(str(store_id).encode("ascii"), digest_size=10).hexdigest()
        return cls(f"st_{digest}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PublicProductId:
    value: str

    def __post_init__(self) -> None:
        value = _public_product_id(self.value, "PublicProductId.value")
        object.__setattr__(self, "value", value)

    @classmethod
    def for_product_id(cls, product_id: ProductId) -> Self:
        if not isinstance(product_id, ProductId):
            raise ValueError("PublicProductId.for_product_id product_id must be a ProductId")
        digest = hashlib.blake2s(str(product_id).encode("ascii"), digest_size=10).hexdigest()
        return cls(f"prd_{digest}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class StorePaymentSettings:
    store_id: StoreId
    store_wallet: WalletAddress | str
    supported_chain_ids: tuple[int, ...]
    supported_payment_asset_ids: tuple[str, ...] = ()
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.store_id, StoreId):
            raise ValueError("StorePaymentSettings.store_id must be a StoreId")
        if not isinstance(self.active, bool):
            raise ValueError("StorePaymentSettings.active must be a bool")
        object.__setattr__(self, "store_wallet", _coerce_wallet(self.store_wallet))
        chains = tuple(_positive_int(chain_id, "StoreProfile.supported_chain_ids") for chain_id in self.supported_chain_ids)
        if not chains:
            raise ValueError("StorePaymentSettings.supported_chain_ids must not be empty")
        if len(set(chains)) != len(chains):
            raise ValueError("StorePaymentSettings.supported_chain_ids cannot contain duplicates")
        object.__setattr__(self, "supported_chain_ids", chains)
        asset_ids = tuple(_bounded_text(asset_id, "StorePaymentSettings.supported_payment_asset_ids", max_length=120) for asset_id in self.supported_payment_asset_ids)
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("StorePaymentSettings.supported_payment_asset_ids cannot contain duplicates")
        object.__setattr__(self, "supported_payment_asset_ids", asset_ids)

    def supports_chain(self, chain_id: int) -> bool:
        return _positive_int(chain_id, "chain_id") in self.supported_chain_ids


@dataclass(frozen=True, init=False)
class StoreProfile:
    store_id: StoreId
    owner_user_id: UserId
    public_store_id: PublicStoreId
    group_id: GroupId | None
    display_name: str
    description: str | None
    status: StoreStatus
    support_email: str | None
    support_email_public: bool
    business_registration_label: str | None
    created_at: datetime
    updated_at: datetime
    payment_settings: StorePaymentSettings | None

    def __init__(
        self,
        *,
        store_id: StoreId,
        owner_user_id: UserId,
        public_store_id: PublicStoreId | str | None = None,
        group_id: GroupId | str | None = None,
        display_name: str = "Untitled Store",
        description: str | None = None,
        status: StoreStatus | str | None = None,
        support_email: str | None = None,
        support_email_public: bool = False,
        business_registration_label: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        payment_settings: StorePaymentSettings | None = None,
        active: bool = True,
        store_wallet: WalletAddress | str | None = None,
        supported_chain_ids: tuple[int, ...] | list[int] | None = None,
    ) -> None:
        if not isinstance(store_id, StoreId):
            raise ValueError("StoreProfile.store_id must be a StoreId")
        if not isinstance(owner_user_id, UserId):
            raise ValueError("StoreProfile.owner_user_id must be a UserId")
        if not isinstance(active, bool):
            raise ValueError("StoreProfile.active must be a bool")
        if not isinstance(support_email_public, bool):
            raise ValueError("StoreProfile.support_email_public must be a bool")
        if status is None:
            status = StoreStatus.ACTIVE if active else StoreStatus.SUSPENDED
        status = _store_status(status)
        group_id = _optional_group_id(group_id)
        if public_store_id is None:
            public_store_id = PublicStoreId.for_store_id(store_id)
        elif not isinstance(public_store_id, PublicStoreId):
            public_store_id = PublicStoreId(public_store_id)
        payment_settings = _payment_settings(
            store_id=store_id,
            active=active,
            store_wallet=store_wallet,
            supported_chain_ids=supported_chain_ids,
            payment_settings=payment_settings,
        )
        if created_at is None:
            created_at = datetime.now(UTC)
        if updated_at is None:
            updated_at = created_at

        object.__setattr__(self, "store_id", store_id)
        object.__setattr__(self, "owner_user_id", owner_user_id)
        object.__setattr__(self, "public_store_id", public_store_id)
        object.__setattr__(self, "group_id", group_id)
        object.__setattr__(self, "display_name", _bounded_text(display_name, "display_name", max_length=120))
        object.__setattr__(
            self,
            "description",
            _optional_bounded_text(description, "description", max_length=2000),
        )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "support_email", _optional_email(support_email, "support_email"))
        object.__setattr__(self, "support_email_public", support_email_public)
        object.__setattr__(
            self,
            "business_registration_label",
            _optional_bounded_text(
                business_registration_label,
                "business_registration_label",
                max_length=160,
            ),
        )
        object.__setattr__(self, "created_at", _aware_datetime(created_at, "StoreProfile.created_at"))
        object.__setattr__(self, "updated_at", _aware_datetime(updated_at, "StoreProfile.updated_at"))
        object.__setattr__(self, "payment_settings", payment_settings)

    @property
    def active(self) -> bool:
        return self.status is StoreStatus.ACTIVE

    @property
    def store_wallet(self) -> WalletAddress | None:
        return self.payment_settings.store_wallet if self.payment_settings is not None else None

    @property
    def supported_chain_ids(self) -> tuple[int, ...]:
        return self.payment_settings.supported_chain_ids if self.payment_settings is not None else ()

    @property
    def supported_payment_asset_ids(self) -> tuple[str, ...]:
        return self.payment_settings.supported_payment_asset_ids if self.payment_settings is not None else ()

    def supports_chain(self, chain_id: int) -> bool:
        return self.payment_settings is not None and self.payment_settings.supports_chain(chain_id)

    def update_business_profile(
        self,
        *,
        display_name: str | None = None,
        description: str | None = None,
        support_email: str | None = None,
        support_email_public: bool | None = None,
        business_registration_label: str | None = None,
        updated_at: datetime,
    ) -> Self:
        return type(self)(
            store_id=self.store_id,
            owner_user_id=self.owner_user_id,
            public_store_id=self.public_store_id,
            group_id=self.group_id,
            display_name=self.display_name if display_name is None else display_name,
            description=self.description if description is None else description,
            status=self.status,
            support_email=self.support_email if support_email is None else support_email,
            support_email_public=self.support_email_public if support_email_public is None else support_email_public,
            business_registration_label=(
                self.business_registration_label
                if business_registration_label is None
                else business_registration_label
            ),
            created_at=self.created_at,
            updated_at=updated_at,
            payment_settings=self.payment_settings,
        )


@dataclass(frozen=True)
class StoreMembership:
    store_id: StoreId
    user_id: UserId
    role: StoreMembershipRole | str
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.store_id, StoreId):
            raise ValueError("StoreMembership.store_id must be a StoreId")
        if not isinstance(self.user_id, UserId):
            raise ValueError("StoreMembership.user_id must be a UserId")
        object.__setattr__(self, "role", _membership_role(self.role))
        if not isinstance(self.active, bool):
            raise ValueError("StoreMembership.active must be a bool")

    @classmethod
    def owner(cls, store_id: StoreId, user_id: UserId, *, active: bool = True) -> Self:
        return cls(store_id=store_id, user_id=user_id, role=StoreMembershipRole.OWNER, active=active)


@dataclass(frozen=True, init=False)
class StoreProduct:
    store_id: StoreId
    product_id: ProductId
    public_product_id: PublicProductId
    public_store_id: PublicStoreId
    title: str
    description: str | None
    category: str | None
    tags: tuple[str, ...]
    media: tuple[str, ...]
    attributes: Mapping[str, Any]
    status: ProductStatus
    visibility: ProductVisibility
    price: Crypto
    created_at: datetime
    updated_at: datetime

    def __init__(
        self,
        *,
        store_id: StoreId,
        product_id: ProductId,
        price: Crypto,
        public_product_id: PublicProductId | str | None = None,
        public_store_id: PublicStoreId | str | None = None,
        title: str | None = None,
        name: str | None = None,
        description: str | None = None,
        category: str | None = None,
        tags: tuple[str, ...] | list[str] | None = None,
        media: tuple[str, ...] | list[str] | None = None,
        attributes: Mapping[str, Any] | None = None,
        status: ProductStatus | str | None = None,
        visibility: ProductVisibility | str = ProductVisibility.PUBLIC,
        active: bool = True,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        if not isinstance(store_id, StoreId):
            raise ValueError("StoreProduct.store_id must be a StoreId")
        if not isinstance(product_id, ProductId):
            raise ValueError("StoreProduct.product_id must be a ProductId")
        if not isinstance(price, Crypto):
            raise ValueError("StoreProduct.price must be a Crypto")
        if not isinstance(active, bool):
            raise ValueError("StoreProduct.active must be a bool")
        if public_product_id is None:
            public_product_id = PublicProductId.for_product_id(product_id)
        elif not isinstance(public_product_id, PublicProductId):
            public_product_id = PublicProductId(public_product_id)
        if public_store_id is None:
            public_store_id = PublicStoreId.for_store_id(store_id)
        elif not isinstance(public_store_id, PublicStoreId):
            public_store_id = PublicStoreId(public_store_id)
        if title is None:
            title = name
        if status is None:
            status = ProductStatus.ACTIVE if active else ProductStatus.INACTIVE
        if created_at is None:
            created_at = datetime.now(UTC)
        if updated_at is None:
            updated_at = created_at

        object.__setattr__(self, "store_id", store_id)
        object.__setattr__(self, "product_id", product_id)
        object.__setattr__(self, "public_product_id", public_product_id)
        object.__setattr__(self, "public_store_id", public_store_id)
        object.__setattr__(self, "title", _bounded_text(title or "", "StoreProduct.title", max_length=160))
        object.__setattr__(
            self,
            "description",
            _optional_bounded_text(description, "StoreProduct.description", max_length=4000),
        )
        object.__setattr__(self, "category", _optional_category(category))
        object.__setattr__(self, "tags", _tags(tags or ()))
        object.__setattr__(self, "media", _media_refs(media or ()))
        object.__setattr__(self, "attributes", MappingProxyType(_attributes(attributes or {})))
        object.__setattr__(self, "status", _product_status(status))
        object.__setattr__(self, "visibility", _product_visibility(visibility))
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "created_at", _aware_datetime(created_at, "StoreProduct.created_at"))
        object.__setattr__(self, "updated_at", _aware_datetime(updated_at, "StoreProduct.updated_at"))

    @property
    def name(self) -> str:
        return self.title

    @property
    def active(self) -> bool:
        return self.status is ProductStatus.ACTIVE

    def update_detail(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
        tags: tuple[str, ...] | list[str] | None = None,
        media: tuple[str, ...] | list[str] | None = None,
        attributes: Mapping[str, Any] | None = None,
        status: ProductStatus | str | None = None,
        visibility: ProductVisibility | str | None = None,
        price: Crypto | None = None,
        updated_at: datetime,
    ) -> Self:
        return type(self)(
            store_id=self.store_id,
            product_id=self.product_id,
            public_product_id=self.public_product_id,
            public_store_id=self.public_store_id,
            title=self.title if title is None else title,
            description=self.description if description is None else description,
            category=self.category if category is None else category,
            tags=self.tags if tags is None else tags,
            media=self.media if media is None else media,
            attributes=dict(self.attributes) if attributes is None else attributes,
            status=self.status if status is None else status,
            visibility=self.visibility if visibility is None else visibility,
            price=self.price if price is None else price,
            created_at=self.created_at,
            updated_at=updated_at,
        )


@dataclass(frozen=True)
class StoreCatalog:
    store: StoreProfile
    products: tuple[StoreProduct, ...]
    memberships: tuple[StoreMembership, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.store, StoreProfile):
            raise ValueError("StoreCatalog.store must be a StoreProfile")
        products = tuple(self.products)
        if not all(isinstance(product, StoreProduct) for product in products):
            raise ValueError("StoreCatalog.products must contain StoreProduct values")
        if any(product.store_id != self.store.store_id for product in products):
            raise ValueError("StoreCatalog.products must belong to the store")
        product_ids = [product.product_id for product in products]
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("StoreCatalog.products cannot contain duplicate product ids within one store")
        memberships = tuple(self.memberships)
        if not all(isinstance(membership, StoreMembership) for membership in memberships):
            raise ValueError("StoreCatalog.memberships must contain StoreMembership values")
        if any(membership.store_id != self.store.store_id for membership in memberships):
            raise ValueError("StoreCatalog.memberships must belong to the store")
        object.__setattr__(self, "products", products)
        object.__setattr__(self, "memberships", memberships)


def _membership_role(value: StoreMembershipRole | str) -> StoreMembershipRole:
    if isinstance(value, StoreMembershipRole):
        return value
    try:
        return StoreMembershipRole(_text(str(value), "StoreMembership.role"))
    except ValueError as exc:
        raise ValueError("StoreMembership.role must be OWNER or MANAGER") from exc


def _coerce_wallet(value: WalletAddress | str) -> WalletAddress:
    if isinstance(value, WalletAddress):
        return value
    return WalletAddress(value)


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must contain positive integers")
    return value


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _public_store_id(value: str, field_name: str) -> str:
    value = _text(value, field_name).lower()
    try:
        UUID(value)
    except ValueError:
        pass
    else:
        raise ValueError(f"{field_name} must not be an internal UUID")
    if value.isdigit():
        raise ValueError(f"{field_name} must not be a sequential numeric id")
    if not _PUBLIC_STORE_ID_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be 8-64 lowercase letters, numbers, underscores, or hyphens")
    if _has_unsafe_text(value):
        raise ValueError(f"{field_name} contains unsafe characters")
    return value


def _public_product_id(value: str, field_name: str) -> str:
    value = _text(value, field_name).lower()
    try:
        UUID(value)
    except ValueError:
        pass
    else:
        raise ValueError(f"{field_name} must not be an internal UUID")
    if value.isdigit():
        raise ValueError(f"{field_name} must not be a sequential numeric id")
    if not _PUBLIC_PRODUCT_ID_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be 8-64 lowercase letters, numbers, underscores, or hyphens")
    if _has_unsafe_text(value):
        raise ValueError(f"{field_name} contains unsafe characters")
    return value


def _bounded_text(value: str, field_name: str, *, max_length: int) -> str:
    value = unicodedata.normalize("NFC", _text(value, field_name))
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    if _has_unsafe_text(value):
        raise ValueError(f"{field_name} contains control characters or null bytes")
    if value.lstrip().startswith(_LOG_CSV_INJECTION_PREFIXES):
        raise ValueError(f"{field_name} cannot start with log/CSV injection-prone characters")
    return value


def _optional_bounded_text(value: str | None, field_name: str, *, max_length: int) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, field_name, max_length=max_length)


def _optional_category(value: str | None) -> str | None:
    category = _optional_bounded_text(value, "StoreProduct.category", max_length=80)
    if category is None:
        return None
    return category.lower()


def _tags(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    tags = tuple(_tag(value) for value in values)
    if len(tags) > 20:
        raise ValueError("StoreProduct.tags must contain at most 20 tags")
    if len(set(tags)) != len(tags):
        raise ValueError("StoreProduct.tags cannot contain duplicates")
    return tags


def _tag(value: str) -> str:
    tag = unicodedata.normalize("NFC", _text(value, "StoreProduct.tag")).lower()
    if _has_unsafe_text(tag):
        raise ValueError("StoreProduct.tag contains unsafe characters")
    if not _TAG_RE.fullmatch(tag):
        raise ValueError("StoreProduct.tag must be lowercase letters, numbers, underscores, or hyphens")
    return tag


def _media_refs(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    refs = tuple(_media_ref(value) for value in values)
    if len(refs) > 12:
        raise ValueError("StoreProduct.media must contain at most 12 refs")
    return refs


def _media_ref(value: str) -> str:
    ref = _bounded_text(value, "StoreProduct.media", max_length=2048)
    from urllib.parse import urlsplit

    parsed = urlsplit(ref)
    if parsed.scheme:
        if parsed.scheme not in {"https", "ipfs"} or not parsed.netloc:
            raise ValueError("StoreProduct.media URL scheme must be https or ipfs")
        return ref
    if ref.startswith("/") or ".." in ref.split("/") or not _OBJECT_KEY_RE.fullmatch(ref):
        raise ValueError("StoreProduct.media object key has an invalid shape")
    return ref


def _attributes(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("StoreProduct.attributes must be a JSON object")
    attributes = _json_object(value, "StoreProduct.attributes", depth=0)
    encoded = json.dumps(attributes, ensure_ascii=False, sort_keys=True, allow_nan=False)
    if len(encoded.encode("utf-8")) > 8192:
        raise ValueError("StoreProduct.attributes serialized size must be at most 8192 bytes")
    return attributes


def _json_object(value: Mapping[str, Any], field_name: str, *, depth: int) -> dict[str, Any]:
    if depth > 4:
        raise ValueError(f"{field_name} is nested too deeply")
    if len(value) > 50:
        raise ValueError(f"{field_name} contains too many keys")
    result: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = _bounded_text(str(raw_key), f"{field_name}.key", max_length=60)
        result[key] = _json_value(raw_value, f"{field_name}.{key}", depth=depth + 1)
    return result


def _json_value(value: Any, field_name: str, *, depth: int) -> Any:
    if depth > 4:
        raise ValueError(f"{field_name} is nested too deeply")
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{field_name} must be finite")
        return value
    if isinstance(value, str):
        return _bounded_text(value, field_name, max_length=200)
    if isinstance(value, list | tuple):
        if len(value) > 25:
            raise ValueError(f"{field_name} contains too many values")
        return [_json_value(item, field_name, depth=depth + 1) for item in value]
    if isinstance(value, Mapping):
        return _json_object(value, field_name, depth=depth)
    raise ValueError(f"{field_name} contains unsupported JSON value type")


def _optional_email(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    value = unicodedata.normalize("NFC", _text(value, field_name)).lower()
    if len(value) > 254:
        raise ValueError(f"{field_name} must be at most 254 characters")
    if _has_unsafe_text(value) or value.lstrip().startswith(_LOG_CSV_INJECTION_PREFIXES):
        raise ValueError(f"{field_name} contains unsafe characters")
    if not _EMAIL_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be an email address")
    return value


def _has_unsafe_text(value: str) -> bool:
    return "\x00" in value or any(unicodedata.category(char).startswith("C") for char in value)


def _store_status(value: StoreStatus | str) -> StoreStatus:
    if isinstance(value, StoreStatus):
        return value
    try:
        return StoreStatus(_text(str(value), "status"))
    except ValueError as exc:
        raise ValueError("StoreProfile.status must be ACTIVE or SUSPENDED") from exc


def _product_status(value: ProductStatus | str) -> ProductStatus:
    if isinstance(value, ProductStatus):
        return value
    try:
        return ProductStatus(_text(str(value), "StoreProduct.status"))
    except ValueError as exc:
        raise ValueError("StoreProduct.status must be ACTIVE, INACTIVE, or ARCHIVED") from exc


def _product_visibility(value: ProductVisibility | str) -> ProductVisibility:
    if isinstance(value, ProductVisibility):
        return value
    try:
        return ProductVisibility(_text(str(value), "StoreProduct.visibility"))
    except ValueError as exc:
        raise ValueError("StoreProduct.visibility must be PUBLIC or PRIVATE") from exc


def _optional_group_id(value: GroupId | str | None) -> GroupId | None:
    if value is None:
        return None
    if isinstance(value, GroupId):
        return value
    return GroupId(value)


def _payment_settings(
    *,
    store_id: StoreId,
    active: bool,
    store_wallet: WalletAddress | str | None,
    supported_chain_ids: tuple[int, ...] | list[int] | None,
    payment_settings: StorePaymentSettings | None,
) -> StorePaymentSettings | None:
    if payment_settings is not None:
        if not isinstance(payment_settings, StorePaymentSettings):
            raise ValueError("StoreProfile.payment_settings must be a StorePaymentSettings")
        if payment_settings.store_id != store_id:
            raise ValueError("StoreProfile.payment_settings must belong to the store")
        return payment_settings
    if store_wallet is None and supported_chain_ids is None:
        return None
    if store_wallet is None or supported_chain_ids is None:
        raise ValueError("StoreProfile payment settings require store_wallet and supported_chain_ids")
    return StorePaymentSettings(
        store_id=store_id,
        store_wallet=store_wallet,
        supported_chain_ids=tuple(supported_chain_ids),
        active=active,
    )


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value

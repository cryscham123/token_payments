"""Canonical store ownership, business profile, and minimal catalog domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import re
import unicodedata
from typing import Self
from uuid import UUID

from token_payments.contexts.auth.domain import GroupId
from token_payments.shared.domain import Crypto, ProductId, StoreId, UserId, WalletAddress


_PUBLIC_STORE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{7,63}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LOG_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@")


class StoreMembershipRole(StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"


class StoreStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


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
class StorePaymentSettings:
    store_id: StoreId
    store_wallet: WalletAddress | str
    supported_chain_ids: tuple[int, ...]
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


@dataclass(frozen=True)
class StoreProduct:
    store_id: StoreId
    product_id: ProductId
    name: str
    price: Crypto
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.store_id, StoreId):
            raise ValueError("StoreProduct.store_id must be a StoreId")
        if not isinstance(self.product_id, ProductId):
            raise ValueError("StoreProduct.product_id must be a ProductId")
        object.__setattr__(self, "name", _text(self.name, "StoreProduct.name"))
        if not isinstance(self.price, Crypto):
            raise ValueError("StoreProduct.price must be a Crypto")
        if not isinstance(self.active, bool):
            raise ValueError("StoreProduct.active must be a bool")


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

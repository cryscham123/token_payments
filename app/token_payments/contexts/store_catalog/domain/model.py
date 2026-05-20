"""Canonical store ownership and minimal catalog domain model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from token_payments.shared.domain import Crypto, ProductId, StoreId, UserId, WalletAddress


class StoreMembershipRole(StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"


@dataclass(frozen=True)
class StoreProfile:
    store_id: StoreId
    owner_user_id: UserId
    active: bool
    store_wallet: WalletAddress | str
    supported_chain_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.store_id, StoreId):
            raise ValueError("StoreProfile.store_id must be a StoreId")
        if not isinstance(self.owner_user_id, UserId):
            raise ValueError("StoreProfile.owner_user_id must be a UserId")
        if not isinstance(self.active, bool):
            raise ValueError("StoreProfile.active must be a bool")
        object.__setattr__(self, "store_wallet", _coerce_wallet(self.store_wallet))
        chains = tuple(_positive_int(chain_id, "StoreProfile.supported_chain_ids") for chain_id in self.supported_chain_ids)
        if not chains:
            raise ValueError("StoreProfile.supported_chain_ids must not be empty")
        if len(set(chains)) != len(chains):
            raise ValueError("StoreProfile.supported_chain_ids cannot contain duplicates")
        object.__setattr__(self, "supported_chain_ids", chains)

    def supports_chain(self, chain_id: int) -> bool:
        return _positive_int(chain_id, "chain_id") in self.supported_chain_ids


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

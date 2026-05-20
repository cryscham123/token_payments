"""Input DTOs for canonical store catalog provisioning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from token_payments.contexts.auth.domain import UserRole
from token_payments.contexts.store_catalog.domain import StoreMembershipRole
from token_payments.shared.domain import CommandId, Crypto, ProductId, StoreId, UserId, WalletAddress


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

    def __post_init__(self) -> None:
        _validate_common(self)
        if not isinstance(self.actor_user_id, UserId):
            raise ValueError("CreateStoreCommand.actor_user_id must be a UserId")
        if not isinstance(self.store_id, StoreId):
            raise ValueError("CreateStoreCommand.store_id must be a StoreId")
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
    actor_platform_role: UserRole
    store_id: StoreId
    product_id: ProductId
    name: str
    price: Crypto
    initial_total_stock: int
    active: bool
    requested_at: datetime
    request_id: str
    payload_hash: str

    def __post_init__(self) -> None:
        _validate_common(self)
        if not isinstance(self.actor_user_id, UserId):
            raise ValueError("RegisterStoreProductCommand.actor_user_id must be a UserId")
        if not isinstance(self.actor_platform_role, UserRole):
            object.__setattr__(
                self,
                "actor_platform_role",
                UserRole(_text(str(self.actor_platform_role), "actor_platform_role")),
            )
        if not isinstance(self.store_id, StoreId):
            raise ValueError("RegisterStoreProductCommand.store_id must be a StoreId")
        if not isinstance(self.product_id, ProductId):
            raise ValueError("RegisterStoreProductCommand.product_id must be a ProductId")
        object.__setattr__(self, "name", _text(self.name, "RegisterStoreProductCommand.name"))
        if not isinstance(self.price, Crypto):
            raise ValueError("RegisterStoreProductCommand.price must be a Crypto")
        if isinstance(self.initial_total_stock, bool) or not isinstance(self.initial_total_stock, int) or self.initial_total_stock < 0:
            raise ValueError("RegisterStoreProductCommand.initial_total_stock must be a non-negative integer")
        if not isinstance(self.active, bool):
            raise ValueError("RegisterStoreProductCommand.active must be a bool")


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


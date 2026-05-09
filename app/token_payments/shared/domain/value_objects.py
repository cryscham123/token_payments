"""Shared immutable value objects for the Token Payments domain."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TRANSACTION_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class WalletAddress:
    address: str

    def __post_init__(self) -> None:
        if not isinstance(self.address, str):
            raise ValueError("WalletAddress must be a string")

        address = self.address.strip()
        if not _EVM_ADDRESS_RE.fullmatch(address):
            raise ValueError("WalletAddress must be a 0x-prefixed 20-byte hex address")

        object.__setattr__(self, "address", address.lower())

    def __str__(self) -> str:
        return self.address


@dataclass(frozen=True)
class ChainNetwork:
    chain_id: int
    name: str

    def __post_init__(self) -> None:
        if isinstance(self.chain_id, bool) or not isinstance(self.chain_id, int) or self.chain_id <= 0:
            raise ValueError("ChainNetwork.chain_id must be a positive integer")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("ChainNetwork.name must be a non-empty string")

        object.__setattr__(self, "name", self.name.strip())


@dataclass(frozen=True)
class TransactionHash:
    hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.hash, str):
            raise ValueError("TransactionHash must be a string")

        value = self.hash.strip()
        if not _TRANSACTION_HASH_RE.fullmatch(value):
            raise ValueError("TransactionHash must be a 0x-prefixed 32-byte hex hash")

        object.__setattr__(self, "hash", value.lower())

    def __str__(self) -> str:
        return self.hash


@dataclass(frozen=True)
class Crypto:
    amount: Decimal
    symbol: str
    chain_id: int
    token_address: WalletAddress | None
    decimals: int

    def __post_init__(self) -> None:
        amount = _coerce_decimal(self.amount)
        if not amount.is_finite() or amount < Decimal("0"):
            raise ValueError("Crypto.amount must be a finite non-negative decimal")

        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("Crypto.symbol must be a non-empty string")

        if isinstance(self.chain_id, bool) or not isinstance(self.chain_id, int) or self.chain_id <= 0:
            raise ValueError("Crypto.chain_id must be a positive integer")

        if isinstance(self.decimals, bool) or not isinstance(self.decimals, int) or self.decimals < 0:
            raise ValueError("Crypto.decimals must be a non-negative integer")

        token_address = self.token_address
        if isinstance(token_address, str):
            token_address = WalletAddress(token_address)
        elif token_address is not None and not isinstance(token_address, WalletAddress):
            raise ValueError("Crypto.token_address must be a WalletAddress, string, or None")

        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "token_address", token_address)


def _coerce_decimal(value: Decimal | str | int) -> Decimal:
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Crypto.amount must be decimal-compatible") from exc

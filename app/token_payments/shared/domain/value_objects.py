"""Shared immutable value objects for the Token Payments domain."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import MappingProxyType
from typing import Mapping
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


_USD_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class Money:
    """A fiat price expressed in a single currency (USD by default).

    Products are priced in fiat; the on-chain amount a buyer pays is derived at
    checkout by converting this through an :class:`ExchangeRate`.
    """

    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        amount = _coerce_decimal(self.amount)
        if not amount.is_finite() or amount < Decimal("0"):
            raise ValueError("Money.amount must be a finite non-negative decimal")
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise ValueError("Money.currency must be a non-empty string")
        object.__setattr__(self, "amount", amount.quantize(_USD_CENTS, rounding=ROUND_HALF_UP))
        object.__setattr__(self, "currency", self.currency.strip().upper())

    def add(self, other: "Money") -> "Money":
        if not isinstance(other, Money) or other.currency != self.currency:
            raise ValueError("Money.add requires the same currency")
        return Money(self.amount + other.amount, self.currency)

    def multiply(self, quantity: int) -> "Money":
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError("Money.multiply requires a non-negative integer quantity")
        return Money(self.amount * quantity, self.currency)


@dataclass(frozen=True)
class ExchangeRate:
    """Fixed conversion between fiat and on-chain assets.

    ``usd_per_unit`` maps an asset symbol to the USD value of one whole token
    (e.g. ``{"ETH": 3000, "USDC": 1, "USDT": 1}``). Stablecoins peg to 1.
    """

    usd_per_unit: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        if not isinstance(self.usd_per_unit, Mapping) or not self.usd_per_unit:
            raise ValueError("ExchangeRate.usd_per_unit must be a non-empty mapping")
        normalized: dict[str, Decimal] = {}
        for symbol, rate in self.usd_per_unit.items():
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("ExchangeRate symbol must be a non-empty string")
            rate_decimal = _coerce_decimal(rate)
            if not rate_decimal.is_finite() or rate_decimal <= Decimal("0"):
                raise ValueError("ExchangeRate value must be a finite positive decimal")
            normalized[symbol.strip().upper()] = rate_decimal
        object.__setattr__(self, "usd_per_unit", MappingProxyType(normalized))

    def to_crypto(
        self,
        price: Money,
        *,
        symbol: str,
        chain_id: int,
        token_address: WalletAddress | str | None,
        decimals: int,
    ) -> Crypto:
        """Convert a fiat *price* into an on-chain :class:`Crypto` amount.

        The token amount is ``fiat / (usd per token)`` quantized to the asset's
        ``decimals`` so it can be expressed exactly in minor units on-chain.
        """

        if price.currency != "USD":
            raise ValueError(f"ExchangeRate only converts USD prices, got {price.currency}")
        key = symbol.strip().upper() if isinstance(symbol, str) else symbol
        if key not in self.usd_per_unit:
            raise ValueError(f"ExchangeRate has no rate for asset symbol {symbol}")
        units = price.amount / self.usd_per_unit[key]
        quantized = units.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
        return Crypto(
            amount=quantized,
            symbol=symbol,
            chain_id=chain_id,
            token_address=token_address,
            decimals=decimals,
        )


@dataclass(frozen=True)
class PriceConversion:
    """An :class:`ExchangeRate` bound to one payment asset.

    The order context resolves the selected payment asset and pairs it with the
    runtime rate, then hands this to the domain so pricing can convert a fiat
    :class:`Money` total into the asset's on-chain :class:`Crypto` amount without
    the domain depending on the payment context.
    """

    rate: ExchangeRate
    asset_id: str
    symbol: str
    chain_id: int
    token_address: WalletAddress | str | None
    decimals: int

    def __post_init__(self) -> None:
        if not isinstance(self.rate, ExchangeRate):
            raise ValueError("PriceConversion.rate must be an ExchangeRate")
        object.__setattr__(self, "asset_id", _require_nonempty(self.asset_id, "PriceConversion.asset_id"))

    def convert(self, price: Money) -> Crypto:
        return self.rate.to_crypto(
            price,
            symbol=self.symbol,
            chain_id=self.chain_id,
            token_address=self.token_address,
            decimals=self.decimals,
        )


def _require_nonempty(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()

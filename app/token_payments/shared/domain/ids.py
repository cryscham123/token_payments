"""Typed UUID identifiers shared by bounded contexts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4


@dataclass(frozen=True)
class _UuidIdentifier:
    value: UUID

    def __post_init__(self) -> None:
        value = self.value
        if isinstance(value, UUID):
            normalized = value
        elif isinstance(value, str) and value.strip():
            try:
                normalized = UUID(value.strip())
            except ValueError as exc:
                raise ValueError(f"{type(self).__name__} must be a valid UUID") from exc
        else:
            raise ValueError(f"{type(self).__name__} must be a non-empty UUID")

        object.__setattr__(self, "value", normalized)

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class OrderId(_UuidIdentifier):
    pass


@dataclass(frozen=True)
class PaymentId(_UuidIdentifier):
    pass


@dataclass(frozen=True)
class CustomerId(_UuidIdentifier):
    pass


@dataclass(frozen=True)
class StoreId(_UuidIdentifier):
    pass


@dataclass(frozen=True)
class ProductId(_UuidIdentifier):
    pass


@dataclass(frozen=True)
class UserId(_UuidIdentifier):
    pass


@dataclass(frozen=True)
class MessageId(_UuidIdentifier):
    pass


# Default variant key for option-less products. Stock is always tracked per
# variant, so option-less products get a single hidden default variant whose
# public id is derived deterministically from the product id. This is the single
# source of truth shared by the store_catalog projection and the inventory
# adapter so both resolve to the same row.
DEFAULT_VARIANT_KEY = "default"


def default_public_variant_id(product_id: ProductId) -> str:
    if not isinstance(product_id, ProductId):
        raise ValueError("default_public_variant_id requires a ProductId")
    digest = hashlib.blake2s(f"{product_id}:{DEFAULT_VARIANT_KEY}".encode("utf-8"), digest_size=10).hexdigest()
    return f"var_{digest}"

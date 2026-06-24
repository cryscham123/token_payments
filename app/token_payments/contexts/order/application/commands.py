"""Input DTOs for order creation use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Mapping

from token_payments.contexts.auth.domain.wallet import WalletId
from token_payments.contexts.order.domain import Address, TrackingId
from token_payments.shared.domain import CommandId, MessageId, OrderId, ProductId, StoreId, UserId


@dataclass(frozen=True)
class CreateOrderItem:
    product_id: ProductId | str
    quantity: int
    public_variant_id: str | None = None
    selected_options: Mapping[str, object] = field(default_factory=dict)
    media: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", _coerce_product_id(self.product_id))
        object.__setattr__(self, "quantity", _coerce_positive_int(self.quantity, "CreateOrderItem.quantity"))
        if self.public_variant_id is not None:
            object.__setattr__(self, "public_variant_id", _require_text(self.public_variant_id, "CreateOrderItem.public_variant_id"))
        object.__setattr__(self, "selected_options", MappingProxyType(_coerce_selected_options(self.selected_options)))
        if self.media:
            object.__setattr__(self, "media", tuple(str(x) for x in self.media if str(x).strip()))


@dataclass(frozen=True)
class CreateOrderCommand:
    authenticated_user_id: UserId | str
    store_id: StoreId | str
    delivery_address: Address
    items: tuple[CreateOrderItem, ...]
    order_id: OrderId | str = field(default_factory=OrderId.new)
    tracking_id: TrackingId | str | None = None
    event_message_id: MessageId | str = field(default_factory=MessageId.new)
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    wallet_id: WalletId | str | None = None
    payment_asset_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "authenticated_user_id", _coerce_user_id(self.authenticated_user_id))
        object.__setattr__(self, "store_id", _coerce_store_id(self.store_id))
        if not isinstance(self.delivery_address, Address):
            raise ValueError("CreateOrderCommand.delivery_address must be an Address")
        object.__setattr__(self, "items", _coerce_items(self.items))
        object.__setattr__(self, "order_id", _coerce_order_id(self.order_id))
        object.__setattr__(self, "tracking_id", _coerce_tracking_id(self.tracking_id))
        object.__setattr__(self, "event_message_id", _coerce_message_id(self.event_message_id))
        object.__setattr__(
            self,
            "requested_at",
            _require_aware_datetime(self.requested_at, "CreateOrderCommand.requested_at"),
        )
        if self.wallet_id is not None and not isinstance(self.wallet_id, WalletId):
            object.__setattr__(self, "wallet_id", WalletId(str(self.wallet_id)))
        if self.payment_asset_id is not None:
            object.__setattr__(self, "payment_asset_id", _require_text(self.payment_asset_id, "CreateOrderCommand.payment_asset_id"))
        if self.causation_id is not None:
            object.__setattr__(
                self,
                "causation_id",
                _require_text(self.causation_id, "CreateOrderCommand.causation_id"),
            )


@dataclass(frozen=True)
class CancelOrderCommand:
    command_id: CommandId
    order_id: OrderId
    reason: str
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, CommandId):
            raise ValueError("CancelOrderCommand.command_id must be a CommandId")
        if not isinstance(self.order_id, OrderId):
            raise ValueError("CancelOrderCommand.order_id must be an OrderId")
        object.__setattr__(self, "reason", _require_text(self.reason, "CancelOrderCommand.reason"))
        object.__setattr__(
            self,
            "requested_at",
            _require_aware_datetime(self.requested_at, "CancelOrderCommand.requested_at"),
        )
        if self.causation_id is not None:
            object.__setattr__(
                self,
                "causation_id",
                _require_text(self.causation_id, "CancelOrderCommand.causation_id"),
            )
        if not isinstance(self.event_message_id, MessageId):
            raise ValueError("CancelOrderCommand.event_message_id must be a MessageId")


def _coerce_items(items: tuple[CreateOrderItem, ...] | list[CreateOrderItem]) -> tuple[CreateOrderItem, ...]:
    if isinstance(items, list):
        items = tuple(items)
    if not isinstance(items, tuple):
        raise ValueError("CreateOrderCommand.items must be a tuple")
    if not items:
        raise ValueError("CreateOrderCommand.items must contain at least one item")
    if not all(isinstance(item, CreateOrderItem) for item in items):
        raise ValueError("CreateOrderCommand.items must contain only CreateOrderItem values")
    return items


def _coerce_user_id(value: UserId | str) -> UserId:
    return value if isinstance(value, UserId) else UserId(value)


def _coerce_store_id(value: StoreId | str) -> StoreId:
    return value if isinstance(value, StoreId) else StoreId(value)


def _coerce_product_id(value: ProductId | str) -> ProductId:
    return value if isinstance(value, ProductId) else ProductId(value)


def _coerce_order_id(value: OrderId | str) -> OrderId:
    return value if isinstance(value, OrderId) else OrderId(value)


def _coerce_message_id(value: MessageId | str) -> MessageId:
    return value if isinstance(value, MessageId) else MessageId(value)


def _coerce_tracking_id(value: TrackingId | str | None) -> TrackingId:
    if value is None:
        return TrackingId.new()
    return value if isinstance(value, TrackingId) else TrackingId(value)


def _coerce_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _coerce_selected_options(values: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(values, Mapping):
        raise ValueError("CreateOrderItem.selected_options must be a mapping")
    normalized: dict[str, object] = {}
    for key, value in values.items():
        option_key = _require_text(str(key), "CreateOrderItem.selected_options key")
        if isinstance(value, list | tuple):
            normalized[option_key] = [_require_text(str(item), f"CreateOrderItem.selected_options.{option_key}") for item in value if str(item).strip()]
        elif value is not None and str(value).strip():
            normalized[option_key] = _require_text(str(value), f"CreateOrderItem.selected_options.{option_key}")
    return dict(sorted(normalized.items()))


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()

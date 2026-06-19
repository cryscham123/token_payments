"""Input DTOs for inventory command handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping

from token_payments.contexts.inventory.domain import Quantity
from token_payments.shared.domain import CommandId, MessageId, OrderId, ProductId, StoreId, UserId


@dataclass(frozen=True)
class ReserveInventoryCommand:
    command_id: CommandId
    order_id: OrderId
    product_id: ProductId
    store_id: StoreId
    quantity: Quantity | int
    public_variant_id: str | None = None
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)
    items: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = ()

    def __post_init__(self) -> None:
        _validate_common_command(self)
        quantity = _coerce_quantity(self.quantity)
        if not quantity.is_positive:
            raise ValueError("ReserveInventoryCommand.quantity must be a positive quantity")
        object.__setattr__(self, "quantity", quantity)


@dataclass(frozen=True)
class ReleaseInventoryCommand:
    command_id: CommandId
    order_id: OrderId
    product_id: ProductId
    store_id: StoreId
    public_variant_id: str | None = None
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)
    items: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = ()

    def __post_init__(self) -> None:
        _validate_common_command(self)


@dataclass(frozen=True)
class ConfirmInventoryCommand:
    command_id: CommandId
    order_id: OrderId
    product_id: ProductId
    store_id: StoreId
    public_variant_id: str | None = None
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)
    items: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = ()

    def __post_init__(self) -> None:
        _validate_common_command(self)


@dataclass(frozen=True)
class StoreOwnerIncreaseStockCommand:
    command_id: CommandId
    store_id: StoreId
    product_id: ProductId
    actor_user_id: UserId
    actor_role: str
    quantity: Quantity | int
    reason: str
    requested_at: datetime
    request_id: str
    actor_store_role: str | None = None

    def __post_init__(self) -> None:
        _validate_store_owner_command(self)
        quantity = _coerce_quantity(self.quantity)
        if not quantity.is_positive:
            raise ValueError("StoreOwnerIncreaseStockCommand.quantity must be a positive quantity")
        object.__setattr__(self, "quantity", quantity)


@dataclass(frozen=True)
class StoreOwnerCorrectStockCommand:
    command_id: CommandId
    store_id: StoreId
    product_id: ProductId
    actor_user_id: UserId
    actor_role: str
    target_total_stock: Quantity | int
    reason: str
    requested_at: datetime
    request_id: str
    actor_store_role: str | None = None

    def __post_init__(self) -> None:
        _validate_store_owner_command(self)
        object.__setattr__(self, "target_total_stock", _coerce_quantity(self.target_total_stock))


@dataclass(frozen=True)
class PauseProductSalesCommand:
    command_id: CommandId
    store_id: StoreId
    product_id: ProductId
    actor_user_id: UserId
    actor_role: str
    reason: str
    requested_at: datetime
    request_id: str
    actor_store_role: str | None = None

    def __post_init__(self) -> None:
        _validate_store_owner_command(self)


@dataclass(frozen=True)
class ResumeProductSalesCommand:
    command_id: CommandId
    store_id: StoreId
    product_id: ProductId
    actor_user_id: UserId
    actor_role: str
    reason: str
    requested_at: datetime
    request_id: str
    actor_store_role: str | None = None

    def __post_init__(self) -> None:
        _validate_store_owner_command(self)


def _validate_common_command(
    command: ReserveInventoryCommand | ReleaseInventoryCommand | ConfirmInventoryCommand,
) -> None:
    if not isinstance(command.command_id, CommandId):
        raise ValueError(f"{type(command).__name__}.command_id must be a CommandId")
    if not isinstance(command.order_id, OrderId):
        raise ValueError(f"{type(command).__name__}.order_id must be an OrderId")
    if not isinstance(command.product_id, ProductId):
        raise ValueError(f"{type(command).__name__}.product_id must be a ProductId")
    if not isinstance(command.store_id, StoreId):
        raise ValueError(f"{type(command).__name__}.store_id must be a StoreId")
    if command.public_variant_id is not None:
        object.__setattr__(
            command,
            "public_variant_id",
            _require_text(command.public_variant_id, f"{type(command).__name__}.public_variant_id"),
        )
    object.__setattr__(command, "items", _coerce_items(command.items, f"{type(command).__name__}.items"))
    object.__setattr__(
        command,
        "requested_at",
        _require_aware_datetime(command.requested_at, f"{type(command).__name__}.requested_at"),
    )
    if command.causation_id is not None:
        object.__setattr__(
            command,
            "causation_id",
            _require_text(command.causation_id, f"{type(command).__name__}.causation_id"),
        )
    if not isinstance(command.event_message_id, MessageId):
        raise ValueError(f"{type(command).__name__}.event_message_id must be a MessageId")


def _validate_store_owner_command(
    command: (
        StoreOwnerIncreaseStockCommand
        | StoreOwnerCorrectStockCommand
        | PauseProductSalesCommand
        | ResumeProductSalesCommand
    ),
) -> None:
    if not isinstance(command.command_id, CommandId):
        raise ValueError(f"{type(command).__name__}.command_id must be a CommandId")
    if not isinstance(command.store_id, StoreId):
        raise ValueError(f"{type(command).__name__}.store_id must be a StoreId")
    if not isinstance(command.product_id, ProductId):
        raise ValueError(f"{type(command).__name__}.product_id must be a ProductId")
    if not isinstance(command.actor_user_id, UserId):
        raise ValueError(f"{type(command).__name__}.actor_user_id must be a UserId")
    object.__setattr__(command, "actor_role", _require_text(str(command.actor_role), "actor_role"))
    object.__setattr__(command, "reason", _require_text(command.reason, f"{type(command).__name__}.reason"))
    object.__setattr__(
        command,
        "requested_at",
        _require_aware_datetime(command.requested_at, f"{type(command).__name__}.requested_at"),
    )
    object.__setattr__(command, "request_id", _require_text(command.request_id, f"{type(command).__name__}.request_id"))
    if command.actor_store_role is not None:
        object.__setattr__(
            command,
            "actor_store_role",
            _require_text(command.actor_store_role, f"{type(command).__name__}.actor_store_role"),
        )


def _coerce_quantity(value: Quantity | int) -> Quantity:
    return value if isinstance(value, Quantity) else Quantity(value)


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


def _coerce_items(
    values: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    field_name: str,
) -> tuple[dict[str, Any], ...]:
    if isinstance(values, list):
        values = tuple(values)
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    items: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, Mapping):
            raise ValueError(f"{field_name} must contain JSON objects")
        items.append(dict(item))
    return tuple(items)

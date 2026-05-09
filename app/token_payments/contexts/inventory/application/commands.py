"""Input DTOs for inventory command handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from token_payments.contexts.inventory.domain import Quantity
from token_payments.shared.domain import CommandId, MessageId, OrderId, ProductId, StoreId


@dataclass(frozen=True)
class ReserveInventoryCommand:
    command_id: CommandId
    order_id: OrderId
    product_id: ProductId
    store_id: StoreId
    quantity: Quantity | int
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)

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
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)

    def __post_init__(self) -> None:
        _validate_common_command(self)


@dataclass(frozen=True)
class ConfirmInventoryCommand:
    command_id: CommandId
    order_id: OrderId
    product_id: ProductId
    store_id: StoreId
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)

    def __post_init__(self) -> None:
        _validate_common_command(self)


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

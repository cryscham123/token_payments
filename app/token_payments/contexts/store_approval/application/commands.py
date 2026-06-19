"""Input DTOs for store approval command handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping

from token_payments.shared.domain import CommandId, MessageId, OrderId, StoreId, UserId


@dataclass(frozen=True)
class RequestStoreApprovalCommand:
    command_id: CommandId
    order_id: OrderId
    store_id: StoreId
    owner_user_id: UserId
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    rejection_reason: str | None = None
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)
    items: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, CommandId):
            raise ValueError("RequestStoreApprovalCommand.command_id must be a CommandId")
        if not isinstance(self.order_id, OrderId):
            raise ValueError("RequestStoreApprovalCommand.order_id must be an OrderId")
        if not isinstance(self.store_id, StoreId):
            raise ValueError("RequestStoreApprovalCommand.store_id must be a StoreId")
        if not isinstance(self.owner_user_id, UserId):
            raise ValueError("RequestStoreApprovalCommand.owner_user_id must be a UserId")
        object.__setattr__(
            self,
            "requested_at",
            _require_aware_datetime(self.requested_at, "RequestStoreApprovalCommand.requested_at"),
        )
        if self.rejection_reason is not None:
            object.__setattr__(
                self,
                "rejection_reason",
                _require_text(self.rejection_reason, "RequestStoreApprovalCommand.rejection_reason"),
            )
        if self.causation_id is not None:
            object.__setattr__(
                self,
                "causation_id",
                _require_text(self.causation_id, "RequestStoreApprovalCommand.causation_id"),
            )
        if not isinstance(self.event_message_id, MessageId):
            raise ValueError("RequestStoreApprovalCommand.event_message_id must be a MessageId")
        object.__setattr__(self, "items", _coerce_items(self.items, "RequestStoreApprovalCommand.items"))


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


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

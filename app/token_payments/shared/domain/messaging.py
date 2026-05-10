"""Messaging and outbox contracts shared by bounded contexts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Self

from .ids import MessageId, OrderId


class CheckoutEventName(StrEnum):
    ORDER_CREATED = "OrderCreatedEvent"
    ORDER_CANCELLED = "OrderCancelledEvent"
    INVENTORY_RESERVED = "InventoryReservedEvent"
    PAYMENT_CONFIRMED = "PaymentConfirmedEvent"
    PAYMENT_FAILED = "PaymentFailedEvent"
    PAYMENT_EXPIRED = "PaymentExpiredEvent"
    ORDER_APPROVED = "OrderApprovedEvent"
    ORDER_REJECTED = "OrderRejectedEvent"


class CheckoutCommandName(StrEnum):
    RESERVE_INVENTORY = "ReserveInventoryCommand"
    INITIATE_PAYMENT = "InitiatePaymentCommand"
    REQUEST_STORE_APPROVAL = "RequestStoreApprovalCommand"
    RELEASE_INVENTORY = "ReleaseInventoryCommand"
    REFUND_PAYMENT = "RefundPaymentCommand"
    CANCEL_ORDER = "CancelOrderCommand"


class OutboxMessageKind(StrEnum):
    EVENT = "EVENT"
    COMMAND = "COMMAND"


class OutboxPublishStatus(StrEnum):
    READY = "READY"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class IdempotencyDecision(StrEnum):
    PROCESS = "PROCESS"
    IGNORE_DUPLICATE = "IGNORE_DUPLICATE"


@dataclass(frozen=True)
class CommandId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("CommandId.value must be a non-empty string")
        object.__setattr__(self, "value", self.value.strip())

    @classmethod
    def for_order_action(cls, order_id: OrderId, action: CheckoutCommandName | str) -> Self:
        if not isinstance(order_id, OrderId):
            raise ValueError("CommandId.for_order_action requires an OrderId")

        action_value = action.value if isinstance(action, CheckoutCommandName) else str(action).strip()
        if not action_value:
            raise ValueError("CommandId action must be a non-empty string")

        return cls(f"{order_id}:{action_value}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class EventMetadata:
    message_id: MessageId
    name: CheckoutEventName | str
    aggregate_id: str
    occurred_at: datetime
    correlation_id: str
    causation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, MessageId):
            raise ValueError("EventMetadata.message_id must be a MessageId")
        object.__setattr__(self, "name", _normalize_message_name(self.name, "EventMetadata.name"))
        object.__setattr__(self, "aggregate_id", _require_text(self.aggregate_id, "EventMetadata.aggregate_id"))
        object.__setattr__(self, "correlation_id", _require_text(self.correlation_id, "EventMetadata.correlation_id"))
        object.__setattr__(self, "occurred_at", _require_aware_datetime(self.occurred_at, "EventMetadata.occurred_at"))
        if self.causation_id is not None:
            object.__setattr__(self, "causation_id", _require_text(self.causation_id, "EventMetadata.causation_id"))


@dataclass(frozen=True)
class CommandMetadata:
    command_id: CommandId
    name: CheckoutCommandName | str
    aggregate_id: str
    issued_at: datetime
    correlation_id: str
    causation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, CommandId):
            raise ValueError("CommandMetadata.command_id must be a CommandId")
        object.__setattr__(self, "name", _normalize_message_name(self.name, "CommandMetadata.name"))
        object.__setattr__(self, "aggregate_id", _require_text(self.aggregate_id, "CommandMetadata.aggregate_id"))
        object.__setattr__(self, "correlation_id", _require_text(self.correlation_id, "CommandMetadata.correlation_id"))
        object.__setattr__(self, "issued_at", _require_aware_datetime(self.issued_at, "CommandMetadata.issued_at"))
        if self.causation_id is not None:
            object.__setattr__(self, "causation_id", _require_text(self.causation_id, "CommandMetadata.causation_id"))


@dataclass(frozen=True)
class OutboxMessage:
    kind: OutboxMessageKind
    identity: str
    name: str
    topic: str
    key: str
    payload: Mapping[str, Any]
    headers: Mapping[str, str] = field(default_factory=dict)
    status: OutboxPublishStatus = OutboxPublishStatus.READY
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None
    failure_count: int = 0
    last_error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OutboxMessageKind):
            raise ValueError("OutboxMessage.kind must be an OutboxMessageKind")
        if not isinstance(self.status, OutboxPublishStatus):
            raise ValueError("OutboxMessage.status must be an OutboxPublishStatus")
        object.__setattr__(self, "identity", _require_text(self.identity, "OutboxMessage.identity"))
        object.__setattr__(self, "name", _require_text(self.name, "OutboxMessage.name"))
        object.__setattr__(self, "topic", _require_text(self.topic, "OutboxMessage.topic"))
        object.__setattr__(self, "key", _require_text(self.key, "OutboxMessage.key"))
        object.__setattr__(self, "created_at", _require_aware_datetime(self.created_at, "OutboxMessage.created_at"))
        if self.published_at is not None:
            object.__setattr__(
                self,
                "published_at",
                _require_aware_datetime(self.published_at, "OutboxMessage.published_at"),
            )
        if isinstance(self.failure_count, bool) or not isinstance(self.failure_count, int) or self.failure_count < 0:
            raise ValueError("OutboxMessage.failure_count must be a non-negative integer")
        if not isinstance(self.payload, Mapping):
            raise ValueError("OutboxMessage.payload must be a mapping")
        if not isinstance(self.headers, Mapping):
            raise ValueError("OutboxMessage.headers must be a mapping")

        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(self, "headers", MappingProxyType({str(k): str(v) for k, v in self.headers.items()}))
        if self.last_error is not None:
            object.__setattr__(self, "last_error", _require_text(self.last_error, "OutboxMessage.last_error"))

    @classmethod
    def record_event(
        cls,
        metadata: EventMetadata,
        topic: str,
        key: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
        created_at: datetime | None = None,
    ) -> Self:
        return cls(
            kind=OutboxMessageKind.EVENT,
            identity=str(metadata.message_id),
            name=str(metadata.name),
            topic=topic,
            key=key,
            payload=payload,
            headers=headers or {},
            created_at=created_at or metadata.occurred_at,
        )

    @classmethod
    def record_command(
        cls,
        metadata: CommandMetadata,
        topic: str,
        key: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
        created_at: datetime | None = None,
    ) -> Self:
        return cls(
            kind=OutboxMessageKind.COMMAND,
            identity=str(metadata.command_id),
            name=str(metadata.name),
            topic=topic,
            key=key,
            payload=payload,
            headers=headers or {},
            created_at=created_at or metadata.issued_at,
        )

    def mark_publishing(self) -> Self:
        if self.status not in {OutboxPublishStatus.READY, OutboxPublishStatus.FAILED}:
            raise ValueError(f"cannot mark {self.status} outbox message as publishing")
        return replace(self, status=OutboxPublishStatus.PUBLISHING)

    def mark_published(self, published_at: datetime | None = None) -> Self:
        if self.status is not OutboxPublishStatus.PUBLISHING:
            raise ValueError(f"cannot mark {self.status} outbox message as published")
        return replace(
            self,
            status=OutboxPublishStatus.PUBLISHED,
            published_at=published_at or datetime.now(UTC),
        )

    def mark_failed(self, error_message: str) -> Self:
        if self.status is OutboxPublishStatus.PUBLISHED:
            raise ValueError("published outbox messages cannot transition to failed")
        return replace(
            self,
            status=OutboxPublishStatus.FAILED,
            failure_count=self.failure_count + 1,
            last_error=_require_text(error_message, "OutboxMessage.last_error"),
        )


@dataclass(frozen=True)
class ProcessedMessage:
    message_id: MessageId
    consumer: str
    processed_at: datetime
    order_id: OrderId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, MessageId):
            raise ValueError("ProcessedMessage.message_id must be a MessageId")
        object.__setattr__(self, "consumer", _require_text(self.consumer, "ProcessedMessage.consumer"))
        object.__setattr__(
            self,
            "processed_at",
            _require_aware_datetime(self.processed_at, "ProcessedMessage.processed_at"),
        )
        if self.order_id is not None and not isinstance(self.order_id, OrderId):
            raise ValueError("ProcessedMessage.order_id must be an OrderId or None")

    @classmethod
    def record(
        cls,
        message_id: MessageId,
        consumer: str,
        processed_at: datetime,
        order_id: OrderId | None = None,
    ) -> Self:
        return cls(message_id=message_id, consumer=consumer, processed_at=processed_at, order_id=order_id)

    @property
    def idempotency_key(self) -> tuple[str, str]:
        return (self.consumer, str(self.message_id))

    @property
    def duplicate_decision(self) -> IdempotencyDecision:
        return IdempotencyDecision.IGNORE_DUPLICATE


@dataclass(frozen=True)
class ProcessedCommand:
    command_id: CommandId
    handler: str
    processed_at: datetime
    order_id: OrderId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command_id, CommandId):
            raise ValueError("ProcessedCommand.command_id must be a CommandId")
        object.__setattr__(self, "handler", _require_text(self.handler, "ProcessedCommand.handler"))
        object.__setattr__(
            self,
            "processed_at",
            _require_aware_datetime(self.processed_at, "ProcessedCommand.processed_at"),
        )
        if self.order_id is not None and not isinstance(self.order_id, OrderId):
            raise ValueError("ProcessedCommand.order_id must be an OrderId or None")

    @classmethod
    def record(
        cls,
        command_id: CommandId,
        handler: str,
        processed_at: datetime,
        order_id: OrderId | None = None,
    ) -> Self:
        return cls(command_id=command_id, handler=handler, processed_at=processed_at, order_id=order_id)

    @property
    def idempotency_key(self) -> tuple[str, str]:
        return (self.handler, str(self.command_id))

    @property
    def duplicate_decision(self) -> IdempotencyDecision:
        return IdempotencyDecision.IGNORE_DUPLICATE


def _normalize_message_name(
    value: CheckoutEventName | CheckoutCommandName | str,
    field_name: str,
) -> CheckoutEventName | CheckoutCommandName | str:
    if isinstance(value, (CheckoutEventName, CheckoutCommandName)):
        return value
    return _require_text(value, field_name)


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

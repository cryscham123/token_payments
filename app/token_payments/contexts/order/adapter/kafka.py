"""Kafka listeners for order lifecycle commands and events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from token_payments.contexts.order.application import (
    CancelOrderCommand,
    OrderCommandHandler,
    OrderStatusEvent,
    OrderStatusEventProjector,
)
from token_payments.shared.adapter.kafka import KafkaInboundMessage, MalformedKafkaMessage
from token_payments.shared.adapter.kafka.listener import decode_payload, header_value
from token_payments.shared.domain import (
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    EventMetadata,
    IdempotencyDecision,
    MessageId,
    OrderId,
    PaymentId,
    ProcessedCommand,
)


class ProcessedCommandRepository(Protocol):
    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        ...

    def record(self, processed_command: ProcessedCommand) -> IdempotencyDecision:
        ...


@dataclass(frozen=True)
class OrderKafkaCommandListenerResult:
    command_id: CommandId
    order_id: OrderId
    handler_result: object | None = None
    duplicate_decision: IdempotencyDecision | None = None


@dataclass(frozen=True)
class OrderStatusKafkaEventListenerResult:
    message_id: MessageId
    order_id: OrderId
    projector_result: object | None = None

    @property
    def duplicate_decision(self) -> IdempotencyDecision | None:
        return getattr(self.projector_result, "duplicate_decision", None)


class OrderKafkaCommandListener:
    """Deserialize order commands and dispatch them to OrderCommandHandler."""

    HANDLER_NAME = OrderCommandHandler.HANDLER_NAME

    def __init__(
        self,
        command_handler: OrderCommandHandler,
        processed_commands: ProcessedCommandRepository,
    ) -> None:
        self._command_handler = command_handler
        self._processed_commands = processed_commands

    def handle(self, message: KafkaInboundMessage) -> OrderKafkaCommandListenerResult:
        payload = decode_payload(message)
        command_id = _command_id(_required_command_id(message, payload))
        command_name = _command_name(_required_payload_text(payload, "commandName", "name", field_name="commandName"))
        order_id = _order_id(_required_payload_text(payload, "orderId", "order_id", field_name="orderId"))
        handler_name = getattr(self._command_handler, "HANDLER_NAME", self.HANDLER_NAME)

        if self._processed_commands.was_processed(command_id, handler_name):
            return OrderKafkaCommandListenerResult(
                command_id=command_id,
                order_id=order_id,
                duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
            )

        if command_name is not CheckoutCommandName.CANCEL_ORDER:
            raise MalformedKafkaMessage(f"unsupported order commandName `{command_name.value}`")

        command = CancelOrderCommand(
            command_id=command_id,
            order_id=order_id,
            reason=_required_payload_text(payload, "reason", "failureReason", field_name="reason"),
            requested_at=_message_time(payload, "requestedAt", "issuedAt", "requested_at", "issued_at"),
            causation_id=_causation_id(message, payload),
            event_message_id=_event_message_id(payload),
        )
        handler_result = self._command_handler.cancel_order(command)
        return OrderKafkaCommandListenerResult(command_id=command_id, order_id=order_id, handler_result=handler_result)


class OrderStatusKafkaEventListener:
    """Deserialize payment/store approval events and project order status."""

    def __init__(self, projector: OrderStatusEventProjector) -> None:
        self._projector = projector

    def handle(self, message: KafkaInboundMessage) -> OrderStatusKafkaEventListenerResult:
        payload = decode_payload(message)
        event = _status_event_from_payload(message, payload)
        result = self._projector.project(event)
        return OrderStatusKafkaEventListenerResult(
            message_id=event.metadata.message_id,
            order_id=event.order_id,
            projector_result=result,
        )


def _status_event_from_payload(message: KafkaInboundMessage, payload: Mapping[str, Any]) -> OrderStatusEvent:
    name = _event_name(_required_payload_text(payload, "eventName", "name", field_name="eventName"))
    order_id = _order_id(_required_payload_text(payload, "orderId", "order_id", field_name="orderId"))
    message_id = _message_id(
        _required_text(
            header_value(message, "message_id", "messageId")
            or _optional_payload_text(payload, "messageId", "message_id"),
            "message_id",
        )
    )
    metadata = EventMetadata(
        message_id=message_id,
        name=name,
        aggregate_id=_optional_payload_text(payload, "aggregateId", "aggregate_id") or str(order_id),
        occurred_at=_message_time(payload, "occurredAt", "createdAt", "expiredAt"),
        correlation_id=(
            header_value(message, "correlation_id", "correlationId")
            or _optional_payload_text(payload, "correlationId", "correlation_id")
            or str(order_id)
        ),
        causation_id=(
            header_value(message, "causation_id", "causationId")
            or _optional_payload_text(payload, "causationId", "causation_id")
        ),
    )
    return OrderStatusEvent(
        metadata=metadata,
        order_id=order_id,
        payment_id=_optional_payment_id(payload),
        reason=_optional_payload_text(payload, "reason", "failureReason", "rejectionReason"),
    )


def _required_command_id(message: KafkaInboundMessage, payload: Mapping[str, Any]) -> str:
    return _required_text(
        header_value(message, "command_id", "commandId")
        or _optional_payload_text(payload, "commandId", "command_id"),
        "commandId",
    )


def _command_name(value: str) -> CheckoutCommandName:
    try:
        return CheckoutCommandName(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"unsupported commandName `{value}`") from exc


def _event_name(value: str) -> CheckoutEventName:
    try:
        return CheckoutEventName(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"unsupported eventName `{value}`") from exc


def _command_id(value: str) -> CommandId:
    try:
        return CommandId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"commandId must be valid: {value}") from exc


def _message_id(value: str) -> MessageId:
    try:
        return MessageId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"message_id must be a valid MessageId: {value}") from exc


def _order_id(value: str) -> OrderId:
    try:
        return OrderId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"orderId must be a valid OrderId: {value}") from exc


def _optional_payment_id(payload: Mapping[str, Any]) -> PaymentId | None:
    value = _optional_payload_text(payload, "paymentId", "payment_id")
    if value is None:
        return None
    try:
        return PaymentId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"paymentId must be a valid PaymentId: {value}") from exc


def _event_message_id(payload: Mapping[str, Any]) -> MessageId:
    value = _optional_payload_text(payload, "eventMessageId", "event_message_id")
    if value is None:
        return MessageId.new()
    return _message_id(value)


def _message_time(payload: Mapping[str, Any], *names: str) -> datetime:
    value = _optional_payload_text(payload, *names)
    if value is None:
        return datetime.now(UTC)
    return _parse_datetime(value, names[0])


def _causation_id(message: KafkaInboundMessage, payload: Mapping[str, Any]) -> str | None:
    return (
        header_value(message, "causation_id", "causationId")
        or _optional_payload_text(payload, "causationId", "causation_id", "sourceMessageId")
    )


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MalformedKafkaMessage(f"{field_name} must be an ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MalformedKafkaMessage(f"{field_name} must be timezone-aware")
    return parsed


def _required_payload_text(payload: Mapping[str, Any], *names: str, field_name: str) -> str:
    return _required_text(_optional_payload_text(payload, *names), field_name)


def _optional_payload_text(payload: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = payload.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _required_text(value: str | None, field_name: str) -> str:
    if value is None or not value.strip():
        raise MalformedKafkaMessage(f"payload missing {field_name}")
    return value.strip()

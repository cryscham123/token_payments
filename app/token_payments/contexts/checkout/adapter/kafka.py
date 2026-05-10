"""Kafka event listener for the checkout process manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from token_payments.contexts.checkout.application import (
    CheckoutCommandDecision,
    CheckoutProcessEvent,
    CheckoutProcessManager,
)
from token_payments.shared.adapter.kafka import KafkaInboundMessage, MalformedKafkaMessage
from token_payments.shared.adapter.kafka.listener import decode_payload, header_value
from token_payments.shared.adapter.messaging import MessageTopicResolver
from token_payments.shared.domain import (
    CheckoutCommandName,
    CheckoutEventName,
    CommandMetadata,
    EventMetadata,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxMessage,
    ProcessedMessage,
)


class ProcessedMessageRepository(Protocol):
    def was_processed(self, message_id: MessageId, consumer: str) -> bool:
        ...

    def record(self, processed_message: ProcessedMessage) -> IdempotencyDecision:
        ...


class OutboxMessageRepository(Protocol):
    def save(self, message: OutboxMessage) -> None:
        ...


@dataclass(frozen=True)
class CheckoutKafkaListenerResult:
    message_id: MessageId
    order_id: OrderId
    outbox_messages: tuple[OutboxMessage, ...] = ()
    duplicate_decision: IdempotencyDecision | None = None


class CheckoutKafkaEventListener:
    """Deserialize checkout events, run the process manager, and save command outbox rows."""

    CONSUMER_NAME = "checkout-process-manager"

    def __init__(
        self,
        process_manager: CheckoutProcessManager,
        processed_messages: ProcessedMessageRepository,
        outbox_messages: OutboxMessageRepository,
        *,
        topic_resolver: MessageTopicResolver | None = None,
    ) -> None:
        self._process_manager = process_manager
        self._processed_messages = processed_messages
        self._outbox_messages = outbox_messages
        self._topic_resolver = topic_resolver or MessageTopicResolver.default()

    def handle(self, message: KafkaInboundMessage) -> CheckoutKafkaListenerResult:
        payload = decode_payload(message)
        event = _checkout_event_from_payload(message, payload)

        if self._processed_messages.was_processed(event.metadata.message_id, self.CONSUMER_NAME):
            return CheckoutKafkaListenerResult(
                message_id=event.metadata.message_id,
                order_id=event.order_id,
                duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
            )

        decisions = self._process_manager.handle(event)
        outbox_messages = tuple(self._outbox_command(decision, payload, event.name) for decision in decisions)
        for outbox_message in outbox_messages:
            self._outbox_messages.save(outbox_message)

        self._processed_messages.record(
            ProcessedMessage.record(
                message_id=event.metadata.message_id,
                consumer=self.CONSUMER_NAME,
                processed_at=event.metadata.occurred_at,
                order_id=event.order_id,
            )
        )
        return CheckoutKafkaListenerResult(
            message_id=event.metadata.message_id,
            order_id=event.order_id,
            outbox_messages=outbox_messages,
        )

    def _outbox_command(
        self,
        decision: CheckoutCommandDecision,
        source_payload: Mapping[str, Any],
        source_event_name: CheckoutEventName,
    ) -> OutboxMessage:
        metadata = decision.metadata
        payload = _command_payload(metadata, decision.order_id, source_payload, source_event_name)
        headers = {"correlationId": metadata.correlation_id}
        if metadata.causation_id is not None:
            headers["causationId"] = metadata.causation_id
        return OutboxMessage.record_command(
            metadata=metadata,
            topic=self._topic_resolver.topic_for(decision.name),
            key=str(decision.order_id),
            payload=payload,
            headers=headers,
        )


def _checkout_event_from_payload(message: KafkaInboundMessage, payload: Mapping[str, Any]) -> CheckoutProcessEvent:
    name = _event_name(_required_payload_text(payload, "eventName", "name", field_name="eventName"))
    order_id = _order_id(_required_payload_text(payload, "orderId", "order_id", field_name="orderId"))
    message_id = _message_id(
        _required_text(
            header_value(message, "message_id", "messageId")
            or _optional_payload_text(payload, "messageId", "message_id"),
            "message_id",
        )
    )
    occurred_at = _optional_datetime(payload, "occurredAt", "createdAt", "expiredAt") or datetime.now(UTC)
    metadata = EventMetadata(
        message_id=message_id,
        name=name,
        aggregate_id=_optional_payload_text(payload, "aggregateId", "aggregate_id") or str(order_id),
        occurred_at=occurred_at,
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
    return CheckoutProcessEvent(metadata=metadata, order_id=order_id)


def _command_payload(
    metadata: CommandMetadata,
    order_id: OrderId,
    source_payload: Mapping[str, Any],
    source_event_name: CheckoutEventName,
) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in source_payload.items()
        if key not in {"eventName", "name", "messageId", "message_id"}
    }
    payload.update(
        {
            "commandName": _command_name_value(metadata.name),
            "commandId": str(metadata.command_id),
            "orderId": str(order_id),
            "issuedAt": metadata.issued_at.isoformat(),
            "sourceEventName": source_event_name.value,
        }
    )
    return payload


def _event_name(value: str) -> CheckoutEventName:
    try:
        return CheckoutEventName(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"unsupported checkout eventName `{value}`") from exc


def _command_name_value(value: CheckoutCommandName | str) -> str:
    if isinstance(value, CheckoutCommandName):
        return value.value
    return str(value)


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


def _optional_datetime(payload: Mapping[str, Any], *names: str) -> datetime | None:
    value = _optional_payload_text(payload, *names)
    if value is None:
        return None
    return _parse_datetime(value, names[0])


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

"""Kafka publisher contracts and client wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from token_payments.shared.adapter.messaging import JsonMessageSerializer
from token_payments.shared.domain import OutboxMessage, OutboxMessageKind


@dataclass(frozen=True)
class KafkaOutboundMessage:
    """JSON payload and headers ready for a Kafka producer."""

    topic: str
    key: str
    value: str
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "topic", _require_text(self.topic, "KafkaOutboundMessage.topic"))
        object.__setattr__(self, "key", _require_text(self.key, "KafkaOutboundMessage.key"))
        object.__setattr__(self, "value", _require_text(self.value, "KafkaOutboundMessage.value"))
        if not isinstance(self.headers, Mapping):
            raise ValueError("KafkaOutboundMessage.headers must be a mapping")
        object.__setattr__(self, "headers", MappingProxyType({str(k): str(v) for k, v in self.headers.items()}))

    @classmethod
    def from_outbox(
        cls,
        message: OutboxMessage,
        *,
        serializer: JsonMessageSerializer | None = None,
    ) -> "KafkaOutboundMessage":
        if not isinstance(message, OutboxMessage):
            raise ValueError("KafkaOutboundMessage.from_outbox requires an OutboxMessage")

        message_serializer = serializer or JsonMessageSerializer()
        envelope = message_serializer.to_dict(message)
        return cls(
            topic=message.topic,
            key=message.key,
            value=json.dumps(
                envelope["payload"],
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            headers=_headers_from_outbox(message),
        )

    def encoded_headers(self) -> list[tuple[str, bytes]]:
        return [(key, value.encode("utf-8")) for key, value in self.headers.items()]


@runtime_checkable
class KafkaPublisher(Protocol):
    def publish(self, message: KafkaOutboundMessage) -> None:
        ...


class KafkaProducerPublisher:
    """Small wrapper around an injected Kafka producer client."""

    def __init__(self, producer: Any, *, send_timeout_seconds: float | None = None) -> None:
        send = getattr(producer, "send", None)
        produce = getattr(producer, "produce", None)
        if not callable(send) and not callable(produce):
            raise ValueError("KafkaProducerPublisher requires a producer with send() or produce()")
        self._producer = producer
        self._send_timeout_seconds = send_timeout_seconds

    def publish(self, message: KafkaOutboundMessage) -> None:
        if not isinstance(message, KafkaOutboundMessage):
            raise ValueError("KafkaProducerPublisher.publish requires a KafkaOutboundMessage")

        send = getattr(self._producer, "send", None)
        if callable(send):
            result = send(
                message.topic,
                key=message.key.encode("utf-8"),
                value=message.value.encode("utf-8"),
                headers=message.encoded_headers(),
            )
            wait = getattr(result, "get", None)
            if callable(wait):
                wait(timeout=self._send_timeout_seconds)
            return

        produce = getattr(self._producer, "produce")
        produce(
            topic=message.topic,
            key=message.key.encode("utf-8"),
            value=message.value.encode("utf-8"),
            headers=message.encoded_headers(),
        )

        flush = getattr(self._producer, "flush", None)
        if callable(flush):
            flush(self._send_timeout_seconds)


def _headers_from_outbox(message: OutboxMessage) -> dict[str, str]:
    headers = {str(key): str(value) for key, value in message.headers.items()}

    correlation_id = _first_header(headers, ("correlation_id", "correlationId", "correlation-id"))
    if correlation_id is not None:
        headers.setdefault("correlation_id", correlation_id)

    causation_id = _first_header(headers, ("causation_id", "causationId", "causation-id"))
    if causation_id is not None:
        headers.setdefault("causation_id", causation_id)

    identity_header = "message_id" if message.kind is OutboxMessageKind.EVENT else "command_id"
    headers.setdefault(identity_header, message.identity)
    return headers


def _first_header(headers: Mapping[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = headers.get(name)
        if value is not None:
            return value
    return None


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()

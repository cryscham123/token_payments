"""Kafka inbound message contracts and a thin consumer loop."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from types import MappingProxyType
from typing import Any, Mapping, Protocol


_logger = logging.getLogger(__name__)


class MalformedKafkaMessage(ValueError):
    """Raised when an inbound Kafka record cannot be mapped to an application DTO."""


@dataclass(frozen=True)
class KafkaInboundMessage:
    """Normalized Kafka record passed to context-specific listeners."""

    topic: str
    key: str
    value: str | bytes
    headers: Mapping[str, str | bytes] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "topic", _require_text(self.topic, "KafkaInboundMessage.topic"))
        object.__setattr__(self, "key", _decode_text(self.key, "KafkaInboundMessage.key", allow_empty=True))
        object.__setattr__(self, "value", _decode_text(self.value, "KafkaInboundMessage.value"))
        if not isinstance(self.headers, Mapping):
            raise ValueError("KafkaInboundMessage.headers must be a mapping")
        object.__setattr__(
            self,
            "headers",
            MappingProxyType(
                {
                    _decode_text(key, "KafkaInboundMessage.header.key"): _decode_text(
                        value,
                        "KafkaInboundMessage.header.value",
                    )
                    for key, value in self.headers.items()
                }
            ),
        )

    @classmethod
    def from_record(cls, record: object) -> "KafkaInboundMessage":
        topic = getattr(record, "topic", None)
        key = getattr(record, "key", "")
        value = getattr(record, "value", None)
        headers = _headers_from_record(getattr(record, "headers", {}) or {})
        return cls(topic=topic, key=key or "", value=value, headers=headers)


class KafkaRecordListener(Protocol):
    def handle(self, message: KafkaInboundMessage) -> object:
        ...


@dataclass(frozen=True)
class KafkaConsumerLoopResult:
    processed: int


class KafkaConsumerLoop:
    """Small adapter that wraps consumer records and commits after listener success."""

    def __init__(self, consumer: object, listener: KafkaRecordListener) -> None:
        self._consumer = consumer
        self._listener = listener

    def run_batch(self, *, limit: int) -> KafkaConsumerLoopResult:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("KafkaConsumerLoop.run_batch limit must be a positive integer")

        processed = 0
        poll = getattr(self._consumer, "poll", None)
        res = None
        if callable(poll):
            try:
                res = poll(timeout_ms=0, max_records=limit)
            except Exception:
                res = None

        if isinstance(res, dict):
            records_list = []
            for partition_records in res.values():
                if isinstance(partition_records, list):
                    records_list.extend(partition_records)
            for record in records_list:
                self._handle_record(record)
                processed += 1
                self._commit()
        else:
            records = iter(self._consumer)
            while processed < limit:
                try:
                    record = next(records)
                except StopIteration:
                    break
                self._handle_record(record)
                processed += 1
                self._commit()
        return KafkaConsumerLoopResult(processed=processed)

    def _handle_record(self, record: object) -> None:
        # A malformed/poison message must not wedge the partition forever: log it and let
        # the caller commit past it. Transient errors still propagate so they can retry.
        try:
            self._listener.handle(KafkaInboundMessage.from_record(record))
        except MalformedKafkaMessage as exc:
            _logger.warning("skipping malformed Kafka record (committing past it): %s", exc)

    def _commit(self) -> None:
        commit = getattr(self._consumer, "commit", None)
        if callable(commit):
            commit()


def decode_payload(message: KafkaInboundMessage) -> Mapping[str, Any]:
    if not isinstance(message, KafkaInboundMessage):
        raise ValueError("decode_payload requires a KafkaInboundMessage")
    try:
        payload = json.loads(message.value)
    except json.JSONDecodeError as exc:
        raise MalformedKafkaMessage("Kafka message value must be valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise MalformedKafkaMessage("Kafka message value must be a JSON object")
    return payload


def header_value(message: KafkaInboundMessage, *names: str) -> str | None:
    if not isinstance(message, KafkaInboundMessage):
        raise ValueError("header_value requires a KafkaInboundMessage")
    for name in names:
        value = message.headers.get(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _headers_from_record(headers: object) -> Mapping[str, str | bytes]:
    if isinstance(headers, Mapping):
        return headers
    try:
        return {key: value for key, value in headers}  # type: ignore[union-attr]
    except (TypeError, ValueError) as exc:
        raise ValueError("Kafka record headers must be a mapping or key/value sequence") from exc


def _decode_text(value: str | bytes | object, field_name: str, *, allow_empty: bool = False) -> str:
    if isinstance(value, bytes):
        try:
            decoded = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{field_name} must be UTF-8 bytes") from exc
        return decoded if allow_empty else _require_text(decoded, field_name)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    return value.strip() if allow_empty else _require_text(value, field_name)


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()

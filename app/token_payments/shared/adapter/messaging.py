"""JSON serialization and topic resolution for adapter implementations."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import json
import math
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from token_payments.shared.domain import (
    ChainNetwork,
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    Crypto,
    CustomerId,
    MessageId,
    OrderId,
    OutboxMessage,
    PaymentId,
    ProductId,
    StoreId,
    TransactionHash,
    UserId,
    WalletAddress,
)


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]

DEFAULT_EVENT_TOPICS: Mapping[str, str] = MappingProxyType(
    {
        CheckoutEventName.ORDER_CREATED.value: "order.events",
        CheckoutEventName.INVENTORY_RESERVED.value: "inventory.events",
        CheckoutEventName.PAYMENT_CONFIRMED.value: "payment.events",
        CheckoutEventName.PAYMENT_FAILED.value: "payment.events",
        CheckoutEventName.PAYMENT_EXPIRED.value: "payment.events",
        CheckoutEventName.ORDER_APPROVED.value: "store-approval.events",
        CheckoutEventName.ORDER_REJECTED.value: "store-approval.events",
    }
)

DEFAULT_COMMAND_TOPICS: Mapping[str, str] = MappingProxyType(
    {
        CheckoutCommandName.RESERVE_INVENTORY.value: "inventory.commands",
        CheckoutCommandName.INITIATE_PAYMENT.value: "payment.commands",
        CheckoutCommandName.REQUEST_STORE_APPROVAL.value: "store-approval.commands",
        CheckoutCommandName.RELEASE_INVENTORY.value: "inventory.commands",
        CheckoutCommandName.REFUND_PAYMENT.value: "payment.commands",
        CheckoutCommandName.CANCEL_ORDER.value: "order.commands",
    }
)

_STRING_VALUE_OBJECT_TYPES = (
    CommandId,
    CustomerId,
    MessageId,
    OrderId,
    PaymentId,
    ProductId,
    StoreId,
    TransactionHash,
    UserId,
    WalletAddress,
)


class JsonMessageSerializer:
    """Serialize outbox messages into deterministic JSON-safe dictionaries."""

    def __init__(self, *, sort_keys: bool = True) -> None:
        self._sort_keys = sort_keys

    def to_dict(self, message: OutboxMessage) -> dict[str, JsonValue]:
        if not isinstance(message, OutboxMessage):
            raise ValueError("JsonMessageSerializer.to_dict requires an OutboxMessage")

        return {
            "kind": message.kind.value,
            "identity": message.identity,
            "name": message.name,
            "topic": message.topic,
            "key": message.key,
            "payload": _to_json_safe(message.payload),
            "headers": _to_json_safe(message.headers),
            "status": message.status.value,
            "created_at": message.created_at.isoformat(),
            "published_at": message.published_at.isoformat() if message.published_at is not None else None,
            "failure_count": message.failure_count,
            "last_error": message.last_error,
        }

    def dumps(self, message: OutboxMessage) -> str:
        return json.dumps(
            self.to_dict(message),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=self._sort_keys,
        )

    def loads(self, raw_message: str) -> dict[str, JsonValue]:
        if not isinstance(raw_message, str) or not raw_message.strip():
            raise ValueError("JsonMessageSerializer.loads requires a non-empty JSON string")

        decoded = json.loads(raw_message)
        if not isinstance(decoded, dict):
            raise ValueError("serialized message JSON root must be an object")
        return decoded


class MessageTopicResolver:
    """Resolve checkout event and command names to broker topic names."""

    def __init__(
        self,
        *,
        event_topics: Mapping[str | CheckoutEventName, str] | None = None,
        command_topics: Mapping[str | CheckoutCommandName, str] | None = None,
    ) -> None:
        self.event_topics = MappingProxyType(_normalize_topic_mapping(event_topics or DEFAULT_EVENT_TOPICS))
        self.command_topics = MappingProxyType(_normalize_topic_mapping(command_topics or DEFAULT_COMMAND_TOPICS))

    @classmethod
    def default(cls) -> "MessageTopicResolver":
        return cls()

    def topic_for(self, message_name: CheckoutEventName | CheckoutCommandName | str) -> str:
        name = _message_name_value(message_name)
        topic = self.event_topics.get(name) or self.command_topics.get(name)
        if topic is None:
            raise ValueError(f"no topic mapping for checkout message `{name}`")
        return topic

    def topic_for_outbox(self, message: OutboxMessage) -> str:
        if not isinstance(message, OutboxMessage):
            raise ValueError("MessageTopicResolver.topic_for_outbox requires an OutboxMessage")
        return self.topic_for(message.name)


def _normalize_topic_mapping(mapping: Mapping[str | StrEnum, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for name, topic in mapping.items():
        key = _message_name_value(name)
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("topic names must be non-empty strings")
        normalized[key] = topic.strip()
    return normalized


def _message_name_value(message_name: str | StrEnum) -> str:
    if isinstance(message_name, StrEnum):
        return message_name.value
    if not isinstance(message_name, str) or not message_name.strip():
        raise ValueError("message name must be a non-empty string")
    return message_name.strip()


def _to_json_safe(value: Any) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON message floats must be finite")
        return value

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, StrEnum):
        return value.value

    if isinstance(value, _STRING_VALUE_OBJECT_TYPES):
        return str(value)

    if isinstance(value, ChainNetwork):
        return {
            "chain_id": value.chain_id,
            "name": value.name,
        }

    if isinstance(value, Crypto):
        return {
            "amount": str(value.amount),
            "symbol": value.symbol,
            "chain_id": value.chain_id,
            "token_address": str(value.token_address) if value.token_address is not None else None,
            "decimals": value.decimals,
        }

    if isinstance(value, Mapping):
        output: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON message mapping keys must be strings")
            output[key] = _to_json_safe(item)
        return output

    if isinstance(value, tuple | list):
        return [_to_json_safe(item) for item in value]

    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _to_json_safe(getattr(value, field.name)) for field in fields(value)}

    raise TypeError(f"{type(value).__name__} is not JSON message serializable")

"""Kafka listener for StoreMembershipProjectionConsumer."""

from __future__ import annotations

from typing import Any, Mapping

from token_payments.contexts.auth.application import StoreMembershipProjectionConsumer
from token_payments.shared.adapter.kafka import KafkaInboundMessage
from token_payments.shared.adapter.kafka.listener import decode_payload


class StoreMembershipProjectionKafkaListener:
    """Deserialize RBAC projection events and dispatch them to StoreMembershipProjectionConsumer."""

    def __init__(self, consumer: StoreMembershipProjectionConsumer) -> None:
        self._consumer = consumer

    def handle(self, message: KafkaInboundMessage) -> dict[str, str] | Any:
        payload = decode_payload(message)
        return self._consumer.handle(payload)

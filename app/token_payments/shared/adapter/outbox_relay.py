"""Outbox relay that publishes committed outbox rows to Kafka."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from token_payments.shared.adapter.kafka import KafkaOutboundMessage, KafkaPublisher
from token_payments.shared.adapter.messaging import JsonMessageSerializer
from token_payments.shared.domain import OutboxMessage, OutboxMessageKind, OutboxPublishStatus


class OutboxRelayRepository(Protocol):
    def claim_ready_batch(self, *, limit: int) -> tuple[OutboxMessage, ...]:
        ...

    def mark_published(
        self,
        kind: OutboxMessageKind | str,
        identity: str,
        *,
        published_at: datetime | None = None,
    ) -> None:
        ...

    def mark_failed(self, kind: OutboxMessageKind | str, identity: str, error_message: str) -> None:
        ...


@dataclass(frozen=True)
class OutboxRelayFailure:
    kind: OutboxMessageKind
    identity: str
    error_message: str


@dataclass(frozen=True)
class OutboxRelayResult:
    claimed: int
    published: int
    failed: int
    failures: tuple[OutboxRelayFailure, ...] = ()


class OutboxRelay:
    """Claim committed outbox rows and publish them through a Kafka publisher."""

    def __init__(
        self,
        outbox_repository: OutboxRelayRepository,
        publisher: KafkaPublisher,
        *,
        serializer: JsonMessageSerializer | None = None,
    ) -> None:
        self._outbox_repository = outbox_repository
        self._publisher = publisher
        self._serializer = serializer or JsonMessageSerializer()

    def publish_batch(self, *, limit: int) -> OutboxRelayResult:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("OutboxRelay.publish_batch limit must be a positive integer")

        messages = self._outbox_repository.claim_ready_batch(limit=limit)
        published = 0
        failures: list[OutboxRelayFailure] = []

        for message in messages:
            _require_publishing(message)
            try:
                self._publisher.publish(KafkaOutboundMessage.from_outbox(message, serializer=self._serializer))
            except Exception as exc:
                error_message = _error_message(exc)
                self._outbox_repository.mark_failed(message.kind, message.identity, error_message)
                failures.append(
                    OutboxRelayFailure(
                        kind=message.kind,
                        identity=message.identity,
                        error_message=error_message,
                    )
                )
            else:
                self._outbox_repository.mark_published(message.kind, message.identity)
                published += 1

        return OutboxRelayResult(
            claimed=len(messages),
            published=published,
            failed=len(failures),
            failures=tuple(failures),
        )


def _require_publishing(message: OutboxMessage) -> None:
    if not isinstance(message, OutboxMessage):
        raise ValueError("outbox relay can publish only OutboxMessage instances")
    if message.status is not OutboxPublishStatus.PUBLISHING:
        raise ValueError("outbox relay requires claimed messages in PUBLISHING status")


def _error_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or type(exc).__name__

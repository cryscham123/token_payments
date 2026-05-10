from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.shared.adapter.kafka import KafkaOutboundMessage  # noqa: E402
from token_payments.shared.adapter.outbox_relay import OutboxRelay  # noqa: E402
from token_payments.shared.adapter.postgres import PostgresOutboxMessageRepository  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    CommandMetadata,
    EventMetadata,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    OutboxPublishStatus,
)


ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
EVENT_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
COMMAND_ID = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.RELEASE_INVENTORY)


def test_outbox_relay_claims_ready_rows_before_publishing_and_marks_success() -> None:
    connection = FakePostgresConnection()
    repository = PostgresOutboxMessageRepository(connection)
    message = _outbox_event()
    repository.save(message)
    publisher = FakeKafkaPublisher(
        before_publish=lambda outbound: _assert_row_status(
            connection,
            message.kind,
            message.identity,
            OutboxPublishStatus.PUBLISHING,
        )
    )
    relay = OutboxRelay(repository, publisher)

    result = relay.publish_batch(limit=10)

    assert result.claimed == 1
    assert result.published == 1
    assert result.failed == 0
    assert publisher.published == [
        KafkaOutboundMessage(
            topic="order.events",
            key=str(ORDER_ID),
            value=json.dumps(
                {
                    "eventName": "OrderCreatedEvent",
                    "orderId": str(ORDER_ID),
                    "attempt": 1,
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            headers={
                "causationId": "api-request-123",
                "causation_id": "api-request-123",
                "correlationId": str(ORDER_ID),
                "correlation_id": str(ORDER_ID),
                "message_id": str(EVENT_ID),
            },
        )
    ]
    row = connection.outbox[(message.kind.value, message.identity)]
    assert row["status"] == OutboxPublishStatus.PUBLISHED.value
    assert row["published_at"] is not None
    assert row["last_error"] is None


def test_outbox_relay_marks_failed_publish_without_losing_retryable_row() -> None:
    connection = FakePostgresConnection()
    repository = PostgresOutboxMessageRepository(connection)
    message = _outbox_command()
    repository.save(message)
    publisher = FakeKafkaPublisher(error=RuntimeError("broker unavailable"))
    relay = OutboxRelay(repository, publisher)

    result = relay.publish_batch(limit=10)

    assert result.claimed == 1
    assert result.published == 0
    assert result.failed == 1
    row = connection.outbox[(message.kind.value, message.identity)]
    assert row["status"] == OutboxPublishStatus.FAILED.value
    assert row["failure_count"] == 1
    assert row["last_error"] == "broker unavailable"
    assert row["published_at"] is None
    assert publisher.attempted[0].headers["command_id"] == str(COMMAND_ID)
    assert json.loads(publisher.attempted[0].value) == {
        "commandName": "ReleaseInventoryCommand",
        "orderId": str(ORDER_ID),
        "reason": "payment-expired",
    }


def test_outbox_relay_reclaims_failed_rows_and_increments_failure_count_on_retry() -> None:
    connection = FakePostgresConnection()
    repository = PostgresOutboxMessageRepository(connection)
    message = _outbox_event()
    repository.save(message)
    relay = OutboxRelay(repository, FakeKafkaPublisher(error=RuntimeError("first broker failure")))

    first = relay.publish_batch(limit=10)
    second = relay.publish_batch(limit=10)

    assert first.failed == 1
    assert second.failed == 1
    row = connection.outbox[(message.kind.value, message.identity)]
    assert row["status"] == OutboxPublishStatus.FAILED.value
    assert row["failure_count"] == 2
    assert row["last_error"] == "first broker failure"

    retry_claim_sql = _normalize_sql(connection.statements[-2].sql)
    assert "status in ('ready', 'failed')" in retry_claim_sql


def _outbox_event() -> OutboxMessage:
    occurred_at = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    metadata = EventMetadata(
        message_id=EVENT_ID,
        name=CheckoutEventName.ORDER_CREATED,
        aggregate_id=str(ORDER_ID),
        occurred_at=occurred_at,
        correlation_id=str(ORDER_ID),
        causation_id="api-request-123",
    )
    return OutboxMessage.record_event(
        metadata=metadata,
        topic="order.events",
        key=str(ORDER_ID),
        payload={
            "eventName": CheckoutEventName.ORDER_CREATED,
            "orderId": ORDER_ID,
            "attempt": 1,
        },
        headers={
            "correlationId": str(ORDER_ID),
            "causationId": "api-request-123",
        },
    )


def _outbox_command() -> OutboxMessage:
    issued_at = datetime(2026, 5, 10, 10, 1, tzinfo=UTC)
    metadata = CommandMetadata(
        command_id=COMMAND_ID,
        name=CheckoutCommandName.RELEASE_INVENTORY,
        aggregate_id=str(ORDER_ID),
        issued_at=issued_at,
        correlation_id=str(ORDER_ID),
        causation_id=str(EVENT_ID),
    )
    return OutboxMessage.record_command(
        metadata=metadata,
        topic="inventory.commands",
        key=str(ORDER_ID),
        payload={
            "commandName": CheckoutCommandName.RELEASE_INVENTORY,
            "orderId": ORDER_ID,
            "reason": "payment-expired",
        },
        headers={
            "correlationId": str(ORDER_ID),
            "causationId": str(EVENT_ID),
        },
    )


def _assert_row_status(
    connection: FakePostgresConnection,
    kind: OutboxMessageKind,
    identity: str,
    status: OutboxPublishStatus,
) -> None:
    row = connection.outbox[(kind.value, identity)]
    assert row["status"] == status.value


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().split())


@dataclass(frozen=True)
class ExecutedStatement:
    sql: str
    params: Mapping[str, Any]


class FakeKafkaPublisher:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        before_publish: Callable[[KafkaOutboundMessage], None] | None = None,
    ) -> None:
        self._error = error
        self._before_publish = before_publish
        self.published: list[KafkaOutboundMessage] = []
        self.attempted: list[KafkaOutboundMessage] = []

    def publish(self, message: KafkaOutboundMessage) -> None:
        self.attempted.append(message)
        if self._before_publish is not None:
            self._before_publish(message)
        if self._error is not None:
            raise self._error
        self.published.append(message)


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class FakePostgresConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []
        self.outbox: dict[tuple[str, str], dict[str, Any]] = {}

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> FakeResult:
        statement = ExecutedStatement(sql=sql, params=dict(params or {}))
        self.statements.append(statement)
        normalized_sql = _normalize_sql(sql)

        if "insert into outbox_messages" in normalized_sql:
            return self._insert_outbox(statement.params)
        if "with next_batch as" in normalized_sql and "outbox_messages" in normalized_sql:
            return self._claim_outbox(statement.params)
        if "update outbox_messages" in normalized_sql and "status = 'published'" in normalized_sql:
            return self._mark_outbox_published(statement.params)
        if "update outbox_messages" in normalized_sql and "status = 'failed'" in normalized_sql:
            return self._mark_outbox_failed(statement.params)
        raise AssertionError(f"unexpected SQL: {sql}")

    def _insert_outbox(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["kind"]), str(params["message_identity"]))
        if key in self.outbox:
            return FakeResult(rowcount=0)
        self.outbox[key] = dict(params) | {"id": len(self.outbox) + 1}
        return FakeResult(rowcount=1)

    def _claim_outbox(self, params: Mapping[str, Any]) -> FakeResult:
        limit = int(params["limit"])
        candidates = [
            row
            for row in self.outbox.values()
            if row["status"] in {OutboxPublishStatus.READY.value, OutboxPublishStatus.FAILED.value}
        ]
        candidates.sort(key=lambda row: row["created_at"])
        claimed = candidates[:limit]
        for row in claimed:
            row["status"] = OutboxPublishStatus.PUBLISHING.value
        return FakeResult(rows=[dict(row) for row in claimed], rowcount=len(claimed))

    def _mark_outbox_published(self, params: Mapping[str, Any]) -> FakeResult:
        row = self.outbox.get((str(params["kind"]), str(params["message_identity"])))
        if row is None or row["status"] != OutboxPublishStatus.PUBLISHING.value:
            return FakeResult(rowcount=0)
        row["status"] = OutboxPublishStatus.PUBLISHED.value
        row["published_at"] = params["published_at"]
        row["last_error"] = None
        return FakeResult(rowcount=1)

    def _mark_outbox_failed(self, params: Mapping[str, Any]) -> FakeResult:
        row = self.outbox.get((str(params["kind"]), str(params["message_identity"])))
        if row is None or row["status"] != OutboxPublishStatus.PUBLISHING.value:
            return FakeResult(rowcount=0)
        row["status"] = OutboxPublishStatus.FAILED.value
        row["failure_count"] += 1
        row["last_error"] = params["last_error"]
        row["published_at"] = None
        return FakeResult(rowcount=1)

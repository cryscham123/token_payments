from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.shared.adapter.postgres import (  # noqa: E402
    PostgresOutboxMessageRepository,
    PostgresProcessedCommandRepository,
    PostgresProcessedMessageRepository,
)
from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    EventMetadata,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    OutboxPublishStatus,
    ProcessedCommand,
    ProcessedMessage,
)


ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")


def test_outbox_repository_persists_schema_columns_and_json_payload() -> None:
    connection = FakePostgresConnection()
    repository = PostgresOutboxMessageRepository(connection)
    message = _outbox_event(
        identity="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22",
        occurred_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
    )

    repository.save(message)

    statement = connection.statements[-1]
    normalized_sql = _normalize_sql(statement.sql)
    for column_name in (
        "message_identity",
        "kind",
        "name",
        "topic",
        "message_key",
        "payload",
        "headers",
        "status",
        "created_at",
        "published_at",
        "failure_count",
        "last_error",
    ):
        assert column_name in normalized_sql

    assert "insert into outbox_messages" in normalized_sql
    assert "on conflict (kind, message_identity) do nothing" in normalized_sql

    row = connection.outbox[(message.kind.value, message.identity)]
    assert row["message_identity"] == message.identity
    assert row["message_key"] == str(ORDER_ID)
    assert row["payload"] == {
        "eventName": "OrderCreatedEvent",
        "orderId": str(ORDER_ID),
        "attempt": 1,
    }
    assert row["headers"] == {"correlationId": str(ORDER_ID)}
    assert row["status"] == OutboxPublishStatus.READY.value


def test_outbox_repository_claims_ready_and_failed_rows_as_publishing() -> None:
    connection = FakePostgresConnection()
    repository = PostgresOutboxMessageRepository(connection)
    ready = _outbox_event(
        identity="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22",
        occurred_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
    )
    failed = _outbox_event(
        identity="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23",
        occurred_at=datetime(2026, 5, 10, 10, 1, tzinfo=UTC),
    ).mark_failed("broker unavailable")
    already_published = (
        _outbox_event(
            identity="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24",
            occurred_at=datetime(2026, 5, 10, 10, 2, tzinfo=UTC),
        )
        .mark_publishing()
        .mark_published(published_at=datetime(2026, 5, 10, 10, 3, tzinfo=UTC))
    )
    repository.save(ready)
    repository.save(failed)
    repository.save(already_published)

    claimed = repository.claim_ready_batch(limit=10)

    assert [message.identity for message in claimed] == [ready.identity, failed.identity]
    assert {message.status for message in claimed} == {OutboxPublishStatus.PUBLISHING}
    assert connection.outbox[(ready.kind.value, ready.identity)]["status"] == OutboxPublishStatus.PUBLISHING.value
    assert connection.outbox[(failed.kind.value, failed.identity)]["status"] == OutboxPublishStatus.PUBLISHING.value
    assert (
        connection.outbox[(already_published.kind.value, already_published.identity)]["status"]
        == OutboxPublishStatus.PUBLISHED.value
    )

    claim_sql = _normalize_sql(connection.statements[-1].sql)
    assert "with next_batch as" in claim_sql
    assert "status in ('ready', 'failed')" in claim_sql
    assert "for update skip locked" in claim_sql
    assert "returning" in claim_sql


def test_outbox_repository_marks_published_and_failed_with_explicit_publish_statuses() -> None:
    connection = FakePostgresConnection()
    repository = PostgresOutboxMessageRepository(connection)
    published_at = datetime(2026, 5, 10, 10, 4, tzinfo=UTC)
    success = _outbox_event(
        identity="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22",
        occurred_at=datetime(2026, 5, 10, 10, 0, tzinfo=UTC),
    )
    failure = _outbox_event(
        identity="018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23",
        occurred_at=datetime(2026, 5, 10, 10, 1, tzinfo=UTC),
    )
    repository.save(success)
    repository.save(failure)
    repository.claim_ready_batch(limit=1)

    repository.mark_published(success.kind, success.identity, published_at=published_at)
    success_row = connection.outbox[(success.kind.value, success.identity)]
    assert success_row["status"] == OutboxPublishStatus.PUBLISHED.value
    assert success_row["published_at"] == published_at
    assert success_row["last_error"] is None

    with pytest.raises(ValueError, match="PUBLISHING"):
        repository.mark_failed(success.kind, success.identity, "late publish failure")

    repository.claim_ready_batch(limit=1)
    repository.mark_failed(failure.kind, failure.identity, "broker unavailable")
    failure_row = connection.outbox[(failure.kind.value, failure.identity)]
    assert failure_row["status"] == OutboxPublishStatus.FAILED.value
    assert failure_row["failure_count"] == 1
    assert failure_row["last_error"] == "broker unavailable"

    status_values = {row["status"] for row in connection.outbox.values()}
    assert status_values <= {status.value for status in OutboxPublishStatus}
    assert status_values.isdisjoint({"pending", "completed", "error", "blocked"})

    transition_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "status = 'published'" in transition_sql
    assert "status = 'failed'" in transition_sql
    assert "failure_count = failure_count + 1" in transition_sql
    assert "and status = 'publishing'" in transition_sql


def test_processed_message_repository_detects_duplicates_by_consumer_and_message_id() -> None:
    connection = FakePostgresConnection()
    repository = PostgresProcessedMessageRepository(connection)
    processed = ProcessedMessage.record(
        message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"),
        consumer="checkout-process-manager",
        processed_at=datetime(2026, 5, 10, 10, 5, tzinfo=UTC),
        order_id=ORDER_ID,
    )

    assert repository.record(processed) == IdempotencyDecision.PROCESS
    assert repository.was_processed(processed.message_id, processed.consumer) is True
    assert repository.record(processed) == IdempotencyDecision.IGNORE_DUPLICATE

    same_message_other_consumer = ProcessedMessage.record(
        message_id=processed.message_id,
        consumer="order-status-listener",
        processed_at=datetime(2026, 5, 10, 10, 6, tzinfo=UTC),
        order_id=ORDER_ID,
    )
    assert repository.record(same_message_other_consumer) == IdempotencyDecision.PROCESS

    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "insert into processed_messages" in normalized_sql
    assert "consumer" in normalized_sql
    assert "message_id" in normalized_sql
    assert "order_id" in normalized_sql
    assert "on conflict (consumer, message_id) do nothing" in normalized_sql


def test_processed_command_repository_detects_duplicates_by_handler_and_command_id() -> None:
    connection = FakePostgresConnection()
    repository = PostgresProcessedCommandRepository(connection)
    command_id = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.RELEASE_INVENTORY)
    processed = ProcessedCommand.record(
        command_id=command_id,
        handler="inventory-command-handler",
        processed_at=datetime(2026, 5, 10, 10, 7, tzinfo=UTC),
        order_id=ORDER_ID,
    )

    assert repository.record(processed) == IdempotencyDecision.PROCESS
    assert repository.was_processed(processed.command_id, processed.handler) is True
    assert repository.record(processed) == IdempotencyDecision.IGNORE_DUPLICATE

    same_command_other_handler = ProcessedCommand.record(
        command_id=processed.command_id,
        handler="payment-command-handler",
        processed_at=datetime(2026, 5, 10, 10, 8, tzinfo=UTC),
        order_id=ORDER_ID,
    )
    assert repository.record(same_command_other_handler) == IdempotencyDecision.PROCESS

    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "insert into processed_commands" in normalized_sql
    assert "handler" in normalized_sql
    assert "command_id" in normalized_sql
    assert "order_id" in normalized_sql
    assert "on conflict (handler, command_id) do nothing" in normalized_sql


def _outbox_event(identity: str, occurred_at: datetime) -> OutboxMessage:
    metadata = EventMetadata(
        message_id=MessageId(identity),
        name=CheckoutEventName.ORDER_CREATED,
        aggregate_id=str(ORDER_ID),
        occurred_at=occurred_at,
        correlation_id=str(ORDER_ID),
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
        headers={"correlationId": str(ORDER_ID)},
    )


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().split())


@dataclass(frozen=True)
class ExecutedStatement:
    sql: str
    params: Mapping[str, Any]


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def fetchone(self) -> dict[str, Any] | None:
        if not self._rows:
            return None
        return self._rows[0]


class FakePostgresConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []
        self.outbox: dict[tuple[str, str], dict[str, Any]] = {}
        self.processed_messages: set[tuple[str, str]] = set()
        self.processed_commands: set[tuple[str, str]] = set()

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
        if "select 1 from processed_messages" in normalized_sql:
            return self._select_processed_message(statement.params)
        if "insert into processed_messages" in normalized_sql:
            return self._insert_processed_message(statement.params)
        if "select 1 from processed_commands" in normalized_sql:
            return self._select_processed_command(statement.params)
        if "insert into processed_commands" in normalized_sql:
            return self._insert_processed_command(statement.params)
        raise AssertionError(f"unexpected SQL: {sql}")

    def _insert_outbox(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["kind"]), str(params["message_identity"]))
        if key in self.outbox:
            return FakeResult(rowcount=0)
        stored_params = dict(params)
        for field in ("payload", "headers"):
            if field in stored_params and isinstance(stored_params[field], str):
                import json
                try:
                    stored_params[field] = json.loads(stored_params[field])
                except Exception:
                    pass
        self.outbox[key] = stored_params | {"id": len(self.outbox) + 1}
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

    def _select_processed_message(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["consumer"]), str(params["message_id"]))
        rows = [{"exists": 1}] if key in self.processed_messages else []
        return FakeResult(rows=rows, rowcount=len(rows))

    def _insert_processed_message(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["consumer"]), str(params["message_id"]))
        if key in self.processed_messages:
            return FakeResult(rowcount=0)
        self.processed_messages.add(key)
        return FakeResult(rows=[{"inserted": 1}], rowcount=1)

    def _select_processed_command(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["handler"]), str(params["command_id"]))
        rows = [{"exists": 1}] if key in self.processed_commands else []
        return FakeResult(rows=rows, rowcount=len(rows))

    def _insert_processed_command(self, params: Mapping[str, Any]) -> FakeResult:
        key = (str(params["handler"]), str(params["command_id"]))
        if key in self.processed_commands:
            return FakeResult(rowcount=0)
        self.processed_commands.add(key)
        return FakeResult(rows=[{"inserted": 1}], rowcount=1)

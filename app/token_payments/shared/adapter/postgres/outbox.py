"""PostgreSQL-backed outbox repository adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from token_payments.shared.adapter.messaging import JsonMessageSerializer
from token_payments.shared.domain import OutboxMessage, OutboxMessageKind, OutboxPublishStatus

from .protocols import PostgresConnection


SAVE_OUTBOX_SQL = """
INSERT INTO outbox_messages (
    message_identity,
    kind,
    name,
    topic,
    message_key,
    payload,
    headers,
    status,
    created_at,
    published_at,
    failure_count,
    last_error
) VALUES (
    %(message_identity)s,
    %(kind)s,
    %(name)s,
    %(topic)s,
    %(message_key)s,
    %(payload)s,
    %(headers)s,
    %(status)s,
    %(created_at)s,
    %(published_at)s,
    %(failure_count)s,
    %(last_error)s
)
ON CONFLICT (kind, message_identity) DO NOTHING
"""

CLAIM_READY_BATCH_SQL = """
WITH next_batch AS (
    SELECT id
    FROM outbox_messages
    WHERE status IN ('READY', 'FAILED')
    ORDER BY created_at
    LIMIT %(limit)s
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_messages AS outbox
SET status = 'PUBLISHING'
FROM next_batch
WHERE outbox.id = next_batch.id
RETURNING
    outbox.id,
    outbox.message_identity,
    outbox.kind,
    outbox.name,
    outbox.topic,
    outbox.message_key,
    outbox.payload,
    outbox.headers,
    outbox.status,
    outbox.created_at,
    outbox.published_at,
    outbox.failure_count,
    outbox.last_error
"""

MARK_PUBLISHED_SQL = """
UPDATE outbox_messages
SET
    status = 'PUBLISHED',
    published_at = %(published_at)s,
    last_error = NULL
WHERE kind = %(kind)s
  AND message_identity = %(message_identity)s
  AND status = 'PUBLISHING'
"""

MARK_FAILED_SQL = """
UPDATE outbox_messages
SET
    status = 'FAILED',
    published_at = NULL,
    failure_count = failure_count + 1,
    last_error = %(last_error)s
WHERE kind = %(kind)s
  AND message_identity = %(message_identity)s
  AND status = 'PUBLISHING'
"""


class PostgresOutboxMessageRepository:
    """Persist and transition outbox rows inside an injected transaction."""

    def __init__(
        self,
        connection: PostgresConnection,
        *,
        serializer: JsonMessageSerializer | None = None,
    ) -> None:
        self._connection = connection
        self._serializer = serializer or JsonMessageSerializer()

    def save(self, message: OutboxMessage) -> None:
        if not isinstance(message, OutboxMessage):
            raise ValueError("PostgresOutboxMessageRepository.save requires an OutboxMessage")

        envelope = self._serializer.to_dict(message)
        self._connection.execute(
            SAVE_OUTBOX_SQL,
            {
                "message_identity": envelope["identity"],
                "kind": envelope["kind"],
                "name": envelope["name"],
                "topic": envelope["topic"],
                "message_key": envelope["key"],
                "payload": envelope["payload"],
                "headers": envelope["headers"],
                "status": envelope["status"],
                "created_at": message.created_at,
                "published_at": message.published_at,
                "failure_count": message.failure_count,
                "last_error": message.last_error,
            },
        )

    def claim_ready_batch(self, *, limit: int) -> tuple[OutboxMessage, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("claim_ready_batch limit must be a positive integer")

        result = self._connection.execute(CLAIM_READY_BATCH_SQL, {"limit": limit})
        return tuple(_row_to_outbox_message(row) for row in _fetch_all(result))

    def mark_published(
        self,
        kind: OutboxMessageKind | str,
        identity: str,
        *,
        published_at: datetime | None = None,
    ) -> None:
        params = {
            "kind": _kind_value(kind),
            "message_identity": _require_text(identity, "identity"),
            "published_at": published_at or datetime.now(UTC),
        }
        result = self._connection.execute(MARK_PUBLISHED_SQL, params)
        _require_updated(result, "PUBLISHING outbox message to mark as PUBLISHED")

    def mark_failed(self, kind: OutboxMessageKind | str, identity: str, error_message: str) -> None:
        params = {
            "kind": _kind_value(kind),
            "message_identity": _require_text(identity, "identity"),
            "last_error": _require_text(error_message, "error_message"),
        }
        result = self._connection.execute(MARK_FAILED_SQL, params)
        _require_updated(result, "PUBLISHING outbox message to mark as FAILED")


def _row_to_outbox_message(row: Mapping[str, Any] | object) -> OutboxMessage:
    return OutboxMessage(
        kind=OutboxMessageKind(_row_value(row, "kind")),
        identity=str(_row_value(row, "message_identity")),
        name=str(_row_value(row, "name")),
        topic=str(_row_value(row, "topic")),
        key=str(_row_value(row, "message_key")),
        payload=_mapping_value(_row_value(row, "payload"), "payload"),
        headers=_mapping_value(_row_value(row, "headers"), "headers"),
        status=OutboxPublishStatus(_row_value(row, "status")),
        created_at=_row_value(row, "created_at"),
        published_at=_row_value(row, "published_at"),
        failure_count=int(_row_value(row, "failure_count")),
        last_error=_row_value(row, "last_error"),
    )


def _fetch_all(result: Any) -> list[Any]:
    if result is None:
        return []
    fetchall = getattr(result, "fetchall", None)
    if callable(fetchall):
        return list(fetchall())
    return list(result)


def _require_updated(result: Any, action: str) -> None:
    rowcount = getattr(result, "rowcount", None)
    if rowcount == 0:
        raise ValueError(f"expected a {action}")


def _kind_value(kind: OutboxMessageKind | str) -> str:
    if isinstance(kind, OutboxMessageKind):
        return kind.value
    return OutboxMessageKind(_require_text(kind, "kind")).value


def _mapping_value(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"outbox row {field_name} must be a mapping")
    return value


def _row_value(row: Mapping[str, Any] | object, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return getattr(row, key)


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


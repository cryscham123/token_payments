"""PostgreSQL idempotency repositories for processed messages and commands."""

from __future__ import annotations

from typing import Any

from token_payments.shared.domain import (
    CommandId,
    IdempotencyDecision,
    MessageId,
    ProcessedCommand,
    ProcessedMessage,
)

from .protocols import PostgresConnection


SELECT_PROCESSED_MESSAGE_SQL = """
SELECT 1
FROM processed_messages
WHERE consumer = %(consumer)s
  AND message_id = %(message_id)s
"""

INSERT_PROCESSED_MESSAGE_SQL = """
INSERT INTO processed_messages (
    consumer,
    message_id,
    order_id,
    processed_at
) VALUES (
    %(consumer)s,
    %(message_id)s,
    %(order_id)s,
    %(processed_at)s
)
ON CONFLICT (consumer, message_id) DO NOTHING
RETURNING 1 AS inserted
"""

SELECT_PROCESSED_COMMAND_SQL = """
SELECT 1
FROM processed_commands
WHERE handler = %(handler)s
  AND command_id = %(command_id)s
"""

INSERT_PROCESSED_COMMAND_SQL = """
INSERT INTO processed_commands (
    handler,
    command_id,
    order_id,
    processed_at
) VALUES (
    %(handler)s,
    %(command_id)s,
    %(order_id)s,
    %(processed_at)s
)
ON CONFLICT (handler, command_id) DO NOTHING
RETURNING 1 AS inserted
"""


class PostgresProcessedMessageRepository:
    """Record consumed event message ids by consumer."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def was_processed(self, message_id: MessageId, consumer: str) -> bool:
        if not isinstance(message_id, MessageId):
            raise ValueError("was_processed message_id must be a MessageId")
        result = self._connection.execute(
            SELECT_PROCESSED_MESSAGE_SQL,
            {
                "consumer": _require_text(consumer, "consumer"),
                "message_id": str(message_id),
            },
        )
        return _fetch_one(result) is not None

    def record(self, processed_message: ProcessedMessage) -> IdempotencyDecision:
        if not isinstance(processed_message, ProcessedMessage):
            raise ValueError("record requires a ProcessedMessage")
        result = self._connection.execute(
            INSERT_PROCESSED_MESSAGE_SQL,
            {
                "consumer": processed_message.consumer,
                "message_id": str(processed_message.message_id),
                "order_id": str(processed_message.order_id) if processed_message.order_id is not None else None,
                "processed_at": processed_message.processed_at,
            },
        )
        return _insert_decision(result)


class PostgresProcessedCommandRepository:
    """Record handled command ids by handler."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        if not isinstance(command_id, CommandId):
            raise ValueError("was_processed command_id must be a CommandId")
        result = self._connection.execute(
            SELECT_PROCESSED_COMMAND_SQL,
            {
                "handler": _require_text(handler, "handler"),
                "command_id": str(command_id),
            },
        )
        return _fetch_one(result) is not None

    def record(self, processed_command: ProcessedCommand) -> IdempotencyDecision:
        if not isinstance(processed_command, ProcessedCommand):
            raise ValueError("record requires a ProcessedCommand")
        result = self._connection.execute(
            INSERT_PROCESSED_COMMAND_SQL,
            {
                "handler": processed_command.handler,
                "command_id": str(processed_command.command_id),
                "order_id": str(processed_command.order_id) if processed_command.order_id is not None else None,
                "processed_at": processed_command.processed_at,
            },
        )
        return _insert_decision(result)


def _insert_decision(result: Any) -> IdempotencyDecision:
    if _fetch_one(result) is not None:
        return IdempotencyDecision.PROCESS
    rowcount = getattr(result, "rowcount", None)
    if rowcount is not None and rowcount > 0:
        return IdempotencyDecision.PROCESS
    return IdempotencyDecision.IGNORE_DUPLICATE


def _fetch_one(result: Any) -> Any:
    if result is None:
        return None
    fetchone = getattr(result, "fetchone", None)
    if callable(fetchone):
        return fetchone()
    iterator = iter(result)
    return next(iterator, None)


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


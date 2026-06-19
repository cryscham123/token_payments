"""Kafka command listener for the store approval context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from token_payments.contexts.store_approval.application import RequestStoreApprovalCommand, StoreApprovalService
from token_payments.shared.adapter.kafka import KafkaInboundMessage, MalformedKafkaMessage
from token_payments.shared.adapter.kafka.listener import decode_payload, header_value
from token_payments.shared.domain import (
    CheckoutCommandName,
    CommandId,
    IdempotencyDecision,
    MessageId,
    OrderId,
    ProcessedCommand,
    StoreId,
    UserId,
)


class ProcessedCommandRepository(Protocol):
    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        ...

    def record(self, processed_command: ProcessedCommand) -> IdempotencyDecision:
        ...


@dataclass(frozen=True)
class StoreApprovalKafkaListenerResult:
    command_id: CommandId
    order_id: OrderId
    handler_result: object | None = None
    duplicate_decision: IdempotencyDecision | None = None


class StoreApprovalKafkaCommandListener:
    """Deserialize store approval commands and dispatch them to StoreApprovalService."""

    HANDLER_NAME = StoreApprovalService.HANDLER_NAME

    def __init__(
        self,
        service: StoreApprovalService,
        processed_commands: ProcessedCommandRepository,
    ) -> None:
        self._service = service
        self._processed_commands = processed_commands

    def handle(self, message: KafkaInboundMessage) -> StoreApprovalKafkaListenerResult:
        payload = decode_payload(message)
        command_id = _command_id(_required_command_id(message, payload))
        command_name = _command_name(_required_payload_text(payload, "commandName", "name", field_name="commandName"))
        order_id = _order_id(_required_payload_text(payload, "orderId", "order_id", field_name="orderId"))
        handler_name = getattr(self._service, "HANDLER_NAME", self.HANDLER_NAME)

        if self._processed_commands.was_processed(command_id, handler_name):
            return StoreApprovalKafkaListenerResult(
                command_id=command_id,
                order_id=order_id,
                duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
            )

        if command_name is not CheckoutCommandName.REQUEST_STORE_APPROVAL:
            raise MalformedKafkaMessage(f"unsupported store approval commandName `{command_name.value}`")

        store_id_str = _optional_payload_text(payload, "storeId", "store_id")
        owner_user_id_str = _optional_payload_text(payload, "ownerUserId", "owner_user_id")

        if store_id_str is None or owner_user_id_str is None:
            order_detail = self._service._order_detail_repository.get(order_id)
            if order_detail is not None:
                if store_id_str is None:
                    store_id_str = str(order_detail.store_id)
                if owner_user_id_str is None:
                    store = self._service._store_repository.get(order_detail.store_id)
                    if store is not None:
                        owner_user_id_str = str(store.owner_user_id)

        if store_id_str is None or owner_user_id_str is None:
            import logging
            logger = logging.getLogger("store_approval")
            logger.warning(
                f"Ignoring RequestStoreApprovalCommand for order {order_id} because "
                f"storeId or ownerUserId could not be resolved (stale/missing order or wiped database)."
            )
            return StoreApprovalKafkaListenerResult(
                command_id=command_id,
                order_id=order_id,
                duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
            )

        command = RequestStoreApprovalCommand(
            command_id=command_id,
            order_id=order_id,
            store_id=_store_id(_required_text(store_id_str, "storeId")),
            owner_user_id=_user_id(_required_text(owner_user_id_str, "ownerUserId")),
            requested_at=_command_time(payload),
            rejection_reason=_optional_payload_text(payload, "rejectionReason", "rejection_reason"),
            causation_id=_causation_id(message, payload),
            event_message_id=_event_message_id(payload),
            items=_optional_items(payload),
        )
        handler_result = self._service.request_store_approval(command)
        return StoreApprovalKafkaListenerResult(command_id=command_id, order_id=order_id, handler_result=handler_result)


def _required_command_id(message: KafkaInboundMessage, payload: Mapping[str, Any]) -> str:
    return _required_text(
        header_value(message, "command_id", "commandId")
        or _optional_payload_text(payload, "commandId", "command_id"),
        "commandId",
    )


def _command_name(value: str) -> CheckoutCommandName:
    try:
        return CheckoutCommandName(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"unsupported commandName `{value}`") from exc


def _command_id(value: str) -> CommandId:
    try:
        return CommandId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"commandId must be valid: {value}") from exc


def _order_id(value: str) -> OrderId:
    try:
        return OrderId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"orderId must be a valid OrderId: {value}") from exc


def _store_id(value: str) -> StoreId:
    try:
        return StoreId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"storeId must be a valid StoreId: {value}") from exc


def _user_id(value: str) -> UserId:
    try:
        return UserId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"ownerUserId must be a valid UserId: {value}") from exc


def _event_message_id(payload: Mapping[str, Any]) -> MessageId:
    value = _optional_payload_text(payload, "eventMessageId", "event_message_id")
    if value is None:
        return MessageId.new()
    try:
        return MessageId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"eventMessageId must be a valid MessageId: {value}") from exc


def _command_time(payload: Mapping[str, Any]) -> datetime:
    value = _optional_payload_text(payload, "requestedAt", "issuedAt", "requested_at", "issued_at")
    if value is None:
        return datetime.now(UTC)
    return _parse_datetime(value, "requestedAt")


def _causation_id(message: KafkaInboundMessage, payload: Mapping[str, Any]) -> str | None:
    return (
        header_value(message, "causation_id", "causationId")
        or _optional_payload_text(payload, "causationId", "causation_id", "sourceMessageId")
    )


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


def _optional_items(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    value = payload.get("items")
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise MalformedKafkaMessage("items must be a JSON array")
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise MalformedKafkaMessage("items must contain JSON objects")
        items.append(dict(item))
    return tuple(items)


def _required_text(value: str | None, field_name: str) -> str:
    if value is None or not value.strip():
        raise MalformedKafkaMessage(f"payload missing {field_name}")
    return value.strip()

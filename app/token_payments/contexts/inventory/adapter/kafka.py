"""Kafka command listener for the inventory context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from token_payments.contexts.inventory.application import (
    ConfirmInventoryCommand,
    InventoryCommandHandler,
    ReleaseInventoryCommand,
    ReserveInventoryCommand,
)
from token_payments.shared.adapter.kafka import KafkaInboundMessage, MalformedKafkaMessage
from token_payments.shared.adapter.kafka.listener import decode_payload, header_value
from token_payments.shared.domain import (
    CheckoutCommandName,
    CommandId,
    IdempotencyDecision,
    MessageId,
    OrderId,
    ProcessedCommand,
    ProductId,
    StoreId,
)


class ProcessedCommandRepository(Protocol):
    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        ...

    def record(self, processed_command: ProcessedCommand) -> IdempotencyDecision:
        ...


@dataclass(frozen=True)
class InventoryKafkaListenerResult:
    command_id: CommandId
    order_id: OrderId
    handler_result: object | None = None
    duplicate_decision: IdempotencyDecision | None = None


class InventoryKafkaCommandListener:
    """Deserialize inventory commands and dispatch them to InventoryCommandHandler."""

    HANDLER_NAME = InventoryCommandHandler.HANDLER_NAME

    def __init__(
        self,
        command_handler: InventoryCommandHandler,
        processed_commands: ProcessedCommandRepository,
    ) -> None:
        self._command_handler = command_handler
        self._processed_commands = processed_commands

    def handle(self, message: KafkaInboundMessage) -> InventoryKafkaListenerResult:
        payload = decode_payload(message)
        command_id = _command_id(_required_command_id(message, payload))
        command_name = _command_name(_required_payload_text(payload, "commandName", "name", field_name="commandName"))
        order_id = _order_id(_required_payload_text(payload, "orderId", "order_id", field_name="orderId"))
        handler_name = getattr(self._command_handler, "HANDLER_NAME", self.HANDLER_NAME)

        if self._processed_commands.was_processed(command_id, handler_name):
            return InventoryKafkaListenerResult(
                command_id=command_id,
                order_id=order_id,
                duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
            )

        if command_name is CheckoutCommandName.RESERVE_INVENTORY:
            command = ReserveInventoryCommand(
                command_id=command_id,
                order_id=order_id,
                product_id=_product_id(_required_payload_text(payload, "productId", "product_id", field_name="productId")),
                store_id=_store_id(_required_payload_text(payload, "storeId", "store_id", field_name="storeId")),
                quantity=_positive_int(_required_payload_value(payload, "quantity"), "quantity"),
                public_variant_id=_optional_payload_text(payload, "publicVariantId", "public_variant_id"),
                requested_at=_command_time(payload),
                causation_id=_causation_id(message, payload),
                event_message_id=_event_message_id(payload),
                items=_optional_items(payload),
            )
            handler_result = self._command_handler.reserve_inventory(command)
        elif command_name is CheckoutCommandName.RELEASE_INVENTORY:
            command = ReleaseInventoryCommand(
                command_id=command_id,
                order_id=order_id,
                product_id=_product_id(_required_payload_text(payload, "productId", "product_id", field_name="productId")),
                store_id=_store_id(_required_payload_text(payload, "storeId", "store_id", field_name="storeId")),
                public_variant_id=_optional_payload_text(payload, "publicVariantId", "public_variant_id"),
                requested_at=_command_time(payload),
                causation_id=_causation_id(message, payload),
                event_message_id=_event_message_id(payload),
                items=_optional_items(payload),
            )
            handler_result = self._command_handler.release_inventory(command)
        elif command_name is CheckoutCommandName.CONFIRM_INVENTORY:
            command = ConfirmInventoryCommand(
                command_id=command_id,
                order_id=order_id,
                product_id=_product_id(_required_payload_text(payload, "productId", "product_id", field_name="productId")),
                store_id=_store_id(_required_payload_text(payload, "storeId", "store_id", field_name="storeId")),
                public_variant_id=_optional_payload_text(payload, "publicVariantId", "public_variant_id"),
                requested_at=_command_time(payload),
                causation_id=_causation_id(message, payload),
                event_message_id=_event_message_id(payload),
                items=_optional_items(payload),
            )
            handler_result = self._command_handler.confirm_inventory(command)
        else:
            raise MalformedKafkaMessage(f"unsupported inventory commandName `{command_name.value}`")

        return InventoryKafkaListenerResult(command_id=command_id, order_id=order_id, handler_result=handler_result)


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


def _product_id(value: str) -> ProductId:
    try:
        return ProductId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"productId must be a valid ProductId: {value}") from exc


def _store_id(value: str) -> StoreId:
    try:
        return StoreId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"storeId must be a valid StoreId: {value}") from exc


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


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise MalformedKafkaMessage(f"{field_name} must be a positive integer")
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise MalformedKafkaMessage(f"{field_name} must be a positive integer") from exc
    if parsed <= 0:
        raise MalformedKafkaMessage(f"{field_name} must be a positive integer")
    return parsed


def _required_payload_text(payload: Mapping[str, Any], *names: str, field_name: str) -> str:
    return _required_text(_optional_payload_text(payload, *names), field_name)


def _required_payload_value(payload: Mapping[str, Any], name: str) -> object:
    if name not in payload or payload[name] is None:
        raise MalformedKafkaMessage(f"payload missing {name}")
    return payload[name]


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


def _optional_payload_text(payload: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = payload.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _required_text(value: str | None, field_name: str) -> str:
    if value is None or not value.strip():
        raise MalformedKafkaMessage(f"payload missing {field_name}")
    return value.strip()

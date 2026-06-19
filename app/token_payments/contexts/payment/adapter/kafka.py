"""Kafka command listener for the payment context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from token_payments.contexts.payment.application import (
    InitiatePaymentCommand,
    PaymentCommandHandler,
    RefundPaymentCommand,
)
from token_payments.shared.adapter.kafka import KafkaInboundMessage, MalformedKafkaMessage
from token_payments.shared.adapter.kafka.listener import decode_payload, header_value
from token_payments.shared.domain import (
    ChainNetwork,
    CheckoutCommandName,
    CommandId,
    Crypto,
    CustomerId,
    IdempotencyDecision,
    MessageId,
    OrderId,
    PaymentId,
    ProcessedCommand,
    UserId,
    WalletAddress,
)


class ProcessedCommandRepository(Protocol):
    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        ...

    def record(self, processed_command: ProcessedCommand) -> IdempotencyDecision:
        ...


@dataclass(frozen=True)
class PaymentKafkaListenerResult:
    command_id: CommandId
    order_id: OrderId
    handler_result: object | None = None
    duplicate_decision: IdempotencyDecision | None = None


class PaymentKafkaCommandListener:
    """Deserialize payment commands and dispatch them to PaymentCommandHandler."""

    HANDLER_NAME = PaymentCommandHandler.HANDLER_NAME

    def __init__(
        self,
        command_handler: PaymentCommandHandler,
        processed_commands: ProcessedCommandRepository,
    ) -> None:
        self._command_handler = command_handler
        self._processed_commands = processed_commands

    def handle(self, message: KafkaInboundMessage) -> PaymentKafkaListenerResult:
        payload = decode_payload(message)
        command_id = _command_id(_required_command_id(message, payload))
        command_name = _command_name(_required_payload_text(payload, "commandName", "name", field_name="commandName"))
        order_id = _order_id(_required_payload_text(payload, "orderId", "order_id", field_name="orderId"))
        handler_name = getattr(self._command_handler, "HANDLER_NAME", self.HANDLER_NAME)

        if self._processed_commands.was_processed(command_id, handler_name):
            return PaymentKafkaListenerResult(
                command_id=command_id,
                order_id=order_id,
                duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
            )

        if command_name is CheckoutCommandName.INITIATE_PAYMENT:
            command = InitiatePaymentCommand(
                command_id=command_id,
                payment_id=_payment_id(
                    _required_payload_text(payload, "paymentId", "payment_id", field_name="paymentId")
                ),
                order_id=order_id,
                customer_id=_customer_id(
                    _required_payload_text(payload, "customerId", "customer_id", field_name="customerId")
                ),
                user_id=_user_id(_required_payload_text(payload, "userId", "user_id", field_name="userId")),
                amount=_crypto(_required_mapping(payload, "amount")),
                wallet_from=_wallet(
                    _required_payload_text(payload, "walletFrom", "wallet_from", field_name="walletFrom"),
                    "walletFrom",
                ),
                wallet_to=_wallet(
                    _required_payload_text(payload, "walletTo", "wallet_to", field_name="walletTo"),
                    "walletTo",
                ),
                chain_network=_chain_network(_required_mapping(payload, "chain", "chainNetwork", "chain_network")),
                expires_at=_parse_datetime(
                    _required_payload_text(payload, "expiresAt", "expires_at", field_name="expiresAt"),
                    "expiresAt",
                ),
                requested_at=_command_time(payload),
                causation_id=_causation_id(message, payload),
                event_message_id=_event_message_id(payload),
                payer_wallet_id=_optional_payload_text(payload, "payerWalletId", "payer_wallet_id"),
                payment_asset_id=_optional_payload_text(payload, "paymentAssetId", "payment_asset_id"),
                items=_optional_items(payload),
            )
            handler_result = self._command_handler.initiate_payment(command)
        elif command_name is CheckoutCommandName.REFUND_PAYMENT:
            command = RefundPaymentCommand(
                command_id=command_id,
                payment_id=_payment_id(
                    _required_payload_text(payload, "paymentId", "payment_id", field_name="paymentId")
                ),
                order_id=order_id,
                requested_at=_command_time(payload),
                causation_id=_causation_id(message, payload),
                event_message_id=_event_message_id(payload),
            )
            handler_result = self._command_handler.refund_payment(command)
        else:
            raise MalformedKafkaMessage(f"unsupported payment commandName `{command_name.value}`")

        return PaymentKafkaListenerResult(command_id=command_id, order_id=order_id, handler_result=handler_result)


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


def _payment_id(value: str) -> PaymentId:
    try:
        return PaymentId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"paymentId must be a valid PaymentId: {value}") from exc


def _customer_id(value: str) -> CustomerId:
    try:
        return CustomerId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"customerId must be a valid CustomerId: {value}") from exc


def _user_id(value: str) -> UserId:
    try:
        return UserId(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"userId must be a valid UserId: {value}") from exc


def _wallet(value: str, field_name: str) -> WalletAddress:
    try:
        return WalletAddress(value)
    except ValueError as exc:
        raise MalformedKafkaMessage(f"{field_name} must be a valid WalletAddress: {value}") from exc


def _crypto(payload: Mapping[str, Any]) -> Crypto:
    try:
        return Crypto(
            amount=_required_payload_text(payload, "amount", field_name="amount"),
            symbol=_required_payload_text(payload, "symbol", field_name="symbol"),
            chain_id=_positive_int(_required_payload_value(payload, "chainId", "chain_id"), "chainId"),
            token_address=_optional_payload_text(payload, "tokenAddress", "token_address"),
            decimals=_non_negative_int(_required_payload_value(payload, "decimals"), "decimals"),
        )
    except ValueError as exc:
        raise MalformedKafkaMessage(str(exc)) from exc


def _chain_network(payload: Mapping[str, Any]) -> ChainNetwork:
    try:
        return ChainNetwork(
            chain_id=_positive_int(_required_payload_value(payload, "chainId", "chain_id"), "chainId"),
            name=_required_payload_text(payload, "name", field_name="name"),
        )
    except ValueError as exc:
        raise MalformedKafkaMessage(str(exc)) from exc


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
    parsed = _int(value, field_name)
    if parsed <= 0:
        raise MalformedKafkaMessage(f"{field_name} must be a positive integer")
    return parsed


def _non_negative_int(value: object, field_name: str) -> int:
    parsed = _int(value, field_name)
    if parsed < 0:
        raise MalformedKafkaMessage(f"{field_name} must be a non-negative integer")
    return parsed


def _int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise MalformedKafkaMessage(f"{field_name} must be an integer")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise MalformedKafkaMessage(f"{field_name} must be an integer") from exc


def _required_mapping(payload: Mapping[str, Any], *names: str) -> Mapping[str, Any]:
    for name in names:
        value = payload.get(name)
        if value is not None:
            if isinstance(value, Mapping):
                return value
            raise MalformedKafkaMessage(f"{name} must be a JSON object")
    raise MalformedKafkaMessage(f"payload missing {names[0]}")


def _optional_items(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    value = payload.get("items")
    if value is None:
        return _single_item_from_inventory_payload(payload)
    if not isinstance(value, list | tuple):
        raise MalformedKafkaMessage("items must be a JSON array")
    # Order items are store-agnostic, but downstream RELEASE/CONFIRM inventory commands
    # (built from payment events) require a storeId per item. Stamp the order-level
    # storeId onto each item so it survives into the payment events.
    store_id = _optional_payload_text(payload, "storeId", "store_id")
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise MalformedKafkaMessage("items must contain JSON objects")
        item_dict = dict(item)
        if store_id is not None and not item_dict.get("storeId") and not item_dict.get("store_id"):
            item_dict["storeId"] = store_id
        items.append(item_dict)
    return tuple(items)


def _single_item_from_inventory_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    product_id = _optional_payload_text(payload, "productId", "product_id")
    if product_id is None:
        return ()
    item: dict[str, Any] = {"productId": product_id}
    store_id = _optional_payload_text(payload, "storeId", "store_id")
    if store_id is not None:
        item["storeId"] = store_id
    public_variant_id = _optional_payload_text(payload, "publicVariantId", "public_variant_id")
    if public_variant_id is not None:
        item["publicVariantId"] = public_variant_id
    order_line_key = _optional_payload_text(payload, "orderLineKey", "order_line_key")
    if order_line_key is not None:
        item["orderLineKey"] = order_line_key
    quantity = _optional_payload_value(payload, "quantity", "reservedQuantity", "reserved_qty")
    if quantity is not None:
        item["quantity"] = _positive_int(quantity, "quantity")
    return (item,)


def _required_payload_text(payload: Mapping[str, Any], *names: str, field_name: str) -> str:
    return _required_text(_optional_payload_text(payload, *names), field_name)


def _required_payload_value(payload: Mapping[str, Any], *names: str) -> object:
    for name in names:
        if name in payload and payload[name] is not None:
            return payload[name]
    raise MalformedKafkaMessage(f"payload missing {names[0]}")


def _optional_payload_value(payload: Mapping[str, Any], *names: str) -> object | None:
    for name in names:
        if name in payload and payload[name] is not None:
            return payload[name]
    return None


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

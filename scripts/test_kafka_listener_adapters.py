from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.checkout.adapter.kafka import CheckoutKafkaEventListener  # noqa: E402
from token_payments.contexts.checkout.application import CheckoutProcessManager  # noqa: E402
from token_payments.contexts.inventory.adapter.kafka import InventoryKafkaCommandListener  # noqa: E402
from token_payments.contexts.inventory.application import (  # noqa: E402
    ReleaseInventoryCommand,
    ReserveInventoryCommand,
)
from token_payments.contexts.payment.adapter.kafka import PaymentKafkaCommandListener  # noqa: E402
from token_payments.contexts.payment.application import (  # noqa: E402
    InitiatePaymentCommand,
    RefundPaymentCommand,
)
from token_payments.contexts.store_approval.adapter.kafka import StoreApprovalKafkaCommandListener  # noqa: E402
from token_payments.contexts.store_approval.application import RequestStoreApprovalCommand  # noqa: E402
from token_payments.shared.adapter.kafka import KafkaInboundMessage, MalformedKafkaMessage  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    Crypto,
    CustomerId,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    PaymentId,
    ProcessedCommand,
    ProcessedMessage,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
EXPIRES_AT = NOW + timedelta(minutes=15)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c27")
OWNER_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c28")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")


def test_checkout_listener_deserializes_event_dispatches_process_manager_and_saves_commands() -> None:
    processed_messages = FakeProcessedMessageRepository()
    outbox_messages = FakeOutboxMessageRepository()
    listener = CheckoutKafkaEventListener(
        process_manager=CheckoutProcessManager(),
        processed_messages=processed_messages,
        outbox_messages=outbox_messages,
    )
    inbound = _event_message(
        CheckoutEventName.PAYMENT_EXPIRED,
        {
            "paymentId": str(PAYMENT_ID),
            "reason": "signature timeout",
            "expiredAt": NOW.isoformat(),
        },
    )

    result = listener.handle(inbound)

    assert result.duplicate_decision is None
    assert result.message_id == MESSAGE_ID
    assert [message.name for message in outbox_messages.saved] == [
        CheckoutCommandName.RELEASE_INVENTORY.value,
        CheckoutCommandName.CANCEL_ORDER.value,
    ]
    assert [message.kind for message in outbox_messages.saved] == [OutboxMessageKind.COMMAND, OutboxMessageKind.COMMAND]
    assert [message.topic for message in outbox_messages.saved] == ["inventory.commands", "order.commands"]
    release = outbox_messages.saved[0]
    assert release.identity == str(CommandId.for_order_action(ORDER_ID, CheckoutCommandName.RELEASE_INVENTORY))
    assert release.key == str(ORDER_ID)
    assert release.headers["correlationId"] == str(ORDER_ID)
    assert release.headers["causationId"] == str(MESSAGE_ID)
    assert release.payload["commandName"] == CheckoutCommandName.RELEASE_INVENTORY.value
    assert release.payload["commandId"] == release.identity
    assert release.payload["orderId"] == str(ORDER_ID)
    assert release.payload["issuedAt"] == NOW.isoformat()
    assert release.payload["paymentId"] == str(PAYMENT_ID)
    assert release.payload["sourceEventName"] == CheckoutEventName.PAYMENT_EXPIRED.value
    assert processed_messages.records == [
        ProcessedMessage.record(
            message_id=MESSAGE_ID,
            consumer=CheckoutKafkaEventListener.CONSUMER_NAME,
            processed_at=NOW,
            order_id=ORDER_ID,
        )
    ]


def test_command_listeners_deserialize_and_dispatch_supported_context_commands() -> None:
    command_id = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.RESERVE_INVENTORY)
    inventory_handler = FakeInventoryCommandHandler()
    InventoryKafkaCommandListener(
        command_handler=inventory_handler,
        processed_commands=FakeProcessedCommandRepository(),
    ).handle(
        _command_message(
            CheckoutCommandName.RESERVE_INVENTORY,
            command_id,
            {
                "productId": str(PRODUCT_ID),
                "storeId": str(STORE_ID),
                "quantity": 3,
                "requestedAt": NOW.isoformat(),
            },
        )
    )

    release_id = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.RELEASE_INVENTORY)
    InventoryKafkaCommandListener(
        command_handler=inventory_handler,
        processed_commands=FakeProcessedCommandRepository(),
    ).handle(
        _command_message(
            CheckoutCommandName.RELEASE_INVENTORY,
            release_id,
            {
                "productId": str(PRODUCT_ID),
                "storeId": str(STORE_ID),
                "requestedAt": NOW.isoformat(),
            },
        )
    )

    payment_handler = FakePaymentCommandHandler()
    initiate_id = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.INITIATE_PAYMENT)
    PaymentKafkaCommandListener(
        command_handler=payment_handler,
        processed_commands=FakeProcessedCommandRepository(),
    ).handle(
        _command_message(
            CheckoutCommandName.INITIATE_PAYMENT,
            initiate_id,
            {
                "paymentId": str(PAYMENT_ID),
                "customerId": str(CUSTOMER_ID),
                "userId": str(USER_ID),
                "amount": _amount_payload(),
                "walletFrom": str(WALLET_FROM),
                "walletTo": str(WALLET_TO),
                "chain": {"chainId": CHAIN.chain_id, "name": CHAIN.name},
                "expiresAt": EXPIRES_AT.isoformat(),
                "requestedAt": NOW.isoformat(),
            },
        )
    )
    refund_id = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.REFUND_PAYMENT)
    PaymentKafkaCommandListener(
        command_handler=payment_handler,
        processed_commands=FakeProcessedCommandRepository(),
    ).handle(
        _command_message(
            CheckoutCommandName.REFUND_PAYMENT,
            refund_id,
            {
                "paymentId": str(PAYMENT_ID),
                "requestedAt": NOW.isoformat(),
            },
        )
    )

    store_handler = FakeStoreApprovalService()
    approval_id = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.REQUEST_STORE_APPROVAL)
    StoreApprovalKafkaCommandListener(
        service=store_handler,
        processed_commands=FakeProcessedCommandRepository(),
    ).handle(
        _command_message(
            CheckoutCommandName.REQUEST_STORE_APPROVAL,
            approval_id,
            {
                "storeId": str(STORE_ID),
                "ownerUserId": str(OWNER_USER_ID),
                "requestedAt": NOW.isoformat(),
            },
        )
    )

    reserve_command = inventory_handler.reserve_calls[0]
    assert isinstance(reserve_command, ReserveInventoryCommand)
    assert reserve_command.command_id == command_id
    assert reserve_command.order_id == ORDER_ID
    assert reserve_command.product_id == PRODUCT_ID
    assert reserve_command.store_id == STORE_ID
    assert reserve_command.quantity.value == 3
    assert reserve_command.causation_id == str(MESSAGE_ID)

    release_command = inventory_handler.release_calls[0]
    assert isinstance(release_command, ReleaseInventoryCommand)
    assert release_command.command_id == release_id
    assert release_command.product_id == PRODUCT_ID
    assert release_command.store_id == STORE_ID

    initiate_command = payment_handler.initiate_calls[0]
    assert isinstance(initiate_command, InitiatePaymentCommand)
    assert initiate_command.command_id == initiate_id
    assert initiate_command.payment_id == PAYMENT_ID
    assert initiate_command.customer_id == CUSTOMER_ID
    assert initiate_command.user_id == USER_ID
    assert initiate_command.amount == Crypto(
        amount=Decimal("1.25"),
        symbol="USDC",
        chain_id=CHAIN.chain_id,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )
    assert initiate_command.wallet_from == WALLET_FROM
    assert initiate_command.wallet_to == WALLET_TO
    assert initiate_command.chain_network == CHAIN
    assert initiate_command.expires_at == EXPIRES_AT

    refund_command = payment_handler.refund_calls[0]
    assert isinstance(refund_command, RefundPaymentCommand)
    assert refund_command.command_id == refund_id
    assert refund_command.payment_id == PAYMENT_ID

    approval_command = store_handler.calls[0]
    assert isinstance(approval_command, RequestStoreApprovalCommand)
    assert approval_command.command_id == approval_id
    assert approval_command.store_id == STORE_ID
    assert approval_command.owner_user_id == OWNER_USER_ID


def test_checkout_listener_ignores_duplicate_message_before_outbox_side_effects() -> None:
    processed_messages = FakeProcessedMessageRepository(
        existing={(CheckoutKafkaEventListener.CONSUMER_NAME, str(MESSAGE_ID))}
    )
    outbox_messages = FakeOutboxMessageRepository()
    process_manager = FakeCheckoutProcessManager()
    listener = CheckoutKafkaEventListener(
        process_manager=process_manager,
        processed_messages=processed_messages,
        outbox_messages=outbox_messages,
    )

    result = listener.handle(_event_message(CheckoutEventName.ORDER_REJECTED, {"rejectionReasons": ["inactive"]}))

    assert result.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert process_manager.calls == []
    assert outbox_messages.saved == []
    assert processed_messages.records == []


def test_command_listener_ignores_duplicate_command_before_handler_side_effects() -> None:
    command_id = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.REFUND_PAYMENT)
    processed_commands = FakeProcessedCommandRepository(
        existing={(FakePaymentCommandHandler.HANDLER_NAME, str(command_id))}
    )
    handler = FakePaymentCommandHandler()
    listener = PaymentKafkaCommandListener(command_handler=handler, processed_commands=processed_commands)

    result = listener.handle(
        _command_message(
            CheckoutCommandName.REFUND_PAYMENT,
            command_id,
            {
                "paymentId": str(PAYMENT_ID),
                "requestedAt": NOW.isoformat(),
            },
        )
    )

    assert result.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert handler.refund_calls == []
    assert processed_commands.records == []


def test_malformed_payload_is_rejected_before_dispatch_or_processed_record() -> None:
    processed_messages = FakeProcessedMessageRepository()
    outbox_messages = FakeOutboxMessageRepository()
    listener = CheckoutKafkaEventListener(
        process_manager=CheckoutProcessManager(),
        processed_messages=processed_messages,
        outbox_messages=outbox_messages,
    )

    with pytest.raises(MalformedKafkaMessage, match="orderId"):
        listener.handle(
            KafkaInboundMessage(
                topic="payment.events",
                key=str(ORDER_ID),
                value=json.dumps(
                    {
                        "eventName": CheckoutEventName.PAYMENT_FAILED.value,
                        "occurredAt": NOW.isoformat(),
                    }
                ),
                headers={"message_id": str(MESSAGE_ID)},
            )
        )

    with pytest.raises(MalformedKafkaMessage, match="JSON object"):
        listener.handle(
            KafkaInboundMessage(
                topic="payment.events",
                key=str(ORDER_ID),
                value="[]",
                headers={"message_id": str(MESSAGE_ID)},
            )
        )

    assert outbox_messages.saved == []
    assert processed_messages.records == []


def _event_message(name: CheckoutEventName, extra_payload: Mapping[str, Any]) -> KafkaInboundMessage:
    return KafkaInboundMessage(
        topic="checkout.events",
        key=str(ORDER_ID),
        value=json.dumps(
            {
                "eventName": name.value,
                "orderId": str(ORDER_ID),
                "occurredAt": NOW.isoformat(),
                **extra_payload,
            }
        ),
        headers={
            "message_id": str(MESSAGE_ID),
            "correlation_id": str(ORDER_ID),
            "causation_id": "upstream-command",
        },
    )


def _command_message(
    name: CheckoutCommandName,
    command_id: CommandId,
    extra_payload: Mapping[str, Any],
) -> KafkaInboundMessage:
    return KafkaInboundMessage(
        topic="checkout.commands",
        key=str(ORDER_ID),
        value=json.dumps(
            {
                "commandName": name.value,
                "commandId": str(command_id),
                "orderId": str(ORDER_ID),
                **extra_payload,
            }
        ),
        headers={
            "command_id": str(command_id),
            "correlation_id": str(ORDER_ID),
            "causation_id": str(MESSAGE_ID),
        },
    )


def _amount_payload() -> dict[str, Any]:
    return {
        "amount": "1.25",
        "symbol": "USDC",
        "chainId": CHAIN.chain_id,
        "tokenAddress": str(TOKEN_ADDRESS),
        "decimals": 6,
    }


@dataclass(frozen=True)
class FakeHandlerResult:
    command_id: CommandId
    order_id: OrderId


class FakeCheckoutProcessManager:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def handle(self, event: Any) -> tuple[Any, ...]:
        self.calls.append(event)
        return ()


class FakeInventoryCommandHandler:
    HANDLER_NAME = "inventory-command-handler"

    def __init__(self) -> None:
        self.reserve_calls: list[ReserveInventoryCommand] = []
        self.release_calls: list[ReleaseInventoryCommand] = []

    def reserve_inventory(self, command: ReserveInventoryCommand) -> FakeHandlerResult:
        self.reserve_calls.append(command)
        return FakeHandlerResult(command.command_id, command.order_id)

    def release_inventory(self, command: ReleaseInventoryCommand) -> FakeHandlerResult:
        self.release_calls.append(command)
        return FakeHandlerResult(command.command_id, command.order_id)


class FakePaymentCommandHandler:
    HANDLER_NAME = "payment-command-handler"

    def __init__(self) -> None:
        self.initiate_calls: list[InitiatePaymentCommand] = []
        self.refund_calls: list[RefundPaymentCommand] = []

    def initiate_payment(self, command: InitiatePaymentCommand) -> FakeHandlerResult:
        self.initiate_calls.append(command)
        return FakeHandlerResult(command.command_id, command.order_id)

    def refund_payment(self, command: RefundPaymentCommand) -> FakeHandlerResult:
        self.refund_calls.append(command)
        return FakeHandlerResult(command.command_id, command.order_id)


class FakeStoreApprovalService:
    HANDLER_NAME = "store-approval-service"

    def __init__(self) -> None:
        self.calls: list[RequestStoreApprovalCommand] = []

    def request_store_approval(self, command: RequestStoreApprovalCommand) -> FakeHandlerResult:
        self.calls.append(command)
        return FakeHandlerResult(command.command_id, command.order_id)


class FakeProcessedMessageRepository:
    def __init__(self, existing: set[tuple[str, str]] | None = None) -> None:
        self.existing = existing or set()
        self.records: list[ProcessedMessage] = []

    def was_processed(self, message_id: MessageId, consumer: str) -> bool:
        return (consumer, str(message_id)) in self.existing

    def record(self, processed_message: ProcessedMessage) -> IdempotencyDecision:
        self.records.append(processed_message)
        self.existing.add(processed_message.idempotency_key)
        return IdempotencyDecision.PROCESS


class FakeProcessedCommandRepository:
    def __init__(self, existing: set[tuple[str, str]] | None = None) -> None:
        self.existing = existing or set()
        self.records: list[ProcessedCommand] = []

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return (handler, str(command_id)) in self.existing

    def record(self, processed_command: ProcessedCommand) -> IdempotencyDecision:
        self.records.append(processed_command)
        self.existing.add(processed_command.idempotency_key)
        return IdempotencyDecision.PROCESS


class FakeOutboxMessageRepository:
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)

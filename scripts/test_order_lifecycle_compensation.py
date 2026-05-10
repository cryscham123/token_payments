from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.order.application import (  # noqa: E402
    CancelOrderCommand,
    OrderCommandHandler,
    OrderCommandResult,
    OrderCommandStatus,
    OrderRepository,
    OutboxMessageRepository,
    ProcessedCommandRepository,
)
from token_payments.contexts.order.domain import (  # noqa: E402
    Address,
    Customer,
    Order,
    OrderStatus,
    Product,
    Store,
    TrackingId,
)
from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    Crypto,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    ProcessedCommand,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
)
from token_payments.shared.domain.ids import CustomerId  # noqa: E402


NOW = datetime(2026, 5, 11, 9, 0, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
COMMAND_ID = CommandId.for_order_action(ORDER_ID, CheckoutCommandName.CANCEL_ORDER)
EVENT_MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")


def test_cancel_order_command_validates_required_contract_fields() -> None:
    command = CancelOrderCommand(
        command_id=COMMAND_ID,
        order_id=ORDER_ID,
        reason="payment expired before wallet signature",
        requested_at=NOW,
        causation_id="payment-expired-message",
        event_message_id=EVENT_MESSAGE_ID,
    )

    assert command.command_id == COMMAND_ID
    assert command.order_id == ORDER_ID
    assert command.reason == "payment expired before wallet signature"
    assert command.requested_at == NOW
    assert command.causation_id == "payment-expired-message"
    assert command.event_message_id == EVENT_MESSAGE_ID


@pytest.mark.parametrize(
    ("field_name", "override", "message"),
    [
        ("command_id", "not-a-command-id", "CancelOrderCommand.command_id must be a CommandId"),
        ("order_id", "not-an-order-id", "CancelOrderCommand.order_id must be an OrderId"),
        ("reason", "   ", "CancelOrderCommand.reason must be a non-empty string"),
        (
            "requested_at",
            datetime(2026, 5, 11, 9, 0),
            "CancelOrderCommand.requested_at must be timezone-aware",
        ),
        ("causation_id", "   ", "CancelOrderCommand.causation_id must be a non-empty string"),
        ("event_message_id", "not-a-message-id", "CancelOrderCommand.event_message_id must be a MessageId"),
    ],
)
def test_cancel_order_command_rejects_invalid_fields(field_name: str, override: object, message: str) -> None:
    values: dict[str, object] = {
        "command_id": COMMAND_ID,
        "order_id": ORDER_ID,
        "reason": "payment failed",
        "requested_at": NOW,
        "causation_id": "payment-failed-message",
        "event_message_id": EVENT_MESSAGE_ID,
    }
    values[field_name] = override

    with pytest.raises(ValueError, match=message):
        CancelOrderCommand(**values)  # type: ignore[arg-type]


def test_cancel_order_handler_saves_cancelled_order_outbox_and_processed_command() -> None:
    orders = FakeOrderRepository(_order())
    processed_commands = FakeProcessedCommandRepository()
    outbox_messages = FakeOutboxMessageRepository()
    handler = OrderCommandHandler(orders, processed_commands, outbox_messages)

    result = handler.cancel_order(_command())

    assert result == OrderCommandResult(
        command_id=COMMAND_ID,
        order_id=ORDER_ID,
        status=OrderCommandStatus.CANCELLED,
        order=result.order,
        outbox_message=result.outbox_message,
    )
    assert result.order is not None
    assert result.order.status == OrderStatus.CANCELLED
    assert result.order.failure_messages == ("payment expired before wallet signature",)
    assert orders.saved == [result.order]

    outbox = outbox_messages.saved[0]
    assert outbox.kind == OutboxMessageKind.EVENT
    assert outbox.name == CheckoutEventName.ORDER_CANCELLED.value
    assert outbox.topic == "order.events"
    assert outbox.key == str(ORDER_ID)
    assert outbox.identity == str(EVENT_MESSAGE_ID)
    assert outbox.headers["correlationId"] == str(ORDER_ID)
    assert outbox.headers["causationId"] == str(COMMAND_ID)
    assert outbox.headers["sourceCausationId"] == "payment-expired-message"
    assert outbox.payload["eventName"] == CheckoutEventName.ORDER_CANCELLED.value
    assert outbox.payload["orderId"] == str(ORDER_ID)
    assert outbox.payload["status"] == OrderStatus.CANCELLED.value
    assert outbox.payload["reason"] == "payment expired before wallet signature"
    assert outbox.payload["occurredAt"] == NOW.isoformat()
    assert outbox.payload["correlationId"] == str(ORDER_ID)
    assert outbox.payload["causationId"] == str(COMMAND_ID)

    assert processed_commands.records == [
        ProcessedCommand.record(
            command_id=COMMAND_ID,
            handler=OrderCommandHandler.HANDLER_NAME,
            processed_at=NOW,
            order_id=ORDER_ID,
        )
    ]


def test_duplicate_cancel_order_command_is_ignored_without_mutation_or_outbox() -> None:
    orders = FakeOrderRepository(_order())
    processed_commands = FakeProcessedCommandRepository(existing={(OrderCommandHandler.HANDLER_NAME, str(COMMAND_ID))})
    outbox_messages = FakeOutboxMessageRepository()
    handler = OrderCommandHandler(orders, processed_commands, outbox_messages)

    result = handler.cancel_order(_command())

    assert result.status == OrderCommandStatus.DUPLICATE_IGNORED
    assert result.order is None
    assert result.outbox_message is None
    assert result.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert orders.get_calls == []
    assert orders.saved == []
    assert outbox_messages.saved == []
    assert processed_commands.records == []


def test_already_cancelled_order_retry_is_idempotent_without_duplicate_failure_message() -> None:
    cancelled = _order().cancel("payment expired before wallet signature")
    orders = FakeOrderRepository(cancelled)
    processed_commands = FakeProcessedCommandRepository()
    outbox_messages = FakeOutboxMessageRepository()
    handler = OrderCommandHandler(orders, processed_commands, outbox_messages)

    result = handler.cancel_order(_command(reason="payment failed after receipt check"))

    assert result.status == OrderCommandStatus.ALREADY_CANCELLED
    assert result.order == cancelled
    assert result.order.failure_messages == ("payment expired before wallet signature",)
    assert result.outbox_message is None
    assert orders.saved == []
    assert outbox_messages.saved == []
    assert processed_commands.records == [
        ProcessedCommand.record(
            command_id=COMMAND_ID,
            handler=OrderCommandHandler.HANDLER_NAME,
            processed_at=NOW,
            order_id=ORDER_ID,
        )
    ]


def test_order_lifecycle_public_contracts_are_protocols_and_exports() -> None:
    import token_payments.contexts.order.application as application

    for port in (OrderRepository, ProcessedCommandRepository, OutboxMessageRepository):
        assert getattr(port, "_is_protocol", False), f"{port.__name__} must be a Protocol"

    hints = get_type_hints(OrderRepository.get)
    assert hints["return"] == Order | None

    assert {
        "CancelOrderCommand",
        "OrderCommandHandler",
        "OrderCommandResult",
        "OrderCommandStatus",
        "OrderRepository",
        "OutboxMessageRepository",
        "ProcessedCommandRepository",
    } <= set(application.__all__)


def test_order_application_does_not_import_external_adapters_or_clients() -> None:
    forbidden_roots = {
        "blockchain",
        "kafka",
        "metamask",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }

    for path in (ROOT / "app/token_payments/contexts/order/application").glob("**/*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        assert imports.isdisjoint(forbidden_roots), f"{path} imports adapter dependency: {imports}"


def _command(reason: str = "payment expired before wallet signature") -> CancelOrderCommand:
    return CancelOrderCommand(
        command_id=COMMAND_ID,
        order_id=ORDER_ID,
        reason=reason,
        requested_at=NOW,
        causation_id="payment-expired-message",
        event_message_id=EVENT_MESSAGE_ID,
    )


def _order(status: OrderStatus = OrderStatus.PENDING) -> Order:
    product = Product(product_id=PRODUCT_ID, name="Ledger Mug", price=_amount())
    customer = Customer(
        customer_id=CUSTOMER_ID,
        user_id=USER_ID,
        customer_wallet=WalletAddress("0x1234567890abcdef1234567890abcdef12345678"),
    )
    store = Store(
        store_id=STORE_ID,
        owner_user_id=USER_ID,
        products=(product,),
        store_wallet=WalletAddress("0x2222222222222222222222222222222222222222"),
    )
    item = Order.initialize_order(
        order_id=ORDER_ID,
        customer=customer,
        store=store,
        delivery_address=Address(id="ship-to", street="2 River Rd"),
        product_quantities={PRODUCT_ID: 1},
        created_at=NOW,
    ).items[0]
    return Order(
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        store_id=STORE_ID,
        delivery_address=Address(id="ship-to", street="2 River Rd"),
        items=(item,),
        tracking_id=TrackingId.new(),
        status=status,
    )


def _amount() -> Crypto:
    return Crypto(
        amount=Decimal("12.50"),
        symbol="USDC",
        chain_id=11155111,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )


class FakeOrderRepository:
    def __init__(self, order: Order | None = None) -> None:
        self.orders: dict[OrderId, Order] = {}
        if order is not None:
            self.orders[order.order_id] = order
        self.get_calls: list[OrderId] = []
        self.saved: list[Order] = []

    def get(self, order_id: OrderId) -> Order | None:
        self.get_calls.append(order_id)
        return self.orders.get(order_id)

    def save(self, order: Order) -> None:
        self.saved.append(order)
        self.orders[order.order_id] = order


class FakeProcessedCommandRepository:
    def __init__(self, existing: set[tuple[str, str]] | None = None) -> None:
        self.existing = existing or set()
        self.records: list[ProcessedCommand] = []

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return (handler, str(command_id)) in self.existing

    def record(self, processed_command: ProcessedCommand) -> None:
        self.records.append(processed_command)
        self.existing.add(processed_command.idempotency_key)


class FakeOutboxMessageRepository:
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)

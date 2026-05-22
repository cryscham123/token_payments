from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.order.application import (  # noqa: E402
    OrderProjectionRejected,
    OrderProjectionRejectionReason,
    OrderProjectionResult,
    OrderProjectionStatus,
    OrderRepository,
    OrderStatusEvent,
    OrderStatusEventProjector,
    ProcessedMessageRepository,
)
from token_payments.contexts.order.application.queries import (  # noqa: E402
    CheckoutCurrentStep,
    CheckoutPendingAction,
    CheckoutTrackingSnapshot,
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
from token_payments.contexts.payment.domain import Payment, PaymentStatus, TransactionReceipt  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    CheckoutEventName,
    Crypto,
    EventMetadata,
    IdempotencyDecision,
    MessageId,
    OrderId,
    OutboxPublishStatus,
    PaymentId,
    ProcessedMessage,
    ProductId,
    StoreId,
    TransactionHash,
    UserId,
    WalletAddress,
)
from token_payments.shared.domain.ids import CustomerId  # noqa: E402


NOW = datetime(2026, 5, 11, 10, 0, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7c21")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7c22")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7c23")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7c24")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7c25")
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7c26")
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7c27")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")


def test_payment_confirmed_event_projects_pending_order_to_paid() -> None:
    orders = FakeOrderRepository(_order(OrderStatus.PENDING))
    processed_messages = FakeProcessedMessageRepository()
    projector = OrderStatusEventProjector(orders, processed_messages)

    result = projector.project(_event(CheckoutEventName.PAYMENT_CONFIRMED, payment_id=PAYMENT_ID))

    assert result.status == OrderProjectionStatus.PAYMENT_CONFIRMED
    assert result.order is not None
    assert result.order.status == OrderStatus.PAID
    assert result.order.payment_id == PAYMENT_ID
    assert orders.saved == [result.order]
    assert processed_messages.records == [
        ProcessedMessage.record(
            message_id=MESSAGE_ID,
            consumer=OrderStatusEventProjector.CONSUMER_NAME,
            processed_at=NOW,
            order_id=ORDER_ID,
        )
    ]


def test_order_approved_event_projects_paid_order_to_approved() -> None:
    paid = _order(OrderStatus.PENDING).confirm_payment(PAYMENT_ID)
    orders = FakeOrderRepository(paid)
    projector = OrderStatusEventProjector(orders, FakeProcessedMessageRepository())

    result = projector.project(_event(CheckoutEventName.ORDER_APPROVED))

    assert result.status == OrderProjectionStatus.ORDER_APPROVED
    assert result.order is not None
    assert result.order.status == OrderStatus.APPROVED
    assert orders.saved == [result.order]


@pytest.mark.parametrize(
    "event_name",
    [
        CheckoutEventName.PAYMENT_FAILED,
        CheckoutEventName.PAYMENT_EXPIRED,
        CheckoutEventName.ORDER_REJECTED,
    ],
)
def test_compensation_trigger_events_are_ignored_by_status_projector(event_name: CheckoutEventName) -> None:
    order = _order(OrderStatus.PENDING)
    orders = FakeOrderRepository(order)
    processed_messages = FakeProcessedMessageRepository()
    projector = OrderStatusEventProjector(orders, processed_messages)

    result = projector.project(_event(event_name, reason="compensation trigger"))

    assert result == OrderProjectionResult(
        message_id=MESSAGE_ID,
        order_id=ORDER_ID,
        status=OrderProjectionStatus.IGNORED,
    )
    assert orders.saved == []
    assert orders.orders[ORDER_ID] == order
    assert processed_messages.records


def test_duplicate_event_message_is_ignored_before_order_mutation() -> None:
    orders = FakeOrderRepository(_order(OrderStatus.PENDING))
    processed_messages = FakeProcessedMessageRepository(
        existing={(OrderStatusEventProjector.CONSUMER_NAME, str(MESSAGE_ID))}
    )
    projector = OrderStatusEventProjector(orders, processed_messages)

    result = projector.project(_event(CheckoutEventName.PAYMENT_CONFIRMED, payment_id=PAYMENT_ID))

    assert result.status == OrderProjectionStatus.DUPLICATE_IGNORED
    assert result.duplicate_decision == IdempotencyDecision.IGNORE_DUPLICATE
    assert orders.get_calls == []
    assert orders.saved == []
    assert processed_messages.records == []


def test_already_projected_events_are_idempotent_without_extra_save() -> None:
    paid = _order(OrderStatus.PENDING).confirm_payment(PAYMENT_ID)
    orders = FakeOrderRepository(paid)
    projector = OrderStatusEventProjector(orders, FakeProcessedMessageRepository())

    result = projector.project(_event(CheckoutEventName.PAYMENT_CONFIRMED, payment_id=PAYMENT_ID))

    assert result.status == OrderProjectionStatus.ALREADY_APPLIED
    assert result.order == paid
    assert orders.saved == []


def test_invalid_projection_state_is_rejected_with_structured_reason() -> None:
    orders = FakeOrderRepository(_order(OrderStatus.PENDING))
    projector = OrderStatusEventProjector(orders, FakeProcessedMessageRepository())

    with pytest.raises(OrderProjectionRejected) as exc_info:
        projector.project(_event(CheckoutEventName.ORDER_APPROVED))

    assert exc_info.value.reason == OrderProjectionRejectionReason.INVALID_STATE
    assert exc_info.value.message_id == MESSAGE_ID
    assert exc_info.value.order_id == ORDER_ID
    assert orders.saved == []


def test_tracking_snapshot_interprets_projected_statuses_and_compensation_statuses() -> None:
    paid = _tracking_snapshot(OrderStatus.PAID, payment=_payment(PaymentStatus.CONFIRMED))
    approved = _tracking_snapshot(OrderStatus.APPROVED, payment=_payment(PaymentStatus.CONFIRMED))
    cancelling = _tracking_snapshot(OrderStatus.CANCELLING, payment=_payment(PaymentStatus.REFUNDED))
    cancelled = _tracking_snapshot(OrderStatus.CANCELLED, failure_messages=("store rejected",))

    assert paid.status == "PAID"
    assert paid.current_step == CheckoutCurrentStep.PAYMENT_CONFIRMED
    assert paid.pending_action == CheckoutPendingAction.WAIT_FOR_STORE_APPROVAL
    assert approved.current_step == CheckoutCurrentStep.ORDER_APPROVED
    assert approved.pending_action is None
    assert cancelling.current_step == CheckoutCurrentStep.ORDER_CANCELLING
    assert cancelling.pending_action == CheckoutPendingAction.WAIT_FOR_COMPENSATION
    assert cancelled.current_step == CheckoutCurrentStep.ORDER_CANCELLED
    assert cancelled.failure_reason == "store rejected"


def test_order_status_projector_public_contracts_are_exported_protocols() -> None:
    import token_payments.contexts.order.application as application

    assert getattr(OrderRepository, "_is_protocol", False)
    assert getattr(ProcessedMessageRepository, "_is_protocol", False)
    assert get_type_hints(ProcessedMessageRepository.was_processed)["return"] is bool
    assert {
        "OrderStatusEvent",
        "OrderStatusEventProjector",
        "OrderProjectionResult",
        "OrderProjectionStatus",
        "ProcessedMessageRepository",
    } <= set(application.__all__)


def _event(
    name: CheckoutEventName,
    *,
    payment_id: PaymentId | None = None,
    reason: str | None = None,
) -> OrderStatusEvent:
    return OrderStatusEvent(
        metadata=EventMetadata(
            message_id=MESSAGE_ID,
            name=name,
            aggregate_id=str(ORDER_ID),
            occurred_at=NOW,
            correlation_id=str(ORDER_ID),
            causation_id="source-message",
        ),
        order_id=ORDER_ID,
        payment_id=payment_id,
        reason=reason,
    )


def _order(status: OrderStatus) -> Order:
    product = Product(product_id=PRODUCT_ID, name="Ledger Mug", price=_amount())
    customer = Customer(
        customer_id=CUSTOMER_ID,
        user_id=USER_ID,
    )
    object.__setattr__(customer, "_customer_wallet", WalletAddress("0x1234567890abcdef1234567890abcdef12345678"))
    store = Store(
        store_id=STORE_ID,
        owner_user_id=USER_ID,
        products=(product,),
        store_wallet=WalletAddress("0x2222222222222222222222222222222222222222"),
    )
    initialized = Order.initialize_order(
        order_id=ORDER_ID,
        customer=customer,
        store=store,
        delivery_address=Address(id="ship-to", street="2 River Rd"),
        product_quantities={PRODUCT_ID: 1},
        created_at=NOW,
    )
    return Order(
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        store_id=STORE_ID,
        delivery_address=Address(id="ship-to", street="2 River Rd"),
        items=initialized.items,
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


def _payment(status: PaymentStatus) -> Payment:
    tx_hash = (
        TransactionHash("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        if status in {
            PaymentStatus.SUBMITTED,
            PaymentStatus.CONFIRMING,
            PaymentStatus.CONFIRMED,
            PaymentStatus.REFUNDED,
        }
        else None
    )
    receipt = (
        TransactionReceipt(hash=tx_hash, block_number=123456, gas_used=21000)
        if status in {PaymentStatus.CONFIRMED, PaymentStatus.REFUNDED} and tx_hash is not None
        else None
    )
    return Payment(
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        amount=_amount(),
        wallet_from=WalletAddress("0x1111111111111111111111111111111111111111"),
        wallet_to=WalletAddress("0x2222222222222222222222222222222222222222"),
        chain_network=ChainNetwork(chain_id=11155111, name="Sepolia"),
        gas_estimate=None,
        expires_at=NOW,
        status=status,
        tx_hash=tx_hash,
        receipt=receipt,
        refund_receipt=(
            TransactionReceipt(
                hash="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                block_number=123457,
                gas_used=23000,
            )
            if status is PaymentStatus.REFUNDED
            else None
        ),
        failure_reason="payment failed" if status in {PaymentStatus.FAILED, PaymentStatus.EXPIRED} else None,
    )


def _tracking_snapshot(
    order_status: OrderStatus,
    *,
    payment: Payment | None = None,
    failure_messages: tuple[str, ...] = (),
) -> CheckoutTrackingSnapshot:
    return CheckoutTrackingSnapshot(
        order_id=ORDER_ID,
        tracking_id=TrackingId.new(),
        order_status=order_status,
        failure_messages=failure_messages,
        payment=payment,
        authorization=None,
        outbox_statuses=(),
        updated_at=NOW,
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


class FakeProcessedMessageRepository:
    def __init__(self, existing: set[tuple[str, str]] | None = None) -> None:
        self.existing = existing or set()
        self.records: list[ProcessedMessage] = []

    def was_processed(self, message_id: MessageId, consumer: str) -> bool:
        return (consumer, str(message_id)) in self.existing

    def record(self, processed_message: ProcessedMessage) -> None:
        self.records.append(processed_message)
        self.existing.add(processed_message.idempotency_key)

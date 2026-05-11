from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.checkout.application import (  # noqa: E402
    CheckoutProcessEvent,
    CheckoutProcessManager,
)
from token_payments.contexts.order.domain import (  # noqa: E402
    Address,
    Customer,
    Order,
    OrderCancelledEvent,
    OrderCreatedEvent,
    OrderItem,
    OrderPaidEvent,
    OrderStatus,
    Product,
    ProductSnapshot,
    Store,
    TrackingId,
)
from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    Crypto,
    CustomerId,
    EventMetadata,
    MessageId,
    OrderId,
    PaymentId,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
WALLET = WalletAddress("0x1234567890abcdef1234567890abcdef12345678")
STORE_WALLET = WalletAddress("0x2222222222222222222222222222222222222222")
USDC = Crypto(
    amount=Decimal("12.50"),
    symbol="USDC",
    chain_id=11155111,
    token_address=WalletAddress("0x3333333333333333333333333333333333333333"),
    decimals=6,
)


def test_order_initialization_creates_pending_order_with_product_snapshot() -> None:
    product = Product(product_id=PRODUCT_ID, name="Ledger Mug", price=USDC)
    store = Store(
        store_id=STORE_ID,
        owner_user_id=USER_ID,
        products=(product,),
        store_address=Address(id="store-address", street="1 Market St"),
        store_wallet=STORE_WALLET,
        supported_chain_ids=(11155111,),
    )
    customer = Customer(customer_id=CUSTOMER_ID, user_id=USER_ID, customer_wallet=WALLET)

    order = Order.initialize_order(
        order_id=ORDER_ID,
        customer=customer,
        store=store,
        delivery_address=Address(id="ship-to", street="2 River Rd"),
        product_quantities={PRODUCT_ID: 2},
        created_at=NOW,
    )

    assert order.status == OrderStatus.PENDING
    assert order.customer_id == CUSTOMER_ID
    assert order.store_id == STORE_ID
    assert isinstance(order.tracking_id, TrackingId)
    assert order.items == (
        OrderItem.from_product(
            order_id=ORDER_ID,
            product=product,
            quantity=2,
            snapshotted_at=NOW,
        ),
    )
    assert order.items[0].product_snapshot == ProductSnapshot(
        product_id=PRODUCT_ID,
        created_date=NOW,
        name="Ledger Mug",
        price=USDC,
    )

    created = order.record_created(NOW)
    assert created == OrderCreatedEvent(order=order, created_at=NOW)


def test_order_status_transitions_emit_payment_and_cancel_events() -> None:
    order = _order()

    paid = order.confirm_payment(payment_id=PAYMENT_ID)
    cancelled = paid.cancel("store rejected")

    assert paid.status == OrderStatus.PAID
    assert paid.payment_id == PAYMENT_ID
    assert paid.record_paid(NOW) == OrderPaidEvent(order=paid, created_at=NOW)
    assert cancelled.status == OrderStatus.CANCELLED
    assert cancelled.failure_messages == ("store rejected",)
    assert cancelled.record_cancelled(NOW) == OrderCancelledEvent(order=cancelled, created_at=NOW)


def test_checkout_process_manager_decides_success_flow_commands() -> None:
    manager = CheckoutProcessManager()

    order_created = manager.handle(_event(CheckoutEventName.ORDER_CREATED))
    inventory_reserved = manager.handle(_event(CheckoutEventName.INVENTORY_RESERVED))
    payment_confirmed = manager.handle(_event(CheckoutEventName.PAYMENT_CONFIRMED))
    order_approved = manager.handle(_event(CheckoutEventName.ORDER_APPROVED))

    assert [command.name for command in order_created] == [CheckoutCommandName.RESERVE_INVENTORY]
    assert [command.name for command in inventory_reserved] == [CheckoutCommandName.INITIATE_PAYMENT]
    assert [command.name for command in payment_confirmed] == [CheckoutCommandName.REQUEST_STORE_APPROVAL]
    assert order_approved == ()


def test_checkout_process_manager_decides_payment_failure_compensation_commands() -> None:
    manager = CheckoutProcessManager()

    for event_name in (CheckoutEventName.PAYMENT_FAILED, CheckoutEventName.PAYMENT_EXPIRED):
        commands = manager.handle(_event(event_name))

        assert [command.name for command in commands] == [
            CheckoutCommandName.RELEASE_INVENTORY,
            CheckoutCommandName.CANCEL_ORDER,
        ]
        assert [str(command.command_id) for command in commands] == [
            f"{ORDER_ID}:ReleaseInventoryCommand",
            f"{ORDER_ID}:CancelOrderCommand",
        ]


def test_checkout_process_manager_decides_order_rejected_compensation_commands() -> None:
    commands = CheckoutProcessManager().handle(_event(CheckoutEventName.ORDER_REJECTED))

    assert [command.name for command in commands] == [
        CheckoutCommandName.REFUND_PAYMENT,
        CheckoutCommandName.RELEASE_INVENTORY,
        CheckoutCommandName.CANCEL_ORDER,
    ]
    assert [str(command.command_id) for command in commands] == [
        f"{ORDER_ID}:RefundPaymentCommand",
        f"{ORDER_ID}:ReleaseInventoryCommand",
        f"{ORDER_ID}:CancelOrderCommand",
    ]


def test_checkout_process_manager_is_pure_domain_logic_without_adapters() -> None:
    forbidden_roots = {
        "blockchain",
        "kafka",
        "metamask",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }

    for context_path in (
        ROOT / "app/token_payments/contexts/order/domain",
        ROOT / "app/token_payments/contexts/order/application",
        ROOT / "app/token_payments/contexts/checkout/domain",
        ROOT / "app/token_payments/contexts/checkout/application",
    ):
        for path in context_path.glob("**/*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])

            assert imports.isdisjoint(forbidden_roots), f"{path} imports adapter dependency: {imports}"


def _order() -> Order:
    product = Product(product_id=PRODUCT_ID, name="Ledger Mug", price=USDC)
    return Order(
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        store_id=STORE_ID,
        delivery_address=Address(id="ship-to", street="2 River Rd"),
        items=(OrderItem.from_product(ORDER_ID, product, 1, NOW),),
        tracking_id=TrackingId.new(),
        status=OrderStatus.PENDING,
    )


def _event(name: CheckoutEventName) -> CheckoutProcessEvent:
    return CheckoutProcessEvent(
        metadata=EventMetadata(
            message_id=MessageId.new(),
            name=name,
            aggregate_id=str(ORDER_ID),
            occurred_at=NOW,
            correlation_id=str(ORDER_ID),
        ),
        order_id=ORDER_ID,
    )

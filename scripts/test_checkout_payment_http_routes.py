from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    CHECKOUT_HTTP_ROUTES,
    PAYMENT_HTTP_ROUTES,
    CheckoutApi,
    HttpRouter,
    PaymentsApi,
    register_checkout_routes,
    register_payment_routes,
)
from token_payments.contexts.order.application import CheckoutTrackingSnapshot  # noqa: E402
from token_payments.contexts.order.domain import OrderStatus, TrackingId  # noqa: E402
from token_payments.contexts.payment.application import (  # noqa: E402
    PaymentHistoryItem,
    PaymentCommandResult,
    PaymentCommandStatus,
    SubmitTransactionHashCommand,
)
from token_payments.contexts.payment.domain import (  # noqa: E402
    GasEstimate,
    Payment,
    PaymentAuthorization,
    PaymentStatus,
    TransactionSignatureRequest,
)
from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    CommandId,
    Crypto,
    CustomerId,
    OrderId,
    PaymentId,
    TransactionHash,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 10, 7, 0, tzinfo=UTC)
UPDATED_AT = NOW + timedelta(minutes=5)
EXPIRES_AT = NOW + timedelta(minutes=15)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c41")
OTHER_ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c42")
TRACKING_ID = TrackingId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c43")
OTHER_TRACKING_ID = TrackingId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c44")
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c45")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c46")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c47")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")
TX_HASH = TransactionHash("0x" + "cd" * 32)
COMMAND_ID = CommandId("ui-submit-tx-route-command")


def test_checkout_payment_route_manifest_exposes_stable_methods_paths_and_operations() -> None:
    assert CHECKOUT_HTTP_ROUTES["get_tracking_by_tracking_id"].method == "GET"
    assert CHECKOUT_HTTP_ROUTES["get_tracking_by_tracking_id"].path == "/checkouts/tracking/{trackingId}"
    assert CHECKOUT_HTTP_ROUTES["get_tracking_by_tracking_id"].operation_id == "getCheckoutTrackingByTrackingId"
    assert CHECKOUT_HTTP_ROUTES["get_tracking_by_order_id"].method == "GET"
    assert CHECKOUT_HTTP_ROUTES["get_tracking_by_order_id"].path == "/checkouts/orders/{orderId}"
    assert CHECKOUT_HTTP_ROUTES["get_tracking_by_order_id"].operation_id == "getCheckoutTrackingByOrderId"

    assert PAYMENT_HTTP_ROUTES["submit_transaction_hash"].method == "POST"
    assert PAYMENT_HTTP_ROUTES["submit_transaction_hash"].path == "/payments/transaction-hashes"
    assert PAYMENT_HTTP_ROUTES["submit_transaction_hash"].operation_id == "submitTransactionHash"
    assert PAYMENT_HTTP_ROUTES["list_payments"].method == "GET"
    assert PAYMENT_HTTP_ROUTES["list_payments"].path == "/payments"
    assert PAYMENT_HTTP_ROUTES["list_payments"].operation_id == "listUserPayments"


def test_checkout_http_routes_call_tracking_facade_with_path_params() -> None:
    query = FakeCheckoutTrackingQuery(_tracking_snapshot())
    router = HttpRouter()

    routes = register_checkout_routes(router, CheckoutApi(query))

    assert [route.operation_id for route in routes] == [
        "getCheckoutTrackingByTrackingId",
        "getCheckoutTrackingByOrderId",
    ]

    tracking = router.handle(
        "GET",
        f"/checkouts/tracking/{TRACKING_ID}",
        headers={"X-Request-Id": "req-checkout-track-path"},
        received_at=NOW,
    )
    order = router.handle(
        "GET",
        f"/checkouts/orders/{ORDER_ID}",
        headers={"X-Request-Id": "req-checkout-order-path"},
        received_at=NOW,
    )

    assert tracking.status_code == 200
    assert tracking.headers["X-Request-Id"] == "req-checkout-track-path"
    assert _json(tracking.body)["checkout"]["trackingId"] == str(TRACKING_ID)
    assert _json(tracking.body)["checkout"]["currentStep"] == "AWAITING_SIGNATURE"

    assert order.status_code == 200
    assert order.headers["X-Request-Id"] == "req-checkout-order-path"
    assert _json(order.body)["checkout"]["orderId"] == str(ORDER_ID)
    assert query.tracking_id_calls == [TRACKING_ID]
    assert query.order_id_calls == [ORDER_ID]


def test_checkout_http_routes_keep_query_string_lookup_compatible_with_facade_contract() -> None:
    query = FakeCheckoutTrackingQuery(_tracking_snapshot())
    router = HttpRouter()
    register_checkout_routes(router, CheckoutApi(query))

    tracking = router.handle(
        "GET",
        f"/checkouts/tracking/{OTHER_TRACKING_ID}",
        query={"trackingId": str(TRACKING_ID)},
        headers={"X-Request-Id": "req-checkout-track-query"},
        received_at=NOW,
    )
    order = router.handle(
        "GET",
        f"/checkouts/orders/{OTHER_ORDER_ID}",
        query=f"orderId={ORDER_ID}",
        headers={"X-Request-Id": "req-checkout-order-query"},
        received_at=NOW,
    )

    assert tracking.status_code == 200
    assert order.status_code == 200
    assert query.tracking_id_calls == [TRACKING_ID]
    assert query.order_id_calls == [ORDER_ID]


def test_payment_http_route_submits_tx_hash_and_preserves_request_id_and_command_id() -> None:
    handler = CapturingPaymentCommandHandler()
    router = HttpRouter()
    query = FakeCheckoutTrackingQuery(_tracking_snapshot())

    routes = register_payment_routes(router, PaymentsApi(handler, tracking_query=query, history_query=FakePaymentHistoryQuery()))

    assert [route.operation_id for route in routes] == ["listUserPayments", "submitTransactionHash", "cancelPayment"]

    response = router.handle(
        "POST",
        "/payments/transaction-hashes",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-payment-submit",
            "X-User-Id": str(USER_ID),
        },
        body=json.dumps(
            {
                "commandId": str(COMMAND_ID),
                "trackingId": str(TRACKING_ID),
                "txHash": str(TX_HASH),
            },
            separators=(",", ":"),
        ).encode("utf-8"),
        received_at=NOW,
    )

    assert response.status_code == 202
    assert response.headers["X-Request-Id"] == "req-payment-submit"
    assert _json(response.body) == {
        "payment": {
            "currentStep": "RECEIPT_PENDING",
            "trackingId": str(TRACKING_ID),
            "pendingAction": "WAIT_FOR_RECEIPT",
            "status": "TX_SUBMITTED",
            "txHash": str(TX_HASH),
            "updatedAt": NOW.isoformat(),
        }
    }

    assert handler.commands == [
        SubmitTransactionHashCommand(
            command_id=COMMAND_ID,
            payment_id=PAYMENT_ID,
            order_id=ORDER_ID,
            tx_hash=TX_HASH,
            submitted_at=NOW,
            causation_id="req-payment-submit",
        )
    ]


def test_payment_http_route_lists_user_payment_history_without_request_body() -> None:
    handler = CapturingPaymentCommandHandler()
    history_query = FakePaymentHistoryQuery((_history_item(),))
    router = HttpRouter()
    register_payment_routes(
        router,
        PaymentsApi(handler, tracking_query=FakeCheckoutTrackingQuery(None), history_query=history_query),
    )

    response = router.handle(
        "GET",
        "/payments",
        query={"status": "SUBMITTED,CONFIRMED", "limit": "20"},
        headers={
            "X-Request-Id": "req-payment-history",
            "X-User-Id": str(USER_ID),
        },
        received_at=NOW,
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "req-payment-history"
    assert _json(response.body) == {
        "payments": [
            {
                "amount": {
                    "amount": "1.25",
                    "chainId": 11155111,
                    "decimals": 6,
                    "symbol": "USDC",
                    "tokenAddress": str(TOKEN_ADDRESS),
                },
                "chain": {"chainId": 11155111, "name": "Sepolia"},
                "currentStep": "RECEIPT_PENDING",
                "failureReason": None,
                "orderId": str(ORDER_ID),
                "paymentAssetId": "local-usdc",
                "paymentId": str(PAYMENT_ID),
                "pendingAction": "WAIT_FOR_RECEIPT",
                "receipt": None,
                "status": "SUBMITTED",
                "trackingId": str(TRACKING_ID),
                "txHash": str(TX_HASH),
                "updatedAt": UPDATED_AT.isoformat(),
                "items": [],
            }
        ],
        "pagination": {"limit": 20, "nextPageToken": None},
    }
    assert history_query.calls == [(USER_ID, (PaymentStatus.SUBMITTED, PaymentStatus.CONFIRMED), 20)]


def test_payment_http_route_cancels_awaiting_signature_payment() -> None:
    handler = CapturingPaymentCommandHandler()
    router = HttpRouter()
    query = FakeCheckoutTrackingQuery(_tracking_snapshot())

    register_payment_routes(router, PaymentsApi(handler, tracking_query=query, history_query=FakePaymentHistoryQuery()))

    response = router.handle(
        "POST",
        "/payments/cancellations",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-payment-cancel",
            "X-User-Id": str(USER_ID),
        },
        body=json.dumps({"trackingId": str(TRACKING_ID)}, separators=(",", ":")).encode("utf-8"),
        received_at=NOW,
    )

    assert response.status_code == 202
    assert response.headers["X-Request-Id"] == "req-payment-cancel"
    assert len(handler.commands) == 1
    cancel_command = handler.commands[0]
    assert cancel_command.order_id == ORDER_ID
    assert cancel_command.payment_id == PAYMENT_ID
    body = _json(response.body)
    assert body["payment"]["status"] == "EXPIRED"
    assert body["payment"]["orderId"] == str(ORDER_ID)


def _json(body: bytes) -> dict[str, object]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


def _tracking_snapshot() -> CheckoutTrackingSnapshot:
    return CheckoutTrackingSnapshot(
        order_id=ORDER_ID,
        tracking_id=TRACKING_ID,
        order_status=OrderStatus.PENDING,
        failure_messages=(),
        payment=_awaiting_payment(),
        authorization=_requested_authorization(),
        outbox_statuses=(),
        updated_at=UPDATED_AT,
    )


def _awaiting_payment() -> Payment:
    return Payment.initialize_payment(
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        amount=_amount(),
        wallet_from=WALLET_FROM,
        wallet_to=WALLET_TO,
        chain_network=CHAIN,
        gas_estimate=_gas_estimate().apply_buffer(),
        expires_at=EXPIRES_AT,
        status=PaymentStatus.AWAITING_SIGNATURE,
    )


def _requested_authorization() -> PaymentAuthorization:
    return PaymentAuthorization.request_transaction_signature(
        payment_id=PAYMENT_ID,
        user_id=USER_ID,
        wallet=WALLET_FROM,
        chain_network=CHAIN,
        signature_request=TransactionSignatureRequest(
            request_id="payment-request-route",
            amount=_amount(),
            to=WALLET_TO,
            expires_at=EXPIRES_AT,
        ),
    )


def _history_item() -> PaymentHistoryItem:
    return PaymentHistoryItem(
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        tracking_id=TRACKING_ID,
        amount=_amount(),
        wallet_from=WALLET_FROM,
        wallet_to=WALLET_TO,
        chain_network=CHAIN,
        status=PaymentStatus.SUBMITTED,
        tx_hash=TX_HASH,
        receipt=None,
        failure_reason=None,
        payment_asset_id="local-usdc",
        updated_at=UPDATED_AT,
    )


def _amount() -> Crypto:
    return Crypto(
        amount="1.25",
        symbol="USDC",
        chain_id=11155111,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )


def _gas_estimate() -> GasEstimate:
    return GasEstimate(
        estimated_fee=Crypto(amount="0.0100", symbol="ETH", chain_id=11155111, token_address=None, decimals=18),
        gas_limit=21000,
        buffer_rate=Decimal("0.10"),
    )


class FakeCheckoutTrackingQuery:
    def __init__(self, snapshot: CheckoutTrackingSnapshot | None) -> None:
        self.snapshot = snapshot
        self.order_id_calls: list[OrderId] = []
        self.tracking_id_calls: list[TrackingId] = []

    def get_by_tracking_id(self, tracking_id: TrackingId) -> CheckoutTrackingSnapshot | None:
        self.tracking_id_calls.append(tracking_id)
        return self.snapshot

    def get_by_order_id(self, order_id: OrderId) -> CheckoutTrackingSnapshot | None:
        self.order_id_calls.append(order_id)
        return self.snapshot

    def resolve_and_verify(self, tracking_id: TrackingId, user_id: UserId) -> tuple[OrderId, PaymentId]:
        if self.snapshot is None:
            raise ValueError("not found")
        if user_id != USER_ID:
            raise ValueError("authenticated user does not own the order")
        return self.snapshot.order_id, self.snapshot.payment.payment_id if self.snapshot.payment else PAYMENT_ID


class FakePaymentHistoryQuery:
    def __init__(self, items: tuple[PaymentHistoryItem, ...] = ()) -> None:
        self.items = items
        self.calls: list[tuple[UserId, tuple[PaymentStatus, ...] | None, int]] = []

    def list_for_user(
        self,
        user_id: UserId,
        *,
        statuses: tuple[PaymentStatus, ...] | None = None,
        limit: int = 50,
    ) -> tuple[PaymentHistoryItem, ...]:
        self.calls.append((user_id, statuses, limit))
        return self.items


class CapturingPaymentCommandHandler:
    def __init__(self) -> None:
        self.commands: list[SubmitTransactionHashCommand] = []

    def submit_transaction_hash(self, command: SubmitTransactionHashCommand) -> PaymentCommandResult:
        self.commands.append(command)
        return PaymentCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=PaymentCommandStatus.TX_SUBMITTED,
            payment=_awaiting_payment().submit_tx_hash(command.tx_hash),
        )

    def expire_awaiting_signature(self, command) -> PaymentCommandResult:
        self.commands.append(command)
        return PaymentCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=PaymentCommandStatus.EXPIRED,
            payment=_awaiting_payment(),
        )

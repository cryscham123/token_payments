from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    OPERATOR_HTTP_ROUTES,
    HttpRouter,
    OperatorApi,
    register_operator_routes,
)
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.contexts.order.domain import OrderStatus  # noqa: E402
from token_payments.contexts.payment.domain import PaymentStatus  # noqa: E402
from token_payments.runtime import HealthState  # noqa: E402
from token_payments.runtime.observability import (  # noqa: E402
    OperatorDashboardQuery,
    OperatorErrorSnapshot,
    OperatorObservabilitySnapshot,
    OperatorOrderSnapshot,
    OperatorOutboxSnapshot,
    OperatorPage,
    OperatorPaymentSnapshot,
    OperatorSortDirection,
    OperatorWorkerSnapshot,
)
from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    Crypto,
    CustomerId,
    OrderId,
    OutboxMessageKind,
    OutboxPublishStatus,
    PaymentId,
    StoreId,
    TransactionHash,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 10, 9, 30, tzinfo=UTC)
CREATED_AT = NOW - timedelta(minutes=20)
UPDATED_AT = NOW - timedelta(minutes=3)
CHECKED_AT = NOW - timedelta(seconds=45)
EXPIRES_AT = NOW - timedelta(minutes=2)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7a11")
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7a12")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7a13")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7a14")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc7a15")
TRACKING_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc7a16"
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")
TX_HASH = TransactionHash("0x" + "ef" * 32)
MESSAGE_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc7a17:CancelOrderCommand"


def test_operator_route_manifest_exposes_stable_methods_paths_and_operations() -> None:
    assert OPERATOR_HTTP_ROUTES["get_dashboard"].method == "GET"
    assert OPERATOR_HTTP_ROUTES["get_dashboard"].path == "/operator/dashboard"
    assert OPERATOR_HTTP_ROUTES["get_dashboard"].operation_id == "getOperatorDashboard"
    assert OPERATOR_HTTP_ROUTES["get_order_detail"].method == "GET"
    assert OPERATOR_HTTP_ROUTES["get_order_detail"].path == "/operator/orders/{orderId}"
    assert OPERATOR_HTTP_ROUTES["get_order_detail"].operation_id == "getOperatorOrderDetail"
    assert OPERATOR_HTTP_ROUTES["get_payment_detail"].method == "GET"
    assert OPERATOR_HTTP_ROUTES["get_payment_detail"].path == "/operator/payments/{paymentId}"
    assert OPERATOR_HTTP_ROUTES["get_payment_detail"].operation_id == "getOperatorPaymentDetail"
    assert OPERATOR_HTTP_ROUTES["get_outbox_detail"].method == "GET"
    assert OPERATOR_HTTP_ROUTES["get_outbox_detail"].path == "/operator/outbox/{messageId}"
    assert OPERATOR_HTTP_ROUTES["get_outbox_detail"].operation_id == "getOperatorOutboxDetail"


def test_operator_dashboard_http_route_forwards_filters_to_facade_query() -> None:
    query = FakeOperatorObservabilityQuery(_operator_snapshot())
    router = HttpRouter()

    routes = register_operator_routes(router, OperatorApi(query))

    assert [route.operation_id for route in routes] == [
        "getOperatorDashboard",
        "getOperatorOrderDetail",
        "getOperatorPaymentDetail",
        "getOperatorOutboxDetail",
    ]

    response = router.handle(
        "GET",
        "/operator/dashboard",
        query={
            "status": "cancelled,failed",
            "context": "orders,payments,outbox",
            "failedOnly": "true",
            "retryCandidatesOnly": "true",
            "limit": "25",
            "pageToken": "cursor-operator-1",
        },
        headers={
            "X-Request-Id": "req-operator-dashboard",
            "X-User-Id": str(USER_ID),
            "X-User-Role": UserRole.ADMIN.value,
        },
        received_at=NOW,
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "req-operator-dashboard"
    assert query.dashboard_queries == [
        OperatorDashboardQuery(
            contexts=("orders", "payments", "outbox"),
            statuses=("CANCELLED", "FAILED"),
            failed_only=True,
            retry_candidates_only=True,
            sort_by="updatedAt",
            sort_direction=OperatorSortDirection.DESC,
            limit=25,
            page_token="cursor-operator-1",
        )
    ]
    payload = _json(response.body)
    assert payload["orders"][0]["status"] == OrderStatus.CANCELLED.value
    assert payload["orders"][0]["failureReason"] == "PaymentExpiredEvent cancelled the order"
    assert payload["payments"][0]["failureReason"] == "signature expired before txHash"
    assert payload["outbox"][0]["retryCandidate"] is True
    assert payload["outbox"][0]["retryReason"] == "FAILED rows are reclaimed by the outbox relay retry policy"


def test_operator_order_detail_http_route_preserves_lifecycle_failure_and_latest_event_payload() -> None:
    query = FakeOperatorObservabilityQuery(_operator_snapshot())
    router = HttpRouter()
    register_operator_routes(router, OperatorApi(query))

    response = router.handle(
        "GET",
        f"/operator/orders/{ORDER_ID}",
        headers={"X-Request-Id": "req-operator-order", "X-User-Role": UserRole.ADMIN.value},
        received_at=NOW,
    )

    assert response.status_code == 200
    assert query.order_detail_calls == [ORDER_ID]
    payload = _json(response.body)
    assert payload["orders"][0] == {
        "orderId": str(ORDER_ID),
        "trackingId": TRACKING_ID,
        "customerId": str(CUSTOMER_ID),
        "storeId": str(STORE_ID),
        "status": OrderStatus.CANCELLED.value,
        "paymentId": str(PAYMENT_ID),
        "paymentStatus": PaymentStatus.EXPIRED.value,
        "totalAmount": _crypto_payload(),
        "failureReason": "PaymentExpiredEvent cancelled the order",
        "latestEvent": "OrderCancelledEvent",
        "createdAt": CREATED_AT.isoformat(),
        "updatedAt": UPDATED_AT.isoformat(),
    }


def test_operator_payment_and_outbox_detail_http_routes_preserve_path_params_and_kind_query() -> None:
    query = FakeOperatorObservabilityQuery(_operator_snapshot())
    router = HttpRouter()
    register_operator_routes(router, OperatorApi(query))

    payment = router.handle(
        "GET",
        f"/operator/payments/{PAYMENT_ID}",
        headers={"X-Request-Id": "req-operator-payment", "X-User-Role": UserRole.ADMIN.value},
        received_at=NOW,
    )
    outbox = router.handle(
        "GET",
        f"/operator/outbox/{MESSAGE_ID}",
        query={"kind": OutboxMessageKind.COMMAND.value},
        headers={"X-Request-Id": "req-operator-outbox", "X-User-Role": UserRole.ADMIN.value},
        received_at=NOW,
    )

    assert payment.status_code == 200
    assert _json(payment.body)["payments"][0]["paymentId"] == str(PAYMENT_ID)
    assert query.payment_detail_calls == [PAYMENT_ID]

    assert outbox.status_code == 200
    assert _json(outbox.body)["outbox"][0]["kind"] == OutboxMessageKind.COMMAND.value
    assert query.outbox_detail_calls == [(OutboxMessageKind.COMMAND, MESSAGE_ID)]


def test_operator_http_routes_serialize_facade_forbidden_response_without_bypassing_policy() -> None:
    query = FakeOperatorObservabilityQuery(_operator_snapshot())
    router = HttpRouter()
    register_operator_routes(router, OperatorApi(query))

    response = router.handle(
        "GET",
        "/operator/dashboard",
        headers={"X-Request-Id": "req-operator-forbidden"},
        received_at=NOW,
    )

    assert response.status_code == 403
    assert response.headers["X-Request-Id"] == "req-operator-forbidden"
    assert _json(response.body) == {
        "error": {
            "code": "OPERATOR_FORBIDDEN",
            "message": "operator access is required",
        }
    }
    assert query.dashboard_queries == []
    assert query.order_detail_calls == []
    assert query.payment_detail_calls == []
    assert query.outbox_detail_calls == []


def _json(body: bytes) -> dict[str, object]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


def _operator_snapshot() -> OperatorObservabilitySnapshot:
    return OperatorObservabilitySnapshot(
        orders=(
            OperatorOrderSnapshot(
                order_id=ORDER_ID,
                tracking_id=TRACKING_ID,
                customer_id=CUSTOMER_ID,
                store_id=STORE_ID,
                status=OrderStatus.CANCELLED,
                payment_id=PAYMENT_ID,
                payment_status=PaymentStatus.EXPIRED,
                total_amount=_amount(),
                failure_reason="PaymentExpiredEvent cancelled the order",
                latest_event="OrderCancelledEvent",
                created_at=CREATED_AT,
                updated_at=UPDATED_AT,
            ),
        ),
        payments=(
            OperatorPaymentSnapshot(
                payment_id=PAYMENT_ID,
                order_id=ORDER_ID,
                customer_id=CUSTOMER_ID,
                status=PaymentStatus.EXPIRED,
                amount=_amount(),
                chain=CHAIN,
                wallet_from=WALLET_FROM,
                wallet_to=WALLET_TO,
                tx_hash=TX_HASH,
                failure_reason="signature expired before txHash",
                expires_at=EXPIRES_AT,
                created_at=CREATED_AT,
                updated_at=UPDATED_AT,
            ),
        ),
        outbox=(
            OperatorOutboxSnapshot(
                identity=MESSAGE_ID,
                kind=OutboxMessageKind.COMMAND,
                name="CancelOrderCommand",
                topic="order.commands",
                key=str(ORDER_ID),
                status=OutboxPublishStatus.FAILED,
                failure_count=3,
                last_error="broker unavailable",
                created_at=CREATED_AT,
                published_at=None,
                updated_at=UPDATED_AT,
            ),
        ),
        workers=(
            OperatorWorkerSnapshot(
                component="outbox-relay",
                state=HealthState.DEGRADED,
                checked_at=CHECKED_AT,
                details={"lastBatchFailed": 1},
            ),
        ),
        errors=(
            OperatorErrorSnapshot(
                context="order",
                aggregate_id=str(ORDER_ID),
                code=OrderStatus.CANCELLED.value,
                message="PaymentExpiredEvent cancelled the order",
                created_at=UPDATED_AT,
            ),
        ),
        pagination={
            "orders": OperatorPage(limit=25, next_page_token="orders:next"),
            "payments": OperatorPage(limit=25, next_page_token="payments:next"),
            "outbox": OperatorPage(limit=25, next_page_token="outbox:next"),
        },
    )


def _amount() -> Crypto:
    return Crypto(
        amount=Decimal("1.25"),
        symbol="USDC",
        chain_id=CHAIN.chain_id,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )


def _crypto_payload() -> dict[str, object]:
    return {
        "amount": "1.25",
        "symbol": "USDC",
        "chainId": 11155111,
        "tokenAddress": str(TOKEN_ADDRESS),
        "decimals": 6,
    }


class FakeOperatorObservabilityQuery:
    def __init__(self, snapshot: OperatorObservabilitySnapshot) -> None:
        self.snapshot = snapshot
        self.dashboard_queries: list[OperatorDashboardQuery] = []
        self.order_detail_calls: list[OrderId] = []
        self.payment_detail_calls: list[PaymentId] = []
        self.outbox_detail_calls: list[tuple[OutboxMessageKind, str]] = []

    def list_dashboard(self, query: OperatorDashboardQuery) -> OperatorObservabilitySnapshot:
        self.dashboard_queries.append(query)
        return self.snapshot

    def get_order_detail(self, order_id: OrderId) -> OperatorObservabilitySnapshot | None:
        self.order_detail_calls.append(order_id)
        if order_id == ORDER_ID:
            return self.snapshot
        return None

    def get_payment_detail(self, payment_id: PaymentId) -> OperatorObservabilitySnapshot | None:
        self.payment_detail_calls.append(payment_id)
        if payment_id == PAYMENT_ID:
            return self.snapshot
        return None

    def get_outbox_detail(
        self,
        kind: OutboxMessageKind,
        identity: str,
    ) -> OperatorObservabilitySnapshot | None:
        self.outbox_detail_calls.append((kind, identity))
        if kind is OutboxMessageKind.COMMAND and identity == MESSAGE_ID:
            return self.snapshot
        return None

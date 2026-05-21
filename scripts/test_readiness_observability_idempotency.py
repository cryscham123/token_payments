from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    HttpRouter,
    OperatorActionApi,
    OperatorCancelOrderActionExecutor,
    OperatorOutboxActionExecutor,
    OrdersApi,
    PaymentsApi,
    register_operator_action_routes,
    register_order_routes,
    register_payment_routes,
)
from token_payments.contexts.order.application import (  # noqa: E402
    CancelOrderCommand,
    CreateOrderCommand,
    OrderCommandResult,
    OrderCommandStatus,
    OrderCreationResult,
)
from token_payments.contexts.order.domain import Address, Customer, Order, Product, Store, TrackingId  # noqa: E402
from token_payments.contexts.payment.application import (  # noqa: E402
    PaymentCommandResult,
    PaymentCommandStatus,
    SubmitTransactionHashCommand,
)
from token_payments.runtime.api_server import build_live_system_router  # noqa: E402
from token_payments.runtime.contracts import HealthState  # noqa: E402
from token_payments.runtime.observability import ReadinessProbeResult  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    CheckoutEventName,
    CommandId,
    Crypto,
    CustomerId,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    PaymentId,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9101")
TRACKING_ID = TrackingId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9102")
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9103")
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9104")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9105")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9106")
OWNER_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9107")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9108")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9109")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")


def test_healthz_reports_process_health_without_running_readiness_probes_or_live_clients() -> None:
    probe = FailingIfCalledProbe("postgres")
    router = build_live_system_router(readiness_probes=(probe,))

    response = router.handle(
        "GET",
        "/healthz",
        headers={"X-Request-Id": "req-health", "Cookie": "access_token=secret-token"},
        received_at=NOW,
    )
    payload = _json(response.body)

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "req-health"
    assert payload["component"] == "runtime"
    assert payload["state"] == "OK"
    assert payload["details"]["serverStarted"] is False
    assert probe.calls == 0
    assert "secret-token" not in json.dumps(payload, sort_keys=True)


def test_readyz_uses_injected_probes_returns_503_details_and_redacts_secrets() -> None:
    router = build_live_system_router(
        readiness_probes=(
            StaticProbe(
                ReadinessProbeResult(
                    component="postgres",
                    state=HealthState.OK,
                    checked_at=NOW,
                    details={"pool": "ready"},
                )
            ),
            StaticProbe(
                ReadinessProbeResult(
                    component="kafka",
                    state=HealthState.UNAVAILABLE,
                    checked_at=NOW,
                    details={"password": "broker-secret", "topic": "checkout.events"},
                    error_code="KAFKA_UNAVAILABLE",
                    message="Kafka broker is unavailable.",
                )
            ),
        )
    )

    response = router.handle("GET", "/readyz", headers={"X-Request-Id": "req-ready"}, received_at=NOW)
    payload = _json(response.body)
    encoded = json.dumps(payload, sort_keys=True)

    assert response.status_code == 503
    assert response.headers["X-Request-Id"] == "req-ready"
    assert payload["state"] == "UNAVAILABLE"
    assert [component["component"] for component in payload["components"]] == ["postgres", "kafka"]
    assert payload["components"][1]["error"]["code"] == "KAFKA_UNAVAILABLE"
    assert "broker-secret" not in encoded
    assert payload["components"][1]["details"]["password"] == "<redacted>"


def test_access_log_event_contract_preserves_route_request_and_redacts_sensitive_inputs() -> None:
    events: list[Mapping[str, Any]] = []
    router = build_live_system_router(access_log_sink=events.append)

    response = router.handle(
        "GET",
        "/healthz",
        headers={
            "X-Request-Id": "req-log",
            "Cookie": "access_token=secret-token",
            "Authorization": "Bearer secret-token",
        },
        received_at=NOW,
    )
    event = events[0]
    encoded = json.dumps(event, sort_keys=True)

    assert response.status_code == 200
    assert event["method"] == "GET"
    assert event["pathTemplate"] == "/healthz"
    assert event["routeId"] == "getRuntimeHealth"
    assert event["status"] == 200
    assert event["requestId"] == "req-log"
    assert event["durationMs"] >= 0
    assert event["actor"] == {"authenticated": False}
    assert "secret-token" not in encoded
    assert "Authorization" not in encoded
    assert "Cookie" not in encoded


def test_idempotency_key_header_standardizes_order_payment_and_operator_action_commands() -> None:
    order_use_case = CapturingOrderUseCase()
    payment_handler = CapturingPaymentHandler()
    cancel_handler = CapturingCancelOrderHandler()

    order_router = HttpRouter()
    register_order_routes(order_router, OrdersApi(order_use_case))
    payment_router = HttpRouter()
    register_payment_routes(payment_router, PaymentsApi(payment_handler))
    operator_router = HttpRouter()
    register_operator_action_routes(
        operator_router,
        OperatorActionApi(
            cancel_order_executor=OperatorCancelOrderActionExecutor(cancel_handler),
            outbox_action_executor=OperatorOutboxActionExecutor(NoopOutboxActionPort(), NoopOutboxActionPort()),
        ),
    )

    order = order_router.handle(
        "POST",
        "/orders",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-order",
            "X-User-Id": str(USER_ID),
            "Idempotency-Key": "idem-order-header",
        },
        body=_json_body(
            {
                "storeId": str(STORE_ID),
                "deliveryAddress": {"id": "ship-to", "street": "2 River Rd"},
                "items": [{"productId": str(PRODUCT_ID), "quantity": 2}],
            }
        ),
        received_at=NOW,
    )
    payment = payment_router.handle(
        "POST",
        "/payments/transaction-hashes",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-payment",
            "Idempotency-Key": "idem-payment-header",
        },
        body=_json_body(
            {
                "orderId": str(ORDER_ID),
                "paymentId": str(PAYMENT_ID),
                "txHash": "0x" + "ab" * 32,
            }
        ),
        received_at=NOW,
    )
    operator = operator_router.handle(
        "POST",
        f"/operator/orders/{ORDER_ID}/cancel",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-operator",
            "X-User-Id": "operator-1",
            "X-User-Scopes": "operator:action",
            "Idempotency-Key": "idem-operator-header",
        },
        body=_json_body({"reason": "customer request"}),
        received_at=NOW,
    )

    assert order.status_code == 201
    assert payment.status_code == 202
    assert operator.status_code == 202
    assert order_use_case.commands[0].causation_id == "idem-order-header"
    assert payment_handler.commands[0].command_id == CommandId("idem-payment-header")
    assert cancel_handler.commands[0].command_id == CommandId("idem-operator-header")
    assert _json(operator.body)["idempotencyKey"] == "idem-operator-header"


def test_idempotency_key_header_conflicts_with_body_command_ids_deterministically() -> None:
    payment_router = HttpRouter()
    register_payment_routes(payment_router, PaymentsApi(CapturingPaymentHandler()))
    operator_router = HttpRouter()
    register_operator_action_routes(
        operator_router,
        OperatorActionApi(
            cancel_order_executor=OperatorCancelOrderActionExecutor(CapturingCancelOrderHandler()),
            outbox_action_executor=OperatorOutboxActionExecutor(NoopOutboxActionPort(), NoopOutboxActionPort()),
        ),
    )

    payment = payment_router.handle(
        "POST",
        "/payments/transaction-hashes",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-payment-conflict",
            "Idempotency-Key": "idem-header",
        },
        body=_json_body(
            {
                "commandId": "idem-body",
                "orderId": str(ORDER_ID),
                "paymentId": str(PAYMENT_ID),
                "txHash": "0x" + "ab" * 32,
            }
        ),
    )
    operator = operator_router.handle(
        "POST",
        f"/operator/orders/{ORDER_ID}/cancel",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-operator-conflict",
            "X-User-Id": "operator-1",
            "X-User-Scopes": "operator:action",
            "Idempotency-Key": "idem-header",
        },
        body=_json_body({"reason": "customer request", "idempotencyKey": "idem-body"}),
    )

    assert payment.status_code == 400
    assert operator.status_code == 400
    assert _json(payment.body)["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert _json(operator.body)["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json(body: bytes) -> dict[str, Any]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


class FailingIfCalledProbe:
    def __init__(self, component: str) -> None:
        self.component = component
        self.calls = 0

    def check(self) -> ReadinessProbeResult:
        self.calls += 1
        raise AssertionError(f"{self.component} probe must not be called")


class StaticProbe:
    def __init__(self, result: ReadinessProbeResult) -> None:
        self.result = result

    def check(self) -> ReadinessProbeResult:
        return self.result


class CapturingOrderUseCase:
    def __init__(self) -> None:
        self.commands: list[CreateOrderCommand] = []

    def createOrder(self, command: CreateOrderCommand) -> OrderCreationResult:
        self.commands.append(command)
        amount = Crypto(
            amount=Decimal("12.50"),
            symbol="USDC",
            chain_id=11155111,
            token_address=TOKEN_ADDRESS,
            decimals=6,
        )
        customer = Customer(
            customer_id=CUSTOMER_ID,
            user_id=command.authenticated_user_id,
            customer_wallet="0x1111111111111111111111111111111111111111",
        )
        store = Store(
            store_id=STORE_ID,
            owner_user_id=OWNER_USER_ID,
            products=(Product(product_id=PRODUCT_ID, name="Ledger Mug", price=amount),),
            store_wallet="0x2222222222222222222222222222222222222222",
            supported_chain_ids=(11155111,),
        )
        order = Order.initialize_order(
            order_id=ORDER_ID,
            customer=customer,
            store=store,
            delivery_address=Address(id="ship-to", street="2 River Rd"),
            product_quantities={PRODUCT_ID: 2},
            created_at=NOW,
            tracking_id=TRACKING_ID,
        )
        return OrderCreationResult(
            order=order,
            total_amount=order.items[0].sub_total,
            outbox_message=OutboxMessage(
                kind=OutboxMessageKind.EVENT,
                identity=str(MESSAGE_ID),
                name=CheckoutEventName.ORDER_CREATED.value,
                topic="order.events",
                key=str(ORDER_ID),
                payload={"orderId": str(ORDER_ID)},
                created_at=NOW,
            ),
        )


class CapturingPaymentHandler:
    def __init__(self) -> None:
        self.commands: list[SubmitTransactionHashCommand] = []

    def submit_transaction_hash(self, command: SubmitTransactionHashCommand) -> PaymentCommandResult:
        self.commands.append(command)
        return PaymentCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=PaymentCommandStatus.TX_SUBMITTED,
            payment=None,
        )


class CapturingCancelOrderHandler:
    def __init__(self) -> None:
        self.commands: list[CancelOrderCommand] = []

    def cancel_order(self, command: CancelOrderCommand) -> OrderCommandResult:
        self.commands.append(command)
        return OrderCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=OrderCommandStatus.CANCELLED,
        )


class NoopOutboxActionPort:
    def request_retry(self, request: Any) -> Any:
        raise AssertionError("retry is not used")

    def request_replay(self, request: Any) -> Any:
        raise AssertionError("replay is not used")

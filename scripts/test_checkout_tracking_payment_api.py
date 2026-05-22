from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, get_type_hints


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiRequest, ApiAuthContext  # noqa: E402
from token_payments.api.checkout import CheckoutApi  # noqa: E402
from token_payments.api.payments import PaymentsApi  # noqa: E402
from token_payments.contexts.order.adapter import PostgresCheckoutTrackingQuery  # noqa: E402
from token_payments.contexts.order.application.queries import (  # noqa: E402
    CheckoutTrackingQueryPort,
    CheckoutTrackingSnapshot,
    OutboxStatusSnapshot,
)
from token_payments.contexts.order.domain import OrderStatus, TrackingId  # noqa: E402
from token_payments.contexts.payment.application import (  # noqa: E402
    PaymentCommandHandler,
    PaymentCommandStatus,
    SubmitTransactionHashCommand,
)
from token_payments.contexts.payment.domain import (  # noqa: E402
    AuthorizationStatus,
    GasEstimate,
    Payment,
    PaymentAuthorization,
    PaymentStatus,
    TransactionReceipt,
    TransactionSignatureRequest,
)
from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    CheckoutCommandName,
    CommandId,
    Crypto,
    CustomerId,
    OrderId,
    OutboxMessage,
    OutboxPublishStatus,
    PaymentId,
    ProcessedCommand,
    TransactionHash,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 10, 7, 0, tzinfo=UTC)
UPDATED_AT = NOW + timedelta(minutes=5)
EXPIRES_AT = NOW + timedelta(minutes=15)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c31")
TRACKING_ID = TrackingId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c32")
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c33")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c34")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c35")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")
TX_HASH = TransactionHash("0x" + "ab" * 32)
SUBMIT_COMMAND_ID = CommandId(f"{ORDER_ID}:SubmitTransactionHashCommand")


def test_tracking_api_returns_awaiting_signature_payment_request_and_gas_estimate() -> None:
    api = CheckoutApi(FakeCheckoutTrackingQuery(_awaiting_snapshot()))

    response = api.get_tracking(
        ApiRequest(
            request_id="req-track",
            method="GET",
            path=f"/checkout/tracking/{TRACKING_ID}",
            query={"trackingId": str(TRACKING_ID)},
            received_at=NOW,
        )
    )

    assert response.status_code == 200
    assert response.request_id == "req-track"
    assert response.body["checkout"] == {
        "orderId": str(ORDER_ID),
        "trackingId": str(TRACKING_ID),
        "paymentId": str(PAYMENT_ID),
        "status": "AWAITING_SIGNATURE",
        "currentStep": "AWAITING_SIGNATURE",
        "pendingAction": "SIGN_PAYMENT",
        "paymentRequest": {
            "requestId": "payment-request-123",
            "amount": {
                "amount": "1.25",
                "symbol": "USDC",
                "chainId": 11155111,
                "tokenAddress": str(TOKEN_ADDRESS),
                "decimals": 6,
            },
            "to": str(WALLET_TO),
            "expiresAt": EXPIRES_AT.isoformat(),
        },
        "gasEstimate": {
            "estimatedFee": {
                "amount": "0.0100",
                "symbol": "ETH",
                "chainId": 11155111,
                "tokenAddress": None,
                "decimals": 18,
            },
            "gasLimit": 21000,
            "bufferRate": "0.10",
            "maxFee": {
                "amount": "0.011000",
                "symbol": "ETH",
                "chainId": 11155111,
                "tokenAddress": None,
                "decimals": 18,
            },
        },
        "txHash": None,
        "failureReason": None,
        "updatedAt": UPDATED_AT.isoformat(),
        "outboxStatus": [
            {
                "messageId": "payment-started-message",
                "name": "PaymentProcessingStartedEvent",
                "status": "READY",
                "updatedAt": (NOW + timedelta(minutes=1)).isoformat(),
            }
        ],
    }


def test_tracking_api_accepts_order_id_and_maps_receipt_pending_state() -> None:
    snapshot = _snapshot(payment=_awaiting_payment().submit_tx_hash(TX_HASH), authorization=_authorized_authorization())
    query = FakeCheckoutTrackingQuery(snapshot)
    api = CheckoutApi(query)

    response = api.get_tracking(
        ApiRequest(
            request_id="req-track-order",
            method="GET",
            path=f"/checkout/orders/{ORDER_ID}",
            query={"orderId": str(ORDER_ID)},
            received_at=NOW,
        )
    )

    assert response.status_code == 200
    assert query.order_id_calls == [ORDER_ID]
    assert query.tracking_id_calls == []
    assert response.body["checkout"]["status"] == "SUBMITTED"
    assert response.body["checkout"]["paymentId"] == str(PAYMENT_ID)
    assert response.body["checkout"]["currentStep"] == "RECEIPT_PENDING"
    assert response.body["checkout"]["pendingAction"] == "WAIT_FOR_RECEIPT"
    assert response.body["checkout"]["txHash"] == str(TX_HASH)


def test_tracking_api_derives_signature_request_from_awaiting_payment_when_authorization_is_missing() -> None:
    api = CheckoutApi(FakeCheckoutTrackingQuery(_snapshot(payment=_awaiting_payment(), authorization=None)))

    response = api.get_tracking(_tracking_request("req-derived-signature-request"))

    assert response.status_code == 200
    assert response.body["checkout"]["paymentId"] == str(PAYMENT_ID)
    assert response.body["checkout"]["currentStep"] == "AWAITING_SIGNATURE"
    assert response.body["checkout"]["pendingAction"] == "SIGN_PAYMENT"
    assert response.body["checkout"]["paymentRequest"] == {
        "requestId": str(PAYMENT_ID),
        "amount": {
            "amount": "1.25",
            "symbol": "USDC",
            "chainId": 11155111,
            "tokenAddress": str(TOKEN_ADDRESS),
            "decimals": 6,
        },
        "to": str(WALLET_TO),
        "expiresAt": EXPIRES_AT.isoformat(),
    }


def test_tracking_status_mapping_for_failed_expired_and_approved_states() -> None:
    failed = CheckoutApi(
        FakeCheckoutTrackingQuery(
            _snapshot(payment=_awaiting_payment().fail_payment("receipt reverted"), authorization=_requested_authorization())
        )
    ).get_tracking(_tracking_request("failed"))
    assert failed.body["checkout"]["status"] == "FAILED"
    assert failed.body["checkout"]["currentStep"] == "PAYMENT_FAILED"
    assert failed.body["checkout"]["pendingAction"] == "WAIT_FOR_COMPENSATION"
    assert failed.body["checkout"]["failureReason"] == "receipt reverted"

    expired = CheckoutApi(
        FakeCheckoutTrackingQuery(
            _snapshot(
                payment=_awaiting_payment().expire_awaiting_signature(now=EXPIRES_AT, reason="signature timeout"),
                authorization=_requested_authorization().expire(now=EXPIRES_AT),
            )
        )
    ).get_tracking(_tracking_request("expired"))
    assert expired.body["checkout"]["status"] == "EXPIRED"
    assert expired.body["checkout"]["currentStep"] == "PAYMENT_EXPIRED"
    assert expired.body["checkout"]["pendingAction"] == "WAIT_FOR_COMPENSATION"
    assert expired.body["checkout"]["failureReason"] == "signature timeout"

    approved = CheckoutApi(
        FakeCheckoutTrackingQuery(
            _snapshot(order_status=OrderStatus.APPROVED, payment=_confirmed_payment(), authorization=_authorized_authorization())
        )
    ).get_tracking(_tracking_request("approved"))
    assert approved.body["checkout"]["status"] == "APPROVED"
    assert approved.body["checkout"]["currentStep"] == "ORDER_APPROVED"
    assert approved.body["checkout"]["pendingAction"] is None
    assert approved.body["checkout"]["failureReason"] is None


def test_tracking_api_maps_not_found_and_validation_errors() -> None:
    api = CheckoutApi(FakeCheckoutTrackingQuery(None))

    missing = api.get_tracking(
        ApiRequest(request_id="req-missing", method="GET", path="/checkout/tracking/missing", query={"orderId": str(ORDER_ID)})
    )
    assert missing.status_code == 404
    assert missing.body["error"]["code"] == "CHECKOUT_NOT_FOUND"

    invalid = api.get_tracking(ApiRequest(request_id="req-invalid", method="GET", path="/checkout/tracking", query={}))
    assert invalid.status_code == 400
    assert invalid.body["error"]["code"] == "VALIDATION_ERROR"


def test_submit_transaction_hash_api_delegates_to_payment_handler_and_returns_receipt_pending() -> None:
    payment_repository = FakePaymentRepository(_awaiting_payment())
    authorization_repository = FakePaymentAuthorizationRepository(_requested_authorization())
    outbox_messages = FakeOutboxMessageRepository()
    blockchain = FakeBlockchainAdapter()
    handler = PaymentCommandHandler(
        payment_repository=payment_repository,
        authorization_repository=authorization_repository,
        processed_commands=FakeProcessedCommandRepository(),
        outbox_messages=outbox_messages,
        blockchain_adapter=blockchain,
        timeout_scheduler=FakePaymentTimeoutScheduler(),
        transaction_service=FakeTransactionService(),
    )
    tracking_query = FakeCheckoutTrackingQuery(_awaiting_snapshot())
    api = PaymentsApi(handler, tracking_query=tracking_query)

    response = api.submit_transaction_hash(
        ApiRequest(
            request_id="req-submit",
            method="POST",
            path=f"/payments/{PAYMENT_ID}/tx-hash",
            body={"trackingId": str(TRACKING_ID), "txHash": str(TX_HASH)},
            auth_context=ApiAuthContext(user_id=str(USER_ID), session_id="session-1"),
            received_at=NOW,
        )
    )

    assert response.status_code == 202
    assert response.body["payment"]["trackingId"] == str(TRACKING_ID)
    assert response.body["payment"]["status"] == PaymentCommandStatus.TX_SUBMITTED.value
    assert response.body["payment"]["currentStep"] == "RECEIPT_PENDING"
    assert response.body["payment"]["pendingAction"] == "WAIT_FOR_RECEIPT"
    assert response.body["payment"]["txHash"] == str(TX_HASH)
    assert response.body["payment"]["updatedAt"] == NOW.isoformat()
    assert payment_repository.saved[0].status == PaymentStatus.SUBMITTED
    assert payment_repository.saved[0].tx_hash == TX_HASH
    assert authorization_repository.saved[0].status == AuthorizationStatus.AUTHORIZED
    assert authorization_repository.saved[0].tx_hash == TX_HASH
    assert outbox_messages.saved == []
    assert blockchain.receipt_calls == []


def test_submit_transaction_hash_api_builds_deterministic_command_and_maps_errors() -> None:
    tracking_query = FakeCheckoutTrackingQuery(_awaiting_snapshot())
    api = PaymentsApi(CapturingPaymentCommandHandler(), tracking_query=tracking_query)

    response = api.submit_transaction_hash(
        ApiRequest(
            request_id="req-capture",
            method="POST",
            path="/payments/submit-tx-hash",
            body={"trackingId": str(TRACKING_ID), "txHash": str(TX_HASH)},
            auth_context=ApiAuthContext(user_id=str(USER_ID), session_id="session-1"),
            received_at=NOW,
        )
    )

    command = api._handler.commands[0]
    assert response.status_code == 202
    assert command == SubmitTransactionHashCommand(
        command_id=CommandId(f"payment.submit_tx:{TRACKING_ID}"),
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        tx_hash=TX_HASH,
        submitted_at=NOW,
        causation_id="req-capture",
    )

    invalid = api.submit_transaction_hash(
        ApiRequest(
            request_id="req-invalid",
            method="POST",
            path="/payments/submit-tx-hash",
            body={"trackingId": str(TRACKING_ID), "txHash": "not-a-hash"},
            auth_context=ApiAuthContext(user_id=str(USER_ID), session_id="session-1"),
            received_at=NOW,
        )
    )
    assert invalid.status_code == 400
    assert invalid.body["error"]["code"] == "VALIDATION_ERROR"


def test_postgres_tracking_query_combines_order_payment_authorization_and_outbox_status() -> None:
    connection = FakeTrackingPostgresConnection()
    query = PostgresCheckoutTrackingQuery(connection)

    snapshot = query.get_by_tracking_id(TRACKING_ID)

    assert snapshot is not None
    assert snapshot.order_id == ORDER_ID
    assert snapshot.tracking_id == TRACKING_ID
    assert snapshot.order_status == OrderStatus.PENDING
    assert snapshot.payment is not None
    assert snapshot.payment.status == PaymentStatus.AWAITING_SIGNATURE
    assert snapshot.payment.gas_estimate == _gas_estimate().apply_buffer()
    assert snapshot.authorization is not None
    assert snapshot.authorization.status == AuthorizationStatus.REQUESTED
    assert snapshot.authorization.signature_request.request_id == "payment-request-123"
    assert snapshot.outbox_statuses == (
        OutboxStatusSnapshot(
            message_id="payment-started-message",
            name="PaymentProcessingStartedEvent",
            status=OutboxPublishStatus.READY,
            updated_at=NOW + timedelta(minutes=1),
        ),
    )
    assert snapshot.updated_at == UPDATED_AT

    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "from orders" in normalized_sql
    assert "from payments" in normalized_sql
    assert "from payment_authorizations" in normalized_sql
    assert "from outbox_messages" in normalized_sql
    assert "insert into" not in normalized_sql
    assert "update " not in normalized_sql
    assert "delete from" not in normalized_sql


def test_tracking_query_contract_is_protocol_and_application_has_no_adapter_imports() -> None:
    assert getattr(CheckoutTrackingQueryPort, "_is_protocol", False)
    hints = get_type_hints(CheckoutTrackingQueryPort.get_by_order_id)
    assert hints["return"] == CheckoutTrackingSnapshot | None

    violations: dict[str, list[str]] = {}
    for path in (ROOT / "app/token_payments/contexts/order/application").glob("**/*.py"):
        illegal = sorted(
            module
            for module in _imported_modules(path)
            if module.startswith("token_payments.api")
            or module.startswith("token_payments.contexts.order.adapter")
            or module.startswith("token_payments.shared.adapter")
            or ".adapter" in module
        )
        if illegal:
            violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


def _tracking_request(request_id: str) -> ApiRequest:
    return ApiRequest(
        request_id=request_id,
        method="GET",
        path=f"/checkout/tracking/{TRACKING_ID}",
        query={"trackingId": str(TRACKING_ID)},
        received_at=NOW,
    )


def _awaiting_snapshot() -> CheckoutTrackingSnapshot:
    return _snapshot(payment=_awaiting_payment(), authorization=_requested_authorization())


def _snapshot(
    *,
    order_status: OrderStatus = OrderStatus.PENDING,
    payment: Payment | None = None,
    authorization: PaymentAuthorization | None = None,
) -> CheckoutTrackingSnapshot:
    return CheckoutTrackingSnapshot(
        order_id=ORDER_ID,
        tracking_id=TRACKING_ID,
        order_status=order_status,
        failure_messages=(),
        payment=payment,
        authorization=authorization,
        outbox_statuses=(
            OutboxStatusSnapshot(
                message_id="payment-started-message",
                name="PaymentProcessingStartedEvent",
                status=OutboxPublishStatus.READY,
                updated_at=NOW + timedelta(minutes=1),
            ),
        ),
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


def _confirmed_payment() -> Payment:
    return _awaiting_payment().submit_tx_hash(TX_HASH).confirm_payment(_receipt())


def _requested_authorization() -> PaymentAuthorization:
    return PaymentAuthorization.request_transaction_signature(
        payment_id=PAYMENT_ID,
        user_id=USER_ID,
        wallet=WALLET_FROM,
        chain_network=CHAIN,
        signature_request=_signature_request(),
    )


def _authorized_authorization() -> PaymentAuthorization:
    return _requested_authorization().authorize_tx_hash(TX_HASH, authorized_at=NOW + timedelta(minutes=2))


def _signature_request() -> TransactionSignatureRequest:
    return TransactionSignatureRequest(
        request_id="payment-request-123",
        amount=_amount(),
        to=WALLET_TO,
        expires_at=EXPIRES_AT,
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


def _receipt() -> TransactionReceipt:
    return TransactionReceipt(hash=TX_HASH, block_number=12345, gas_used=21000)


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


class FakePaymentRepository:
    def __init__(self, payment: Payment | None = None) -> None:
        self.payments: dict[PaymentId, Payment] = {}
        if payment is not None:
            self.payments[payment.payment_id] = payment
        self.saved: list[Payment] = []

    def get(self, payment_id: PaymentId) -> Payment | None:
        return self.payments.get(payment_id)

    def save(self, payment: Payment) -> None:
        self.saved.append(payment)
        self.payments[payment.payment_id] = payment


class FakePaymentAuthorizationRepository:
    def __init__(self, authorization: PaymentAuthorization | None = None) -> None:
        self.authorizations: dict[PaymentId, PaymentAuthorization] = {}
        if authorization is not None:
            self.authorizations[authorization.payment_id] = authorization
        self.saved: list[PaymentAuthorization] = []

    def get(self, payment_id: PaymentId) -> PaymentAuthorization | None:
        return self.authorizations.get(payment_id)

    def save(self, authorization: PaymentAuthorization) -> None:
        self.saved.append(authorization)
        self.authorizations[authorization.payment_id] = authorization


class FakeProcessedCommandRepository:
    def __init__(self) -> None:
        self.records: list[ProcessedCommand] = []

    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return False

    def record(self, processed_command: ProcessedCommand) -> None:
        self.records.append(processed_command)


class FakeOutboxMessageRepository:
    def __init__(self) -> None:
        self.saved: list[OutboxMessage] = []

    def save(self, message: OutboxMessage) -> None:
        self.saved.append(message)


class FakeBlockchainAdapter:
    def __init__(self) -> None:
        self.receipt_calls: list[TransactionHash] = []

    def estimate_gas(
        self,
        amount: Crypto,
        wallet_from: WalletAddress,
        wallet_to: WalletAddress,
        chain_network: ChainNetwork,
    ) -> GasEstimate:
        return _gas_estimate()

    def get_transaction_receipt(self, tx_hash: TransactionHash) -> TransactionReceipt | None:
        self.receipt_calls.append(tx_hash)
        return None


class FakePaymentTimeoutScheduler:
    def schedule_expiration(self, payment_id: PaymentId, expires_at: datetime) -> None:
        pass

    def cancel_expiration(self, payment_id: PaymentId) -> None:
        pass


class FakeTransactionService:
    def create_signature_request(
        self,
        payment_id: PaymentId,
        amount: Crypto,
        wallet_to: WalletAddress,
        expires_at: datetime,
    ) -> TransactionSignatureRequest:
        return _signature_request()

    def refund_payment(self, payment: Payment) -> TransactionReceipt:
        return _receipt()


class CapturingPaymentCommandHandler:
    def __init__(self) -> None:
        self.commands: list[SubmitTransactionHashCommand] = []

    def submit_transaction_hash(self, command: SubmitTransactionHashCommand) -> Any:
        self.commands.append(command)
        return type(
            "Result",
            (),
            {
                "status": PaymentCommandStatus.TX_SUBMITTED,
                "command_id": command.command_id,
                "order_id": command.order_id,
                "payment": _awaiting_payment().submit_tx_hash(command.tx_hash),
            },
        )()


class FakeTrackingPostgresConnection:
    def __init__(self) -> None:
        self.statements: list[FakeStatement] = []
        self.order_row = {
            "order_id": str(ORDER_ID),
            "tracking_id": str(TRACKING_ID),
            "status": OrderStatus.PENDING.value,
            "failure_messages": [],
            "order_updated_at": UPDATED_AT - timedelta(minutes=2),
        }
        self.payment_row = {
            "payment_id": str(PAYMENT_ID),
            "order_id": str(ORDER_ID),
            "customer_id": str(CUSTOMER_ID),
            "amount_numeric": Decimal("1.25"),
            "amount_symbol": "USDC",
            "amount_chain_id": 11155111,
            "amount_token_address": str(TOKEN_ADDRESS),
            "amount_decimals": 6,
            "status": PaymentStatus.AWAITING_SIGNATURE.value,
            "wallet_from": str(WALLET_FROM),
            "wallet_to": str(WALLET_TO),
            "chain_id": 11155111,
            "chain_name": "Sepolia",
            "tx_hash": None,
            "gas_estimated_fee": Decimal("0.0100"),
            "gas_fee_symbol": "ETH",
            "gas_fee_chain_id": 11155111,
            "gas_fee_token_address": None,
            "gas_fee_decimals": 18,
            "gas_limit": 21000,
            "gas_buffer_rate": Decimal("0.10"),
            "gas_max_fee": Decimal("0.011000"),
            "receipt_block_number": None,
            "receipt_gas_used": None,
            "failure_reason": None,
            "refund_tx_hash": None,
            "refund_block_number": None,
            "refund_gas_used": None,
            "expires_at": EXPIRES_AT,
            "payment_updated_at": UPDATED_AT,
        }
        self.authorization_row = {
            "payment_id": str(PAYMENT_ID),
            "user_id": str(USER_ID),
            "wallet_address": str(WALLET_FROM),
            "chain_id": 11155111,
            "chain_name": "Sepolia",
            "request_id": "payment-request-123",
            "amount_numeric": Decimal("1.25"),
            "amount_symbol": "USDC",
            "amount_chain_id": 11155111,
            "amount_token_address": str(TOKEN_ADDRESS),
            "amount_decimals": 6,
            "to_wallet_address": str(WALLET_TO),
            "status": AuthorizationStatus.REQUESTED.value,
            "tx_hash": None,
            "expires_at": EXPIRES_AT,
            "authorized_at": None,
            "authorization_updated_at": UPDATED_AT - timedelta(minutes=1),
        }
        self.outbox_rows = [
            {
                "message_identity": "payment-started-message",
                "name": "PaymentProcessingStartedEvent",
                "status": OutboxPublishStatus.READY.value,
                "outbox_updated_at": NOW + timedelta(minutes=1),
            }
        ]

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> "FakeResult":
        self.statements.append(FakeStatement(sql=sql, params=dict(params or {})))
        normalized = _normalize_sql(sql)
        if "from orders" in normalized:
            if params and params.get("tracking_id") == str(TRACKING_ID):
                return FakeResult([self.order_row])
            if params and params.get("order_id") == str(ORDER_ID):
                return FakeResult([self.order_row])
            return FakeResult([])
        if "from payments" in normalized:
            return FakeResult([self.payment_row])
        if "from payment_authorizations" in normalized:
            return FakeResult([self.authorization_row])
        if "from outbox_messages" in normalized:
            return FakeResult(self.outbox_rows)
        return FakeResult([])


@dataclass(frozen=True)
class FakeStatement:
    sql: str
    params: Mapping[str, Any]


class FakeResult:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self._rows = rows

    def fetchone(self) -> Mapping[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Mapping[str, Any]]:
        return self._rows


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().split())


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules

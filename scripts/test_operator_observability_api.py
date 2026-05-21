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

from token_payments.api import ApiRequest  # noqa: E402
from token_payments.api.operator import OperatorApi, OperatorClaims  # noqa: E402
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.contexts.order.domain import OrderStatus  # noqa: E402
from token_payments.contexts.payment.domain import PaymentStatus  # noqa: E402
from token_payments.runtime import HealthState  # noqa: E402
from token_payments.runtime.observability import (  # noqa: E402
    OperatorDashboardQuery,
    OperatorErrorSnapshot,
    OperatorObservabilityQueryPort,
    OperatorObservabilitySnapshot,
    OperatorOrderSnapshot,
    OperatorOutboxSnapshot,
    OperatorPage,
    OperatorPaymentSnapshot,
    OperatorSortDirection,
    OperatorWorkerSnapshot,
    PostgresOperatorObservabilityQuery,
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
CREATED_AT = NOW - timedelta(minutes=15)
UPDATED_AT = NOW - timedelta(minutes=2)
CHECKED_AT = NOW - timedelta(seconds=30)
EXPIRES_AT = NOW + timedelta(minutes=10)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6d11")
ORDER_ID_2 = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6d12")
TRACKING_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6d13"
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6d14")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6d15")
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6d16")
PAYMENT_ID_2 = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6d17")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6d18")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")
TX_HASH = TransactionHash("0x" + "ab" * 32)


def test_operator_dashboard_lists_read_models_with_filters_sort_page_tokens_and_worker_health() -> None:
    query = FakeOperatorObservabilityQuery(_dashboard_snapshot())
    policy = FakeOperatorPolicy(allowed=True)
    api = OperatorApi(query, policy=policy)

    response = api.get_dashboard(
        ApiRequest(
            request_id="req-operator-list",
            method="GET",
            path="/operator/observability",
            headers={"X-User-Id": str(USER_ID), "X-User-Scopes": "operator:read"},
            query={
                "context": "orders,payments,outbox",
                "status": "FAILED,EXPIRED",
                "chainId": CHAIN.chain_id,
                "storeId": str(STORE_ID),
                "failedOnly": "true",
                "retryCandidatesOnly": "true",
                "sort": "-updatedAt",
                "limit": "25",
                "pageToken": "cursor-1",
            },
            received_at=NOW,
        )
    )

    assert response.status_code == 200
    assert response.request_id == "req-operator-list"
    assert policy.claims == [
        OperatorClaims(user_id=str(USER_ID), scopes=("operator:read",)),
    ]
    assert query.dashboard_queries == [
        OperatorDashboardQuery(
            contexts=("orders", "payments", "outbox"),
            statuses=("FAILED", "EXPIRED"),
            chain_id=CHAIN.chain_id,
            store_id=str(STORE_ID),
            failed_only=True,
            retry_candidates_only=True,
            sort_by="updatedAt",
            sort_direction=OperatorSortDirection.DESC,
            limit=25,
            page_token="cursor-1",
        )
    ]
    assert response.body == {
        "orders": [
            {
                "orderId": str(ORDER_ID),
                "trackingId": TRACKING_ID,
                "customerId": str(CUSTOMER_ID),
                "storeId": str(STORE_ID),
                "status": OrderStatus.CANCELLING.value,
                "paymentId": str(PAYMENT_ID),
                "paymentStatus": PaymentStatus.FAILED.value,
                "totalAmount": _crypto_payload(),
                "failureReason": "receipt reverted",
                "latestEvent": "PaymentFailedEvent",
                "createdAt": CREATED_AT.isoformat(),
                "updatedAt": UPDATED_AT.isoformat(),
            }
        ],
        "payments": [
            {
                "paymentId": str(PAYMENT_ID),
                "orderId": str(ORDER_ID),
                "customerId": str(CUSTOMER_ID),
                "status": PaymentStatus.FAILED.value,
                "amount": _crypto_payload(),
                "chain": {"chainId": 11155111, "name": "Sepolia"},
                "walletFrom": str(WALLET_FROM),
                "walletTo": str(WALLET_TO),
                "txHash": str(TX_HASH),
                "failureReason": "receipt reverted",
                "expiresAt": EXPIRES_AT.isoformat(),
                "createdAt": CREATED_AT.isoformat(),
                "updatedAt": UPDATED_AT.isoformat(),
            }
        ],
        "outbox": [
            {
                "messageId": "failed-payment-message",
                "kind": OutboxMessageKind.EVENT.value,
                "name": "PaymentFailedEvent",
                "topic": "payment.events",
                "key": str(ORDER_ID),
                "status": OutboxPublishStatus.FAILED.value,
                "failureCount": 2,
                "lastError": "broker unavailable",
                "retryCandidate": True,
                "retryReason": "FAILED rows are reclaimed by the outbox relay retry policy",
                "createdAt": CREATED_AT.isoformat(),
                "publishedAt": None,
                "updatedAt": UPDATED_AT.isoformat(),
            }
        ],
        "workers": [
            {
                "component": "outbox-relay",
                "state": HealthState.DEGRADED.value,
                "checkedAt": CHECKED_AT.isoformat(),
                "details": {"lastBatchFailed": 1},
            }
        ],
        "errors": [
            {
                "context": "payment",
                "aggregateId": str(PAYMENT_ID),
                "code": PaymentStatus.FAILED.value,
                "message": "receipt reverted",
                "createdAt": UPDATED_AT.isoformat(),
            }
        ],
        "pagination": {
            "orders": {"limit": 25, "nextPageToken": "orders:next"},
            "payments": {"limit": 25, "nextPageToken": "payments:next"},
            "outbox": {"limit": 25, "nextPageToken": "outbox:next"},
        },
    }


def test_operator_detail_endpoints_return_stable_read_only_envelopes_and_not_found_errors() -> None:
    query = FakeOperatorObservabilityQuery(_dashboard_snapshot())
    api = OperatorApi(query, policy=FakeOperatorPolicy(allowed=True))

    order = api.get_order(
        ApiRequest(
            request_id="req-order-detail",
            method="GET",
            path=f"/operator/orders/{ORDER_ID}",
            headers={"X-User-Role": UserRole.ADMIN.value},
            received_at=NOW,
        )
    )
    assert order.status_code == 200
    assert order.body["orders"][0]["orderId"] == str(ORDER_ID)
    assert order.body["orders"][0]["failureReason"] == "receipt reverted"
    assert order.body["payments"][0]["paymentId"] == str(PAYMENT_ID)
    assert query.order_detail_calls == [ORDER_ID]

    payment = api.get_payment(
        ApiRequest(
            request_id="req-payment-detail",
            method="GET",
            path=f"/operator/payments/{PAYMENT_ID}",
            headers={"X-User-Role": UserRole.ADMIN.value},
            received_at=NOW,
        )
    )
    assert payment.status_code == 200
    assert payment.body["payments"][0]["failureReason"] == "receipt reverted"
    assert query.payment_detail_calls == [PAYMENT_ID]

    outbox = api.get_outbox_message(
        ApiRequest(
            request_id="req-outbox-detail",
            method="GET",
            path="/operator/outbox/failed-payment-message",
            headers={"X-User-Role": UserRole.ADMIN.value},
            query={"kind": OutboxMessageKind.EVENT.value},
            received_at=NOW,
        )
    )
    assert outbox.status_code == 200
    assert outbox.body["outbox"][0]["retryCandidate"] is True
    assert outbox.body["outbox"][0]["retryReason"] == "FAILED rows are reclaimed by the outbox relay retry policy"
    assert query.outbox_detail_calls == [(OutboxMessageKind.EVENT, "failed-payment-message")]

    missing = api.get_order(
        ApiRequest(
            request_id="req-missing",
            method="GET",
            path=f"/operator/orders/{ORDER_ID_2}",
            headers={"X-User-Role": UserRole.ADMIN.value},
            received_at=NOW,
        )
    )
    assert missing.status_code == 404
    assert missing.body["error"]["code"] == "OPERATOR_RESOURCE_NOT_FOUND"


def test_operator_policy_denies_non_operator_without_querying() -> None:
    query = FakeOperatorObservabilityQuery(_dashboard_snapshot())
    policy = FakeOperatorPolicy(allowed=False)
    api = OperatorApi(query, policy=policy)

    response = api.get_dashboard(
        ApiRequest(
            request_id="req-forbidden",
            method="GET",
            path="/operator/observability",
            headers={"X-User-Id": str(USER_ID), "X-User-Scopes": "user:self"},
            received_at=NOW,
        )
    )

    assert response.status_code == 403
    assert response.body["error"]["code"] == "OPERATOR_FORBIDDEN"
    assert policy.claims == [OperatorClaims(user_id=str(USER_ID), scopes=("user:self",))]
    assert query.dashboard_queries == []
    assert query.order_detail_calls == []
    assert query.payment_detail_calls == []
    assert query.outbox_detail_calls == []


def test_default_operator_policy_uses_operator_read_scope_not_role_header() -> None:
    query = FakeOperatorObservabilityQuery(_dashboard_snapshot())
    api = OperatorApi(query)

    admin = api.get_dashboard(
        ApiRequest(
            request_id="req-admin",
            method="GET",
            path="/operator/observability",
            headers={"X-User-Role": UserRole.ADMIN.value, "X-User-Scopes": "operator:read"},
            received_at=NOW,
        )
    )
    customer = api.get_dashboard(
        ApiRequest(
            request_id="req-customer",
            method="GET",
            path="/operator/observability",
            headers={"X-User-Role": UserRole.ADMIN.value},
            received_at=NOW,
        )
    )

    assert admin.status_code == 200
    assert customer.status_code == 403


def test_postgres_operator_observability_query_reads_orders_payments_outbox_without_mutation() -> None:
    connection = FakeOperatorPostgresConnection()
    query = PostgresOperatorObservabilityQuery(
        connection,
        workers=(
            OperatorWorkerSnapshot(
                component="payment-timeout",
                state=HealthState.OK,
                checked_at=CHECKED_AT,
                details={"expiredCandidates": 0},
            ),
        ),
    )

    snapshot = query.list_dashboard(
        OperatorDashboardQuery(
            contexts=("orders", "payments", "outbox"),
            statuses=("FAILED",),
            chain_id=CHAIN.chain_id,
            store_id=str(STORE_ID),
            failed_only=True,
            retry_candidates_only=True,
            limit=1,
            sort_by="updatedAt",
            sort_direction=OperatorSortDirection.DESC,
        )
    )

    assert [order.order_id for order in snapshot.orders] == [ORDER_ID]
    assert snapshot.orders[0].failure_reason == "receipt reverted"
    assert [payment.payment_id for payment in snapshot.payments] == [PAYMENT_ID]
    assert snapshot.payments[0].failure_reason == "receipt reverted"
    assert [row.identity for row in snapshot.outbox] == ["failed-payment-message"]
    assert snapshot.outbox[0].retry_candidate is True
    assert snapshot.outbox[0].retry_reason == "FAILED rows are reclaimed by the outbox relay retry policy"
    assert snapshot.workers[0].component == "payment-timeout"
    assert snapshot.errors == (
        OperatorErrorSnapshot(
            context="order",
            aggregate_id=str(ORDER_ID),
            code=OrderStatus.CANCELLING.value,
            message="receipt reverted",
            created_at=UPDATED_AT,
        ),
        OperatorErrorSnapshot(
            context="payment",
            aggregate_id=str(PAYMENT_ID),
            code=PaymentStatus.FAILED.value,
            message="receipt reverted",
            created_at=UPDATED_AT,
        ),
        OperatorErrorSnapshot(
            context="outbox",
            aggregate_id="failed-payment-message",
            code=OutboxPublishStatus.FAILED.value,
            message="broker unavailable",
            created_at=UPDATED_AT,
        ),
    )
    assert snapshot.pagination == {
        "orders": OperatorPage(limit=1, next_page_token="orders:2026-05-10T09:27:00+00:00:018f33aa-9e6d-73d8-9dc3-47d6cdcc6d12"),
        "payments": OperatorPage(limit=1, next_page_token="payments:2026-05-10T09:27:00+00:00:018f33aa-9e6d-73d8-9dc3-47d6cdcc6d17"),
        "outbox": OperatorPage(limit=1, next_page_token="outbox:2026-05-10T09:27:00+00:00:another-failed-message"),
    }

    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "from orders" in normalized_sql
    assert "from payments" in normalized_sql
    assert "from outbox_messages" in normalized_sql
    assert "%(statuses)s::text[]" in normalized_sql
    assert "%(store_id)s::uuid" in normalized_sql
    assert "%(chain_id)s::integer" in normalized_sql
    assert "insert into" not in normalized_sql
    assert "update " not in normalized_sql
    assert "delete from" not in normalized_sql
    assert all(statement.params["limit"] == 2 for statement in connection.statements)


def test_postgres_operator_detail_queries_are_select_only_and_query_contract_is_protocol() -> None:
    connection = FakeOperatorPostgresConnection()
    query = PostgresOperatorObservabilityQuery(connection)

    order = query.get_order_detail(ORDER_ID)
    payment = query.get_payment_detail(PAYMENT_ID)
    outbox = query.get_outbox_detail(OutboxMessageKind.EVENT, "failed-payment-message")

    assert order is not None
    assert order.orders[0].order_id == ORDER_ID
    assert payment is not None
    assert payment.payments[0].payment_id == PAYMENT_ID
    assert outbox is not None
    assert outbox.outbox[0].identity == "failed-payment-message"

    hints = get_type_hints(OperatorObservabilityQueryPort.list_dashboard)
    assert getattr(OperatorObservabilityQueryPort, "_is_protocol", False)
    assert hints["return"] == OperatorObservabilitySnapshot

    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "payments.order_id = %(order_id)s" in normalized_sql
    assert "outbox_messages.message_key = %(message_key)s" in normalized_sql
    assert "insert into" not in normalized_sql
    assert "update " not in normalized_sql
    assert "delete from" not in normalized_sql


def test_operator_api_does_not_import_write_side_command_handlers() -> None:
    imported_modules = _imported_modules(ROOT / "app/token_payments/api/operator.py")

    forbidden = sorted(
        module
        for module in imported_modules
        if module.startswith("token_payments.contexts.payment.application")
        or module.startswith("token_payments.contexts.inventory.application")
        or module.startswith("token_payments.contexts.store_approval.application")
        or module.startswith("token_payments.contexts.checkout.application")
        or module.startswith("token_payments.contexts.order.application.service")
    )
    assert forbidden == []


def _dashboard_snapshot() -> OperatorObservabilitySnapshot:
    return OperatorObservabilitySnapshot(
        orders=(
            OperatorOrderSnapshot(
                order_id=ORDER_ID,
                tracking_id=TRACKING_ID,
                customer_id=CUSTOMER_ID,
                store_id=STORE_ID,
                status=OrderStatus.CANCELLING,
                payment_id=PAYMENT_ID,
                payment_status=PaymentStatus.FAILED,
                total_amount=_amount(),
                failure_reason="receipt reverted",
                latest_event="PaymentFailedEvent",
                created_at=CREATED_AT,
                updated_at=UPDATED_AT,
            ),
        ),
        payments=(
            OperatorPaymentSnapshot(
                payment_id=PAYMENT_ID,
                order_id=ORDER_ID,
                customer_id=CUSTOMER_ID,
                status=PaymentStatus.FAILED,
                amount=_amount(),
                chain=CHAIN,
                wallet_from=WALLET_FROM,
                wallet_to=WALLET_TO,
                tx_hash=TX_HASH,
                failure_reason="receipt reverted",
                expires_at=EXPIRES_AT,
                created_at=CREATED_AT,
                updated_at=UPDATED_AT,
            ),
        ),
        outbox=(
            OperatorOutboxSnapshot(
                identity="failed-payment-message",
                kind=OutboxMessageKind.EVENT,
                name="PaymentFailedEvent",
                topic="payment.events",
                key=str(ORDER_ID),
                status=OutboxPublishStatus.FAILED,
                failure_count=2,
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
                context="payment",
                aggregate_id=str(PAYMENT_ID),
                code=PaymentStatus.FAILED.value,
                message="receipt reverted",
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


def _crypto_payload() -> dict[str, Any]:
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
        if kind is OutboxMessageKind.EVENT and identity == "failed-payment-message":
            return self.snapshot
        return None


class FakeOperatorPolicy:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed = allowed
        self.claims: list[OperatorClaims] = []

    def can_read_observability(self, claims: OperatorClaims) -> bool:
        self.claims.append(claims)
        return self.allowed


class FakeOperatorPostgresConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []
        self.order_rows = [
            _order_row(ORDER_ID, TRACKING_ID, UPDATED_AT),
            _order_row(ORDER_ID_2, "018f33aa-9e6d-73d8-9dc3-47d6cdcc6d19", UPDATED_AT - timedelta(minutes=1)),
        ]
        self.payment_rows = [
            _payment_row(PAYMENT_ID, ORDER_ID, UPDATED_AT),
            _payment_row(PAYMENT_ID_2, ORDER_ID_2, UPDATED_AT - timedelta(minutes=1)),
        ]
        self.outbox_rows = [
            _outbox_row("failed-payment-message", ORDER_ID, UPDATED_AT),
            _outbox_row("another-failed-message", ORDER_ID_2, UPDATED_AT - timedelta(minutes=1)),
        ]

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> "FakeResult":
        statement = ExecutedStatement(sql=sql, params=dict(params or {}))
        self.statements.append(statement)
        normalized_sql = _normalize_sql(sql)
        if "from orders" in normalized_sql:
            order_id = statement.params.get("order_id")
            if order_id is not None:
                return FakeResult([row for row in self.order_rows if row["order_id"] == str(order_id)])
            return FakeResult(self.order_rows[: int(statement.params["limit"])])
        if "from payments" in normalized_sql:
            payment_id = statement.params.get("payment_id")
            if payment_id is not None:
                return FakeResult([row for row in self.payment_rows if row["payment_id"] == str(payment_id)])
            order_id = statement.params.get("order_id")
            if order_id is not None:
                return FakeResult([row for row in self.payment_rows if row["order_id"] == str(order_id)])
            return FakeResult(self.payment_rows[: int(statement.params["limit"])])
        if "from outbox_messages" in normalized_sql:
            identity = statement.params.get("message_identity")
            if identity is not None:
                return FakeResult([row for row in self.outbox_rows if row["message_identity"] == str(identity)])
            message_key = statement.params.get("message_key")
            if message_key is not None:
                return FakeResult([row for row in self.outbox_rows if row["message_key"] == str(message_key)])
            return FakeResult(self.outbox_rows[: int(statement.params["limit"])])
        raise AssertionError(f"unexpected SQL: {sql}")


def _order_row(order_id: OrderId, tracking_id: str, updated_at: datetime) -> dict[str, Any]:
    return {
        "order_id": str(order_id),
        "tracking_id": tracking_id,
        "customer_id": str(CUSTOMER_ID),
        "store_id": str(STORE_ID),
        "status": OrderStatus.CANCELLING.value,
        "payment_id": str(PAYMENT_ID),
        "payment_status": PaymentStatus.FAILED.value,
        "total_amount_numeric": Decimal("1.25"),
        "total_amount_symbol": "USDC",
        "total_amount_chain_id": CHAIN.chain_id,
        "total_amount_token_address": str(TOKEN_ADDRESS),
        "total_amount_decimals": 6,
        "failure_messages": ["receipt reverted"],
        "payment_failure_reason": "receipt reverted",
        "latest_event": "PaymentFailedEvent",
        "created_at": CREATED_AT,
        "updated_at": updated_at,
    }


def _payment_row(payment_id: PaymentId, order_id: OrderId, updated_at: datetime) -> dict[str, Any]:
    return {
        "payment_id": str(payment_id),
        "order_id": str(order_id),
        "customer_id": str(CUSTOMER_ID),
        "status": PaymentStatus.FAILED.value,
        "amount_numeric": Decimal("1.25"),
        "amount_symbol": "USDC",
        "amount_chain_id": CHAIN.chain_id,
        "amount_token_address": str(TOKEN_ADDRESS),
        "amount_decimals": 6,
        "chain_id": CHAIN.chain_id,
        "chain_name": CHAIN.name,
        "wallet_from": str(WALLET_FROM),
        "wallet_to": str(WALLET_TO),
        "tx_hash": str(TX_HASH),
        "failure_reason": "receipt reverted",
        "expires_at": EXPIRES_AT,
        "created_at": CREATED_AT,
        "updated_at": updated_at,
    }


def _outbox_row(identity: str, order_id: OrderId, updated_at: datetime) -> dict[str, Any]:
    return {
        "message_identity": identity,
        "kind": OutboxMessageKind.EVENT.value,
        "name": "PaymentFailedEvent",
        "topic": "payment.events",
        "message_key": str(order_id),
        "status": OutboxPublishStatus.FAILED.value,
        "failure_count": 2,
        "last_error": "broker unavailable",
        "created_at": CREATED_AT,
        "published_at": None,
        "updated_at": updated_at,
    }


@dataclass(frozen=True)
class ExecutedStatement:
    sql: str
    params: Mapping[str, Any]


class FakeResult:
    def __init__(self, rows: list[Mapping[str, Any]]) -> None:
        self._rows = rows

    def fetchone(self) -> Mapping[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Mapping[str, Any]]:
        return list(self._rows)


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

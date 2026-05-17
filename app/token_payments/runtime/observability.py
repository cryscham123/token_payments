"""Read-only operator observability query contracts and PostgreSQL adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from token_payments.contexts.order.domain import OrderStatus
from token_payments.contexts.payment.domain import PaymentStatus
from token_payments.shared.adapter.postgres import PostgresConnection
from token_payments.shared.domain import (
    ChainNetwork,
    Crypto,
    CustomerId,
    OrderId,
    OutboxMessageKind,
    OutboxPublishStatus,
    PaymentId,
    StoreId,
    TransactionHash,
    WalletAddress,
)

from .contracts import HealthState, JsonValue


class OperatorSortDirection(StrEnum):
    ASC = "ASC"
    DESC = "DESC"


SENSITIVE_DETAIL_MARKERS = (
    "authorization",
    "cookie",
    "password",
    "private",
    "secret",
    "signature",
    "token",
)


class ReadinessProbe(Protocol):
    """Injected readiness probe used by live-only system routes."""

    def check(self) -> "ReadinessProbeResult":
        ...


@dataclass(frozen=True)
class ReadinessProbeResult:
    """JSON-safe readiness result for one live dependency component."""

    component: str
    state: HealthState
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: Mapping[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "component", _require_text(self.component, "ReadinessProbeResult.component"))
        if not isinstance(self.state, HealthState):
            object.__setattr__(self, "state", HealthState(str(self.state)))
        object.__setattr__(self, "checked_at", _require_aware_datetime(self.checked_at, "checked_at"))
        if not isinstance(self.details, Mapping):
            raise ValueError("ReadinessProbeResult.details must be a mapping")
        object.__setattr__(self, "details", MappingProxyType(_redacted_json_mapping(self.details)))
        if self.error_code is not None:
            object.__setattr__(self, "error_code", _require_text(self.error_code, "ReadinessProbeResult.error_code"))
        if self.message is not None:
            object.__setattr__(self, "message", _require_text(self.message, "ReadinessProbeResult.message"))

    def to_dict(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "component": self.component,
            "state": self.state.value,
            "checkedAt": self.checked_at.isoformat(),
            "details": dict(self.details),
        }
        if self.error_code is not None:
            payload["error"] = {
                "code": self.error_code,
                "message": self.message or self.error_code,
            }
        return payload


@dataclass(frozen=True)
class RuntimeReadinessStatus:
    """Aggregate readiness payload returned by the live-only /readyz route."""

    components: tuple[ReadinessProbeResult, ...]
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.components, tuple):
            raise ValueError("RuntimeReadinessStatus.components must be a tuple")
        if any(not isinstance(component, ReadinessProbeResult) for component in self.components):
            raise ValueError("RuntimeReadinessStatus.components must contain ReadinessProbeResult values")
        object.__setattr__(self, "checked_at", _require_aware_datetime(self.checked_at, "checked_at"))

    @property
    def state(self) -> HealthState:
        if all(component.state is HealthState.OK for component in self.components):
            return HealthState.OK
        return HealthState.UNAVAILABLE

    @property
    def ready(self) -> bool:
        return self.state is HealthState.OK

    @property
    def status_code(self) -> int:
        return 200 if self.ready else 503

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "component": "runtime-readiness",
            "state": self.state.value,
            "checkedAt": self.checked_at.isoformat(),
            "components": [component.to_dict() for component in self.components],
        }


@dataclass(frozen=True)
class AccessLogEvent:
    """Structured, redacted access log event contract for live HTTP requests."""

    method: str
    path_template: str
    route_id: str
    status: int
    request_id: str
    duration_ms: float
    actor: Mapping[str, Any] = field(default_factory=dict)
    error_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", _require_text(self.method, "AccessLogEvent.method").upper())
        object.__setattr__(self, "path_template", _require_text(self.path_template, "AccessLogEvent.path_template"))
        object.__setattr__(self, "route_id", _require_text(self.route_id, "AccessLogEvent.route_id"))
        if isinstance(self.status, bool) or not isinstance(self.status, int):
            raise ValueError("AccessLogEvent.status must be an integer")
        object.__setattr__(self, "request_id", _require_text(self.request_id, "AccessLogEvent.request_id"))
        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, (int, float)) or self.duration_ms < 0:
            raise ValueError("AccessLogEvent.duration_ms must be a non-negative number")
        if not isinstance(self.actor, Mapping):
            raise ValueError("AccessLogEvent.actor must be a mapping")
        object.__setattr__(self, "actor", MappingProxyType(_redacted_json_mapping(self.actor)))
        if self.error_code is not None:
            object.__setattr__(self, "error_code", _require_text(self.error_code, "AccessLogEvent.error_code"))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "method": self.method,
            "pathTemplate": self.path_template,
            "routeId": self.route_id,
            "status": self.status,
            "requestId": self.request_id,
            "durationMs": self.duration_ms,
            "actor": dict(self.actor),
            "errorCode": self.error_code,
        }


def evaluate_readiness(
    probes: Sequence[ReadinessProbe],
    *,
    checked_at: datetime | None = None,
) -> RuntimeReadinessStatus:
    """Evaluate injected readiness probes and convert failures to bounded JSON."""

    results: list[ReadinessProbeResult] = []
    for probe in probes:
        try:
            result = probe.check()
        except Exception as exc:
            result = ReadinessProbeResult(
                component=_probe_component(probe),
                state=HealthState.UNAVAILABLE,
                checked_at=checked_at or datetime.now(UTC),
                error_code="READINESS_PROBE_FAILED",
                message=f"{type(exc).__name__}: {exc}",
            )
        if not isinstance(result, ReadinessProbeResult):
            raise ValueError("readiness probes must return ReadinessProbeResult")
        results.append(result)
    return RuntimeReadinessStatus(components=tuple(results), checked_at=checked_at or datetime.now(UTC))


def actor_summary(auth_context: Any | None) -> dict[str, JsonValue]:
    if auth_context is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "userId": getattr(auth_context, "user_id", None),
        "role": getattr(auth_context, "role", None),
        "scopes": list(getattr(auth_context, "scopes", ()) or ()),
    }


@dataclass(frozen=True)
class OperatorPage:
    limit: int
    next_page_token: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "limit", _require_positive_int(self.limit, "OperatorPage.limit"))
        if self.next_page_token is not None:
            object.__setattr__(
                self,
                "next_page_token",
                _require_text(self.next_page_token, "OperatorPage.next_page_token"),
            )


@dataclass(frozen=True)
class OperatorDashboardQuery:
    contexts: tuple[str, ...] = ("orders", "payments", "outbox")
    statuses: tuple[str, ...] = ()
    chain_id: int | None = None
    store_id: str | None = None
    failed_only: bool = False
    retry_candidates_only: bool = False
    sort_by: str = "updatedAt"
    sort_direction: OperatorSortDirection = OperatorSortDirection.DESC
    limit: int = 50
    page_token: str | None = None

    def __post_init__(self) -> None:
        contexts = tuple(_require_text(context, "OperatorDashboardQuery.contexts").lower() for context in self.contexts)
        if not contexts:
            contexts = ("orders", "payments", "outbox")
        invalid_contexts = set(contexts) - {"checkout", "orders", "payments", "outbox", "workers", "errors"}
        if invalid_contexts:
            raise ValueError(f"unsupported operator context: {sorted(invalid_contexts)[0]}")
        object.__setattr__(self, "contexts", contexts)
        object.__setattr__(
            self,
            "statuses",
            tuple(_require_text(status, "OperatorDashboardQuery.statuses").upper() for status in self.statuses),
        )
        if self.chain_id is not None:
            object.__setattr__(self, "chain_id", _require_positive_int(self.chain_id, "OperatorDashboardQuery.chain_id"))
        if self.store_id is not None:
            object.__setattr__(self, "store_id", _require_text(self.store_id, "OperatorDashboardQuery.store_id"))
        if not isinstance(self.failed_only, bool):
            raise ValueError("OperatorDashboardQuery.failed_only must be a bool")
        if not isinstance(self.retry_candidates_only, bool):
            raise ValueError("OperatorDashboardQuery.retry_candidates_only must be a bool")
        if self.sort_by not in {"createdAt", "updatedAt", "status"}:
            raise ValueError("OperatorDashboardQuery.sort_by must be createdAt, updatedAt, or status")
        if not isinstance(self.sort_direction, OperatorSortDirection):
            object.__setattr__(self, "sort_direction", OperatorSortDirection(str(self.sort_direction).upper()))
        object.__setattr__(self, "limit", _require_positive_int(self.limit, "OperatorDashboardQuery.limit"))
        if self.limit > 100:
            raise ValueError("OperatorDashboardQuery.limit must be at most 100")
        if self.page_token is not None:
            object.__setattr__(self, "page_token", _require_text(self.page_token, "OperatorDashboardQuery.page_token"))


@dataclass(frozen=True)
class OperatorOrderSnapshot:
    order_id: OrderId
    tracking_id: str
    customer_id: CustomerId
    store_id: StoreId
    status: OrderStatus
    payment_id: PaymentId | None
    payment_status: PaymentStatus | str | None
    total_amount: Crypto
    failure_reason: str | None
    latest_event: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, OrderId):
            object.__setattr__(self, "order_id", OrderId(self.order_id))
        object.__setattr__(self, "tracking_id", _require_text(self.tracking_id, "OperatorOrderSnapshot.tracking_id"))
        if not isinstance(self.customer_id, CustomerId):
            object.__setattr__(self, "customer_id", CustomerId(self.customer_id))
        if not isinstance(self.store_id, StoreId):
            object.__setattr__(self, "store_id", StoreId(self.store_id))
        if not isinstance(self.status, OrderStatus):
            object.__setattr__(self, "status", OrderStatus(str(self.status)))
        if self.payment_id is not None and not isinstance(self.payment_id, PaymentId):
            object.__setattr__(self, "payment_id", PaymentId(self.payment_id))
        if self.payment_status is not None and not isinstance(self.payment_status, PaymentStatus):
            object.__setattr__(self, "payment_status", PaymentStatus(str(self.payment_status)))
        if not isinstance(self.total_amount, Crypto):
            raise ValueError("OperatorOrderSnapshot.total_amount must be a Crypto value")
        if self.failure_reason is not None:
            object.__setattr__(
                self,
                "failure_reason",
                _require_text(self.failure_reason, "OperatorOrderSnapshot.failure_reason"),
            )
        if self.latest_event is not None:
            object.__setattr__(self, "latest_event", _require_text(self.latest_event, "OperatorOrderSnapshot.latest_event"))
        object.__setattr__(self, "created_at", _require_aware_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _require_aware_datetime(self.updated_at, "updated_at"))


@dataclass(frozen=True)
class OperatorPaymentSnapshot:
    payment_id: PaymentId
    order_id: OrderId
    customer_id: CustomerId
    status: PaymentStatus
    amount: Crypto
    chain: ChainNetwork
    wallet_from: WalletAddress
    wallet_to: WalletAddress
    tx_hash: TransactionHash | None
    failure_reason: str | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.payment_id, PaymentId):
            object.__setattr__(self, "payment_id", PaymentId(self.payment_id))
        if not isinstance(self.order_id, OrderId):
            object.__setattr__(self, "order_id", OrderId(self.order_id))
        if not isinstance(self.customer_id, CustomerId):
            object.__setattr__(self, "customer_id", CustomerId(self.customer_id))
        if not isinstance(self.status, PaymentStatus):
            object.__setattr__(self, "status", PaymentStatus(str(self.status)))
        if not isinstance(self.amount, Crypto):
            raise ValueError("OperatorPaymentSnapshot.amount must be a Crypto value")
        if not isinstance(self.chain, ChainNetwork):
            raise ValueError("OperatorPaymentSnapshot.chain must be a ChainNetwork")
        if not isinstance(self.wallet_from, WalletAddress):
            object.__setattr__(self, "wallet_from", WalletAddress(self.wallet_from))
        if not isinstance(self.wallet_to, WalletAddress):
            object.__setattr__(self, "wallet_to", WalletAddress(self.wallet_to))
        if self.tx_hash is not None and not isinstance(self.tx_hash, TransactionHash):
            object.__setattr__(self, "tx_hash", TransactionHash(self.tx_hash))
        if self.failure_reason is not None:
            object.__setattr__(
                self,
                "failure_reason",
                _require_text(self.failure_reason, "OperatorPaymentSnapshot.failure_reason"),
            )
        object.__setattr__(self, "expires_at", _require_aware_datetime(self.expires_at, "expires_at"))
        object.__setattr__(self, "created_at", _require_aware_datetime(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _require_aware_datetime(self.updated_at, "updated_at"))


@dataclass(frozen=True)
class OperatorOutboxSnapshot:
    identity: str
    kind: OutboxMessageKind
    name: str
    topic: str
    key: str
    status: OutboxPublishStatus
    failure_count: int
    last_error: str | None
    created_at: datetime
    published_at: datetime | None
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity", _require_text(self.identity, "OperatorOutboxSnapshot.identity"))
        if not isinstance(self.kind, OutboxMessageKind):
            object.__setattr__(self, "kind", OutboxMessageKind(str(self.kind)))
        object.__setattr__(self, "name", _require_text(self.name, "OperatorOutboxSnapshot.name"))
        object.__setattr__(self, "topic", _require_text(self.topic, "OperatorOutboxSnapshot.topic"))
        object.__setattr__(self, "key", _require_text(self.key, "OperatorOutboxSnapshot.key"))
        if not isinstance(self.status, OutboxPublishStatus):
            object.__setattr__(self, "status", OutboxPublishStatus(str(self.status)))
        object.__setattr__(
            self,
            "failure_count",
            _require_non_negative_int(self.failure_count, "OperatorOutboxSnapshot.failure_count"),
        )
        if self.last_error is not None:
            object.__setattr__(self, "last_error", _require_text(self.last_error, "OperatorOutboxSnapshot.last_error"))
        object.__setattr__(self, "created_at", _require_aware_datetime(self.created_at, "created_at"))
        if self.published_at is not None:
            object.__setattr__(self, "published_at", _require_aware_datetime(self.published_at, "published_at"))
        object.__setattr__(self, "updated_at", _require_aware_datetime(self.updated_at, "updated_at"))

    @property
    def retry_candidate(self) -> bool:
        return self.status is OutboxPublishStatus.FAILED

    @property
    def retry_reason(self) -> str | None:
        if not self.retry_candidate:
            return None
        return "FAILED rows are reclaimed by the outbox relay retry policy"


@dataclass(frozen=True)
class OperatorWorkerSnapshot:
    component: str
    state: HealthState
    checked_at: datetime
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "component", _require_text(self.component, "OperatorWorkerSnapshot.component"))
        if not isinstance(self.state, HealthState):
            object.__setattr__(self, "state", HealthState(str(self.state)))
        object.__setattr__(self, "checked_at", _require_aware_datetime(self.checked_at, "checked_at"))
        if not isinstance(self.details, Mapping):
            raise ValueError("OperatorWorkerSnapshot.details must be a mapping")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True)
class OperatorErrorSnapshot:
    context: str
    aggregate_id: str
    code: str
    message: str
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", _require_text(self.context, "OperatorErrorSnapshot.context"))
        object.__setattr__(self, "aggregate_id", _require_text(self.aggregate_id, "OperatorErrorSnapshot.aggregate_id"))
        object.__setattr__(self, "code", _require_text(self.code, "OperatorErrorSnapshot.code"))
        object.__setattr__(self, "message", _require_text(self.message, "OperatorErrorSnapshot.message"))
        object.__setattr__(self, "created_at", _require_aware_datetime(self.created_at, "created_at"))


@dataclass(frozen=True)
class OperatorObservabilitySnapshot:
    orders: tuple[OperatorOrderSnapshot, ...] = ()
    payments: tuple[OperatorPaymentSnapshot, ...] = ()
    outbox: tuple[OperatorOutboxSnapshot, ...] = ()
    workers: tuple[OperatorWorkerSnapshot, ...] = ()
    errors: tuple[OperatorErrorSnapshot, ...] = ()
    pagination: Mapping[str, OperatorPage] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "orders", _coerce_tuple(self.orders, OperatorOrderSnapshot, "orders"))
        object.__setattr__(self, "payments", _coerce_tuple(self.payments, OperatorPaymentSnapshot, "payments"))
        object.__setattr__(self, "outbox", _coerce_tuple(self.outbox, OperatorOutboxSnapshot, "outbox"))
        object.__setattr__(self, "workers", _coerce_tuple(self.workers, OperatorWorkerSnapshot, "workers"))
        object.__setattr__(self, "errors", _coerce_tuple(self.errors, OperatorErrorSnapshot, "errors"))
        if not isinstance(self.pagination, Mapping):
            raise ValueError("OperatorObservabilitySnapshot.pagination must be a mapping")
        pages: dict[str, OperatorPage] = {}
        for key, value in self.pagination.items():
            page_key = _require_text(str(key), "OperatorObservabilitySnapshot.pagination key")
            if not isinstance(value, OperatorPage):
                raise ValueError("OperatorObservabilitySnapshot.pagination values must be OperatorPage")
            pages[page_key] = value
        object.__setattr__(self, "pagination", pages)


class OperatorObservabilityQueryPort(Protocol):
    def list_dashboard(self, query: OperatorDashboardQuery) -> OperatorObservabilitySnapshot:
        ...

    def get_order_detail(self, order_id: OrderId) -> OperatorObservabilitySnapshot | None:
        ...

    def get_payment_detail(self, payment_id: PaymentId) -> OperatorObservabilitySnapshot | None:
        ...

    def get_outbox_detail(
        self,
        kind: OutboxMessageKind,
        identity: str,
    ) -> OperatorObservabilitySnapshot | None:
        ...


SELECT_OPERATOR_ORDERS_SQL = """
SELECT
    orders.order_id,
    orders.tracking_id,
    orders.customer_id,
    orders.store_id,
    orders.status,
    orders.payment_id,
    payments.status AS payment_status,
    orders.total_amount_numeric,
    orders.total_amount_symbol,
    orders.total_amount_chain_id,
    orders.total_amount_token_address,
    orders.total_amount_decimals,
    orders.failure_messages,
    payments.failure_reason AS payment_failure_reason,
    latest_outbox.name AS latest_event,
    orders.created_at,
    orders.updated_at
FROM orders
LEFT JOIN payments ON payments.order_id = orders.order_id
LEFT JOIN LATERAL (
    SELECT outbox_messages.name
    FROM outbox_messages
    WHERE outbox_messages.message_key = orders.order_id::text
    ORDER BY outbox_messages.created_at DESC
    LIMIT 1
) AS latest_outbox ON true
WHERE (%(statuses)s IS NULL OR orders.status = ANY(%(statuses)s) OR payments.status = ANY(%(statuses)s))
  AND (%(store_id)s IS NULL OR orders.store_id = %(store_id)s)
  AND (%(chain_id)s IS NULL OR orders.total_amount_chain_id = %(chain_id)s OR payments.chain_id = %(chain_id)s)
  AND (%(failed_only)s IS FALSE OR jsonb_array_length(orders.failure_messages) > 0 OR payments.failure_reason IS NOT NULL)
  AND (%(page_token)s IS NULL OR %(page_token)s IS NOT NULL)
ORDER BY {sort_column} {sort_direction}, orders.order_id {sort_direction}
LIMIT %(limit)s
"""

SELECT_OPERATOR_PAYMENTS_SQL = """
SELECT
    payments.payment_id,
    payments.order_id,
    payments.customer_id,
    payments.status,
    payments.amount_numeric,
    payments.amount_symbol,
    payments.amount_chain_id,
    payments.amount_token_address,
    payments.amount_decimals,
    payments.chain_id,
    payments.chain_name,
    payments.wallet_from,
    payments.wallet_to,
    payments.tx_hash,
    payments.failure_reason,
    payments.expires_at,
    payments.created_at,
    payments.updated_at
FROM payments
LEFT JOIN orders ON orders.order_id = payments.order_id
WHERE (%(statuses)s IS NULL OR payments.status = ANY(%(statuses)s))
  AND (%(store_id)s IS NULL OR orders.store_id = %(store_id)s)
  AND (%(chain_id)s IS NULL OR payments.chain_id = %(chain_id)s)
  AND (%(failed_only)s IS FALSE OR payments.failure_reason IS NOT NULL OR payments.status IN ('FAILED', 'EXPIRED'))
  AND (%(page_token)s IS NULL OR %(page_token)s IS NOT NULL)
ORDER BY {sort_column} {sort_direction}, payments.payment_id {sort_direction}
LIMIT %(limit)s
"""

SELECT_OPERATOR_OUTBOX_SQL = """
SELECT
    outbox_messages.message_identity,
    outbox_messages.kind,
    outbox_messages.name,
    outbox_messages.topic,
    outbox_messages.message_key,
    outbox_messages.status,
    outbox_messages.failure_count,
    outbox_messages.last_error,
    outbox_messages.created_at,
    outbox_messages.published_at,
    COALESCE(outbox_messages.published_at, outbox_messages.created_at) AS updated_at
FROM outbox_messages
WHERE (%(statuses)s IS NULL OR outbox_messages.status = ANY(%(statuses)s))
  AND (%(failed_only)s IS FALSE OR outbox_messages.last_error IS NOT NULL OR outbox_messages.status = 'FAILED')
  AND (%(retry_candidates_only)s IS FALSE OR outbox_messages.status = 'FAILED')
  AND (%(page_token)s IS NULL OR %(page_token)s IS NOT NULL)
ORDER BY {sort_column} {sort_direction}, outbox_messages.message_identity {sort_direction}
LIMIT %(limit)s
"""

SELECT_OPERATOR_ORDER_DETAIL_SQL = SELECT_OPERATOR_ORDERS_SQL.replace(
    "WHERE (%(statuses)s IS NULL OR orders.status = ANY(%(statuses)s) OR payments.status = ANY(%(statuses)s))",
    "WHERE orders.order_id = %(order_id)s",
)

SELECT_OPERATOR_PAYMENT_DETAIL_SQL = SELECT_OPERATOR_PAYMENTS_SQL.replace(
    "WHERE (%(statuses)s IS NULL OR payments.status = ANY(%(statuses)s))",
    "WHERE payments.payment_id = %(payment_id)s",
)

SELECT_OPERATOR_PAYMENTS_BY_ORDER_SQL = SELECT_OPERATOR_PAYMENTS_SQL.replace(
    "WHERE (%(statuses)s IS NULL OR payments.status = ANY(%(statuses)s))",
    "WHERE payments.order_id = %(order_id)s",
)

SELECT_OPERATOR_OUTBOX_DETAIL_SQL = SELECT_OPERATOR_OUTBOX_SQL.replace(
    "WHERE (%(statuses)s IS NULL OR outbox_messages.status = ANY(%(statuses)s))",
    "WHERE outbox_messages.kind = %(kind)s AND outbox_messages.message_identity = %(message_identity)s",
)

SELECT_OPERATOR_OUTBOX_BY_KEY_SQL = SELECT_OPERATOR_OUTBOX_SQL.replace(
    "WHERE (%(statuses)s IS NULL OR outbox_messages.status = ANY(%(statuses)s))",
    "WHERE outbox_messages.message_key = %(message_key)s",
)


class PostgresOperatorObservabilityQuery:
    """Build read-only operator dashboard snapshots from PostgreSQL read models."""

    def __init__(
        self,
        connection: PostgresConnection,
        *,
        workers: Sequence[OperatorWorkerSnapshot] = (),
    ) -> None:
        self._connection = connection
        self._workers = tuple(workers)

    def list_dashboard(self, query: OperatorDashboardQuery) -> OperatorObservabilitySnapshot:
        if not isinstance(query, OperatorDashboardQuery):
            raise ValueError("PostgresOperatorObservabilityQuery.list_dashboard requires OperatorDashboardQuery")

        limit = query.limit + 1
        order_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_ORDERS_SQL, resource="orders", query=query),
            _params(query, limit=limit),
        ) if _context_enabled(query, "orders") else []
        payment_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_PAYMENTS_SQL, resource="payments", query=query),
            _params(query, limit=limit),
        ) if _context_enabled(query, "payments") else []
        outbox_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_OUTBOX_SQL, resource="outbox", query=query),
            _params(query, limit=limit),
        ) if _context_enabled(query, "outbox") else []

        visible_order_rows, order_page = _paginate("orders", order_rows, query.limit, "order_id")
        visible_payment_rows, payment_page = _paginate("payments", payment_rows, query.limit, "payment_id")
        visible_outbox_rows, outbox_page = _paginate("outbox", outbox_rows, query.limit, "message_identity")

        orders = tuple(_order_from_row(row) for row in visible_order_rows)
        payments = tuple(_payment_from_row(row) for row in visible_payment_rows)
        outbox = tuple(_outbox_from_row(row) for row in visible_outbox_rows)

        return OperatorObservabilitySnapshot(
            orders=orders,
            payments=payments,
            outbox=outbox,
            workers=self._workers if _context_enabled(query, "workers") or query.contexts == ("orders", "payments", "outbox") else (),
            errors=_errors_from(orders, payments, outbox),
            pagination={
                "orders": order_page,
                "payments": payment_page,
                "outbox": outbox_page,
            },
        )

    def get_order_detail(self, order_id: OrderId) -> OperatorObservabilitySnapshot | None:
        if not isinstance(order_id, OrderId):
            raise ValueError("PostgresOperatorObservabilityQuery.get_order_detail requires an OrderId")
        query = OperatorDashboardQuery(limit=100)
        order_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_ORDER_DETAIL_SQL, resource="orders", query=query),
            _params(query, limit=100, order_id=str(order_id)),
        )
        if not order_rows:
            return None
        payment_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_PAYMENTS_BY_ORDER_SQL, resource="payments", query=query),
            _params(query, limit=100, order_id=str(order_id)),
        )
        outbox_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_OUTBOX_BY_KEY_SQL, resource="outbox", query=query),
            _params(query, limit=100, message_key=str(order_id)),
        )
        return _detail_snapshot(order_rows, payment_rows, outbox_rows)

    def get_payment_detail(self, payment_id: PaymentId) -> OperatorObservabilitySnapshot | None:
        if not isinstance(payment_id, PaymentId):
            raise ValueError("PostgresOperatorObservabilityQuery.get_payment_detail requires a PaymentId")
        query = OperatorDashboardQuery(limit=100)
        payment_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_PAYMENT_DETAIL_SQL, resource="payments", query=query),
            _params(query, limit=100, payment_id=str(payment_id)),
        )
        if not payment_rows:
            return None
        order_id = str(_row_value(payment_rows[0], "order_id"))
        order_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_ORDER_DETAIL_SQL, resource="orders", query=query),
            _params(query, limit=100, order_id=order_id),
        )
        outbox_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_OUTBOX_BY_KEY_SQL, resource="outbox", query=query),
            _params(query, limit=100, message_key=order_id),
        )
        return _detail_snapshot(order_rows, payment_rows, outbox_rows)

    def get_outbox_detail(
        self,
        kind: OutboxMessageKind,
        identity: str,
    ) -> OperatorObservabilitySnapshot | None:
        if not isinstance(kind, OutboxMessageKind):
            kind = OutboxMessageKind(str(kind))
        identity = _require_text(identity, "identity")
        query = OperatorDashboardQuery(limit=100)
        outbox_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_OUTBOX_DETAIL_SQL, resource="outbox", query=query),
            _params(query, limit=100, kind=kind.value, message_identity=identity),
        )
        if not outbox_rows:
            return None
        order_id = str(_row_value(outbox_rows[0], "message_key"))
        order_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_ORDER_DETAIL_SQL, resource="orders", query=query),
            _params(query, limit=100, order_id=order_id),
        )
        payment_rows = self._fetch_rows(
            _sql(SELECT_OPERATOR_PAYMENTS_BY_ORDER_SQL, resource="payments", query=query),
            _params(query, limit=100, order_id=order_id),
        )
        return _detail_snapshot(order_rows, payment_rows, outbox_rows)

    def _fetch_rows(self, sql: str, params: Mapping[str, Any]) -> list[Any]:
        return _fetch_all(self._connection.execute(sql, params))


def _detail_snapshot(
    order_rows: Sequence[Mapping[str, Any] | object],
    payment_rows: Sequence[Mapping[str, Any] | object],
    outbox_rows: Sequence[Mapping[str, Any] | object],
) -> OperatorObservabilitySnapshot:
    orders = tuple(_order_from_row(row) for row in order_rows)
    payments = tuple(_payment_from_row(row) for row in payment_rows)
    outbox = tuple(_outbox_from_row(row) for row in outbox_rows)
    return OperatorObservabilitySnapshot(
        orders=orders,
        payments=payments,
        outbox=outbox,
        errors=_errors_from(orders, payments, outbox),
        pagination={
            "orders": OperatorPage(limit=max(len(orders), 1)),
            "payments": OperatorPage(limit=max(len(payments), 1)),
            "outbox": OperatorPage(limit=max(len(outbox), 1)),
        },
    )


def _sql(template: str, *, resource: str, query: OperatorDashboardQuery) -> str:
    sort_column = _sort_column(resource, query.sort_by)
    return template.format(
        sort_column=sort_column,
        sort_direction=query.sort_direction.value,
    )


def _sort_column(resource: str, sort_by: str) -> str:
    if sort_by == "createdAt":
        return {
            "orders": "orders.created_at",
            "payments": "payments.created_at",
            "outbox": "outbox_messages.created_at",
        }[resource]
    if sort_by == "status":
        return {
            "orders": "orders.status",
            "payments": "payments.status",
            "outbox": "outbox_messages.status",
        }[resource]
    return {
        "orders": "orders.updated_at",
        "payments": "payments.updated_at",
        "outbox": "COALESCE(outbox_messages.published_at, outbox_messages.created_at)",
    }[resource]


def _params(query: OperatorDashboardQuery, *, limit: int, **extra: Any) -> dict[str, Any]:
    params = {
        "statuses": list(query.statuses) if query.statuses else None,
        "chain_id": query.chain_id,
        "store_id": query.store_id,
        "failed_only": query.failed_only,
        "retry_candidates_only": query.retry_candidates_only,
        "page_token": query.page_token,
        "limit": limit,
    }
    params.update(extra)
    return params


def _context_enabled(query: OperatorDashboardQuery, context: str) -> bool:
    if context == "orders" and "checkout" in query.contexts:
        return True
    return context in query.contexts


def _paginate(
    resource: str,
    rows: Sequence[Mapping[str, Any] | object],
    limit: int,
    identity_key: str,
) -> tuple[list[Mapping[str, Any] | object], OperatorPage]:
    visible = list(rows[:limit])
    next_page_token = None
    if len(rows) > limit:
        cursor = rows[limit]
        next_page_token = f"{resource}:{_row_value(cursor, 'updated_at').isoformat()}:{_row_value(cursor, identity_key)}"
    return visible, OperatorPage(limit=limit, next_page_token=next_page_token)


def _order_from_row(row: Mapping[str, Any] | object) -> OperatorOrderSnapshot:
    return OperatorOrderSnapshot(
        order_id=OrderId(_row_value(row, "order_id")),
        tracking_id=str(_row_value(row, "tracking_id")),
        customer_id=CustomerId(_row_value(row, "customer_id")),
        store_id=StoreId(_row_value(row, "store_id")),
        status=OrderStatus(_row_value(row, "status")),
        payment_id=_optional_payment_id(_row_value(row, "payment_id")),
        payment_status=_optional_payment_status(_row_value(row, "payment_status")),
        total_amount=_crypto_from_row(row, "total_amount"),
        failure_reason=_failure_reason_from_order_row(row),
        latest_event=_row_value(row, "latest_event"),
        created_at=_row_value(row, "created_at"),
        updated_at=_row_value(row, "updated_at"),
    )


def _payment_from_row(row: Mapping[str, Any] | object) -> OperatorPaymentSnapshot:
    return OperatorPaymentSnapshot(
        payment_id=PaymentId(_row_value(row, "payment_id")),
        order_id=OrderId(_row_value(row, "order_id")),
        customer_id=CustomerId(_row_value(row, "customer_id")),
        status=PaymentStatus(_row_value(row, "status")),
        amount=_crypto_from_row(row, "amount"),
        chain=ChainNetwork(chain_id=int(_row_value(row, "chain_id")), name=str(_row_value(row, "chain_name"))),
        wallet_from=WalletAddress(_row_value(row, "wallet_from")),
        wallet_to=WalletAddress(_row_value(row, "wallet_to")),
        tx_hash=_optional_tx_hash(_row_value(row, "tx_hash")),
        failure_reason=_row_value(row, "failure_reason"),
        expires_at=_row_value(row, "expires_at"),
        created_at=_row_value(row, "created_at"),
        updated_at=_row_value(row, "updated_at"),
    )


def _outbox_from_row(row: Mapping[str, Any] | object) -> OperatorOutboxSnapshot:
    return OperatorOutboxSnapshot(
        identity=str(_row_value(row, "message_identity")),
        kind=OutboxMessageKind(_row_value(row, "kind")),
        name=str(_row_value(row, "name")),
        topic=str(_row_value(row, "topic")),
        key=str(_row_value(row, "message_key")),
        status=OutboxPublishStatus(_row_value(row, "status")),
        failure_count=int(_row_value(row, "failure_count")),
        last_error=_row_value(row, "last_error"),
        created_at=_row_value(row, "created_at"),
        published_at=_row_value(row, "published_at"),
        updated_at=_row_value(row, "updated_at"),
    )


def _errors_from(
    orders: Sequence[OperatorOrderSnapshot],
    payments: Sequence[OperatorPaymentSnapshot],
    outbox: Sequence[OperatorOutboxSnapshot],
) -> tuple[OperatorErrorSnapshot, ...]:
    errors: list[OperatorErrorSnapshot] = []
    for order in orders:
        if order.failure_reason is not None:
            errors.append(
                OperatorErrorSnapshot(
                    context="order",
                    aggregate_id=str(order.order_id),
                    code=order.status.value,
                    message=order.failure_reason,
                    created_at=order.updated_at,
                )
            )
    for payment in payments:
        if payment.failure_reason is not None:
            errors.append(
                OperatorErrorSnapshot(
                    context="payment",
                    aggregate_id=str(payment.payment_id),
                    code=payment.status.value,
                    message=payment.failure_reason,
                    created_at=payment.updated_at,
                )
            )
    for message in outbox:
        if message.last_error is not None:
            errors.append(
                OperatorErrorSnapshot(
                    context="outbox",
                    aggregate_id=message.identity,
                    code=message.status.value,
                    message=message.last_error,
                    created_at=message.updated_at,
                )
            )
    return tuple(errors)


def _crypto_from_row(row: Mapping[str, Any] | object, prefix: str) -> Crypto:
    return Crypto(
        amount=_row_value(row, f"{prefix}_numeric"),
        symbol=str(_row_value(row, f"{prefix}_symbol")),
        chain_id=int(_row_value(row, f"{prefix}_chain_id")),
        token_address=_row_value(row, f"{prefix}_token_address"),
        decimals=int(_row_value(row, f"{prefix}_decimals")),
    )


def _failure_reason_from_order_row(row: Mapping[str, Any] | object) -> str | None:
    payment_failure = _row_value(row, "payment_failure_reason")
    if payment_failure is not None:
        return str(payment_failure)
    messages = _row_value(row, "failure_messages")
    if isinstance(messages, list | tuple) and messages:
        return str(messages[-1])
    return None


def _optional_payment_id(value: Any) -> PaymentId | None:
    if value is None:
        return None
    return PaymentId(value)


def _optional_payment_status(value: Any) -> PaymentStatus | None:
    if value is None:
        return None
    return PaymentStatus(value)


def _optional_tx_hash(value: Any) -> TransactionHash | None:
    if value is None:
        return None
    return TransactionHash(value)


def _fetch_all(result: Any) -> list[Any]:
    if result is None:
        return []
    fetchall = getattr(result, "fetchall", None)
    if callable(fetchall):
        return list(fetchall())
    return list(result)


def _row_value(row: Mapping[str, Any] | object, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return getattr(row, key)


def _probe_component(probe: object) -> str:
    component = getattr(probe, "component", None)
    if isinstance(component, str) and component.strip():
        return component.strip()
    return type(probe).__name__


def _redacted_json_mapping(value: Mapping[str, Any]) -> dict[str, JsonValue]:
    return {str(key): _redacted_json_value(str(key), item) for key, item in value.items()}


def _redacted_json_value(key: str, value: Any) -> JsonValue:
    if _is_sensitive_key(key):
        return "<redacted>"
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime):
        return _require_aware_datetime(value, key).isoformat()
    if isinstance(value, Mapping):
        return _redacted_json_mapping(value)
    if isinstance(value, tuple | list):
        return [_redacted_json_value(key, item) for item in value]
    return str(value)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return any(marker in normalized for marker in SENSITIVE_DETAIL_MARKERS)


def _coerce_tuple(values: tuple[object, ...], item_type: type, field_name: str):
    if not isinstance(values, tuple):
        raise ValueError(f"OperatorObservabilitySnapshot.{field_name} must be a tuple")
    if any(not isinstance(value, item_type) for value in values):
        raise ValueError(f"OperatorObservabilitySnapshot.{field_name} must contain {item_type.__name__} values")
    return values


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


__all__ = [
    "AccessLogEvent",
    "OperatorDashboardQuery",
    "OperatorErrorSnapshot",
    "OperatorObservabilityQueryPort",
    "OperatorObservabilitySnapshot",
    "OperatorOrderSnapshot",
    "OperatorOutboxSnapshot",
    "OperatorPage",
    "OperatorPaymentSnapshot",
    "OperatorSortDirection",
    "OperatorWorkerSnapshot",
    "PostgresOperatorObservabilityQuery",
    "ReadinessProbe",
    "ReadinessProbeResult",
    "RuntimeReadinessStatus",
    "actor_summary",
    "evaluate_readiness",
]

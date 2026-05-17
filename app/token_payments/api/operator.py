"""Framework-neutral read-only operator observability API handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from token_payments.contexts.auth.domain import UserRole
from token_payments.runtime.observability import (
    OperatorDashboardQuery,
    OperatorObservabilityQueryPort,
    OperatorObservabilitySnapshot,
    OperatorOrderSnapshot,
    OperatorOutboxSnapshot,
    OperatorPage,
    OperatorPaymentSnapshot,
    OperatorSortDirection,
    OperatorWorkerSnapshot,
)
from token_payments.shared.domain import Crypto, OrderId, OutboxMessageKind, PaymentId

from .contracts import ApiRequest, ApiResponse, json_response


@dataclass(frozen=True)
class OperatorClaims:
    user_id: str | None = None
    role: UserRole | str | None = None
    scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.user_id is not None:
            object.__setattr__(self, "user_id", _require_text(self.user_id, "OperatorClaims.user_id"))
        if self.role is not None and not isinstance(self.role, UserRole):
            object.__setattr__(self, "role", UserRole(_require_text(str(self.role), "OperatorClaims.role")))
        if not isinstance(self.scopes, tuple):
            raise ValueError("OperatorClaims.scopes must be a tuple")
        object.__setattr__(self, "scopes", tuple(_require_text(scope, "OperatorClaims.scopes") for scope in self.scopes))


class OperatorAccessPolicy(Protocol):
    def can_read_observability(self, claims: OperatorClaims) -> bool:
        ...


class AdminRoleOperatorPolicy:
    """Minimal policy that accepts an ADMIN role claim supplied by the auth layer."""

    def can_read_observability(self, claims: OperatorClaims) -> bool:
        return claims.role is UserRole.ADMIN


class OperatorApi:
    """Operator dashboard API facade backed only by read model query ports."""

    def __init__(
        self,
        query: OperatorObservabilityQueryPort,
        *,
        policy: OperatorAccessPolicy | None = None,
    ) -> None:
        self._query = query
        self._policy = policy or AdminRoleOperatorPolicy()

    def get_dashboard(self, request: ApiRequest) -> ApiResponse:
        try:
            if not self._can_read(request):
                return _error_response("OPERATOR_FORBIDDEN", "operator access is required", 403, request.request_id)
            snapshot = self._query.list_dashboard(_dashboard_query_from_request(request))
            return json_response(_snapshot_payload(snapshot), request_id=request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def get_order(self, request: ApiRequest) -> ApiResponse:
        try:
            if not self._can_read(request):
                return _error_response("OPERATOR_FORBIDDEN", "operator access is required", 403, request.request_id)
            snapshot = self._query.get_order_detail(OrderId(_lookup_value(request, "orderId")))
            if snapshot is None:
                return _not_found_response(request.request_id)
            return json_response(_snapshot_payload(snapshot), request_id=request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def get_payment(self, request: ApiRequest) -> ApiResponse:
        try:
            if not self._can_read(request):
                return _error_response("OPERATOR_FORBIDDEN", "operator access is required", 403, request.request_id)
            snapshot = self._query.get_payment_detail(PaymentId(_lookup_value(request, "paymentId")))
            if snapshot is None:
                return _not_found_response(request.request_id)
            return json_response(_snapshot_payload(snapshot), request_id=request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def get_outbox_message(self, request: ApiRequest) -> ApiResponse:
        try:
            if not self._can_read(request):
                return _error_response("OPERATOR_FORBIDDEN", "operator access is required", 403, request.request_id)
            kind_value = _optional_text(request.query.get("kind")) or OutboxMessageKind.EVENT.value
            identity = _lookup_value(request, "messageId")
            snapshot = self._query.get_outbox_detail(OutboxMessageKind(kind_value), identity)
            if snapshot is None:
                return _not_found_response(request.request_id)
            return json_response(_snapshot_payload(snapshot), request_id=request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def _can_read(self, request: ApiRequest) -> bool:
        return self._policy.can_read_observability(_claims_from_request(request))


def _dashboard_query_from_request(request: ApiRequest) -> OperatorDashboardQuery:
    sort_by, sort_direction = _sort_from_request(request)
    return OperatorDashboardQuery(
        contexts=_csv_values(request.query.get("context", request.query.get("contexts"))) or ("orders", "payments", "outbox"),
        statuses=tuple(status.upper() for status in _csv_values(request.query.get("status"))),
        chain_id=_optional_int(request.query.get("chainId")),
        store_id=_optional_text(request.query.get("storeId")),
        failed_only=_bool_value(request.query.get("failedOnly"), default=False),
        retry_candidates_only=_bool_value(request.query.get("retryCandidatesOnly"), default=False),
        sort_by=sort_by,
        sort_direction=sort_direction,
        limit=_int_value(request.query.get("limit"), default=50),
        page_token=_optional_text(request.query.get("pageToken")),
    )


def _sort_from_request(request: ApiRequest) -> tuple[str, OperatorSortDirection]:
    raw_sort = _optional_text(request.query.get("sort")) or "-updatedAt"
    if raw_sort.startswith("-"):
        return raw_sort[1:], OperatorSortDirection.DESC
    return raw_sort, OperatorSortDirection.ASC


def _claims_from_request(request: ApiRequest) -> OperatorClaims:
    if request.auth_context is not None:
        return OperatorClaims(
            user_id=request.auth_context.user_id,
            role=_optional_role(request.auth_context.role),
            scopes=request.auth_context.scopes,
        )
    if not request.local_auth_fallback_enabled:
        return OperatorClaims()
    headers = _lower_headers(request.headers)
    return OperatorClaims(
        user_id=_optional_text(headers.get("x-user-id")),
        role=_optional_role(headers.get("x-user-role")),
        scopes=tuple(_csv_values(headers.get("x-user-scopes"))),
    )


def _snapshot_payload(snapshot: OperatorObservabilitySnapshot) -> dict[str, Any]:
    return {
        "orders": [_order_payload(order) for order in snapshot.orders],
        "payments": [_payment_payload(payment) for payment in snapshot.payments],
        "outbox": [_outbox_payload(message) for message in snapshot.outbox],
        "workers": [_worker_payload(worker) for worker in snapshot.workers],
        "errors": [
            {
                "context": error.context,
                "aggregateId": error.aggregate_id,
                "code": error.code,
                "message": error.message,
                "createdAt": error.created_at.isoformat(),
            }
            for error in snapshot.errors
        ],
        "pagination": {key: _page_payload(page) for key, page in snapshot.pagination.items()},
    }


def _order_payload(order: OperatorOrderSnapshot) -> dict[str, Any]:
    return {
        "orderId": str(order.order_id),
        "trackingId": order.tracking_id,
        "customerId": str(order.customer_id),
        "storeId": str(order.store_id),
        "status": order.status.value,
        "paymentId": str(order.payment_id) if order.payment_id is not None else None,
        "paymentStatus": order.payment_status.value if hasattr(order.payment_status, "value") else order.payment_status,
        "totalAmount": _crypto_payload(order.total_amount),
        "failureReason": order.failure_reason,
        "latestEvent": order.latest_event,
        "createdAt": order.created_at.isoformat(),
        "updatedAt": order.updated_at.isoformat(),
    }


def _payment_payload(payment: OperatorPaymentSnapshot) -> dict[str, Any]:
    return {
        "paymentId": str(payment.payment_id),
        "orderId": str(payment.order_id),
        "customerId": str(payment.customer_id),
        "status": payment.status.value,
        "amount": _crypto_payload(payment.amount),
        "chain": {
            "chainId": payment.chain.chain_id,
            "name": payment.chain.name,
        },
        "walletFrom": str(payment.wallet_from),
        "walletTo": str(payment.wallet_to),
        "txHash": str(payment.tx_hash) if payment.tx_hash is not None else None,
        "failureReason": payment.failure_reason,
        "expiresAt": payment.expires_at.isoformat(),
        "createdAt": payment.created_at.isoformat(),
        "updatedAt": payment.updated_at.isoformat(),
    }


def _outbox_payload(message: OperatorOutboxSnapshot) -> dict[str, Any]:
    return {
        "messageId": message.identity,
        "kind": message.kind.value,
        "name": message.name,
        "topic": message.topic,
        "key": message.key,
        "status": message.status.value,
        "failureCount": message.failure_count,
        "lastError": message.last_error,
        "retryCandidate": message.retry_candidate,
        "retryReason": message.retry_reason,
        "createdAt": message.created_at.isoformat(),
        "publishedAt": message.published_at.isoformat() if message.published_at is not None else None,
        "updatedAt": message.updated_at.isoformat(),
    }


def _worker_payload(worker: OperatorWorkerSnapshot) -> dict[str, Any]:
    return {
        "component": worker.component,
        "state": worker.state.value,
        "checkedAt": worker.checked_at.isoformat(),
        "details": dict(worker.details),
    }


def _page_payload(page: OperatorPage) -> dict[str, Any]:
    return {
        "limit": page.limit,
        "nextPageToken": page.next_page_token,
    }


def _crypto_payload(value: Crypto) -> dict[str, Any]:
    return {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }


def _lookup_value(request: ApiRequest, key: str) -> str:
    value = _optional_text(request.query.get(key))
    if value is not None:
        return value
    parts = [part for part in request.path.strip("/").split("/") if part]
    if parts:
        return _require_text(parts[-1], key)
    raise ValueError(f"{key} is required")


def _lower_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def _csv_values(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, list | tuple):
        values: list[str] = []
        for item in value:
            values.extend(_csv_values(item))
        return tuple(values)
    raise ValueError("query list values must be strings")


def _optional_role(value: object) -> UserRole | None:
    text = _optional_text(value)
    if text is None:
        return None
    return UserRole(text)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("query values must be non-empty strings")
    return value.strip()


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int_value(value, default=0)


def _int_value(value: object, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("integer query values must not be bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    raise ValueError("integer query values must be integers")


def _bool_value(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError("boolean query values must be true or false")


def _not_found_response(request_id: str | None) -> ApiResponse:
    return _error_response("OPERATOR_RESOURCE_NOT_FOUND", "operator resource was not found", 404, request_id)


def _error_response(code: str, message: str, status_code: int, request_id: str | None) -> ApiResponse:
    return json_response(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
        request_id=request_id,
    )


__all__ = [
    "AdminRoleOperatorPolicy",
    "OperatorAccessPolicy",
    "OperatorApi",
    "OperatorClaims",
]

"""Map framework-neutral API payloads into UI-only view models."""

from __future__ import annotations

from typing import Any, Mapping

from .models import (
    CheckoutTimelineItem,
    CheckoutViewModel,
    GasEstimateView,
    MoneyView,
    OperatorDashboardViewModel,
    OperatorDetailView,
    OperatorFilterState,
    OperatorTableRow,
    StatusBadge,
)


def checkout_view_from_api_payload(
    payload: Mapping[str, Any],
    *,
    wallet_address: str | None = None,
    network_name: str | None = None,
    timeline: tuple[CheckoutTimelineItem, ...] = (),
) -> CheckoutViewModel:
    payload = _api_body(payload)
    checkout = _child_mapping(payload, "checkout", default=payload)
    payment_request = _optional_mapping(checkout.get("paymentRequest"))
    amount = _money_from_payload(payment_request.get("amount")) if payment_request else None
    gas_estimate = _gas_estimate_from_payload(checkout.get("gasEstimate"))
    chain_id = amount.chain_id if amount is not None else None

    outbox_items = tuple(
        CheckoutTimelineItem(
            label=_text(item.get("name"), "outboxStatus.name"),
            status=StatusBadge(_text(item.get("status"), "outboxStatus.status")),
            message_id=_optional_text(item.get("messageId")),
            occurred_at=_optional_text(item.get("updatedAt")),
        )
        for item in _mapping_items(checkout.get("outboxStatus"), "outboxStatus")
    )

    timeline_items = timeline or _default_checkout_timeline(checkout)
    return CheckoutViewModel(
        order_id=_text(checkout.get("orderId"), "checkout.orderId"),
        tracking_id=_text(checkout.get("trackingId"), "checkout.trackingId"),
        status=StatusBadge(_text(checkout.get("status"), "checkout.status")),
        current_step=_text(checkout.get("currentStep"), "checkout.currentStep"),
        pending_action=_optional_text(checkout.get("pendingAction")),
        wallet_address=wallet_address,
        network_label=network_name,
        chain_id=chain_id,
        token_amount=amount,
        gas_estimate=gas_estimate,
        payment_expires_at=_optional_text(payment_request.get("expiresAt")) if payment_request else None,
        receiver_wallet=_optional_text(payment_request.get("to")) if payment_request else None,
        tx_hash=_optional_text(checkout.get("txHash")),
        failure_reason=_optional_text(checkout.get("failureReason")),
        timeline=timeline_items + outbox_items,
        updated_at=_optional_text(checkout.get("updatedAt")),
    )


def operator_dashboard_from_api_payload(
    payload: Mapping[str, Any],
    *,
    filters: Mapping[str, Any] | None = None,
    detail: Mapping[str, Any] | None = None,
) -> OperatorDashboardViewModel:
    payload = _api_body(payload)
    filter_state = _operator_filters(filters or {})
    orders = tuple(_order_row(item) for item in _mapping_items(payload.get("orders"), "orders"))
    payments = tuple(_payment_row(item) for item in _mapping_items(payload.get("payments"), "payments"))
    outbox = tuple(_outbox_row(item) for item in _mapping_items(payload.get("outbox"), "outbox"))
    workers = tuple(_worker_row(item) for item in _mapping_items(payload.get("workers"), "workers"))
    errors = tuple(_error_row(item) for item in _mapping_items(payload.get("errors"), "errors"))
    detail_view = OperatorDetailView(title="Detail", fields=detail) if detail is not None else None

    return OperatorDashboardViewModel(
        filters=filter_state,
        orders=orders,
        payments=payments,
        outbox=outbox,
        workers=workers,
        errors=errors,
        detail=detail_view,
    )


def _operator_filters(payload: Mapping[str, Any]) -> OperatorFilterState:
    return OperatorFilterState(
        contexts=_text_tuple(payload.get("contexts"), default=("orders", "payments", "outbox")),
        statuses=_text_tuple(payload.get("statuses"), default=()),
        chain_id=_optional_int(payload.get("chain_id", payload.get("chainId"))),
        store_id=_optional_text(payload.get("store_id", payload.get("storeId"))),
        failed_only=_bool_value(payload.get("failed_only", payload.get("failedOnly")), default=False),
        retry_candidates_only=_bool_value(
            payload.get("retry_candidates_only", payload.get("retryCandidatesOnly")),
            default=False,
        ),
        sort=_optional_text(payload.get("sort")) or "-updatedAt",
    )


def _api_body(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    body = payload.get("body")
    if body is None:
        return payload
    return _mapping(body, "body")


def _order_row(payload: Mapping[str, Any]) -> OperatorTableRow:
    total_amount = _money_from_payload(payload.get("totalAmount"))
    return OperatorTableRow(
        resource="orders",
        identity=_text(payload.get("orderId"), "order.orderId"),
        status=StatusBadge(_text(payload.get("status"), "order.status")),
        primary=_optional_text(payload.get("latestEvent")) or _text(payload.get("trackingId"), "order.trackingId"),
        secondary=f"store {_optional_text(payload.get('storeId')) or '-'} / customer {_optional_text(payload.get('customerId')) or '-'}",
        amount=total_amount,
        chain_id=total_amount.chain_id,
        updated_at=_optional_text(payload.get("updatedAt")),
        failure_reason=_optional_text(payload.get("failureReason")),
        latest_event=_optional_text(payload.get("latestEvent")),
        metadata={"paymentStatus": _optional_text(payload.get("paymentStatus")) or "none"},
    )


def _payment_row(payload: Mapping[str, Any]) -> OperatorTableRow:
    amount = _money_from_payload(payload.get("amount"))
    chain = _optional_mapping(payload.get("chain"))
    chain_id = _optional_int(chain.get("chainId")) if chain else amount.chain_id
    secondary = f"{_optional_text(payload.get('walletFrom')) or '-'} -> {_optional_text(payload.get('walletTo')) or '-'}"
    return OperatorTableRow(
        resource="payments",
        identity=_text(payload.get("paymentId"), "payment.paymentId"),
        status=StatusBadge(_text(payload.get("status"), "payment.status")),
        primary=f"order {_optional_text(payload.get('orderId')) or '-'}",
        secondary=secondary,
        amount=amount,
        chain_id=chain_id,
        updated_at=_optional_text(payload.get("updatedAt")),
        failure_reason=_optional_text(payload.get("failureReason")),
        tx_hash=_optional_text(payload.get("txHash")),
        metadata={
            "expiresAt": _optional_text(payload.get("expiresAt")) or "none",
            "chain": _optional_text(chain.get("name")) if chain else None,
        },
    )


def _outbox_row(payload: Mapping[str, Any]) -> OperatorTableRow:
    retry_candidate = _bool_value(payload.get("retryCandidate"), default=False)
    metadata: dict[str, Any] = {
        "kind": _optional_text(payload.get("kind")),
        "failureCount": payload.get("failureCount"),
    }
    if retry_candidate:
        metadata["retry"] = "Retry candidate"
    return OperatorTableRow(
        resource="outbox",
        identity=_text(payload.get("messageId"), "outbox.messageId"),
        status=StatusBadge(_text(payload.get("status"), "outbox.status")),
        primary=_text(payload.get("name"), "outbox.name"),
        secondary=f"{_optional_text(payload.get('topic')) or '-'} / key {_optional_text(payload.get('key')) or '-'}",
        updated_at=_optional_text(payload.get("updatedAt")),
        failure_reason=_optional_text(payload.get("lastError")),
        latest_event=_optional_text(payload.get("name")),
        metadata=metadata,
    )


def _worker_row(payload: Mapping[str, Any]) -> OperatorTableRow:
    details = _optional_mapping(payload.get("details")) or {}
    return OperatorTableRow(
        resource="workers",
        identity=_text(payload.get("component"), "worker.component"),
        status=StatusBadge(_text(payload.get("state"), "worker.state")),
        primary=_text(payload.get("component"), "worker.component"),
        updated_at=_optional_text(payload.get("checkedAt")),
        metadata=details,
    )


def _error_row(payload: Mapping[str, Any]) -> OperatorTableRow:
    return OperatorTableRow(
        resource="errors",
        identity=_text(payload.get("aggregateId"), "error.aggregateId"),
        status=StatusBadge(_text(payload.get("code"), "error.code")),
        primary=_text(payload.get("context"), "error.context"),
        updated_at=_optional_text(payload.get("createdAt")),
        failure_reason=_text(payload.get("message"), "error.message"),
    )


def _default_checkout_timeline(payload: Mapping[str, Any]) -> tuple[CheckoutTimelineItem, ...]:
    current_step = _text(payload.get("currentStep"), "checkout.currentStep")
    status = _text(payload.get("status"), "checkout.status")
    items = [
        CheckoutTimelineItem(label="ORDER_CREATED", status="ORDER_CREATED"),
        CheckoutTimelineItem(label=current_step, status=status, occurred_at=_optional_text(payload.get("updatedAt"))),
    ]
    tx_hash = _optional_text(payload.get("txHash"))
    if tx_hash:
        items.append(CheckoutTimelineItem(label="txHash submitted", status="SUBMITTED", message_id=tx_hash))
    failure_reason = _optional_text(payload.get("failureReason"))
    if failure_reason:
        items.append(CheckoutTimelineItem(label="failure reason", status=status, detail=failure_reason))
    return tuple(items)


def _gas_estimate_from_payload(value: object) -> GasEstimateView | None:
    payload = _optional_mapping(value)
    if payload is None:
        return None
    max_fee_payload = payload.get("maxFee")
    return GasEstimateView(
        estimated_fee=_money_from_payload(payload.get("estimatedFee")),
        gas_limit=_int_value(payload.get("gasLimit"), "gasEstimate.gasLimit"),
        buffer_rate=_text(payload.get("bufferRate"), "gasEstimate.bufferRate"),
        max_fee=_money_from_payload(max_fee_payload) if max_fee_payload is not None else None,
    )


def _money_from_payload(value: object) -> MoneyView:
    payload = _mapping(value, "money")
    return MoneyView(
        amount=_text(payload.get("amount"), "money.amount"),
        symbol=_text(payload.get("symbol"), "money.symbol"),
        chain_id=_optional_int(payload.get("chainId")),
        token_address=_optional_text(payload.get("tokenAddress")),
        decimals=_optional_int(payload.get("decimals")),
    )


def _child_mapping(payload: Mapping[str, Any], key: str, *, default: Mapping[str, Any]) -> Mapping[str, Any]:
    child = payload.get(key)
    if child is None:
        return default
    return _mapping(child, key)


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return value


def _optional_mapping(value: object) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _mapping(value, "mapping")


def _mapping_items(value: object, field_name: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ValueError(f"{field_name} must be a list")
    return tuple(_mapping(item, field_name) for item in value)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value, "text")


def _text_tuple(value: object, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, tuple | list):
        return tuple(_text(item, "tuple value") for item in value)
    raise ValueError("tuple value must be a string or sequence of strings")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int_value(value, "integer")


def _int_value(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must not be bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    raise ValueError(f"{field_name} must be an integer")


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
    raise ValueError("boolean values must be true or false")


__all__ = [
    "checkout_view_from_api_payload",
    "operator_dashboard_from_api_payload",
]

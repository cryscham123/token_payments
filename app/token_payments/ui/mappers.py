"""Map framework-neutral API payloads into UI-only view models."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote

from .models import (
    CheckoutAction,
    CheckoutOrderItemView,
    CheckoutTimelineItem,
    CheckoutViewModel,
    GasEstimateView,
    MoneyView,
    OperatorActionIntent,
    OperatorDashboardViewModel,
    OperatorDetailView,
    OperatorFilterState,
    OperatorSummaryItem,
    OperatorTableRow,
    StatusBadge,
)


OPERATOR_ACTION_SOURCE = "operator-dashboard"
OPERATOR_CANCEL_STATUSES = {
    "PENDING",
    "AWAITING_SIGNATURE",
    "SUBMITTED",
    "FAILED",
    "EXPIRED",
    "CANCELLING",
}

CHECKOUT_TIMELINE_STAGES = (
    ("ORDER_CREATED", "Order created"),
    ("INVENTORY_RESERVED", "Inventory reserved"),
    ("AWAITING_SIGNATURE", "Payment signature"),
    ("TX_SUBMITTED", "tx submitted"),
    ("PAYMENT_CONFIRMED", "Payment confirmation"),
    ("STORE_APPROVAL", "Store approval"),
    ("COMPLETED", "Completed"),
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
    order = _optional_mapping(payload.get("order")) or checkout
    payment_request = _optional_mapping(checkout.get("paymentRequest"))
    amount = _money_from_payload(payment_request.get("amount")) if payment_request else None
    if amount is None and order.get("totalAmount") is not None:
        amount = _money_from_payload(order.get("totalAmount"))
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

    timeline_items = timeline or _timeline_from_payload(checkout.get("timeline")) or _default_checkout_timeline(checkout)
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
        payment_expires_in=_payment_expires_in(checkout),
        receiver_wallet=_optional_text(payment_request.get("to")) if payment_request else None,
        tx_hash=_optional_text(checkout.get("txHash")),
        tx_hash_status=_optional_text(checkout.get("txHashStatus")),
        failure_reason=_optional_text(checkout.get("failureReason")),
        order_items=_order_items_from_payload(order, checkout),
        actions=_actions_from_payload(checkout),
        timeline=timeline_items + outbox_items,
        updated_at=_optional_text(checkout.get("updatedAt")),
    )


def operator_dashboard_from_api_payload(
    payload: Mapping[str, Any],
    *,
    filters: Mapping[str, Any] | None = None,
    detail: Mapping[str, Any] | None = None,
    actions: tuple[OperatorActionIntent, ...] | None = None,
) -> OperatorDashboardViewModel:
    payload = _api_body(payload)
    filter_state = _operator_filters(filters or {})
    orders = tuple(_order_row(item) for item in _mapping_items(payload.get("orders"), "orders"))
    payments = tuple(_payment_row(item) for item in _mapping_items(payload.get("payments"), "payments"))
    inventory = tuple(_inventory_row(item) for item in _mapping_items(payload.get("inventory"), "inventory"))
    store_approvals = tuple(
        _store_approval_row(item)
        for item in _mapping_items(
            payload.get("storeApprovals", payload.get("store_approvals", payload.get("approvals"))),
            "storeApprovals",
        )
    )
    outbox = tuple(_outbox_row(item) for item in _mapping_items(payload.get("outbox"), "outbox"))
    workers = tuple(_worker_row(item) for item in _mapping_items(payload.get("workers"), "workers"))
    errors = tuple(_error_row(item) for item in _mapping_items(payload.get("errors"), "errors"))
    detail_payload = detail if detail is not None else _optional_mapping(payload.get("detail"))
    detail_view = _operator_detail_view(detail_payload) if detail_payload is not None else None
    action_intents = _operator_action_override(actions)
    if action_intents is None:
        action_intents = _operator_action_override_from_payload(payload)
    if action_intents is None:
        action_intents = _operator_action_intents(
            payload=payload,
            orders=orders,
            outbox=outbox,
            detail=detail_payload,
        )

    return OperatorDashboardViewModel(
        filters=filter_state,
        summary=_operator_summary_items(outbox=outbox, workers=workers),
        orders=orders,
        payments=payments,
        inventory=inventory,
        store_approvals=store_approvals,
        outbox=outbox,
        workers=workers,
        errors=errors,
        actions=action_intents,
        detail=detail_view,
    )


def _operator_filters(payload: Mapping[str, Any]) -> OperatorFilterState:
    statuses = tuple(status.upper() for status in _text_tuple(payload.get("statuses", payload.get("status")), default=()))
    return OperatorFilterState(
        contexts=_text_tuple(
            payload.get("contexts", payload.get("context")),
            default=("orders", "payments", "inventory", "store-approvals", "outbox", "workers", "errors"),
        ),
        statuses=statuses,
        chain_id=_optional_int(payload.get("chain_id", payload.get("chainId"))),
        store_id=_optional_text(payload.get("store_id", payload.get("storeId"))),
        created_at_from=_optional_text(payload.get("created_at_from", payload.get("createdAtFrom"))),
        created_at_to=_optional_text(payload.get("created_at_to", payload.get("createdAtTo"))),
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
        store_id=_optional_text(payload.get("storeId")),
        created_at=_optional_text(payload.get("createdAt")),
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
        gas=_optional_money_from_payload(payload.get("gasEstimate", payload.get("gas"))),
        chain_id=chain_id,
        created_at=_optional_text(payload.get("createdAt")),
        updated_at=_optional_text(payload.get("updatedAt")),
        failure_reason=_optional_text(payload.get("failureReason")),
        tx_hash=_optional_text(payload.get("txHash")),
        metadata={
            "expiresAt": _optional_text(payload.get("expiresAt")) or "none",
            "chain": _optional_text(chain.get("name")) if chain else None,
        },
    )


def _inventory_row(payload: Mapping[str, Any]) -> OperatorTableRow:
    reserved_qty = _optional_int(payload.get("reservedQty", payload.get("quantity")))
    available_stock = _optional_int(payload.get("availableStock"))
    return OperatorTableRow(
        resource="inventory",
        identity=_optional_text(payload.get("reservationId")) or _text(payload.get("productId"), "inventory.productId"),
        status=StatusBadge(_text(payload.get("status"), "inventory.status")),
        primary=_optional_text(payload.get("latestEvent")) or _text(payload.get("productId"), "inventory.productId"),
        secondary=f"order {_optional_text(payload.get('orderId')) or '-'} / product {_optional_text(payload.get('productId')) or '-'}",
        quantity=reserved_qty,
        chain_id=_optional_int(payload.get("chainId")),
        store_id=_optional_text(payload.get("storeId")),
        created_at=_optional_text(payload.get("createdAt")),
        updated_at=_optional_text(payload.get("updatedAt")),
        failure_reason=_optional_text(payload.get("failureReason")),
        latest_event=_optional_text(payload.get("latestEvent")),
        metadata={
            "availableStock": available_stock,
            "orderId": _optional_text(payload.get("orderId")),
            "productId": _optional_text(payload.get("productId")),
        },
    )


def _store_approval_row(payload: Mapping[str, Any]) -> OperatorTableRow:
    amount_payload = payload.get("totalAmount", payload.get("amount"))
    amount = _money_from_payload(amount_payload) if amount_payload is not None else None
    return OperatorTableRow(
        resource="store-approvals",
        identity=_optional_text(payload.get("approvalId")) or _text(payload.get("orderId"), "storeApproval.orderId"),
        status=StatusBadge(_text(payload.get("status"), "storeApproval.status")),
        primary=_optional_text(payload.get("latestEvent")) or f"order {_text(payload.get('orderId'), 'storeApproval.orderId')}",
        secondary=f"order {_optional_text(payload.get('orderId')) or '-'}",
        amount=amount,
        chain_id=_optional_int(payload.get("chainId")) or (amount.chain_id if amount else None),
        store_id=_optional_text(payload.get("storeId")),
        created_at=_optional_text(payload.get("createdAt")),
        updated_at=_optional_text(payload.get("updatedAt")),
        failure_reason=_optional_text(payload.get("failureReason")),
        latest_event=_optional_text(payload.get("latestEvent")),
        metadata={
            "rejectionReasons": payload.get("rejectionReasons"),
            "ownerUserId": _optional_text(payload.get("ownerUserId")),
        },
    )


def _outbox_row(payload: Mapping[str, Any]) -> OperatorTableRow:
    retry_candidate = _bool_value(payload.get("retryCandidate"), default=False)
    metadata: dict[str, Any] = {
        "kind": _optional_text(payload.get("kind")),
        "failureCount": payload.get("failureCount"),
        "retryReason": _optional_text(payload.get("retryReason")),
    }
    if retry_candidate:
        metadata["retry"] = "Retry candidate"
    return OperatorTableRow(
        resource="outbox",
        identity=_text(payload.get("messageId"), "outbox.messageId"),
        status=StatusBadge(_text(payload.get("status"), "outbox.status")),
        primary=_text(payload.get("name"), "outbox.name"),
        secondary=f"{_optional_text(payload.get('topic')) or '-'} / key {_optional_text(payload.get('key')) or '-'}",
        created_at=_optional_text(payload.get("createdAt")),
        updated_at=_optional_text(payload.get("updatedAt")),
        failure_reason=_optional_text(payload.get("lastError")),
        latest_event=_optional_text(payload.get("name")),
        retry_candidate=retry_candidate,
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
        created_at=_optional_text(payload.get("createdAt")),
        updated_at=_optional_text(payload.get("createdAt")),
        failure_reason=_text(payload.get("message"), "error.message"),
    )


def _operator_summary_items(
    *,
    outbox: tuple[OperatorTableRow, ...],
    workers: tuple[OperatorTableRow, ...],
) -> tuple[OperatorSummaryItem, ...]:
    retry_candidates = sum(1 for row in outbox if row.retry_candidate)
    failed_outbox = sum(1 for row in outbox if row.status.label == "FAILED")
    unhealthy_workers = sum(1 for row in workers if row.status.label != "OK")
    return (
        OperatorSummaryItem(
            key="retry-candidates",
            label="Retry candidates",
            value=retry_candidates,
            status="FAILED" if retry_candidates else "OK",
            detail="Read-only candidates for relay or compensation inspection",
        ),
        OperatorSummaryItem(
            key="failed-outbox",
            label="Failed outbox",
            value=failed_outbox,
            status="FAILED" if failed_outbox else "OK",
            detail="Outbox rows currently marked FAILED",
        ),
        OperatorSummaryItem(
            key="unhealthy-workers",
            label="Unhealthy workers",
            value=unhealthy_workers,
            status="UNAVAILABLE" if unhealthy_workers else "OK",
            detail="Workers not reporting OK health",
        ),
    )


def _operator_detail_view(payload: Mapping[str, Any]) -> OperatorDetailView:
    title = _optional_text(payload.get("title")) or "Detail"
    return OperatorDetailView(
        title=title,
        fields={str(key): value for key, value in payload.items() if str(key) != "title"},
    )


def _operator_action_override(
    actions: tuple[OperatorActionIntent, ...] | object,
) -> tuple[OperatorActionIntent, ...] | None:
    if actions is None:
        return None
    if isinstance(actions, tuple) and all(isinstance(action, OperatorActionIntent) for action in actions):
        return actions
    return tuple(
        _operator_action_intent_from_payload(action)
        for action in _mapping_items(actions, "operator actions")
    )


def _operator_action_override_from_payload(payload: Mapping[str, Any]) -> tuple[OperatorActionIntent, ...] | None:
    if "operatorActions" in payload:
        return _operator_action_override(payload.get("operatorActions"))
    if "actions" in payload:
        return _operator_action_override(payload.get("actions"))
    return None


def _operator_action_intent_from_payload(payload: Mapping[str, Any]) -> OperatorActionIntent:
    return OperatorActionIntent(
        action_id=_text(payload.get("actionId", payload.get("action_id")), "operatorAction.actionId"),
        label=_text(payload.get("label"), "operatorAction.label"),
        kind=_optional_text(payload.get("kind")) or "secondary",
        method=_text(payload.get("method"), "operatorAction.method"),
        endpoint=_text(payload.get("endpoint"), "operatorAction.endpoint"),
        operation_id=_text(
            payload.get("operationId", payload.get("operation_id")),
            "operatorAction.operationId",
        ),
        target_kind=_text(
            payload.get("targetKind", payload.get("target_kind")),
            "operatorAction.targetKind",
        ),
        target_id=_text(payload.get("targetId", payload.get("target_id")), "operatorAction.targetId"),
        reason=_text(payload.get("reason"), "operatorAction.reason"),
        enabled=_bool_value(payload.get("enabled"), default=True),
        confirmation=_text(payload.get("confirmation"), "operatorAction.confirmation"),
        idempotency_key=_text(
            payload.get("idempotencyKey", payload.get("idempotency_key")),
            "operatorAction.idempotencyKey",
        ),
        body_template=_mapping(
            payload.get("bodyTemplate", payload.get("body_template")),
            "operatorAction.bodyTemplate",
        ),
    )


def _operator_action_intents(
    *,
    payload: Mapping[str, Any],
    orders: tuple[OperatorTableRow, ...],
    outbox: tuple[OperatorTableRow, ...],
    detail: Mapping[str, Any] | None,
) -> tuple[OperatorActionIntent, ...]:
    action_intents: list[OperatorActionIntent] = []
    seen_action_ids: set[str] = set()

    for order in orders:
        if order.status.label.upper() in OPERATOR_CANCEL_STATUSES:
            _append_unique(action_intents, seen_action_ids, _cancel_order_intent(order))

    for row in outbox:
        status = row.status.label.upper()
        if row.retry_candidate or status == "FAILED":
            _append_unique(action_intents, seen_action_ids, _retry_outbox_intent(row))

    detail_replay = _replay_intent_from_detail(detail)
    if detail_replay is not None:
        _append_unique(action_intents, seen_action_ids, detail_replay)

    for item in _mapping_items(payload.get("replayMessages", payload.get("replay_messages")), "replayMessages"):
        replay = _replay_intent_from_payload(item)
        if replay is not None:
            _append_unique(action_intents, seen_action_ids, replay)

    return tuple(action_intents)


def _append_unique(
    action_intents: list[OperatorActionIntent],
    seen_action_ids: set[str],
    intent: OperatorActionIntent,
) -> None:
    if intent.action_id in seen_action_ids:
        return
    action_intents.append(intent)
    seen_action_ids.add(intent.action_id)


def _cancel_order_intent(order: OperatorTableRow) -> OperatorActionIntent:
    order_id = order.identity
    reason = f"operator dashboard cancel requested for order {order_id}"
    idempotency_key = f"operator:cancelOrder:{order_id}"
    route = _operator_action_route("cancel_order")
    return OperatorActionIntent(
        action_id=f"cancelOrder:{order_id}",
        label="Cancel order",
        kind="danger",
        method=route.method,
        endpoint=_route_path("cancel_order", orderId=order_id),
        operation_id=route.operation_id,
        target_kind="order",
        target_id=order_id,
        reason=reason,
        enabled=True,
        confirmation=f"Cancel order {order_id}?",
        idempotency_key=idempotency_key,
        body_template=_action_body_template(reason=reason, idempotency_key=idempotency_key),
    )


def _retry_outbox_intent(row: OperatorTableRow) -> OperatorActionIntent:
    message_id = row.identity
    message_kind = _message_kind_from_values(
        row.metadata.get("kind"),
        row.latest_event,
        row.primary,
    )
    reason = (
        _optional_text(row.metadata.get("retryReason"))
        or row.failure_reason
        or f"operator dashboard retry requested for outbox message {message_id}"
    )
    idempotency_key = f"operator:retryOutboxMessage:{message_id}"
    route = _operator_action_route("retry_outbox_message")
    return OperatorActionIntent(
        action_id=f"retryOutboxMessage:{message_id}",
        label="Retry outbox message",
        kind="secondary",
        method=route.method,
        endpoint=_route_path("retry_outbox_message", messageId=message_id),
        operation_id=route.operation_id,
        target_kind="outboxMessage",
        target_id=message_id,
        reason=reason,
        enabled=row.retry_candidate,
        confirmation=f"Retry outbox message {message_id}?",
        idempotency_key=idempotency_key,
        body_template=_action_body_template(
            reason=reason,
            idempotency_key=idempotency_key,
            kind=message_kind,
        ),
    )


def _replay_intent_from_detail(detail: Mapping[str, Any] | None) -> OperatorActionIntent | None:
    if detail is None:
        return None
    if "replayCandidate" in detail and not _bool_value(detail.get("replayCandidate"), default=False):
        return None
    message_id = _optional_text(detail.get("replayMessageId"))
    if message_id is None and (
        "messageKind" in detail or "kind" in detail or _bool_value(detail.get("replayCandidate"), default=False)
    ):
        message_id = _optional_text(detail.get("messageId"))
    if message_id is None:
        return None
    message_kind = _message_kind_from_values(
        detail.get("messageKind", detail.get("kind")),
        detail.get("latestEvent"),
    )
    reason = _optional_text(detail.get("replayReason", detail.get("reason"))) or (
        f"operator dashboard replay requested for message {message_id}"
    )
    return _replay_message_intent(message_id=message_id, message_kind=message_kind, reason=reason)


def _replay_intent_from_payload(payload: Mapping[str, Any]) -> OperatorActionIntent | None:
    if "replayCandidate" in payload and not _bool_value(payload.get("replayCandidate"), default=False):
        return None
    message_id = _optional_text(payload.get("messageId", payload.get("id")))
    if message_id is None:
        return None
    message_kind = _message_kind_from_values(
        payload.get("messageKind", payload.get("kind")),
        payload.get("name", payload.get("latestEvent")),
    )
    reason = _optional_text(payload.get("reason")) or f"operator dashboard replay requested for message {message_id}"
    return _replay_message_intent(message_id=message_id, message_kind=message_kind, reason=reason)


def _replay_message_intent(*, message_id: str, message_kind: str, reason: str) -> OperatorActionIntent:
    idempotency_key = f"operator:replayMessage:{message_id}"
    route = _operator_action_route("replay_message")
    return OperatorActionIntent(
        action_id=f"replayMessage:{message_id}",
        label="Replay message",
        kind="secondary",
        method=route.method,
        endpoint=_route_path("replay_message", messageId=message_id),
        operation_id=route.operation_id,
        target_kind="message",
        target_id=message_id,
        reason=reason,
        enabled=True,
        confirmation=f"Replay message {message_id}?",
        idempotency_key=idempotency_key,
        body_template=_action_body_template(reason=reason, idempotency_key=idempotency_key, kind=message_kind),
    )


def _action_body_template(*, reason: str, idempotency_key: str, kind: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "reason": reason,
        "idempotencyKey": idempotency_key,
        "parameters": {"source": OPERATOR_ACTION_SOURCE},
    }
    if kind is not None:
        body["kind"] = kind
    return body


def _route_path(route_key: str, **params: str) -> str:
    path = _operator_action_route(route_key).path
    for key, value in params.items():
        path = path.replace("{" + key + "}", quote(value, safe=""))
    return path


def _operator_action_route(route_key: str):
    from token_payments.api.http import OPERATOR_ACTION_HTTP_ROUTES

    return OPERATOR_ACTION_HTTP_ROUTES[route_key]


def _message_kind_from_values(*values: object) -> str:
    for value in values:
        text = _optional_text(value)
        if text:
            normalized = text.upper()
            if normalized in {"EVENT", "COMMAND"}:
                return normalized
            if "COMMAND" in normalized:
                return "COMMAND"
            if "EVENT" in normalized:
                return "EVENT"
    return "EVENT"


def _default_checkout_timeline(payload: Mapping[str, Any]) -> tuple[CheckoutTimelineItem, ...]:
    current_step = _text(payload.get("currentStep"), "checkout.currentStep")
    status = _text(payload.get("status"), "checkout.status")
    updated_at = _optional_text(payload.get("updatedAt"))
    tx_hash = _optional_text(payload.get("txHash"))
    failure_reason = _optional_text(payload.get("failureReason"))
    pending_action = _optional_text(payload.get("pendingAction"))

    completed_payment_steps = {
        "AWAITING_SIGNATURE",
        "RECEIPT_PENDING",
        "PAYMENT_CONFIRMED",
        "ORDER_APPROVED",
    }
    payment_failed = current_step in {"PAYMENT_FAILED", "PAYMENT_EXPIRED"} or status in {"FAILED", "EXPIRED"}
    payment_confirmed = current_step in {"PAYMENT_CONFIRMED", "ORDER_APPROVED"} or status in {"CONFIRMED", "APPROVED"}
    order_approved = current_step == "ORDER_APPROVED" or status == "APPROVED"

    compensation_status = None
    if payment_failed and pending_action == "WAIT_FOR_COMPENSATION":
        compensation_status = "ReleaseInventoryCommand PENDING; CancelOrderCommand PENDING"

    return (
        CheckoutTimelineItem(
            label="Order created",
            status="ORDER_CREATED",
            stage="ORDER_CREATED",
        ),
        CheckoutTimelineItem(
            label="Inventory reserved",
            status="CONFIRMED" if current_step in completed_payment_steps or payment_failed else "PENDING",
            stage="INVENTORY_RESERVED",
        ),
        CheckoutTimelineItem(
            label="Payment signature",
            status="CONFIRMED" if tx_hash or payment_confirmed else "AWAITING_SIGNATURE",
            stage="AWAITING_SIGNATURE",
            occurred_at=updated_at if current_step == "AWAITING_SIGNATURE" else None,
        ),
        CheckoutTimelineItem(
            label="tx submitted",
            status="SUBMITTED" if tx_hash else "PENDING",
            stage="TX_SUBMITTED",
            message_id=tx_hash,
        ),
        CheckoutTimelineItem(
            label="Payment confirmation",
            status=status if payment_failed else ("CONFIRMED" if payment_confirmed else "PENDING"),
            stage="PAYMENT_CONFIRMED",
            occurred_at=updated_at if current_step in {"PAYMENT_CONFIRMED", "PAYMENT_FAILED", "PAYMENT_EXPIRED"} else None,
            detail=failure_reason if payment_failed else None,
            compensation_status=compensation_status,
        ),
        CheckoutTimelineItem(
            label="Store approval",
            status="APPROVED" if order_approved else "PENDING",
            stage="STORE_APPROVAL",
        ),
        CheckoutTimelineItem(
            label="Completed",
            status="COMPLETED" if order_approved else "PENDING",
            stage="COMPLETED",
        ),
    )


def _timeline_from_payload(value: object) -> tuple[CheckoutTimelineItem, ...]:
    raw_items = _mapping_items(value, "timeline")
    if not raw_items:
        return ()

    by_stage = {
        _text(item.get("stage"), "timeline.stage"): item
        for item in raw_items
    }
    items: list[CheckoutTimelineItem] = []
    for stage, default_label in CHECKOUT_TIMELINE_STAGES:
        item = by_stage.get(stage)
        if item is None:
            items.append(CheckoutTimelineItem(label=default_label, status="PENDING", stage=stage))
            continue
        items.append(
            CheckoutTimelineItem(
                label=_optional_text(item.get("label")) or default_label,
                status=StatusBadge(_text(item.get("status"), "timeline.status")),
                stage=stage,
                message_id=_optional_text(item.get("messageId")),
                command_id=_optional_text(item.get("commandId")),
                occurred_at=_optional_text(item.get("occurredAt", item.get("updatedAt"))),
                detail=_optional_text(item.get("detail")),
                compensation_status=_optional_text(item.get("compensationStatus")),
            )
        )
    return tuple(items)


def _order_items_from_payload(order: Mapping[str, Any], checkout: Mapping[str, Any]) -> tuple[CheckoutOrderItemView, ...]:
    raw_items = _mapping_items(order.get("items"), "order.items")
    if not raw_items:
        raw_items = _mapping_items(checkout.get("items"), "checkout.items")
    return tuple(_order_item_from_payload(item) for item in raw_items)


def _order_item_from_payload(item: Mapping[str, Any]) -> CheckoutOrderItemView:
    return CheckoutOrderItemView(
        product_id=_text(item.get("productId"), "order.items.productId"),
        name=_text(item.get("name"), "order.items.name"),
        quantity=_int_value(item.get("quantity"), "order.items.quantity"),
        unit_price=_money_from_payload(item.get("unitPrice")),
        sub_total=_money_from_payload(item.get("subTotal")),
    )


def _actions_from_payload(checkout: Mapping[str, Any]) -> tuple[CheckoutAction, ...]:
    raw_actions = _mapping_items(checkout.get("actions"), "checkout.actions")
    if raw_actions:
        return tuple(_action_from_payload(action) for action in raw_actions)

    pending_action = _optional_text(checkout.get("pendingAction"))
    return (
        CheckoutAction(
            action_id="connect-wallet",
            label="Connect Wallet",
            kind="secondary",
            tooltip="Connect wallet address",
            aria_label="Connect wallet address",
        ),
        CheckoutAction(
            action_id="sign-payment",
            label="Sign Payment",
            kind="primary",
            enabled=pending_action == "SIGN_PAYMENT",
            tooltip="Request MetaMask payment signature",
            aria_label="Request MetaMask payment signature",
            disabled_reason=None if pending_action == "SIGN_PAYMENT" else "Payment signature is not the pending action",
        ),
        CheckoutAction(
            action_id="submit-tx-hash",
            label="Submit txHash",
            kind="primary",
            enabled=pending_action in {"SUBMIT_TX_HASH", "WAIT_FOR_RECEIPT"},
            tooltip="Submit signed transaction hash",
            aria_label="Submit signed transaction hash",
            disabled_reason=None if pending_action in {"SUBMIT_TX_HASH", "WAIT_FOR_RECEIPT"} else "txHash submission is not ready",
        ),
        CheckoutAction(
            action_id="track-order",
            label="Track Order",
            kind="secondary",
            tooltip="Track checkout status",
            aria_label="Track checkout status",
        ),
    )


def _action_from_payload(action: Mapping[str, Any]) -> CheckoutAction:
    return CheckoutAction(
        action_id=_text(action.get("id", action.get("actionId")), "checkout.actions.id"),
        label=_text(action.get("label"), "checkout.actions.label"),
        kind=_optional_text(action.get("kind")) or "secondary",
        enabled=_bool_value(action.get("enabled"), default=True),
        tooltip=_optional_text(action.get("tooltip")),
        aria_label=_optional_text(action.get("ariaLabel", action.get("aria_label"))),
        disabled_reason=_optional_text(action.get("disabledReason", action.get("disabled_reason"))),
    )


def _payment_expires_in(checkout: Mapping[str, Any]) -> str | None:
    text_value = _optional_text(checkout.get("paymentExpiresIn"))
    if text_value:
        return text_value
    seconds = checkout.get("expiresInSeconds")
    if seconds is None:
        return None
    total_seconds = _int_value(seconds, "checkout.expiresInSeconds")
    if total_seconds < 0:
        raise ValueError("checkout.expiresInSeconds must be non-negative")
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


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


def _optional_money_from_payload(value: object) -> MoneyView | None:
    if value is None:
        return None
    return _money_from_payload(value)


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

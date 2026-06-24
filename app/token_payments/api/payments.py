"""Framework-neutral payment API handlers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from token_payments.contexts.payment.application import (
    ExpireAwaitingSignatureCommand,
    PaymentHistoryItem,
    PaymentHistoryQueryPort,
    PaymentCommandHandler,
    PaymentCommandRejected,
    PaymentCommandRejectionReason,
    PaymentCommandResult,
    PaymentCommandStatus,
    SubmitTransactionHashCommand,
)
from token_payments.contexts.payment.domain import PaymentStatus
from token_payments.shared.domain import CommandId, OrderId, PaymentId, UserId
from token_payments.contexts.order.domain import TrackingId

from .contracts import ApiRequest, ApiResponse, json_response
from .idempotency import IdempotencyKeyConflict, idempotency_conflict_response, idempotency_key_from_request


class PaymentsApi:
    """Payment API facade that delegates state changes to the payment application handler."""

    def __init__(
        self,
        handler: PaymentCommandHandler,
        tracking_query: Any = None,
        history_query: PaymentHistoryQueryPort | None = None,
    ) -> None:
        self._handler = handler
        self._tracking_query = tracking_query
        self._history_query = history_query

    def list_payments(self, request: ApiRequest) -> ApiResponse:
        try:
            user_id = _user_id_from_request(request)
            if user_id is None:
                return _error_response(
                    "AUTHENTICATION_REQUIRED",
                    "authenticated session is required",
                    401,
                    request.request_id,
                )
            if self._history_query is None:
                raise ValueError("payment history query is not configured")
            limit = _query_limit(request.query.get("limit"))
            statuses = _status_filter(request.query.get("status"))
            items = self._history_query.list_for_user(user_id, statuses=statuses, limit=limit)
            return json_response(
                {
                    "payments": [_history_item_payload(item) for item in items],
                    "pagination": {"limit": limit, "nextPageToken": None},
                },
                request_id=request.request_id,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def submit_transaction_hash(self, request: ApiRequest) -> ApiResponse:
        try:
            body = _request_body(request)
            if "orderId" in body:
                raise ValueError("orderId is not allowed in request body")

            tracking_id = TrackingId(_required_text(body, "trackingId"))

            user_id = _user_id_from_request(request)
            if user_id is None:
                raise ValueError("authenticated session is required")

            if self._tracking_query is None:
                raise ValueError("tracking query is not configured")

            order_id, payment_id = self._tracking_query.resolve_and_verify(tracking_id, user_id)

            command = SubmitTransactionHashCommand(
                command_id=_command_id(request, body, tracking_id),
                payment_id=payment_id,
                order_id=order_id,
                tx_hash=_required_text(body, "txHash"),
                submitted_at=request.received_at,
                causation_id=request.request_id,
            )
            result = self._handler.submit_transaction_hash(command)
            return json_response(_submit_payload(result, tracking_id, request.received_at), status_code=202, request_id=request.request_id)
        except IdempotencyKeyConflict as exc:
            return idempotency_conflict_response(exc, request.request_id)
        except PaymentCommandRejected as exc:
            return _payment_error_response(exc, request.request_id)
        except ValueError as exc:
            msg = str(exc)
            if "not own" in msg or "forbidden" in msg:
                return _error_response("FORBIDDEN", msg, 403, request.request_id)
            if "not found" in msg or "NotFound" in msg:
                return _error_response("NOT_FOUND", msg, 404, request.request_id)
            return _error_response("VALIDATION_ERROR", msg, 400, request.request_id)

    def cancel_payment(self, request: ApiRequest) -> ApiResponse:
        """Customer-initiated cancel of a payment still awaiting signature. Reuses the expiry
        flow (PAYMENT_EXPIRED -> RELEASE_INVENTORY + CANCEL_ORDER); rejected once the payment
        has moved past AWAITING_SIGNATURE (e.g. a tx was already submitted)."""
        try:
            body = _request_body(request)
            tracking_id = TrackingId(_required_text(body, "trackingId"))

            user_id = _user_id_from_request(request)
            if user_id is None:
                raise ValueError("authenticated session is required")

            if self._tracking_query is None:
                raise ValueError("tracking query is not configured")

            order_id, payment_id = self._tracking_query.resolve_and_verify(tracking_id, user_id)

            command = ExpireAwaitingSignatureCommand(
                command_id=CommandId(f"{order_id}:ExpireAwaitingSignatureCommand"),
                payment_id=payment_id,
                order_id=order_id,
                expired_at=request.received_at,
                reason="cancelled by customer",
                force=True,
                causation_id=request.request_id,
            )
            result = self._handler.expire_awaiting_signature(command)
            status = result.status.value if hasattr(result.status, "value") else str(result.status)
            return json_response(
                {"payment": {"orderId": str(order_id), "status": status}},
                status_code=202,
                request_id=request.request_id,
            )
        except IdempotencyKeyConflict as exc:
            return idempotency_conflict_response(exc, request.request_id)
        except PaymentCommandRejected as exc:
            return _payment_error_response(exc, request.request_id)
        except ValueError as exc:
            msg = str(exc)
            if "not own" in msg or "forbidden" in msg:
                return _error_response("FORBIDDEN", msg, 403, request.request_id)
            if "not found" in msg or "NotFound" in msg:
                return _error_response("NOT_FOUND", msg, 404, request.request_id)
            return _error_response("VALIDATION_ERROR", msg, 400, request.request_id)


def _request_body(request: ApiRequest) -> Mapping[str, Any]:
    if not isinstance(request.body, Mapping):
        raise ValueError("request body must be an object")
    return request.body


def _required_text(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _user_id_from_request(request: ApiRequest) -> UserId | None:
    if request.auth_context is not None and request.auth_context.user_id is not None:
        return UserId(request.auth_context.user_id)
    if request.local_auth_fallback_enabled:
        for key, value in request.headers.items():
            if key.lower() == "x-user-id" and value.strip():
                return UserId(value.strip())
    return None


def _query_limit(value: object) -> int:
    if value is None:
        return 50
    if isinstance(value, list | tuple):
        if len(value) != 1:
            raise ValueError("limit must be provided once")
        value = value[0]
    if isinstance(value, bool):
        raise ValueError("limit must be a positive integer")
    try:
        limit = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be a positive integer") from exc
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    return limit


def _status_filter(value: object) -> tuple[PaymentStatus, ...] | None:
    if value is None or value == "":
        return None
    raw_values = value if isinstance(value, list | tuple) else (value,)
    statuses: list[PaymentStatus] = []
    for raw in raw_values:
        for chunk in str(raw).split(","):
            normalized = chunk.strip()
            if not normalized:
                continue
            if normalized == "TX_SUBMITTED":
                normalized = PaymentStatus.SUBMITTED.value
            statuses.append(PaymentStatus(normalized))
    return tuple(statuses) if statuses else None


def _command_id(request: ApiRequest, body: Mapping[str, Any], tracking_id: TrackingId) -> CommandId:
    return CommandId(
        idempotency_key_from_request(
            request,
            body,
            fallback=f"payment.submit_tx:{tracking_id}",
        )
    )


def _submit_payload(result: PaymentCommandResult, tracking_id: TrackingId, updated_at: datetime) -> dict[str, Any]:
    payment = result.payment
    tx_hash = payment.tx_hash if payment is not None else None
    return {
        "payment": {
            "trackingId": str(tracking_id),
            "status": result.status.value,
            "currentStep": _current_step(result.status),
            "pendingAction": _pending_action(result.status),
            "txHash": str(tx_hash) if tx_hash is not None else None,
            "updatedAt": updated_at.isoformat(),
        }
    }


def _history_item_payload(item: PaymentHistoryItem) -> dict[str, Any]:
    return {
        "paymentId": str(item.payment_id),
        "orderId": str(item.order_id),
        "trackingId": str(item.tracking_id),
        "status": item.status.value,
        "currentStep": _current_step(item.status),
        "pendingAction": _pending_action(item.status),
        "amount": _crypto_payload(item.amount),
        "chain": {"chainId": item.chain_network.chain_id, "name": item.chain_network.name},
        "paymentAssetId": item.payment_asset_id,
        "txHash": str(item.tx_hash) if item.tx_hash is not None else None,
        "receipt": _receipt_payload(item.receipt),
        "failureReason": item.failure_reason,
        "updatedAt": item.updated_at.isoformat(),
        "items": [
            {
                "productId": str(x.get("productId")),
                "publicProductId": x.get("publicProductId"),
                "publicVariantId": x.get("publicVariantId"),
                "name": x.get("name"),
                "title": x.get("title"),
                "selectedOptions": dict(x.get("selectedOptions") or {}),
                "quantity": x.get("quantity"),
                "unitPrice": {
                    "amount": str(x.get("unitPrice", {}).get("amount", "0")),
                    "symbol": x.get("unitPrice", {}).get("symbol", "ETH"),
                    "decimals": int(x.get("unitPrice", {}).get("decimals", 18)),
                } if x.get("unitPrice") else None,
            }
            for x in item.items
        ]
    }


def _current_step(status: PaymentCommandStatus | PaymentStatus) -> str:
    status_value = _status_value(status)
    if status_value in {"TX_SUBMITTED", "SUBMITTED", "CONFIRMING"}:
        return "RECEIPT_PENDING"
    if status_value == "AWAITING_SIGNATURE":
        return "AWAITING_SIGNATURE"
    if status_value == "CONFIRMED":
        return "PAYMENT_CONFIRMED"
    if status_value == "FAILED":
        return "PAYMENT_FAILED"
    if status_value == "EXPIRED":
        return "PAYMENT_EXPIRED"
    if status_value == "REFUNDED":
        return "PAYMENT_REFUNDED"
    return status_value


def _pending_action(status: PaymentCommandStatus | PaymentStatus) -> str | None:
    status_value = _status_value(status)
    if status_value in {"TX_SUBMITTED", "SUBMITTED", "CONFIRMING"}:
        return "WAIT_FOR_RECEIPT"
    if status_value == "AWAITING_SIGNATURE":
        return "SIGN_PAYMENT"
    if status_value == "CONFIRMED":
        return "WAIT_FOR_STORE_APPROVAL"
    if status_value in {"FAILED", "EXPIRED"}:
        return "WAIT_FOR_COMPENSATION"
    return None


def _crypto_payload(value: Any) -> dict[str, Any]:
    return {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }


def _receipt_payload(receipt: Any | None) -> dict[str, Any] | None:
    if receipt is None:
        return None
    return {
        "transactionHash": str(_attribute_or_key(receipt, "hash")),
        "blockNumber": int(_attribute_or_key(receipt, "block_number")),
        "gasUsed": int(_attribute_or_key(receipt, "gas_used")),
    }


def _attribute_or_key(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        camel_key = _camel_case(key)
        return value[camel_key]
    return getattr(value, key)


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _status_value(status: PaymentCommandStatus | PaymentStatus) -> str:
    enum_value = getattr(status, "value", None)
    return str(enum_value if enum_value is not None else status)


def _payment_error_response(error: PaymentCommandRejected, request_id: str | None) -> ApiResponse:
    status_code = {
        PaymentCommandRejectionReason.PAYMENT_NOT_FOUND: 404,
        PaymentCommandRejectionReason.AUTHORIZATION_NOT_FOUND: 404,
        PaymentCommandRejectionReason.INVALID_STATE: 409,
    }[error.reason]
    return _error_response(error.reason.value, str(error), status_code, request_id)


def _error_response(code: str, message: str, status_code: int, request_id: str | None) -> ApiResponse:
    return json_response(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
        request_id=request_id,
    )


__all__ = ["PaymentsApi"]

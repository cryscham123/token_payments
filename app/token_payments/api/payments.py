"""Framework-neutral payment API handlers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from token_payments.contexts.payment.application import (
    PaymentCommandHandler,
    PaymentCommandRejected,
    PaymentCommandRejectionReason,
    PaymentCommandResult,
    PaymentCommandStatus,
    SubmitTransactionHashCommand,
)
from token_payments.shared.domain import CommandId, OrderId, PaymentId, UserId
from token_payments.contexts.order.domain import TrackingId

from .contracts import ApiRequest, ApiResponse, json_response
from .idempotency import IdempotencyKeyConflict, idempotency_conflict_response, idempotency_key_from_request


class PaymentsApi:
    """Payment API facade that delegates state changes to the payment application handler."""

    def __init__(self, handler: PaymentCommandHandler, tracking_query: Any = None) -> None:
        self._handler = handler
        self._tracking_query = tracking_query

    def submit_transaction_hash(self, request: ApiRequest) -> ApiResponse:
        try:
            body = _request_body(request)
            if "orderId" in body:
                raise ValueError("orderId is not allowed in request body")
            
            tracking_id = TrackingId(_required_text(body, "trackingId"))
            
            user_id_str = None
            if request.auth_context is not None and request.auth_context.user_id is not None:
                user_id_str = request.auth_context.user_id
            elif request.local_auth_fallback_enabled:
                for key, value in request.headers.items():
                    if key.lower() == "x-user-id" and value.strip():
                        user_id_str = value.strip()
                        break

            if user_id_str is None:
                raise ValueError("authenticated session is required")

            user_id = UserId(user_id_str)
            
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


def _request_body(request: ApiRequest) -> Mapping[str, Any]:
    if not isinstance(request.body, Mapping):
        raise ValueError("request body must be an object")
    return request.body


def _required_text(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


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


def _current_step(status: PaymentCommandStatus) -> str:
    if status is PaymentCommandStatus.TX_SUBMITTED:
        return "RECEIPT_PENDING"
    if status is PaymentCommandStatus.AWAITING_SIGNATURE:
        return "AWAITING_SIGNATURE"
    if status is PaymentCommandStatus.CONFIRMED:
        return "PAYMENT_CONFIRMED"
    if status is PaymentCommandStatus.FAILED:
        return "PAYMENT_FAILED"
    if status is PaymentCommandStatus.EXPIRED:
        return "PAYMENT_EXPIRED"
    if status is PaymentCommandStatus.REFUNDED:
        return "PAYMENT_REFUNDED"
    return status.value


def _pending_action(status: PaymentCommandStatus) -> str | None:
    if status is PaymentCommandStatus.TX_SUBMITTED:
        return "WAIT_FOR_RECEIPT"
    if status is PaymentCommandStatus.AWAITING_SIGNATURE:
        return "SIGN_PAYMENT"
    if status is PaymentCommandStatus.CONFIRMED:
        return "WAIT_FOR_STORE_APPROVAL"
    if status in {PaymentCommandStatus.FAILED, PaymentCommandStatus.EXPIRED}:
        return "WAIT_FOR_COMPENSATION"
    return None


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

"""Framework-neutral checkout tracking API handlers."""

from __future__ import annotations

from typing import Any

from token_payments.contexts.order.application import CheckoutTrackingQueryPort, CheckoutTrackingSnapshot
from token_payments.contexts.order.domain import TrackingId
from token_payments.contexts.payment.domain import GasEstimate, TransactionSignatureRequest
from token_payments.shared.domain import Crypto, OrderId

from .contracts import ApiRequest, ApiResponse, json_response


class CheckoutApi:
    """Checkout tracking facade that can be adapted by any HTTP framework."""

    def __init__(self, tracking_query: CheckoutTrackingQueryPort) -> None:
        self._tracking_query = tracking_query

    def get_tracking(self, request: ApiRequest) -> ApiResponse:
        try:
            lookup_kind, lookup_value = _tracking_lookup(request)
            if lookup_kind == "trackingId":
                snapshot = self._tracking_query.get_by_tracking_id(TrackingId(lookup_value))
            else:
                snapshot = self._tracking_query.get_by_order_id(OrderId(lookup_value))
            if snapshot is None:
                return _error_response("CHECKOUT_NOT_FOUND", "checkout tracking record was not found", 404, request.request_id)
            return json_response({"checkout": _tracking_payload(snapshot)}, request_id=request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)


def _tracking_lookup(request: ApiRequest) -> tuple[str, str]:
    tracking_id = _optional_text(request.query.get("trackingId"))
    order_id = _optional_text(request.query.get("orderId"))
    if tracking_id and order_id:
        raise ValueError("provide either trackingId or orderId, not both")
    if tracking_id:
        return ("trackingId", tracking_id)
    if order_id:
        return ("orderId", order_id)

    parts = [part for part in request.path.strip("/").split("/") if part]
    if len(parts) >= 3 and parts[-2] == "tracking":
        return ("trackingId", parts[-1])
    if len(parts) >= 3 and parts[-2] in {"orders", "order"}:
        return ("orderId", parts[-1])
    raise ValueError("trackingId or orderId is required")


def _tracking_payload(snapshot: CheckoutTrackingSnapshot) -> dict[str, Any]:
    payload = {
        "orderId": str(snapshot.order_id),
        "trackingId": str(snapshot.tracking_id),
        "paymentId": str(snapshot.payment_id) if snapshot.payment_id is not None else None,
        "status": snapshot.status,
        "currentStep": snapshot.current_step.value,
        "pendingAction": snapshot.pending_action.value if snapshot.pending_action is not None else None,
        "paymentRequest": _payment_request_payload(snapshot.payment_request),
        "gasEstimate": _gas_estimate_payload(snapshot.gas_estimate),
        "txHash": str(snapshot.tx_hash) if snapshot.tx_hash is not None else None,
        "failureReason": snapshot.failure_reason,
        "updatedAt": snapshot.updated_at.isoformat(),
        "outboxStatus": [
            {
                "messageId": outbox.message_id,
                "name": outbox.name,
                "status": outbox.status.value,
                "updatedAt": outbox.updated_at.isoformat(),
            }
            for outbox in snapshot.outbox_statuses
        ],
    }
    payer_wallet = _payer_wallet_payload(snapshot)
    if payer_wallet is not None:
        payload["payerWallet"] = payer_wallet
    return payload


def _payment_request_payload(request: TransactionSignatureRequest | None) -> dict[str, Any] | None:
    if request is None:
        return None
    payload = {
        "requestId": request.request_id,
        "amount": _crypto_payload(request.amount),
        "to": str(request.to),
        "expiresAt": request.expires_at.isoformat(),
    }
    if request.payment_asset_id is not None:
        payload["paymentAssetId"] = request.payment_asset_id
    if request.transfer_type is not None:
        payload["transferType"] = request.transfer_type
    if request.token_address is not None:
        payload["tokenAddress"] = str(request.token_address)
    if request.amount_minor_units is not None:
        payload["amountMinorUnits"] = str(request.amount_minor_units)
    if request.chain_id is not None:
        payload["chainId"] = request.chain_id
    return payload


def _gas_estimate_payload(gas_estimate: GasEstimate | None) -> dict[str, Any] | None:
    if gas_estimate is None:
        return None
    return {
        "estimatedFee": _crypto_payload(gas_estimate.estimated_fee),
        "gasLimit": gas_estimate.gas_limit,
        "bufferRate": str(gas_estimate.buffer_rate),
        "maxFee": _crypto_payload(gas_estimate.max_fee) if gas_estimate.max_fee is not None else None,
    }


def _crypto_payload(value: Crypto) -> dict[str, Any]:
    return {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }


def _payer_wallet_payload(snapshot: CheckoutTrackingSnapshot) -> dict[str, Any] | None:
    payment = snapshot.payment
    if payment is None or payment.payer_wallet_id is None:
        return None
    address = str(payment.wallet_from)
    return {
        "walletId": str(payment.payer_wallet_id),
        "chainId": payment.chain_network.chain_id,
        "addressPreview": f"{address[:6]}...{address[-4:]}",
    }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("tracking lookup values must be non-empty strings")
    return value.strip()


def _error_response(code: str, message: str, status_code: int, request_id: str | None) -> ApiResponse:
    return json_response(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
        request_id=request_id,
    )


__all__ = ["CheckoutApi"]

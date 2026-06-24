"""Framework-neutral order API handlers."""

from __future__ import annotations

from typing import Any, Mapping

import hashlib

from token_payments.contexts.order.application import (
    CreateOrderCommand,
    CreateOrderItem,
    OrderApplicationError,
    OrderCreationResult,
    OrderErrorCode,
    OrderUseCase,
)
from token_payments.contexts.order.domain import Address, OrderItem
from token_payments.contexts.auth.domain.wallet import WalletId
from token_payments.shared.domain import Crypto

from .contracts import ApiRequest, ApiResponse, json_response
from .idempotency import IdempotencyKeyConflict, idempotency_conflict_response, idempotency_key_from_request


class OrdersApi:
    """Order API facade that can be adapted by any HTTP framework."""

    def __init__(self, use_case: OrderUseCase, *, target_resolver: Any | None = None) -> None:
        self._use_case = use_case
        self._target_resolver = target_resolver

    def create_order(self, request: ApiRequest) -> ApiResponse:
        try:
            body = _request_body(request)
            store_id, items = self._resolve_order_targets(body)
            result = self._use_case.createOrder(
                CreateOrderCommand(
                    authenticated_user_id=_authenticated_user_id(request),
                    store_id=store_id,
                    delivery_address=_address_from_body(_required_mapping(body, "deliveryAddress")),
                    items=items,
                    requested_at=request.received_at,
                    causation_id=idempotency_key_from_request(request, body, fallback=request.request_id),
                    wallet_id=_optional_wallet_id(body, "walletId"),
                    payment_asset_id=_optional_text(body, "paymentAssetId"),
                )
            )
            return json_response(_order_creation_payload(result), status_code=201, request_id=request.request_id)
        except IdempotencyKeyConflict as exc:
            return idempotency_conflict_response(exc, request.request_id)
        except (OrderApplicationError, ValueError) as exc:
            return _error_response(_coerce_order_error(exc), request.request_id)

    def _resolve_order_targets(self, body: Mapping[str, Any]) -> tuple[str, tuple[CreateOrderItem, ...]]:
        """Resolve internal store/product UUIDs, accepting public ids that the public catalog
        exposes (internal UUIDs are redacted from public reads, so the client only knows the
        public ids). Explicit UUIDs are used as-is for backward compatibility."""
        explicit_store = _optional_text(body, "storeId")
        public_store = _optional_text(body, "publicStoreId")
        raw_items = _raw_order_items(body)
        public_product_ids = [
            public_id
            for raw_item in raw_items
            if not _optional_text(raw_item, "productId") and (public_id := _optional_text(raw_item, "publicProductId"))
        ]

        resolved_store_id: str | None = None
        resolved_products: Mapping[str, str] = {}
        if public_store is not None and (explicit_store is None or public_product_ids):
            if self._target_resolver is None:
                raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, "public id resolution is not available")
            resolved_store_id, resolved_products = self._target_resolver.resolve(public_store, public_product_ids)

        store_id = explicit_store or resolved_store_id
        if not store_id:
            raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, "storeId or publicStoreId is required")

        items: list[CreateOrderItem] = []
        for raw_item in raw_items:
            explicit_product = _optional_text(raw_item, "productId")
            public_product = _optional_text(raw_item, "publicProductId")
            product_id = explicit_product or (resolved_products.get(public_product) if public_product else None)
            if not product_id:
                raise OrderApplicationError(
                    OrderErrorCode.VALIDATION_ERROR,
                    "each item requires productId or a resolvable publicProductId",
                )
            items.append(
                CreateOrderItem(
                    product_id=product_id,
                    quantity=_required_int(raw_item, "quantity"),
                    public_variant_id=_optional_text(raw_item, "publicVariantId") or _optional_text(raw_item, "public_variant_id"),
                    selected_options=_optional_mapping(raw_item, "selectedOptions") or _optional_mapping(raw_item, "selected_options") or {},
                    media=tuple(_raw_media(raw_item.get("media"))),
                )
            )
        return store_id, tuple(items)


def _order_creation_payload(result: OrderCreationResult) -> dict[str, Any]:
    order = result.order
    digest = hashlib.blake2s(str(order.store_id).encode("ascii"), digest_size=10).hexdigest()
    public_store_id = f"st_{digest}"
    return {
        "order": {
            "orderId": str(order.order_id),
            "trackingId": str(order.tracking_id),
            "publicStoreId": public_store_id,
            "status": order.status.value,
            "deliveryAddress": {
                "id": order.delivery_address.id,
                "street": order.delivery_address.street,
            },
            "totalAmount": _crypto_payload(result.total_amount),
            "items": [_item_payload(item) for item in order.items],
        }
    }


def _item_payload(item: OrderItem) -> dict[str, Any]:
    snapshot = item.product_snapshot
    payload = {
        "orderItemId": str(item.order_item_id),
        "productId": str(snapshot.product_id),
        "name": snapshot.name,
        "quantity": item.quantity,
        "unitPrice": _crypto_payload(snapshot.price),
        "subTotal": _crypto_payload(item.sub_total),
    }
    public_variant_id = getattr(snapshot, "public_variant_id", None)
    selected_options = getattr(snapshot, "selected_options", None)
    if public_variant_id is not None:
        payload["publicVariantId"] = public_variant_id
    if selected_options:
        payload["selectedOptions"] = dict(selected_options)
    return payload


def _crypto_payload(value: Crypto) -> dict[str, Any]:
    return {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }


def _request_body(request: ApiRequest) -> Mapping[str, Any]:
    if not isinstance(request.body, Mapping):
        raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, "request body must be an object")
    return request.body


def _authenticated_user_id(request: ApiRequest) -> str:
    if request.auth_context is not None and request.auth_context.user_id is not None:
        return request.auth_context.user_id
    if request.local_auth_fallback_enabled:
        for key, value in request.headers.items():
            if key.lower() == "x-user-id" and value.strip():
                return value.strip()
    raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, "X-User-Id header is required")


def _address_from_body(body: Mapping[str, Any]) -> Address:
    return Address(
        id=_required_text(body, "id"),
        street=_required_text(body, "street"),
    )


def _raw_order_items(body: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw_items = body.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, "items must contain at least one item")
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, "items must contain objects")
    return tuple(raw_items)


def _required_mapping(body: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = body.get(key)
    if not isinstance(value, Mapping):
        raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, f"{key} must be an object")
    return value


def _optional_mapping(body: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, f"{key} must be an object")
    return value


def _required_text(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, f"{key} is required")
    return value.strip()


def _optional_text(body: Mapping[str, Any], key: str) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, f"{key} must be a non-empty string")
    return value.strip()


def _optional_wallet_id(body: Mapping[str, Any], key: str) -> WalletId | None:
    value = _optional_text(body, key)
    return WalletId(value) if value is not None else None


def _required_int(body: Mapping[str, Any], key: str) -> int:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, f"{key} must be an integer")
    return value


def _error_response(error: OrderApplicationError, request_id: str | None) -> ApiResponse:
    return json_response(
        {
            "error": {
                "code": error.code.value,
                "message": str(error),
            }
        },
        status_code=_status_for_error(error.code),
        request_id=request_id,
    )


def _status_for_error(code: OrderErrorCode) -> int:
    return {
        OrderErrorCode.CUSTOMER_NOT_FOUND: 404,
        OrderErrorCode.STORE_NOT_FOUND: 404,
        OrderErrorCode.VALIDATION_ERROR: 400,
        OrderErrorCode.OPEN_ORDER_EXISTS: 409,
    }[code]


def _coerce_order_error(error: OrderApplicationError | ValueError) -> OrderApplicationError:
    if isinstance(error, OrderApplicationError):
        return error
    return OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, _public_order_error_message(str(error)))


def _public_order_error_message(message: str) -> str:
    lower = message.lower()
    if (
        ("eth_estimategas" in lower or "vm exception" in lower)
        and (
            "insufficient balance" in lower
            or "exceeds balance" in lower
            or "transfer amount exceeds balance" in lower
        )
    ):
        return "payment token balance is insufficient"
    if "json-rpc" in lower and "insufficient funds" in lower:
        return "payment gas balance is insufficient"
    return message


def _raw_media(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


__all__ = ["OrdersApi"]

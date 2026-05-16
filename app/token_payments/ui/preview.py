"""Local-only UI preview fixtures and rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .mappers import checkout_view_from_api_payload, operator_dashboard_from_api_payload
from .renderers import render_checkout_page, render_operator_dashboard


UI_PREVIEW_CONTRACT = "CommandDispatchResult.details.preview"
DEFAULT_UI_PREVIEW_VIEW = "customer"
AVAILABLE_UI_PREVIEW_VIEWS = ("customer", "operator")
UNKNOWN_UI_PREVIEW_ERROR = "UNKNOWN_UI_PREVIEW_VIEW"


@dataclass(frozen=True)
class UiPreviewSample:
    name: str
    view: str
    html: str
    content_type: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "view": self.view,
            "contentType": self.content_type,
            "html": self.html,
        }


class UnknownUiPreviewView(ValueError):
    """Raised when a preview route selector is not known."""

    def __init__(self, view: str) -> None:
        self.view = view
        super().__init__(f"unknown UI preview view: {view}")

    def to_error(self) -> dict[str, object]:
        return {
            "code": UNKNOWN_UI_PREVIEW_ERROR,
            "view": self.view,
            "availableViews": list(AVAILABLE_UI_PREVIEW_VIEWS),
        }


def render_ui_preview(view: str | None = None) -> dict[str, object]:
    route = _normalize_view(view)
    if route == "customer":
        samples = _customer_preview_samples()
    elif route == "operator":
        samples = (_operator_preview_sample(),)
    else:
        raise UnknownUiPreviewView(route)

    primary = samples[0]
    return {
        "contract": UI_PREVIEW_CONTRACT,
        "view": route,
        "route": route,
        "contentType": primary.content_type,
        "html": primary.html,
        "samples": [sample.to_dict() for sample in samples],
    }


def _normalize_view(view: str | None) -> str:
    if view is None or not view.strip():
        return DEFAULT_UI_PREVIEW_VIEW
    normalized = view.strip().lower()
    aliases = {
        "checkout": "customer",
        "customer-checkout": "customer",
        "dashboard": "operator",
        "operator-dashboard": "operator",
    }
    return aliases.get(normalized, normalized)


def _customer_preview_samples() -> tuple[UiPreviewSample, ...]:
    return (
        _customer_sample("customer-happy-path", _customer_happy_path_payload()),
        _customer_sample("customer-tx-submitted-pending-receipt", _customer_pending_receipt_payload()),
        _customer_sample("customer-payment-failed-compensation", _customer_payment_failed_payload()),
        _customer_sample("customer-payment-expired-compensation", _customer_payment_expired_payload()),
    )


def _customer_sample(name: str, payload: Mapping[str, Any]) -> UiPreviewSample:
    rendered = render_checkout_page(
        checkout_view_from_api_payload(
            payload,
            wallet_address="0x1111111111111111111111111111111111111111",
            network_name="Sepolia",
        )
    )
    return UiPreviewSample(name=name, view="customer", html=rendered.html, content_type=rendered.content_type)


def _base_customer_payload() -> dict[str, object]:
    return {
        "order": {
            "orderId": "order-preview-001",
            "trackingId": "tracking-preview-001",
            "status": "PENDING",
            "items": [
                {
                    "orderItemId": "item-preview-001",
                    "productId": "product-ledger-mug",
                    "name": "Ledger Mug <sample>",
                    "quantity": 2,
                    "unitPrice": _money("12.50", "USDC", decimals=6),
                    "subTotal": _money("25.00", "USDC", decimals=6),
                }
            ],
        },
        "checkout": {
            "orderId": "order-preview-001",
            "trackingId": "tracking-preview-001",
            "status": "AWAITING_SIGNATURE",
            "currentStep": "AWAITING_SIGNATURE",
            "pendingAction": "SIGN_PAYMENT",
            "paymentExpiresIn": "00:12:00",
            "paymentRequest": {
                "requestId": "payment-request-preview-001",
                "amount": _money("25.00", "USDC", decimals=6),
                "to": "0x2222222222222222222222222222222222222222",
                "expiresAt": "2026-05-10T10:15:00+00:00",
            },
            "gasEstimate": {
                "estimatedFee": _money("0.0100", "ETH", decimals=18),
                "gasLimit": 21000,
                "bufferRate": "0.10",
                "maxFee": _money("0.011000", "ETH", decimals=18),
            },
            "txHash": None,
            "txHashStatus": None,
            "failureReason": None,
            "updatedAt": "2026-05-10T10:08:00+00:00",
            "actions": [
                {
                    "id": "connect-wallet",
                    "label": "Connect Wallet",
                    "kind": "secondary",
                    "enabled": True,
                    "tooltip": "Connect wallet address",
                    "ariaLabel": "Connect wallet address",
                },
                {
                    "id": "sign-payment",
                    "label": "Sign Payment",
                    "kind": "primary",
                    "enabled": True,
                    "tooltip": "Request MetaMask payment signature",
                    "ariaLabel": "Request MetaMask payment signature",
                },
                {
                    "id": "submit-tx-hash",
                    "label": "Submit txHash",
                    "kind": "primary",
                    "enabled": False,
                    "tooltip": "Submit signed transaction hash",
                    "ariaLabel": "Submit signed transaction hash",
                    "disabledReason": "Waiting for wallet signature",
                },
                {
                    "id": "track-order",
                    "label": "Track Order",
                    "kind": "secondary",
                    "enabled": True,
                    "tooltip": "Track checkout status",
                    "ariaLabel": "Track checkout status",
                },
            ],
            "timeline": _timeline(
                payment_status="AWAITING_SIGNATURE",
                payment_detail="waiting for wallet signature",
                store_status="PENDING",
                store_detail="waiting for payment confirmation",
                completed_status="PENDING",
                completed_detail="waiting for store approval",
            ),
        },
    }


def _customer_happy_path_payload() -> dict[str, object]:
    payload = _base_customer_payload()
    checkout = _checkout(payload)
    checkout["status"] = "APPROVED"
    checkout["currentStep"] = "ORDER_APPROVED"
    checkout["pendingAction"] = "NONE"
    checkout["txHash"] = "0x" + "ab" * 32
    checkout["txHashStatus"] = "CONFIRMED"
    checkout["updatedAt"] = "2026-05-10T10:12:00+00:00"
    checkout["timeline"] = _timeline(
        tx_status="CONFIRMED",
        payment_status="CONFIRMED",
        payment_detail="PaymentConfirmedEvent",
        store_status="APPROVED",
        store_detail="OrderApprovedEvent",
        completed_status="COMPLETED",
        completed_detail="checkout completed",
    )
    return payload


def _customer_pending_receipt_payload() -> dict[str, object]:
    payload = _base_customer_payload()
    checkout = _checkout(payload)
    checkout["status"] = "SUBMITTED"
    checkout["currentStep"] = "TX_SUBMITTED"
    checkout["pendingAction"] = "WAIT_FOR_RECEIPT"
    checkout["txHash"] = "0x" + "bc" * 32
    checkout["txHashStatus"] = "SUBMITTED"
    checkout["paymentExpiresIn"] = "00:08:30"
    checkout["timeline"] = _timeline(
        tx_status="SUBMITTED",
        payment_status="PENDING",
        payment_detail="waiting for receipt",
        store_status="PENDING",
        store_detail="waiting for payment confirmation",
        completed_status="PENDING",
        completed_detail="waiting for store approval",
    )
    return payload


def _customer_payment_failed_payload() -> dict[str, object]:
    payload = _base_customer_payload()
    checkout = _checkout(payload)
    checkout["status"] = "FAILED"
    checkout["currentStep"] = "PAYMENT_FAILED"
    checkout["pendingAction"] = "WAIT_FOR_COMPENSATION"
    checkout["txHash"] = "0x" + "cd" * 32
    checkout["txHashStatus"] = "FAILED"
    checkout["failureReason"] = "receipt <reverted>"
    checkout["paymentExpiresIn"] = "00:00:00"
    checkout["timeline"] = _timeline(
        tx_status="SUBMITTED",
        payment_status="FAILED",
        payment_detail="PaymentFailedEvent: receipt <reverted>",
        payment_compensation="ReleaseInventoryCommand PENDING; CancelOrderCommand PENDING",
        store_status="PENDING",
        store_detail="blocked by failed payment",
        completed_status="PENDING",
        completed_detail="waiting for compensation",
    )
    return payload


def _customer_payment_expired_payload() -> dict[str, object]:
    payload = _base_customer_payload()
    checkout = _checkout(payload)
    checkout["status"] = "EXPIRED"
    checkout["currentStep"] = "PAYMENT_EXPIRED"
    checkout["pendingAction"] = "WAIT_FOR_COMPENSATION"
    checkout["txHash"] = None
    checkout["txHashStatus"] = None
    checkout["failureReason"] = "signature expired before txHash submission"
    checkout["paymentExpiresIn"] = "00:00:00"
    checkout["timeline"] = _timeline(
        tx_status="PENDING",
        payment_status="EXPIRED",
        payment_detail="PaymentExpiredEvent: signature expired before txHash submission",
        payment_compensation="ReleaseInventoryCommand PENDING; CancelOrderCommand PENDING",
        store_status="PENDING",
        store_detail="blocked by expired payment",
        completed_status="PENDING",
        completed_detail="waiting for compensation",
    )
    return payload


def _checkout(payload: dict[str, object]) -> dict[str, object]:
    checkout = payload["checkout"]
    if not isinstance(checkout, dict):
        raise ValueError("customer preview checkout payload must be a mapping")
    return checkout


def _timeline(
    *,
    tx_status: str = "PENDING",
    payment_status: str,
    payment_detail: str,
    store_status: str,
    store_detail: str,
    completed_status: str,
    completed_detail: str,
    payment_compensation: str | None = None,
) -> list[dict[str, object]]:
    payment_item: dict[str, object] = {
        "stage": "PAYMENT_CONFIRMED",
        "label": "Payment confirmation",
        "status": payment_status,
        "detail": payment_detail,
        "messageId": "payment-preview-message",
    }
    if payment_compensation:
        payment_item["compensationStatus"] = payment_compensation

    return [
        {
            "stage": "ORDER_CREATED",
            "label": "Order created",
            "status": "CONFIRMED",
            "occurredAt": "2026-05-10T10:00:00+00:00",
            "messageId": "order-created-preview-message",
        },
        {
            "stage": "INVENTORY_RESERVED",
            "label": "Inventory reserved",
            "status": "CONFIRMED",
            "occurredAt": "2026-05-10T10:02:00+00:00",
            "commandId": "order-preview-001:ReserveInventory",
        },
        {
            "stage": "AWAITING_SIGNATURE",
            "label": "Payment signature",
            "status": "CONFIRMED" if tx_status != "PENDING" or payment_status in {"CONFIRMED", "FAILED"} else "AWAITING_SIGNATURE",
            "occurredAt": "2026-05-10T10:03:00+00:00",
            "messageId": "payment-started-preview-message",
        },
        {
            "stage": "TX_SUBMITTED",
            "label": "tx submitted",
            "status": tx_status,
            "occurredAt": "2026-05-10T10:05:00+00:00",
            "messageId": "payment-submitted-preview-message",
        },
        payment_item,
        {
            "stage": "STORE_APPROVAL",
            "label": "Store approval",
            "status": store_status,
            "detail": store_detail,
        },
        {
            "stage": "COMPLETED",
            "label": "Completed",
            "status": completed_status,
            "detail": completed_detail,
        },
    ]


def _operator_preview_sample() -> UiPreviewSample:
    rendered = render_operator_dashboard(
        operator_dashboard_from_api_payload(
            _operator_payload(),
            filters={
                "contexts": ("orders", "payments", "inventory", "store-approvals", "outbox", "workers", "errors"),
                "statuses": ("APPROVED", "FAILED", "UNAVAILABLE"),
                "chainId": 11155111,
                "storeId": "store-preview-001",
                "failedOnly": False,
                "retryCandidatesOnly": False,
                "sort": "-updatedAt",
            },
            detail={
                "title": "Outbox retry candidate",
                "aggregateId": "order-preview-expired",
                "latestEvent": "PaymentExpiredEvent",
                "outboxStatus": "FAILED",
                "processedMessages": ("payment-expired-preview-message",),
                "processedCommands": ("ReleaseInventoryCommand", "CancelOrderCommand"),
                "retryCandidate": True,
            },
        )
    )
    return UiPreviewSample(
        name="operator-dashboard-mixed-status",
        view="operator",
        html=rendered.html,
        content_type=rendered.content_type,
    )


def _operator_payload() -> dict[str, object]:
    return {
        "orders": [
            {
                "orderId": "order-preview-approved",
                "trackingId": "tracking-preview-approved",
                "customerId": "customer-preview-001",
                "storeId": "store-preview-001",
                "status": "APPROVED",
                "paymentId": "payment-preview-approved",
                "paymentStatus": "CONFIRMED",
                "totalAmount": _money("25.00", "USDC", decimals=6),
                "failureReason": None,
                "latestEvent": "OrderApprovedEvent normal approved order",
                "createdAt": "2026-05-10T09:45:00+00:00",
                "updatedAt": "2026-05-10T10:12:00+00:00",
            },
            {
                "orderId": "order-preview-expired",
                "trackingId": "tracking-preview-expired",
                "customerId": "customer-preview-002",
                "storeId": "store-preview-001",
                "status": "CANCELLING",
                "paymentId": "payment-preview-expired",
                "paymentStatus": "EXPIRED",
                "totalAmount": _money("18.00", "USDC", decimals=6),
                "failureReason": "signature expired before txHash submission",
                "latestEvent": "PaymentExpiredEvent",
                "createdAt": "2026-05-10T09:40:00+00:00",
                "updatedAt": "2026-05-10T10:16:00+00:00",
            },
        ],
        "payments": [
            {
                "paymentId": "payment-preview-approved",
                "orderId": "order-preview-approved",
                "customerId": "customer-preview-001",
                "status": "CONFIRMED",
                "amount": _money("25.00", "USDC", decimals=6),
                "gasEstimate": _money("0.0100", "ETH", decimals=18),
                "chain": {"chainId": 11155111, "name": "Sepolia"},
                "walletFrom": "0x1111111111111111111111111111111111111111",
                "walletTo": "0x2222222222222222222222222222222222222222",
                "txHash": "0x" + "ab" * 32,
                "failureReason": None,
                "expiresAt": "2026-05-10T10:15:00+00:00",
                "updatedAt": "2026-05-10T10:11:00+00:00",
            },
            {
                "paymentId": "payment-preview-expired",
                "orderId": "order-preview-expired",
                "customerId": "customer-preview-002",
                "status": "EXPIRED",
                "amount": _money("18.00", "USDC", decimals=6),
                "gasEstimate": _money("0.0090", "ETH", decimals=18),
                "chain": {"chainId": 11155111, "name": "Sepolia"},
                "walletFrom": "0x4444444444444444444444444444444444444444",
                "walletTo": "0x2222222222222222222222222222222222222222",
                "txHash": None,
                "failureReason": "signature expired before txHash submission",
                "expiresAt": "2026-05-10T10:14:00+00:00",
                "updatedAt": "2026-05-10T10:16:00+00:00",
            },
        ],
        "inventory": [
            {
                "reservationId": "reservation-preview-approved",
                "orderId": "order-preview-approved",
                "productId": "product-ledger-mug",
                "storeId": "store-preview-001",
                "status": "CONFIRMED",
                "reservedQty": 2,
                "availableStock": 8,
                "latestEvent": "InventoryConfirmedEvent",
                "updatedAt": "2026-05-10T10:10:00+00:00",
            }
        ],
        "storeApprovals": [
            {
                "approvalId": "approval-preview-approved",
                "orderId": "order-preview-approved",
                "storeId": "store-preview-001",
                "status": "APPROVED",
                "totalAmount": _money("25.00", "USDC", decimals=6),
                "latestEvent": "OrderApprovedEvent",
                "updatedAt": "2026-05-10T10:12:00+00:00",
            }
        ],
        "outbox": [
            {
                "messageId": "outbox-preview-failed",
                "kind": "EVENT",
                "name": "PaymentExpiredEvent",
                "topic": "payment.events",
                "key": "order-preview-expired",
                "status": "FAILED",
                "failureCount": 3,
                "lastError": "broker unavailable",
                "retryCandidate": True,
                "retryReason": "FAILED rows are reclaimed by the outbox relay retry policy",
                "createdAt": "2026-05-10T10:14:00+00:00",
                "updatedAt": "2026-05-10T10:17:00+00:00",
            }
        ],
        "replayMessages": [
            {
                "messageId": "kafka:payments.events:0:81",
                "kind": "EVENT",
                "reason": "operator dashboard replay requested after handler fix",
            }
        ],
        "workers": [
            {
                "component": "outbox-relay",
                "state": "UNAVAILABLE",
                "checkedAt": "2026-05-10T10:18:00+00:00",
                "details": {"lastBatchFailed": 1, "nextRetryBatchSize": 10},
            },
            {
                "component": "payment-timeout",
                "state": "OK",
                "checkedAt": "2026-05-10T10:18:00+00:00",
                "details": {"expiredCandidates": 1},
            },
        ],
        "errors": [
            {
                "context": "outbox",
                "aggregateId": "outbox-preview-failed",
                "code": "FAILED",
                "message": "broker unavailable",
                "createdAt": "2026-05-10T10:17:00+00:00",
            }
        ],
    }


def _money(amount: str, symbol: str, *, decimals: int) -> dict[str, object]:
    return {
        "amount": amount,
        "symbol": symbol,
        "chainId": 11155111,
        "tokenAddress": "0x3333333333333333333333333333333333333333" if symbol == "USDC" else None,
        "decimals": decimals,
    }


__all__ = [
    "AVAILABLE_UI_PREVIEW_VIEWS",
    "DEFAULT_UI_PREVIEW_VIEW",
    "UNKNOWN_UI_PREVIEW_ERROR",
    "UI_PREVIEW_CONTRACT",
    "UiPreviewSample",
    "UnknownUiPreviewView",
    "render_ui_preview",
]

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


ORDER_ID = 'order-<script>alert("order")</script>'
PAYMENT_ID = "payment-018f33aa9e6d73d89dc347d6cdcc6d16"
STORE_ID = "store-018f33aa9e6d73d89dc347d6cdcc6d15"
RESERVATION_ID = "reservation-018f33aa9e6d73d89dc347d6cdcc6d20"
APPROVAL_ID = "approval-018f33aa9e6d73d89dc347d6cdcc6d21"
MESSAGE_ID = "message-018f33aa9e6d73d89dc347d6cdcc6d22"
TX_HASH = "0x" + "cd" * 32


def test_operator_dashboard_maps_filters_summary_rows_and_detail_panel() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload

    view = operator_dashboard_from_api_payload(
        _operator_fixture(),
        filters={
            "contexts": ("orders", "payments", "inventory", "store-approvals", "outbox", "workers", "errors"),
            "statuses": ("FAILED", "AWAITING_SIGNATURE"),
            "chainId": 11155111,
            "storeId": STORE_ID,
            "createdAtFrom": "2026-05-10T09:00:00+00:00",
            "createdAtTo": "2026-05-10T11:00:00+00:00",
            "failedOnly": True,
            "retryCandidatesOnly": True,
            "sort": "-createdAt",
        },
        detail=_detail_fixture(),
    )

    assert view.filters.contexts == (
        "orders",
        "payments",
        "inventory",
        "store-approvals",
        "outbox",
        "workers",
        "errors",
    )
    assert view.filters.statuses == ("FAILED", "AWAITING_SIGNATURE")
    assert view.filters.chain_id == 11155111
    assert view.filters.store_id == STORE_ID
    assert view.filters.created_at_from == "2026-05-10T09:00:00+00:00"
    assert view.filters.created_at_to == "2026-05-10T11:00:00+00:00"
    assert view.filters.failed_only is True
    assert view.filters.retry_candidates_only is True

    assert [item.value for item in view.summary] == [1, 1, 1]
    assert [item.key for item in view.summary] == ["retry-candidates", "failed-outbox", "unhealthy-workers"]
    assert view.orders[0].status.label == "CANCELLED"
    assert view.payments[0].status.label == "AWAITING_SIGNATURE"
    assert view.inventory[0].quantity == 2
    assert view.store_approvals[0].status.label == "REJECTED"
    assert view.outbox[0].retry_candidate is True
    assert view.workers[0].status.label == "UNAVAILABLE"
    assert view.errors[0].failure_reason == 'receipt <reverted> & needs "operator" review'
    assert view.detail is not None
    assert view.detail.fields["aggregateId"] == ORDER_ID
    assert view.detail.fields["outboxStatus"] == "FAILED"
    assert view.detail.fields["processedMessages"] == ("message-1", "message-2")
    assert view.detail.fields["processedCommands"] == ("CancelOrderCommand", "ReleaseInventoryCommand")
    assert view.detail.fields["errorReason"] == 'receipt <reverted> & needs "operator" review'


def test_operator_dashboard_html_renders_read_only_dense_status_surface_and_copy_affordances() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload, render_operator_dashboard

    view = operator_dashboard_from_api_payload(
        _operator_fixture(),
        filters={
            "contexts": "orders,payments,inventory,store-approvals,outbox,workers,errors",
            "statuses": "FAILED,AWAITING_SIGNATURE",
            "chain_id": 11155111,
            "store_id": STORE_ID,
            "created_at_from": "2026-05-10T09:00:00+00:00",
            "created_at_to": "2026-05-10T11:00:00+00:00",
            "failed_only": True,
            "retry_candidates_only": True,
        },
        detail=_detail_fixture(),
    )
    html = render_operator_dashboard(view).html

    assert '<main class="tp-shell tp-operator" data-view="operator">' in html
    assert "Operator Dashboard" in html
    assert "orders, payments, inventory, store-approvals, outbox, workers, errors" in html
    assert "Created from" in html
    assert "2026-05-10T09:00:00+00:00" in html
    assert "Retry candidates" in html
    assert "Failed outbox" in html
    assert "Unhealthy workers" in html
    assert '<span class="tp-badge" data-tone="danger">FAILED</span>' in html
    assert '<span class="tp-badge" data-tone="pending">AWAITING_SIGNATURE</span>' in html
    assert '<span class="tp-badge" data-tone="danger">UNAVAILABLE</span>' in html
    assert "InventoryReservedEvent" in html
    assert "OrderRejectedEvent" in html
    assert "Retry candidate" in html
    assert "read-only" in html

    assert "25.00 USDC" in html
    assert "0.0100 ETH" in html
    assert "<td class=\"tp-num\">2</td>" in html
    assert 'class="tp-mono tp-copy-value"' in html
    assert f'data-copy-value="{TX_HASH}"' in html
    assert "Copy tx hash" in html
    assert "data-action-id" not in html
    assert "Retry Refund" not in html
    assert "Execute retry" not in html


def test_operator_dashboard_empty_state_and_healthy_worker_badge() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload, render_operator_dashboard

    view = operator_dashboard_from_api_payload(
        {
            "orders": [],
            "payments": [],
            "inventory": [],
            "storeApprovals": [],
            "outbox": [],
            "workers": [
                {
                    "component": "payment-timeout",
                    "state": "OK",
                    "checkedAt": "2026-05-10T10:03:00+00:00",
                    "details": {"expiredCandidates": 0},
                }
            ],
            "errors": [],
        }
    )
    html = render_operator_dashboard(view).html

    assert "No operator rows match these filters" in html
    assert '<span class="tp-badge" data-tone="success">OK</span>' in html
    assert "payment-timeout" in html
    assert "expiredCandidates=0" in html
    assert "Unhealthy workers" in html
    assert ">0<" in html


def test_operator_dashboard_escapes_html_and_redacts_secret_like_detail_values() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload, render_operator_dashboard

    fixture = _operator_fixture()
    fixture["workers"][0]["details"]["privateKey"] = "0x" + "11" * 32
    view = operator_dashboard_from_api_payload(
        fixture,
        detail={
            "aggregateId": ORDER_ID,
            "latestEvent": 'PaymentFailedEvent<script>alert("event")</script>',
            "outboxStatus": "FAILED",
            "processedMessages": ("message-1",),
            "processedCommands": ("CancelOrderCommand",),
            "errorReason": 'receipt <reverted> & needs "operator" review',
            "private_key": "do-not-render",
        },
    )
    html = render_operator_dashboard(view).html

    assert "<script>" not in html
    assert "alert(&quot;order&quot;)" in html
    assert "alert(&quot;event&quot;)" in html
    assert "receipt &lt;reverted&gt; &amp; needs &quot;operator&quot; review" in html
    assert "privateKey=REDACTED" in html
    assert "private_key" in html
    assert "do-not-render" not in html
    assert "REDACTED" in html


def _operator_fixture() -> dict[str, object]:
    return {
        "orders": [
            {
                "orderId": ORDER_ID,
                "trackingId": "tracking-123",
                "customerId": "customer-123",
                "storeId": STORE_ID,
                "status": "CANCELLED",
                "paymentId": PAYMENT_ID,
                "paymentStatus": "FAILED",
                "totalAmount": _money("25.00", "USDC", decimals=6),
                "failureReason": 'receipt <reverted> & needs "operator" review',
                "latestEvent": "PaymentFailedEvent",
                "createdAt": "2026-05-10T09:45:00+00:00",
                "updatedAt": "2026-05-10T10:00:00+00:00",
            }
        ],
        "payments": [
            {
                "paymentId": PAYMENT_ID,
                "orderId": ORDER_ID,
                "customerId": "customer-123",
                "status": "AWAITING_SIGNATURE",
                "amount": _money("25.00", "USDC", decimals=6),
                "gasEstimate": _money("0.0100", "ETH", decimals=18),
                "chain": {"chainId": 11155111, "name": "Sepolia"},
                "walletFrom": "0x1111111111111111111111111111111111111111",
                "walletTo": "0x2222222222222222222222222222222222222222",
                "txHash": TX_HASH,
                "failureReason": None,
                "expiresAt": "2026-05-10T10:15:00+00:00",
                "createdAt": "2026-05-10T09:47:00+00:00",
                "updatedAt": "2026-05-10T10:01:00+00:00",
            }
        ],
        "inventory": [
            {
                "reservationId": RESERVATION_ID,
                "orderId": ORDER_ID,
                "productId": "product-ledger-mug",
                "storeId": STORE_ID,
                "status": "CONFIRMED",
                "reservedQty": 2,
                "availableStock": 8,
                "latestEvent": "InventoryReservedEvent",
                "updatedAt": "2026-05-10T10:02:00+00:00",
            }
        ],
        "storeApprovals": [
            {
                "approvalId": APPROVAL_ID,
                "orderId": ORDER_ID,
                "storeId": STORE_ID,
                "status": "REJECTED",
                "totalAmount": _money("25.00", "USDC", decimals=6),
                "latestEvent": "OrderRejectedEvent",
                "rejectionReasons": ("price changed",),
                "updatedAt": "2026-05-10T10:03:00+00:00",
            }
        ],
        "outbox": [
            {
                "messageId": MESSAGE_ID,
                "kind": "EVENT",
                "name": "PaymentFailedEvent",
                "topic": "payment.events",
                "key": ORDER_ID,
                "status": "FAILED",
                "failureCount": 2,
                "lastError": "broker unavailable",
                "retryCandidate": True,
                "retryReason": "FAILED rows are reclaimed by the outbox relay retry policy",
                "createdAt": "2026-05-10T09:58:00+00:00",
                "updatedAt": "2026-05-10T10:04:00+00:00",
            }
        ],
        "workers": [
            {
                "component": "outbox-relay",
                "state": "UNAVAILABLE",
                "checkedAt": "2026-05-10T10:05:00+00:00",
                "details": {"lastBatchFailed": 1},
            }
        ],
        "errors": [
            {
                "context": "payment",
                "aggregateId": PAYMENT_ID,
                "code": "FAILED",
                "message": 'receipt <reverted> & needs "operator" review',
                "createdAt": "2026-05-10T10:06:00+00:00",
            }
        ],
    }


def _detail_fixture() -> dict[str, object]:
    return {
        "aggregateId": ORDER_ID,
        "latestEvent": "PaymentFailedEvent",
        "outboxStatus": "FAILED",
        "processedMessages": ("message-1", "message-2"),
        "processedCommands": ("CancelOrderCommand", "ReleaseInventoryCommand"),
        "errorReason": 'receipt <reverted> & needs "operator" review',
        "retryCandidate": True,
    }


def _money(amount: str, symbol: str, *, decimals: int) -> dict[str, object]:
    return {
        "amount": amount,
        "symbol": symbol,
        "chainId": 11155111,
        "tokenAddress": "0x3333333333333333333333333333333333333333" if symbol == "USDC" else None,
        "decimals": decimals,
    }

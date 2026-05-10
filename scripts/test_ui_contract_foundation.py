from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


UI_EXPORTS = {
    "CheckoutTimelineItem",
    "CheckoutViewModel",
    "CopyToken",
    "GasEstimateView",
    "MoneyView",
    "OperatorDashboardViewModel",
    "OperatorDetailView",
    "OperatorFilterState",
    "OperatorTableRow",
    "RenderedHtml",
    "StatusBadge",
    "checkout_view_from_api_payload",
    "operator_dashboard_from_api_payload",
    "render_checkout_page",
    "render_operator_dashboard",
    "render_status_badge",
}

FORBIDDEN_UI_IMPORT_FRAGMENTS = (
    ".adapter",
    "postgres",
    "kafka",
    "blockchain",
    "web3",
    "psycopg",
    "requests",
    "token_payments.runtime.observability",
)


def test_ui_package_exports_framework_neutral_render_contracts() -> None:
    ui = importlib.import_module("token_payments.ui")
    exported = set(getattr(ui, "__all__", ()))

    assert UI_EXPORTS <= exported
    assert all(hasattr(ui, name) for name in UI_EXPORTS)


def test_checkout_payload_maps_to_view_model_and_escaped_html_foundation() -> None:
    from token_payments.ui import checkout_view_from_api_payload, render_checkout_page

    view = checkout_view_from_api_payload(
        {
            "checkout": {
                "orderId": 'order-<script>alert("x")</script>',
                "trackingId": "track-123",
                "status": "AWAITING_SIGNATURE",
                "currentStep": "AWAITING_SIGNATURE",
                "pendingAction": "SIGN_PAYMENT",
                "paymentRequest": {
                    "requestId": "request-123",
                    "amount": {
                        "amount": "1.25",
                        "symbol": "USDC",
                        "chainId": 11155111,
                        "tokenAddress": "0x3333333333333333333333333333333333333333",
                        "decimals": 6,
                    },
                    "to": "0x2222222222222222222222222222222222222222",
                    "expiresAt": "2026-05-10T10:15:00+00:00",
                },
                "gasEstimate": {
                    "estimatedFee": {
                        "amount": "0.0100",
                        "symbol": "ETH",
                        "chainId": 11155111,
                        "tokenAddress": None,
                        "decimals": 18,
                    },
                    "gasLimit": 21000,
                    "bufferRate": "0.10",
                    "maxFee": {
                        "amount": "0.011000",
                        "symbol": "ETH",
                        "chainId": 11155111,
                        "tokenAddress": None,
                        "decimals": 18,
                    },
                },
                "txHash": "0x" + "ab" * 32,
                "failureReason": '<img src=x onerror="alert(1)">',
                "updatedAt": "2026-05-10T10:00:00+00:00",
                "outboxStatus": [
                    {
                        "messageId": "message-<unsafe>",
                        "name": "PaymentProcessingStartedEvent",
                        "status": "READY",
                        "updatedAt": "2026-05-10T09:58:00+00:00",
                    }
                ],
            }
        },
        wallet_address="0x1111111111111111111111111111111111111111",
        network_name="Sepolia",
    )

    assert view.wallet_address == "0x1111111111111111111111111111111111111111"
    assert view.network_label == "Sepolia"
    assert view.chain_id == 11155111
    assert view.token_amount.amount == "1.25"
    assert view.status.label == "AWAITING_SIGNATURE"
    assert view.payment_expires_at == "2026-05-10T10:15:00+00:00"
    assert view.tx_hash == "0x" + "ab" * 32
    assert view.timeline[-1].message_id == "message-<unsafe>"

    html = render_checkout_page(view).html

    assert "<script>" not in html
    assert "<img src=x" not in html
    assert "order-&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html
    assert "AWAITING_SIGNATURE" in html
    assert "SIGN_PAYMENT" in html
    assert "1.25 USDC" in html
    assert "0.0100 ETH" in html
    assert "21000" in html
    assert 'class="tp-mono tp-copy-value"' in html
    assert 'data-copy-value="0xabab' in html
    assert 'data-view="checkout"' in html


def test_operator_payload_renders_dense_tables_filters_detail_and_redacts_secrets() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload, render_operator_dashboard

    view = operator_dashboard_from_api_payload(
        {
            "orders": [
                {
                    "orderId": "order-123",
                    "trackingId": "tracking-123",
                    "customerId": "customer-123",
                    "storeId": "store-123",
                    "status": "CANCELLING",
                    "paymentId": "payment-123",
                    "paymentStatus": "FAILED",
                    "totalAmount": {"amount": "1.25", "symbol": "USDC", "chainId": 11155111, "tokenAddress": None, "decimals": 6},
                    "failureReason": "receipt reverted",
                    "latestEvent": "PaymentFailedEvent",
                    "updatedAt": "2026-05-10T10:00:00+00:00",
                }
            ],
            "payments": [
                {
                    "paymentId": "payment-123",
                    "orderId": "order-123",
                    "customerId": "customer-123",
                    "status": "FAILED",
                    "amount": {"amount": "1.25", "symbol": "USDC", "chainId": 11155111, "tokenAddress": None, "decimals": 6},
                    "chain": {"chainId": 11155111, "name": "Sepolia"},
                    "walletFrom": "0x1111111111111111111111111111111111111111",
                    "walletTo": "0x2222222222222222222222222222222222222222",
                    "txHash": "0x" + "cd" * 32,
                    "failureReason": "receipt reverted",
                    "expiresAt": "2026-05-10T10:15:00+00:00",
                    "updatedAt": "2026-05-10T10:01:00+00:00",
                }
            ],
            "outbox": [
                {
                    "messageId": "message-123",
                    "kind": "EVENT",
                    "name": "PaymentFailedEvent",
                    "topic": "payment.events",
                    "key": "order-123",
                    "status": "FAILED",
                    "failureCount": 2,
                    "lastError": "broker unavailable",
                    "retryCandidate": True,
                    "updatedAt": "2026-05-10T10:02:00+00:00",
                }
            ],
            "workers": [
                {
                    "component": "outbox-relay",
                    "state": "DEGRADED",
                    "checkedAt": "2026-05-10T10:03:00+00:00",
                    "details": {
                        "lastBatchFailed": 1,
                        "privateKey": "0x" + "11" * 32,
                    },
                }
            ],
            "errors": [
                {
                    "context": "payment",
                    "aggregateId": "payment-123",
                    "code": "FAILED",
                    "message": "receipt reverted",
                    "createdAt": "2026-05-10T10:01:00+00:00",
                }
            ],
        },
        filters={
            "contexts": ("orders", "payments", "outbox"),
            "statuses": ("FAILED",),
            "chain_id": 11155111,
            "store_id": "store-123",
            "failed_only": True,
            "retry_candidates_only": True,
            "sort": "-updatedAt",
        },
        detail={"private_key": "do-not-render", "txHash": "0x" + "cd" * 32},
    )

    html = render_operator_dashboard(view).html

    assert 'data-view="operator"' in html
    assert "orders, payments, outbox" in html
    assert "FAILED" in html
    assert "CANCELLING" in html
    assert "Retry candidate" in html
    assert "PaymentFailedEvent" in html
    assert "receipt reverted" in html
    assert "privateKey" in html
    assert "private_key" in html
    assert "do-not-render" not in html
    assert "0x1111111111111111111111111111111111111111111111111111111111111111" not in html
    assert "REDACTED" in html
    assert 'class="tp-table"' in html
    assert 'class="tp-mono tp-copy-value"' in html


def test_css_foundation_matches_ui_guide_density_and_avoids_banned_visual_patterns() -> None:
    from token_payments.ui.renderers import DEFAULT_CSS

    assert "#f7f8fa" in DEFAULT_CSS
    assert "#111827" in DEFAULT_CSS
    assert "#d5dbe3" in DEFAULT_CSS
    assert "#15803d" in DEFAULT_CSS
    assert "#2563eb" in DEFAULT_CSS
    assert "#b45309" in DEFAULT_CSS
    assert "#b91c1c" in DEFAULT_CSS
    assert "height: 24px" in DEFAULT_CSS
    assert "border-radius: 999px" in DEFAULT_CSS
    assert "height: 48px" in DEFAULT_CSS
    assert "overflow-wrap: anywhere" in DEFAULT_CSS
    assert "backdrop-filter" not in DEFAULT_CSS
    assert "linear-gradient" not in DEFAULT_CSS
    assert "gradient" not in DEFAULT_CSS.lower()
    assert "orb" not in DEFAULT_CSS.lower()


def test_ui_package_does_not_import_infrastructure_clients_or_runtime_read_adapters() -> None:
    violations: dict[str, list[str]] = {}
    ui_root = ROOT / "app/token_payments/ui"

    for path in sorted(ui_root.rglob("*.py")):
        illegal = sorted(
            module
            for module in _imported_modules(path)
            if any(fragment in module.lower() for fragment in FORBIDDEN_UI_IMPORT_FRAGMENTS)
        )
        if illegal:
            violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules

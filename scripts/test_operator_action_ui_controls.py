from __future__ import annotations

import json
import sys
from html import escape
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


ORDER_ID = 'order-<script>alert("cancel")</script>'
APPROVED_ORDER_ID = "order-approved-no-action"
OUTBOX_MESSAGE_ID = "outbox-message-018f33aa9e6d73d89dc347d6cdcc6d22"
DISABLED_OUTBOX_MESSAGE_ID = "outbox-message-disabled-018f33aa9e6d73d89dc347d6cdcc6d23"
REPLAY_MESSAGE_ID = "kafka:payments.events:0:81"


def test_operator_dashboard_renders_action_controls_with_safe_data_contract() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload, render_operator_dashboard

    view = operator_dashboard_from_api_payload(_operator_action_fixture(), detail=_detail_fixture())
    html = render_operator_dashboard(view).html
    controls = _action_controls(html)

    assert "Operator Actions" in html
    assert 'data-region="operator-actions"' in html
    assert {control["data-operation-id"] for control in controls} == {
        "cancelOperatorOrder",
        "retryOperatorOutboxMessage",
        "replayOperatorMessage",
    }
    assert all(control["_tag"] == "button" for control in controls)

    for control in controls:
        assert control["data-action-id"]
        assert control["data-method"] == "POST"
        assert control["data-endpoint"].startswith("/operator/")
        assert control["data-operation-id"]
        assert control["data-target-kind"] in {"order", "outboxMessage", "message"}
        assert control["data-target-id"]

        body = json.loads(control["data-body-template"])
        assert body["reason"]
        assert body["idempotencyKey"]
        assert body["parameters"]["source"] == "operator-dashboard"

        assert control["data-endpoint"] in html
        assert escape(control["data-confirmation"], quote=True) in html

    cancel = _control_by_operation(controls, "cancelOperatorOrder")
    assert cancel["data-target-id"] == ORDER_ID
    assert cancel["class"] == "tp-button tp-button-danger tp-operator-action-button"
    assert f"cancelOrder:{APPROVED_ORDER_ID}" not in html
    assert f"/operator/orders/{APPROVED_ORDER_ID}/cancel" not in html

    retry = _control_by_operation(controls, "retryOperatorOutboxMessage")
    assert retry["class"] == "tp-button tp-operator-action-button"
    assert retry["data-target-id"] == OUTBOX_MESSAGE_ID

    replay = _control_by_operation(controls, "replayOperatorMessage")
    assert replay["class"] == "tp-button tp-operator-action-button"
    assert replay["data-target-id"] == REPLAY_MESSAGE_ID

    assert "/operator/orders/order-%3Cscript%3Ealert%28%22cancel%22%29%3C%2Fscript%3E/cancel" in html
    assert f"/operator/outbox/{OUTBOX_MESSAGE_ID}/retry" in html
    assert "/operator/messages/kafka%3Apayments.events%3A0%3A81/replay" in html
    assert "cancelOperatorOrder" in html
    assert "retryOperatorOutboxMessage" in html
    assert "replayOperatorMessage" in html
    assert "<script>" not in html
    assert "alert(&quot;cancel&quot;)" in html

    assert '<table class="tp-table">' in html
    assert 'class="tp-mono tp-copy-value"' in html
    assert "Copy orders id" in html
    assert "<script" not in html.lower()
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html


def test_operator_dashboard_renders_disabled_actions_redacts_secrets_and_avoids_banned_css() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload, render_operator_dashboard
    from token_payments.ui.renderers import DEFAULT_CSS

    fixture = _operator_action_fixture()
    fixture["outbox"].append(
        {
            "messageId": DISABLED_OUTBOX_MESSAGE_ID,
            "kind": "EVENT",
            "name": "PaymentFailedEvent",
            "topic": "payment.events",
            "key": ORDER_ID,
            "status": "FAILED",
            "failureCount": 7,
            "lastError": "broker outage",
            "retryCandidate": False,
            "createdAt": "2026-05-10T10:18:00+00:00",
            "updatedAt": "2026-05-10T10:19:00+00:00",
        }
    )
    fixture["workers"][0]["details"]["privateKey"] = "0x" + "11" * 32

    view = operator_dashboard_from_api_payload(
        fixture,
        detail={
            **_detail_fixture(),
            "private_key": "do-not-render",
        },
    )
    html = render_operator_dashboard(view).html
    controls = _action_controls(html)

    disabled = next(control for control in controls if control["data-target-id"] == DISABLED_OUTBOX_MESSAGE_ID)
    assert "disabled" in disabled
    assert disabled["aria-disabled"] == "true"
    assert "Disabled: action is not currently eligible for this target" in html

    retry = _control_by_target(controls, OUTBOX_MESSAGE_ID)
    assert retry["aria-disabled"] == "false"
    assert retry["data-body-template"].startswith("{")
    assert "data-body-template=\"{&quot;" in html
    retry_body = json.loads(retry["data-body-template"])
    assert retry_body["reason"] == "retry after &lt;broker&gt; outage"
    assert retry_body["parameters"]["source"] == "operator-dashboard"

    assert "privateKey=REDACTED" in html
    assert "private_key" in html
    assert "do-not-render" not in html
    assert "0x1111111111111111111111111111111111111111111111111111111111111111" not in html

    css = DEFAULT_CSS.lower()
    for banned in (
        "backdrop-filter",
        "linear-gradient",
        "radial-gradient",
        "gradient",
        "text-shadow",
        "box-shadow: 0 0",
        "#7c3aed",
        "#4f46e5",
    ):
        assert banned not in css
    assert "border-radius: 8px" in DEFAULT_CSS
    assert "min-height: 36px" in DEFAULT_CSS


def _operator_action_fixture() -> dict[str, object]:
    return {
        "orders": [
            {
                "orderId": ORDER_ID,
                "trackingId": "tracking-cancellable",
                "customerId": "customer-123",
                "storeId": "store-123",
                "status": "AWAITING_SIGNATURE",
                "paymentId": "payment-cancellable",
                "paymentStatus": "AWAITING_SIGNATURE",
                "totalAmount": _money("18.00", "USDC", decimals=6),
                "failureReason": None,
                "latestEvent": "PaymentProcessingStartedEvent",
                "createdAt": "2026-05-10T10:00:00+00:00",
                "updatedAt": "2026-05-10T10:05:00+00:00",
            },
            {
                "orderId": APPROVED_ORDER_ID,
                "trackingId": "tracking-approved",
                "customerId": "customer-approved",
                "storeId": "store-123",
                "status": "APPROVED",
                "paymentId": "payment-approved",
                "paymentStatus": "CONFIRMED",
                "totalAmount": _money("25.00", "USDC", decimals=6),
                "failureReason": None,
                "latestEvent": "OrderApprovedEvent",
                "createdAt": "2026-05-10T09:45:00+00:00",
                "updatedAt": "2026-05-10T10:12:00+00:00",
            },
        ],
        "outbox": [
            {
                "messageId": OUTBOX_MESSAGE_ID,
                "kind": "EVENT",
                "name": "PaymentExpiredEvent",
                "topic": "payment.events",
                "key": ORDER_ID,
                "status": "FAILED",
                "failureCount": 3,
                "lastError": "broker unavailable",
                "retryCandidate": True,
                "retryReason": "retry after &lt;broker&gt; outage",
                "createdAt": "2026-05-10T10:14:00+00:00",
                "updatedAt": "2026-05-10T10:17:00+00:00",
            }
        ],
        "replayMessages": [
            {
                "messageId": REPLAY_MESSAGE_ID,
                "kind": "COMMAND",
                "reason": "handler fix deployed; replay from dashboard",
            }
        ],
        "workers": [
            {
                "component": "outbox-relay",
                "state": "OK",
                "checkedAt": "2026-05-10T10:18:00+00:00",
                "details": {"lastBatchFailed": 0},
            }
        ],
    }


def _detail_fixture() -> dict[str, object]:
    return {
        "title": "Outbox retry candidate",
        "aggregateId": ORDER_ID,
        "latestEvent": "PaymentExpiredEvent",
        "outboxStatus": "FAILED",
        "processedMessages": ("payment-expired-preview-message",),
        "processedCommands": ("ReleaseInventoryCommand", "CancelOrderCommand"),
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


def _action_controls(html: str) -> list[dict[str, str]]:
    parser = _ControlParser()
    parser.feed(html)
    return [
        attrs
        for attrs in parser.controls
        if attrs.get("data-operation-id")
        in {"cancelOperatorOrder", "retryOperatorOutboxMessage", "replayOperatorMessage"}
    ]


def _control_by_operation(controls: list[dict[str, str]], operation_id: str) -> dict[str, str]:
    matches = [control for control in controls if control["data-operation-id"] == operation_id]
    assert len(matches) == 1
    return matches[0]


def _control_by_target(controls: list[dict[str, str]], target_id: str) -> dict[str, str]:
    matches = [control for control in controls if control["data-target-id"] == target_id]
    assert len(matches) == 1
    return matches[0]


class _ControlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.controls: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {"button", "form"}:
            return
        mapped = {key: value if value is not None else "" for key, value in attrs}
        mapped["_tag"] = tag
        if "data-action-id" in mapped:
            self.controls.append(mapped)

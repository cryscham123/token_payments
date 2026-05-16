from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


ORDER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdccaa11"
APPROVED_ORDER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdccaa12"
OUTBOX_MESSAGE_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdccaa13"
FAILED_OUTBOX_MESSAGE_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdccaa14"
INBOUND_MESSAGE_ID = "kafka:payments.events:0:81"


def test_operator_action_intent_is_public_immutable_and_json_safe() -> None:
    import token_payments.ui as ui
    from token_payments.ui import OperatorActionIntent

    assert "OperatorActionIntent" in ui.__all__
    assert ui.OperatorActionIntent is OperatorActionIntent

    mutable_body = {
        "reason": "retry after broker outage",
        "idempotencyKey": f"operator:retryOutboxMessage:{OUTBOX_MESSAGE_ID}",
        "kind": "EVENT",
        "parameters": {
            "source": "operator-dashboard",
            "labels": ["manual", "outbox"],
        },
    }
    intent = OperatorActionIntent(
        action_id=f"retryOutboxMessage:{OUTBOX_MESSAGE_ID}",
        label="Retry outbox message",
        kind="secondary",
        method="POST",
        endpoint=f"/operator/outbox/{OUTBOX_MESSAGE_ID}/retry",
        operation_id="retryOperatorOutboxMessage",
        target_kind="outboxMessage",
        target_id=OUTBOX_MESSAGE_ID,
        reason="retry after broker outage",
        enabled=True,
        confirmation="Retry failed outbox message?",
        idempotency_key=f"operator:retryOutboxMessage:{OUTBOX_MESSAGE_ID}",
        body_template=mutable_body,
    )

    mutable_body["reason"] = "changed"
    mutable_body["parameters"]["source"] = "changed"
    mutable_body["parameters"]["labels"].append("changed")

    assert intent.body_template["reason"] == "retry after broker outage"
    assert intent.body_template["parameters"]["source"] == "operator-dashboard"
    assert intent.body_template["parameters"]["labels"] == ("manual", "outbox")
    assert json.loads(json.dumps(intent.body_template, sort_keys=True)) == {
        "idempotencyKey": f"operator:retryOutboxMessage:{OUTBOX_MESSAGE_ID}",
        "kind": "EVENT",
        "parameters": {"labels": ["manual", "outbox"], "source": "operator-dashboard"},
        "reason": "retry after broker outage",
    }

    with pytest.raises(ValueError, match="kind must be primary, secondary, or danger"):
        OperatorActionIntent(
            action_id="bad-kind",
            label="Bad kind",
            kind="warning",
            method="POST",
            endpoint="/operator/orders/order-1/cancel",
            operation_id="cancelOperatorOrder",
            target_kind="order",
            target_id="order-1",
            reason="bad kind",
            enabled=True,
            confirmation="Bad kind?",
            idempotency_key="operator:cancelOrder:order-1",
            body_template={
                "reason": "bad kind",
                "idempotencyKey": "operator:cancelOrder:order-1",
                "parameters": {"source": "operator-dashboard"},
            },
        )

    with pytest.raises(ValueError, match="endpoint must be an absolute path without origin"):
        OperatorActionIntent(
            action_id="external",
            label="External",
            kind="secondary",
            method="POST",
            endpoint="https://example.test/operator/orders/order-1/cancel",
            operation_id="cancelOperatorOrder",
            target_kind="order",
            target_id="order-1",
            reason="external endpoint",
            enabled=True,
            confirmation="External?",
            idempotency_key="operator:cancelOrder:order-1",
            body_template={
                "reason": "external endpoint",
                "idempotencyKey": "operator:cancelOrder:order-1",
                "parameters": {"source": "operator-dashboard"},
            },
        )

    with pytest.raises(ValueError, match="body_template"):
        OperatorActionIntent(
            action_id="not-json",
            label="Not JSON",
            kind="secondary",
            method="POST",
            endpoint="/operator/orders/order-1/cancel",
            operation_id="cancelOperatorOrder",
            target_kind="order",
            target_id="order-1",
            reason="not json",
            enabled=True,
            confirmation="Not JSON?",
            idempotency_key="operator:cancelOrder:order-1",
            body_template={
                "reason": "not json",
                "idempotencyKey": "operator:cancelOrder:order-1",
                "parameters": {"source": "operator-dashboard", "unsafe": object()},
            },
        )


def test_operator_dashboard_derives_cancel_retry_and_replay_intents_from_safe_candidates() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload

    view = operator_dashboard_from_api_payload(
        {
            "orders": [
                _order(ORDER_ID, "AWAITING_SIGNATURE"),
                _order(APPROVED_ORDER_ID, "APPROVED"),
            ],
            "outbox": [
                {
                    "messageId": OUTBOX_MESSAGE_ID,
                    "kind": "EVENT",
                    "name": "PaymentExpiredEvent",
                    "topic": "payment.events",
                    "key": ORDER_ID,
                    "status": "FAILED",
                    "failureCount": 2,
                    "lastError": "broker outage",
                    "retryCandidate": True,
                    "retryReason": "FAILED rows are reclaimed by the outbox relay retry policy",
                }
            ],
            "replayMessages": [
                {
                    "messageId": INBOUND_MESSAGE_ID,
                    "kind": "COMMAND",
                    "reason": "handler bug fixed; replay command intent",
                }
            ],
        },
        detail={
            "title": "Order detail",
            "aggregateId": ORDER_ID,
            "latestEvent": "PaymentExpiredEvent",
            "replayMessageId": "kafka:payments.events:0:82",
            "messageKind": "EVENT",
        },
    )

    assert [intent.action_id for intent in view.actions] == [
        f"cancelOrder:{ORDER_ID}",
        f"retryOutboxMessage:{OUTBOX_MESSAGE_ID}",
        "replayMessage:kafka:payments.events:0:82",
        f"replayMessage:{INBOUND_MESSAGE_ID}",
    ]

    cancel = view.actions[0]
    assert cancel.label == "Cancel order"
    assert cancel.kind == "danger"
    assert cancel.method == "POST"
    assert cancel.endpoint == f"/operator/orders/{ORDER_ID}/cancel"
    assert cancel.operation_id == "cancelOperatorOrder"
    assert cancel.target_kind == "order"
    assert cancel.target_id == ORDER_ID
    assert cancel.enabled is True
    assert cancel.idempotency_key == f"operator:cancelOrder:{ORDER_ID}"
    assert cancel.body_template == {
        "reason": cancel.reason,
        "idempotencyKey": cancel.idempotency_key,
        "parameters": {"source": "operator-dashboard"},
    }
    assert "kind" not in cancel.body_template

    retry = view.actions[1]
    assert retry.label == "Retry outbox message"
    assert retry.kind == "secondary"
    assert retry.method == "POST"
    assert retry.endpoint == f"/operator/outbox/{OUTBOX_MESSAGE_ID}/retry"
    assert retry.operation_id == "retryOperatorOutboxMessage"
    assert retry.target_kind == "outboxMessage"
    assert retry.target_id == OUTBOX_MESSAGE_ID
    assert retry.enabled is True
    assert retry.idempotency_key == f"operator:retryOutboxMessage:{OUTBOX_MESSAGE_ID}"
    assert retry.body_template["kind"] == "EVENT"
    assert retry.body_template["parameters"] == {"source": "operator-dashboard"}

    detail_replay = view.actions[2]
    assert detail_replay.label == "Replay message"
    assert detail_replay.kind == "secondary"
    assert detail_replay.method == "POST"
    assert detail_replay.endpoint == "/operator/messages/kafka%3Apayments.events%3A0%3A82/replay"
    assert detail_replay.operation_id == "replayOperatorMessage"
    assert detail_replay.target_kind == "message"
    assert detail_replay.target_id == "kafka:payments.events:0:82"
    assert detail_replay.idempotency_key == "operator:replayMessage:kafka:payments.events:0:82"
    assert detail_replay.body_template["kind"] == "EVENT"
    assert detail_replay.body_template["parameters"]["source"] == "operator-dashboard"

    payload_replay = view.actions[3]
    assert payload_replay.endpoint == "/operator/messages/kafka%3Apayments.events%3A0%3A81/replay"
    assert payload_replay.body_template["kind"] == "COMMAND"
    assert payload_replay.reason == "handler bug fixed; replay command intent"


def test_operator_dashboard_only_exposes_retry_intents_for_failed_or_candidate_outbox_rows() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload

    view = operator_dashboard_from_api_payload(
        {
            "outbox": [
                {
                    "messageId": FAILED_OUTBOX_MESSAGE_ID,
                    "kind": "EVENT",
                    "name": "PaymentFailedEvent",
                    "topic": "payment.events",
                    "key": ORDER_ID,
                    "status": "FAILED",
                    "retryCandidate": False,
                    "lastError": "broker unavailable",
                },
                {
                    "messageId": "published-message",
                    "kind": "EVENT",
                    "name": "OrderApprovedEvent",
                    "topic": "order.events",
                    "key": APPROVED_ORDER_ID,
                    "status": "PUBLISHED",
                    "retryCandidate": False,
                },
            ]
        }
    )

    assert [intent.action_id for intent in view.actions] == [
        f"retryOutboxMessage:{FAILED_OUTBOX_MESSAGE_ID}",
    ]
    assert view.actions[0].enabled is False
    assert view.actions[0].body_template["kind"] == "EVENT"


def test_operator_dashboard_omits_action_intents_for_non_actionable_rows() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload

    view = operator_dashboard_from_api_payload(
        {
            "orders": [_order(APPROVED_ORDER_ID, "APPROVED")],
            "outbox": [
                {
                    "messageId": "published-message",
                    "kind": "EVENT",
                    "name": "OrderApprovedEvent",
                    "topic": "order.events",
                    "key": APPROVED_ORDER_ID,
                    "status": "PUBLISHED",
                    "retryCandidate": False,
                }
            ],
            "detail": {
                "aggregateId": APPROVED_ORDER_ID,
                "latestEvent": "OrderApprovedEvent",
                "messageId": "observed-message-not-a-replay-candidate",
            },
        }
    )

    assert view.actions == ()


def test_operator_action_intents_keep_script_like_input_as_plain_text_not_executable_html() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload

    script_order_id = 'order-<script>alert("cancel")</script>'
    view = operator_dashboard_from_api_payload({"orders": [_order(script_order_id, "PENDING")]})

    assert len(view.actions) == 1
    intent = view.actions[0]
    assert intent.target_id == script_order_id
    assert intent.body_template["reason"].endswith(script_order_id)
    assert "&lt;script&gt;" not in intent.target_id
    assert "<script>" not in intent.endpoint
    assert "%3Cscript%3E" in intent.endpoint


def _order(order_id: str, status: str) -> dict[str, object]:
    return {
        "orderId": order_id,
        "trackingId": f"tracking-{order_id[-4:]}",
        "customerId": "customer-1",
        "storeId": "store-1",
        "status": status,
        "paymentStatus": "AWAITING_SIGNATURE",
        "totalAmount": {
            "amount": "25.00",
            "symbol": "USDC",
            "chainId": 11155111,
            "tokenAddress": "0x3333333333333333333333333333333333333333",
            "decimals": 6,
        },
        "latestEvent": "OrderCreatedEvent",
        "createdAt": "2026-05-10T09:45:00+00:00",
        "updatedAt": "2026-05-10T10:00:00+00:00",
    }

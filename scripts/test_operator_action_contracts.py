from __future__ import annotations

import ast
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    AdminRoleOperatorActionPolicy,
    AdminRoleOperatorPolicy,
    OperatorActionAuditRecord,
    OperatorActionCommand,
    OperatorActionName,
    OperatorActionPolicy,
    OperatorActionResult,
    OperatorActionResultStatus,
    OperatorActionTarget,
    OperatorActionTargetKind,
    OperatorClaims,
)
from token_payments.contexts.auth.domain import UserRole  # noqa: E402


NOW = datetime(2026, 5, 11, 5, 30, tzinfo=UTC)
ORDER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc8011"
OUTBOX_MESSAGE_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc8012:PaymentExpiredEvent"
INBOUND_MESSAGE_ID = "kafka:payments.events:0:81"
REQUEST_ID = "req-operator-action-1"
IDEMPOTENCY_KEY = "operator:cancelOrder:018f33aa-9e6d-73d8-9dc3-47d6cdcc8011"


def test_operator_action_names_and_targets_are_stable_contract_values() -> None:
    assert [action.value for action in OperatorActionName] == [
        "cancelOrder",
        "retryOutboxMessage",
        "replayMessage",
    ]

    assert OperatorActionTarget(OperatorActionTargetKind.ORDER, ORDER_ID).to_payload() == {
        "kind": "order",
        "id": ORDER_ID,
    }
    assert OperatorActionTarget("outboxMessage", OUTBOX_MESSAGE_ID).kind is OperatorActionTargetKind.OUTBOX_MESSAGE


def test_operator_action_command_validates_actor_idempotency_reason_time_and_parameters() -> None:
    command = OperatorActionCommand(
        action="cancelOrder",
        target=OperatorActionTarget("order", ORDER_ID),
        actor=OperatorClaims(user_id="operator-1", role=UserRole.ADMIN, scopes=("operator:read",)),
        request_id=REQUEST_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        reason="customer support confirmed payment expired",
        requested_at=NOW,
        parameters={
            "source": "operator-dashboard",
            "notifyCustomer": True,
            "attempt": 2,
            "labels": ("manual", "compensation"),
        },
    )

    assert command.action is OperatorActionName.CANCEL_ORDER
    assert command.target.kind is OperatorActionTargetKind.ORDER
    assert command.actor.role is UserRole.ADMIN
    assert command.request_id == REQUEST_ID
    assert command.idempotency_key == IDEMPOTENCY_KEY
    assert command.reason == "customer support confirmed payment expired"
    assert command.requested_at == NOW
    assert command.parameters == {
        "source": "operator-dashboard",
        "notifyCustomer": True,
        "attempt": 2,
        "labels": ["manual", "compensation"],
    }

    with pytest.raises(ValueError, match="OperatorActionCommand.requested_at must be timezone-aware"):
        OperatorActionCommand(
            action=OperatorActionName.CANCEL_ORDER,
            target=OperatorActionTarget(OperatorActionTargetKind.ORDER, ORDER_ID),
            actor=OperatorClaims(role=UserRole.ADMIN),
            request_id=REQUEST_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            reason="manual cancellation",
            requested_at=datetime(2026, 5, 11, 5, 30),
        )

    with pytest.raises(ValueError, match="parameters"):
        OperatorActionCommand(
            action=OperatorActionName.CANCEL_ORDER,
            target=OperatorActionTarget(OperatorActionTargetKind.ORDER, ORDER_ID),
            actor=OperatorClaims(role=UserRole.ADMIN),
            request_id=REQUEST_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            reason="manual cancellation",
            requested_at=NOW,
            parameters={"unsafe": object()},
        )


def test_operator_action_command_rejects_mismatched_action_target_pairs() -> None:
    with pytest.raises(ValueError, match="cancelOrder targets must be order"):
        OperatorActionCommand(
            action=OperatorActionName.CANCEL_ORDER,
            target=OperatorActionTarget(OperatorActionTargetKind.OUTBOX_MESSAGE, OUTBOX_MESSAGE_ID),
            actor=OperatorClaims(role=UserRole.ADMIN),
            request_id=REQUEST_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            reason="wrong target kind",
            requested_at=NOW,
        )

    with pytest.raises(ValueError, match="retryOutboxMessage targets must be outboxMessage"):
        OperatorActionCommand(
            action=OperatorActionName.RETRY_OUTBOX_MESSAGE,
            target=OperatorActionTarget(OperatorActionTargetKind.MESSAGE, INBOUND_MESSAGE_ID),
            actor=OperatorClaims(role=UserRole.ADMIN),
            request_id=REQUEST_ID,
            idempotency_key="operator:retryOutboxMessage:bad-target",
            reason="wrong target kind",
            requested_at=NOW,
        )

    replay = OperatorActionCommand(
        action=OperatorActionName.REPLAY_MESSAGE,
        target=OperatorActionTarget(OperatorActionTargetKind.MESSAGE, INBOUND_MESSAGE_ID),
        actor=OperatorClaims(role=UserRole.ADMIN),
        request_id=REQUEST_ID,
        idempotency_key="operator:replayMessage:kafka:payments.events:0:81",
        reason="replay failed event after handler fix",
        requested_at=NOW,
    )
    assert replay.target.kind is OperatorActionTargetKind.MESSAGE


def test_operator_action_result_serializes_json_safe_status_target_ids_and_summary() -> None:
    result = OperatorActionResult(
        status=OperatorActionResultStatus.ACCEPTED,
        action=OperatorActionName.CANCEL_ORDER,
        target=OperatorActionTarget(OperatorActionTargetKind.ORDER, ORDER_ID),
        idempotency_key=IDEMPOTENCY_KEY,
        summary="CancelOrderCommand accepted for order 018f33aa-9e6d-73d8-9dc3-47d6cdcc8011.",
        command_id="018f33aa-9e6d-73d8-9dc3-47d6cdcc8011:CancelOrderCommand",
        audit_id="audit-operator-action-1",
        details={"requestedAt": NOW, "duplicate": False},
    )

    payload = result.to_payload()
    assert payload == {
        "action": "cancelOrder",
        "status": "accepted",
        "target": {"kind": "order", "id": ORDER_ID},
        "idempotencyKey": IDEMPOTENCY_KEY,
        "commandId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc8011:CancelOrderCommand",
        "messageId": None,
        "auditId": "audit-operator-action-1",
        "summary": "CancelOrderCommand accepted for order 018f33aa-9e6d-73d8-9dc3-47d6cdcc8011.",
        "details": {"requestedAt": NOW.isoformat(), "duplicate": False},
    }
    json.dumps(payload, sort_keys=True)

    duplicate = OperatorActionResult(
        status="duplicate",
        action="retryOutboxMessage",
        target=OperatorActionTarget("outboxMessage", OUTBOX_MESSAGE_ID),
        idempotency_key="operator:retryOutboxMessage:duplicate",
        summary="Retry was already accepted for this idempotency key.",
        message_id=OUTBOX_MESSAGE_ID,
    )
    assert duplicate.status is OperatorActionResultStatus.DUPLICATE
    assert duplicate.to_payload()["status"] == "duplicate"

    rejected = OperatorActionResult(
        status=OperatorActionResultStatus.REJECTED,
        action=OperatorActionName.REPLAY_MESSAGE,
        target=OperatorActionTarget("message", INBOUND_MESSAGE_ID),
        idempotency_key="operator:replayMessage:rejected",
        summary="Replay rejected because the message is already processed.",
    )
    assert rejected.to_payload()["status"] == "rejected"


def test_operator_action_audit_record_preserves_actor_action_target_and_outcome() -> None:
    actor = OperatorClaims(user_id="operator-1", role=UserRole.ADMIN, scopes=("operator:read",))
    audit = OperatorActionAuditRecord(
        actor=actor,
        action=OperatorActionName.REPLAY_MESSAGE,
        target=OperatorActionTarget(OperatorActionTargetKind.MESSAGE, INBOUND_MESSAGE_ID),
        idempotency_key="operator:replayMessage:kafka:payments.events:0:81",
        request_id=REQUEST_ID,
        outcome=OperatorActionResultStatus.REJECTED,
        reason="message was already processed",
        recorded_at=NOW,
    )

    assert audit.actor is actor
    assert audit.action is OperatorActionName.REPLAY_MESSAGE
    assert audit.target.id == INBOUND_MESSAGE_ID
    assert audit.idempotency_key == "operator:replayMessage:kafka:payments.events:0:81"
    assert audit.request_id == REQUEST_ID
    assert audit.outcome is OperatorActionResultStatus.REJECTED
    assert audit.reason == "message was already processed"
    assert audit.recorded_at == NOW
    assert audit.to_payload() == {
        "actor": {
            "userId": "operator-1",
            "role": UserRole.ADMIN.value,
            "scopes": ["operator:read"],
        },
        "action": "replayMessage",
        "target": {"kind": "message", "id": INBOUND_MESSAGE_ID},
        "idempotencyKey": "operator:replayMessage:kafka:payments.events:0:81",
        "requestId": REQUEST_ID,
        "outcome": "rejected",
        "reason": "message was already processed",
        "recordedAt": NOW.isoformat(),
    }


def test_operator_action_policy_allows_only_admin_role_and_stays_separate_from_read_only_policy() -> None:
    policy: OperatorActionPolicy = AdminRoleOperatorActionPolicy()

    assert policy.can_execute_action(OperatorClaims(role=UserRole.ADMIN), OperatorActionName.CANCEL_ORDER)
    assert not policy.can_execute_action(
        OperatorClaims(role=UserRole.CUSTOMER, scopes=("operator:read", "operator:action")),
        OperatorActionName.CANCEL_ORDER,
    )
    assert not policy.can_execute_action(OperatorClaims(role=None, scopes=("operator:action",)), OperatorActionName.REPLAY_MESSAGE)

    read_policy = AdminRoleOperatorPolicy()
    assert read_policy.can_read_observability(OperatorClaims(role=UserRole.ADMIN))
    assert not hasattr(read_policy, "can_execute_action")
    assert not hasattr(policy, "can_read_observability")


def test_operator_action_contract_module_stays_framework_and_infrastructure_neutral() -> None:
    path = ROOT / "app/token_payments/api/operator_actions.py"
    imported_modules = _imported_modules(path)

    assert "fastapi" not in imported_modules
    assert "flask" not in imported_modules
    assert "django" not in imported_modules
    assert not any(module.startswith("token_payments.shared.adapter") for module in imported_modules)
    assert not any(".adapter" in module for module in imported_modules)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules

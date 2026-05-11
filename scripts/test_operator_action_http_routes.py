from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    OPERATOR_ACTION_HTTP_ROUTES,
    HttpRouter,
    OperatorActionApi,
    OperatorActionResultStatus,
    OperatorCancelOrderActionExecutor,
    OperatorClaims,
    OperatorOutboxActionExecutor,
    OperatorOutboxActionPortResult,
    OperatorOutboxActionStatus,
    register_operator_action_routes,
)
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.contexts.order.application import (  # noqa: E402
    CancelOrderCommand,
    OrderCommandRejected,
    OrderCommandRejectionReason,
    OrderCommandResult,
    OrderCommandStatus,
)
from token_payments.shared.domain import CommandId, MessageId, OrderId, OutboxMessageKind  # noqa: E402


NOW = datetime(2026, 5, 11, 10, 30, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a11")
OUTBOX_MESSAGE_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc9a12"
INBOUND_MESSAGE_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc9a13:ReleaseInventoryCommand"


def test_operator_action_route_manifest_exposes_stable_operations() -> None:
    assert OPERATOR_ACTION_HTTP_ROUTES["cancel_order"].method == "POST"
    assert OPERATOR_ACTION_HTTP_ROUTES["cancel_order"].path == "/operator/orders/{orderId}/cancel"
    assert OPERATOR_ACTION_HTTP_ROUTES["cancel_order"].operation_id == "cancelOperatorOrder"
    assert OPERATOR_ACTION_HTTP_ROUTES["retry_outbox_message"].method == "POST"
    assert OPERATOR_ACTION_HTTP_ROUTES["retry_outbox_message"].path == "/operator/outbox/{messageId}/retry"
    assert OPERATOR_ACTION_HTTP_ROUTES["retry_outbox_message"].operation_id == "retryOperatorOutboxMessage"
    assert OPERATOR_ACTION_HTTP_ROUTES["replay_message"].method == "POST"
    assert OPERATOR_ACTION_HTTP_ROUTES["replay_message"].path == "/operator/messages/{messageId}/replay"
    assert OPERATOR_ACTION_HTTP_ROUTES["replay_message"].operation_id == "replayOperatorMessage"


def test_operator_action_routes_preserve_json_body_headers_claims_and_request_id() -> None:
    order_handler = RecordingOrderCommandHandler(OrderCommandStatus.CANCELLED)
    retry_port = RecordingRetryPort(OperatorOutboxActionStatus.RETRYABLE)
    replay_port = RecordingReplayPort(OperatorOutboxActionStatus.RECORDED)
    audit = RecordingOperatorActionAuditRepository()
    router = HttpRouter()

    routes = register_operator_action_routes(
        router,
        OperatorActionApi(
            cancel_order_executor=OperatorCancelOrderActionExecutor(order_handler, audit_repository=audit),
            outbox_action_executor=OperatorOutboxActionExecutor(
                retry_port=retry_port,
                replay_port=replay_port,
                audit_repository=audit,
            ),
        ),
    )

    assert [route.operation_id for route in routes] == [
        "cancelOperatorOrder",
        "retryOperatorOutboxMessage",
        "replayOperatorMessage",
    ]

    cancel_response = router.handle(
        "POST",
        f"/operator/orders/{ORDER_ID}/cancel",
        headers=_admin_headers("req-action-cancel"),
        body=_json_body(
            {
                "reason": "customer support confirmed checkout was abandoned",
                "idempotencyKey": "operator-cancel-explicit-key",
                "parameters": {"source": "operator-dashboard", "notifyCustomer": True},
            }
        ),
        received_at=NOW,
    )
    retry_response = router.handle(
        "POST",
        f"/operator/outbox/{OUTBOX_MESSAGE_ID}/retry",
        headers=_admin_headers("req-action-retry"),
        body=_json_body(
            {
                "kind": "EVENT",
                "reason": "broker outage resolved; retry failed publish",
                "idempotencyKey": "operator-retry-explicit-key",
                "parameters": {"source": "operator-dashboard", "attempt": 2},
            }
        ),
        received_at=NOW,
    )
    replay_response = router.handle(
        "POST",
        f"/operator/messages/{INBOUND_MESSAGE_ID}/replay",
        headers=_admin_headers("req-action-replay"),
        body=_json_body(
            {
                "kind": "COMMAND",
                "reason": "handler bug fixed; replay command intent",
                "idempotencyKey": "operator-replay-explicit-key",
                "parameters": {"source": "operator-dashboard", "dryRun": False},
            }
        ),
        received_at=NOW,
    )

    assert cancel_response.status_code == 202
    cancel_payload = _json(cancel_response.body)
    assert cancel_response.headers["X-Request-Id"] == "req-action-cancel"
    assert cancel_payload["status"] == OperatorActionResultStatus.ACCEPTED.value
    assert cancel_payload["details"]["parameters"] == {"source": "operator-dashboard", "notifyCustomer": True}
    cancel_command = order_handler.calls[0]
    assert cancel_command.command_id == CommandId("operator-cancel-explicit-key")
    assert cancel_command.order_id == ORDER_ID
    assert cancel_command.reason == "customer support confirmed checkout was abandoned"
    assert cancel_command.causation_id == "req-action-cancel"
    assert cancel_command.requested_at == NOW

    assert retry_response.status_code == 202
    retry_request = retry_port.requests[0]
    assert retry_request.message_kind is OutboxMessageKind.EVENT
    assert retry_request.message_identity == OUTBOX_MESSAGE_ID
    assert retry_request.reason == "broker outage resolved; retry failed publish"
    assert retry_request.request_id == "req-action-retry"
    assert retry_request.idempotency_key == "operator-retry-explicit-key"
    assert retry_request.requested_at == NOW
    assert retry_request.actor == _admin_claims()
    assert _json(retry_response.body)["details"]["messageKind"] == "EVENT"
    assert _json(retry_response.body)["details"]["parameters"] == {"source": "operator-dashboard", "attempt": 2}

    assert replay_response.status_code == 202
    replay_request = replay_port.requests[0]
    assert replay_request.message_kind is OutboxMessageKind.COMMAND
    assert replay_request.message_identity == INBOUND_MESSAGE_ID
    assert replay_request.request_id == "req-action-replay"
    assert replay_request.idempotency_key == "operator-replay-explicit-key"
    assert replay_request.actor == _admin_claims()
    assert _json(replay_response.body)["details"]["messageKind"] == "COMMAND"
    assert _json(replay_response.body)["details"]["parameters"] == {"source": "operator-dashboard", "dryRun": False}

    assert audit.records[0].actor == _admin_claims()
    assert audit.records[0].request_id == "req-action-cancel"
    assert audit.records[1].actor == _admin_claims()
    assert audit.records[1].request_id == "req-action-retry"
    assert audit.records[2].actor == _admin_claims()
    assert audit.records[2].request_id == "req-action-replay"


def test_operator_action_http_routes_serialize_forbidden_and_validation_errors() -> None:
    order_handler = RecordingOrderCommandHandler(OrderCommandStatus.CANCELLED)
    router = HttpRouter()
    register_operator_action_routes(
        router,
        OperatorActionApi(
            cancel_order_executor=OperatorCancelOrderActionExecutor(order_handler),
            outbox_action_executor=OperatorOutboxActionExecutor(
                retry_port=RecordingRetryPort(OperatorOutboxActionStatus.RETRYABLE),
                replay_port=RecordingReplayPort(OperatorOutboxActionStatus.RECORDED),
            ),
        ),
    )

    forbidden = router.handle(
        "POST",
        f"/operator/orders/{ORDER_ID}/cancel",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-action-forbidden",
            "X-User-Id": "customer-1",
            "X-User-Role": UserRole.CUSTOMER.value,
            "X-User-Scopes": "operator:action",
        },
        body=_json_body({"reason": "customer attempted manual cancellation"}),
        received_at=NOW,
    )
    validation = router.handle(
        "POST",
        f"/operator/outbox/{OUTBOX_MESSAGE_ID}/retry",
        headers=_admin_headers("req-action-validation"),
        body=_json_body({"reason": "retry failed publish without declaring message kind"}),
        received_at=NOW,
    )

    assert forbidden.status_code == 403
    forbidden_payload = _json(forbidden.body)
    assert forbidden_payload["action"] == "cancelOrder"
    assert forbidden_payload["status"] == "rejected"
    assert forbidden_payload["target"] == {"kind": "order", "id": str(ORDER_ID)}
    assert forbidden_payload["idempotencyKey"] == f"operator:cancelOrder:{ORDER_ID}:req-action-forbidden"
    assert forbidden_payload["commandId"] == str(CommandId.for_order_action(ORDER_ID, "CancelOrderCommand"))
    assert forbidden_payload["messageId"]
    assert forbidden_payload["auditId"] is None
    assert forbidden_payload["summary"] == "operator ADMIN role is required to execute cancelOrder"
    assert forbidden_payload["details"] == {
        "errorCode": "OPERATOR_FORBIDDEN",
        "orderId": str(ORDER_ID),
    }
    assert order_handler.calls == []

    assert validation.status_code == 400
    assert _json(validation.body) == {
        "error": {
            "code": "OPERATOR_ACTION_VALIDATION_FAILED",
            "message": "kind is required",
        }
    }


def test_operator_action_http_routes_serialize_rejected_and_duplicate_results() -> None:
    rejection = OrderCommandRejected(
        reason=OrderCommandRejectionReason.INVALID_STATE,
        command_id=CommandId.for_order_action(ORDER_ID, "CancelOrderCommand"),
        order_id=ORDER_ID,
        message="cannot cancel an already approved order",
    )
    router = HttpRouter()
    register_operator_action_routes(
        router,
        OperatorActionApi(
            cancel_order_executor=OperatorCancelOrderActionExecutor(RecordingOrderCommandHandler(rejection)),
            outbox_action_executor=OperatorOutboxActionExecutor(
                retry_port=RecordingRetryPort(OperatorOutboxActionStatus.DUPLICATE_IGNORED),
                replay_port=RecordingReplayPort(OperatorOutboxActionStatus.RECORDED),
            ),
        ),
    )

    rejected = router.handle(
        "POST",
        f"/operator/orders/{ORDER_ID}/cancel",
        headers=_admin_headers("req-action-rejected"),
        body=_json_body({"reason": "operator requested cancellation"}),
        received_at=NOW,
    )
    duplicate = router.handle(
        "POST",
        f"/operator/outbox/{OUTBOX_MESSAGE_ID}/retry",
        headers=_admin_headers("req-action-duplicate"),
        body=_json_body(
            {
                "kind": "EVENT",
                "reason": "same action was already accepted",
                "idempotencyKey": "operator-duplicate-key",
            }
        ),
        received_at=NOW,
    )

    assert rejected.status_code == 409
    rejected_payload = _json(rejected.body)
    assert rejected_payload["status"] == "rejected"
    assert rejected_payload["details"]["rejectionReason"] == OrderCommandRejectionReason.INVALID_STATE.value
    assert rejected_payload["summary"] == "cannot cancel an already approved order"

    assert duplicate.status_code == 200
    duplicate_payload = _json(duplicate.body)
    assert duplicate_payload["status"] == "duplicate"
    assert duplicate_payload["idempotencyKey"] == "operator-duplicate-key"
    assert duplicate_payload["details"]["duplicateDecision"] == OperatorOutboxActionStatus.DUPLICATE_IGNORED.value


def _admin_headers(request_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Request-Id": request_id,
        "X-User-Id": "operator-1",
        "X-User-Role": UserRole.ADMIN.value,
        "X-User-Scopes": "operator:read, operator:action",
    }


def _admin_claims() -> OperatorClaims:
    return OperatorClaims(user_id="operator-1", role=UserRole.ADMIN, scopes=("operator:read", "operator:action"))


def _json_body(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json(body: bytes) -> dict[str, object]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


class RecordingOrderCommandHandler:
    def __init__(self, outcome: OrderCommandStatus | OrderCommandRejected) -> None:
        self.outcome = outcome
        self.calls: list[CancelOrderCommand] = []
        self.generated_message_ids: list[str] = []

    def cancel_order(self, command: CancelOrderCommand) -> OrderCommandResult:
        self.calls.append(command)
        self.generated_message_ids.append(str(command.event_message_id))
        if isinstance(self.outcome, OrderCommandRejected):
            raise self.outcome
        return OrderCommandResult(command_id=command.command_id, order_id=command.order_id, status=self.outcome)


class RecordingRetryPort:
    def __init__(self, status: OperatorOutboxActionStatus) -> None:
        self.status = status
        self.requests = []

    def request_retry(self, request):
        self.requests.append(request)
        return OperatorOutboxActionPortResult(
            status=self.status,
            message_kind=request.message_kind,
            message_identity=request.message_identity,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            summary=_summary_for(self.status),
        )


class RecordingReplayPort:
    def __init__(self, status: OperatorOutboxActionStatus) -> None:
        self.status = status
        self.requests = []

    def request_replay(self, request):
        self.requests.append(request)
        return OperatorOutboxActionPortResult(
            status=self.status,
            message_kind=request.message_kind,
            message_identity=request.message_identity,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            summary=_summary_for(self.status),
        )


class RecordingOperatorActionAuditRepository:
    def __init__(self) -> None:
        self.records = []

    def record(self, audit_record):
        self.records.append(audit_record)
        return f"audit-{len(self.records)}"


def _summary_for(status: OperatorOutboxActionStatus) -> str:
    if status is OperatorOutboxActionStatus.DUPLICATE_IGNORED:
        return "Duplicate operator outbox action ignored for idempotency key."
    if status is OperatorOutboxActionStatus.RETRYABLE:
        return "Outbox message retry request recorded and message is retryable."
    return "Message replay request recorded."

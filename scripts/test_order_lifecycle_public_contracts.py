from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_order_lifecycle_application_and_adapter_exports_are_public() -> None:
    import token_payments.contexts.order.adapter as adapter
    import token_payments.contexts.order.application as application

    assert {
        "CancelOrderCommand",
        "OrderCommandHandler",
        "OrderCommandResult",
        "OrderCommandStatus",
        "OrderStatusEvent",
        "OrderStatusEventProjector",
        "OrderProjectionResult",
        "OrderProjectionStatus",
        "ProcessedMessageRepository",
    } <= set(application.__all__)
    assert {
        "OrderKafkaCommandListener",
        "OrderKafkaCommandListenerResult",
        "OrderStatusKafkaEventListener",
        "OrderStatusKafkaEventListenerResult",
        "PostgresOrderRepository",
    } <= set(adapter.__all__)


def test_compensation_smoke_contract_has_wired_cancel_order_handler() -> None:
    from token_payments.runtime.smoke import run_smoke_scenario

    result = run_smoke_scenario("compensation-checkout").to_dict()
    details = result["details"]

    assert details["cancelOrderHandlerWired"] is True
    for scenario in details["subScenarios"].values():
        assert scenario["finalOrderStatus"] == "CANCELLED"
        assert scenario["duplicateCommandResults"]["CancelOrderCommand"] == "DUPLICATE_IGNORED"
    json.dumps(result)


def test_happy_path_smoke_contract_uses_order_status_projector() -> None:
    from token_payments.runtime.smoke import run_smoke_scenario

    details = run_smoke_scenario("happy-path-checkout").to_dict()["details"]

    assert details["finalOrderStatus"] == "APPROVED"
    assert details["orderStatusProjector"] == {
        "PaymentConfirmedEvent": "PAYMENT_CONFIRMED",
        "OrderApprovedEvent": "ORDER_APPROVED",
        "processedMessageCount": 2,
    }


def test_order_lifecycle_docs_are_current() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    app_readme = (ROOT / "app/README.md").read_text(encoding="utf-8")

    assert "app/README.md" in readme
    assert "phase별 완료 로그" in readme
    assert "Order Lifecycle Compensation" in app_readme
    assert "cancelOrderHandlerWired=true" in app_readme
    assert "scripts/test_order_lifecycle_public_contracts.py" in app_readme
    assert "HTTP framework adapter" in app_readme

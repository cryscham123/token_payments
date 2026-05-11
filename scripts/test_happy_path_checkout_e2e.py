from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_happy_path_checkout_smoke_runs_real_application_flow() -> None:
    from token_payments.runtime.smoke import run_smoke_scenario

    result = run_smoke_scenario("happy-path-checkout").to_dict()

    assert result["scenario"] == "happy-path-checkout"
    assert result["status"] == "passed"
    assert result["summary"] == "happy-path checkout reached approved order status with in-memory ports"
    assert [step["name"] for step in result["steps"]] == [
        "OrderCreatedEvent",
        "ReserveInventoryCommand",
        "InventoryReservedEvent",
        "InitiatePaymentCommand",
        "payment signature request/gas estimate",
        "txHash submit result",
        "PaymentConfirmedEvent",
        "RequestStoreApprovalCommand",
        "OrderApprovedEvent",
    ]

    details = result["details"]
    assert details["orderId"] == "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"
    assert details["trackingId"] == "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c29"
    assert details["paymentId"] == "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25"
    assert details["finalOrderStatus"] == "APPROVED"
    assert details["finalStoreApprovalStatus"] == "APPROVED"
    assert details["orderStatusProjector"] == {
        "PaymentConfirmedEvent": "PAYMENT_CONFIRMED",
        "OrderApprovedEvent": "ORDER_APPROVED",
        "processedMessageCount": 2,
    }
    assert details["savedOutboxEventNames"] == [
        "OrderCreatedEvent",
        "InventoryReservedEvent",
        "PaymentProcessingStartedEvent",
        "PaymentConfirmedEvent",
        "OrderApprovedEvent",
    ]
    assert details["processManagerCommandIds"] == {
        "ReserveInventoryCommand": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21:ReserveInventoryCommand",
        "InitiatePaymentCommand": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21:InitiatePaymentCommand",
        "RequestStoreApprovalCommand": (
            "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21:RequestStoreApprovalCommand"
        ),
    }
    assert details["idempotency"] == {
        "normalProcessing": True,
        "duplicateCommandDecisions": [],
        "processedCommandCount": 5,
        "processedMessageCount": 4,
    }
    json.dumps(result)


def test_happy_path_checkout_smoke_cli_outputs_bounded_json() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")

    completed = subprocess.run(
        [sys.executable, "-m", "token_payments", "smoke", "happy-path-checkout"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["command"] == "smoke"
    assert payload["status"] == "SUCCEEDED"
    assert payload["details"]["smoke"]["scenario"] == "happy-path-checkout"
    assert payload["details"]["smoke"]["status"] == "passed"
    assert payload["details"]["smoke"]["details"]["finalOrderStatus"] == "APPROVED"
    assert payload["details"]["smoke"]["details"]["finalStoreApprovalStatus"] == "APPROVED"
    assert len(completed.stdout) < 12000

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_compensation_checkout_smoke_runs_failure_expiration_and_rejection_flows() -> None:
    from token_payments.runtime.smoke import run_smoke_scenario

    result = run_smoke_scenario("compensation-checkout").to_dict()

    assert result["scenario"] == "compensation-checkout"
    assert result["status"] == "passed"
    assert result["summary"] == (
        "compensation checkout emitted deterministic idempotent commands for failure, expiration, and rejection"
    )
    assert [step["name"] for step in result["steps"]] == [
        "payment receipt failure compensation",
        "payment signature expiration compensation",
        "store rejection compensation",
    ]

    details = result["details"]
    sub_scenarios = details["subScenarios"]
    assert set(sub_scenarios) == {
        "paymentReceiptFailure",
        "paymentSignatureExpiration",
        "storeRejectionAfterPaymentConfirmation",
    }
    assert details["cancelOrderHandlerWired"] is True

    failure = sub_scenarios["paymentReceiptFailure"]
    assert failure["triggerEvent"] == "PaymentFailedEvent"
    assert failure["compensationCommandIds"] == {
        "ReleaseInventoryCommand": "018f33aa-9e6d-73d8-9dc3-47d6cdcc7c21:ReleaseInventoryCommand",
        "CancelOrderCommand": "018f33aa-9e6d-73d8-9dc3-47d6cdcc7c21:CancelOrderCommand",
    }
    assert failure["duplicateEventReplay"]["ignoredByProcessedMessageRepository"] is True
    assert failure["duplicateEventReplay"]["sameDirectDecisionIdsOnReplay"] is True
    assert failure["duplicateCommandResults"]["ReleaseInventoryCommand"] == "DUPLICATE_IGNORED"
    assert failure["duplicateCommandResults"]["CancelOrderCommand"] == "DUPLICATE_IGNORED"
    assert failure["finalInventory"] == {"availableStock": 10, "reservedStock": 0}
    assert failure["finalOrderStatus"] == "CANCELLED"

    expiration = sub_scenarios["paymentSignatureExpiration"]
    assert expiration["triggerEvent"] == "PaymentExpiredEvent"
    assert expiration["compensationCommandIds"] == {
        "ReleaseInventoryCommand": "018f33aa-9e6d-73d8-9dc3-47d6cdcc8c21:ReleaseInventoryCommand",
        "CancelOrderCommand": "018f33aa-9e6d-73d8-9dc3-47d6cdcc8c21:CancelOrderCommand",
    }
    assert expiration["duplicateCommandResults"]["ReleaseInventoryCommand"] == "DUPLICATE_IGNORED"
    assert expiration["duplicateCommandResults"]["CancelOrderCommand"] == "DUPLICATE_IGNORED"
    assert expiration["finalPaymentStatus"] == "EXPIRED"
    assert expiration["finalInventory"] == {"availableStock": 10, "reservedStock": 0}
    assert expiration["finalOrderStatus"] == "CANCELLED"

    rejection = sub_scenarios["storeRejectionAfterPaymentConfirmation"]
    assert rejection["triggerEvent"] == "OrderRejectedEvent"
    assert rejection["compensationCommandIds"] == {
        "RefundPaymentCommand": "018f33aa-9e6d-73d8-9dc3-47d6cdcc9c21:RefundPaymentCommand",
        "ReleaseInventoryCommand": "018f33aa-9e6d-73d8-9dc3-47d6cdcc9c21:ReleaseInventoryCommand",
        "CancelOrderCommand": "018f33aa-9e6d-73d8-9dc3-47d6cdcc9c21:CancelOrderCommand",
    }
    assert rejection["duplicateCommandResults"]["RefundPaymentCommand"] == "DUPLICATE_IGNORED"
    assert rejection["duplicateCommandResults"]["ReleaseInventoryCommand"] == "DUPLICATE_IGNORED"
    assert rejection["duplicateCommandResults"]["CancelOrderCommand"] == "DUPLICATE_IGNORED"
    assert rejection["finalPaymentStatus"] == "REFUNDED"
    assert rejection["finalStoreApprovalStatus"] == "REJECTED"
    assert rejection["finalInventory"] == {"availableStock": 10, "reservedStock": 0}
    assert rejection["finalOrderStatus"] == "CANCELLED"

    assert details["duplicateSummary"] == {
        "duplicateEventReplaysIgnored": 3,
        "deterministicProcessManagerReplays": 3,
        "duplicateCommandResults": {
            "ReleaseInventoryCommand": ["DUPLICATE_IGNORED", "DUPLICATE_IGNORED", "DUPLICATE_IGNORED"],
            "RefundPaymentCommand": ["DUPLICATE_IGNORED"],
            "CancelOrderCommand": ["DUPLICATE_IGNORED", "DUPLICATE_IGNORED", "DUPLICATE_IGNORED"],
        },
    }
    json.dumps(result)


def test_compensation_checkout_smoke_cli_outputs_bounded_json() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")

    completed = subprocess.run(
        [sys.executable, "-m", "token_payments", "smoke", "compensation-checkout"],
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
    assert payload["details"]["smoke"]["scenario"] == "compensation-checkout"
    assert payload["details"]["smoke"]["status"] == "passed"
    assert payload["details"]["smoke"]["details"]["cancelOrderHandlerWired"] is True
    assert len(completed.stdout) < 20000

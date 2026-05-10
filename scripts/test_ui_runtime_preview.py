from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_runtime_dispatch_renders_customer_preview_contract_and_scenarios() -> None:
    from token_payments.runtime import dispatch_runtime_command

    result = dispatch_runtime_command(["ui", "customer"])
    payload = result.to_dict()
    preview = payload["details"]["preview"]

    assert result.success is True
    assert payload["command"] == "ui"
    assert preview["view"] == "customer"
    assert preview["route"] == "customer"
    assert preview["contentType"] == "text/html; charset=utf-8"
    assert '<main class="tp-shell tp-checkout" data-view="checkout">' in preview["html"]
    assert preview["contract"] == "CommandDispatchResult.details.preview"
    assert [sample["name"] for sample in preview["samples"]] == [
        "customer-happy-path",
        "customer-tx-submitted-pending-receipt",
        "customer-payment-failed-compensation",
        "customer-payment-expired-compensation",
    ]

    rendered = "\n".join(sample["html"] for sample in preview["samples"])
    assert "OrderApprovedEvent" in rendered
    assert "waiting for receipt" in rendered
    assert "PaymentFailedEvent" in rendered
    assert "PaymentExpiredEvent" in rendered
    assert "ReleaseInventoryCommand PENDING; CancelOrderCommand PENDING" in rendered
    assert "Ledger Mug &lt;sample&gt;" in rendered
    assert "<script" not in rendered.lower()


def test_runtime_dispatch_defaults_to_customer_preview_and_selects_operator_preview() -> None:
    from token_payments.runtime import dispatch_runtime_command

    default_payload = dispatch_runtime_command(["ui"]).to_dict()
    operator_payload = dispatch_runtime_command(["ui", "operator"]).to_dict()
    operator_preview = operator_payload["details"]["preview"]

    assert default_payload["details"]["preview"]["view"] == "customer"
    assert operator_preview["view"] == "operator"
    assert operator_preview["route"] == "operator"
    assert '<main class="tp-shell tp-operator" data-view="operator">' in operator_preview["html"]
    assert "OrderApprovedEvent" in operator_preview["html"]
    assert "normal approved order" in operator_preview["html"]
    assert "PaymentExpiredEvent" in operator_preview["html"]
    assert "Retry candidate" in operator_preview["html"]
    assert "outbox-relay" in operator_preview["html"]
    assert '<span class="tp-badge" data-tone="danger">UNAVAILABLE</span>' in operator_preview["html"]


def test_runtime_dispatch_unknown_ui_view_returns_structured_error() -> None:
    from token_payments.runtime import dispatch_runtime_command

    result = dispatch_runtime_command(["ui", "unknown-view"])
    payload = result.to_dict()

    assert result.success is False
    assert payload["command"] == "ui"
    assert payload["exitCode"] == 64
    assert payload["details"]["error"] == {
        "code": "UNKNOWN_UI_PREVIEW_VIEW",
        "view": "unknown-view",
        "availableViews": ["customer", "operator"],
    }


def test_cli_outputs_bounded_json_preview_without_secret_material() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")
    result = subprocess.run(
        [sys.executable, "-m", "token_payments", "ui", "customer"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    html = payload["details"]["preview"]["html"]

    assert payload["command"] == "ui"
    assert payload["status"] == "SUCCEEDED"
    assert "http.server" not in result.stdout
    assert "uvicorn" not in result.stdout
    assert "<script" not in result.stdout.lower()
    assert "Ledger Mug &lt;sample&gt;" in result.stdout
    for forbidden in ("private_key", "privateKey", "seed phrase", "mnemonic", "secret"):
        assert forbidden not in result.stdout
    assert html.startswith("<!doctype html>")


def test_readmes_document_ui_preview_runtime_contract_and_verification_commands() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    app_readme = (ROOT / "app/README.md").read_text(encoding="utf-8")

    for text in (
        "PYTHONPATH=app python3 -m token_payments ui",
        "PYTHONPATH=app python3 -m token_payments ui customer",
        "PYTHONPATH=app python3 -m token_payments ui operator",
        "scripts/test_ui_runtime_preview.py",
        "CommandDispatchResult.details.preview",
        "customer/operator UI phase",
    ):
        assert text in readme
        assert text in app_readme

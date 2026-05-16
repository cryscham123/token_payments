from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


PUBLIC_EXPORTS = {
    "AVAILABLE_UI_PREVIEW_VIEWS",
    "CheckoutAction",
    "CheckoutOrderItemView",
    "CheckoutTimelineItem",
    "CheckoutViewModel",
    "CopyToken",
    "GasEstimateView",
    "MoneyView",
    "OperatorActionIntent",
    "OperatorDashboardViewModel",
    "OperatorDetailView",
    "OperatorFilterState",
    "OperatorSummaryItem",
    "OperatorTableRow",
    "RenderedHtml",
    "StatusBadge",
    "UI_PREVIEW_CONTRACT",
    "UNKNOWN_UI_PREVIEW_ERROR",
    "UnknownUiPreviewView",
    "checkout_view_from_api_payload",
    "operator_dashboard_from_api_payload",
    "render_checkout_page",
    "render_operator_dashboard",
    "render_status_badge",
    "render_ui_preview",
}

FORBIDDEN_IMPORT_PARTS = (
    ".adapter",
    "postgres",
    "kafka",
    "blockchain",
    "web3",
    "psycopg",
    "requests",
    "token_payments.runtime.observability",
)

BANNED_CSS_PATTERNS = (
    "backdrop-filter",
    "linear-gradient",
    "radial-gradient",
    "gradient",
    "text-shadow",
    "box-shadow: 0 0",
    "#7c3aed",
    "#4f46e5",
)


def test_ui_package_public_exports_cover_renderers_models_and_preview_contract() -> None:
    import token_payments.ui as ui

    exported = set(ui.__all__)

    assert PUBLIC_EXPORTS <= exported
    assert ui.UI_PREVIEW_CONTRACT == "CommandDispatchResult.details.preview"
    assert ui.AVAILABLE_UI_PREVIEW_VIEWS == ("customer", "operator")
    assert all(hasattr(ui, name) for name in PUBLIC_EXPORTS)


def test_renderers_return_html_documents_with_stable_content_type_and_view_markers() -> None:
    from token_payments.ui import (
        CheckoutViewModel,
        OperatorDashboardViewModel,
        render_checkout_page,
        render_operator_dashboard,
    )

    checkout_html = render_checkout_page(
        CheckoutViewModel(
            order_id="order-public",
            tracking_id="tracking-public",
            status="AWAITING_SIGNATURE",
            current_step="AWAITING_SIGNATURE",
        )
    )
    operator_html = render_operator_dashboard(OperatorDashboardViewModel())

    assert checkout_html.content_type == "text/html; charset=utf-8"
    assert operator_html.content_type == "text/html; charset=utf-8"
    assert checkout_html.html.startswith("<!doctype html>")
    assert operator_html.html.startswith("<!doctype html>")
    assert 'data-view="checkout"' in checkout_html.html
    assert 'data-view="operator"' in operator_html.html


def test_ui_preview_dispatch_is_bounded_json_and_handles_unknown_views() -> None:
    from token_payments.runtime import dispatch_runtime_command

    customer = dispatch_runtime_command(["ui", "customer"]).to_dict()
    operator = dispatch_runtime_command(["ui", "operator"]).to_dict()
    unknown = dispatch_runtime_command(["ui", "not-a-view"]).to_dict()

    assert customer["status"] == "SUCCEEDED"
    assert operator["status"] == "SUCCEEDED"
    assert customer["details"]["preview"]["contract"] == "CommandDispatchResult.details.preview"
    assert operator["details"]["preview"]["view"] == "operator"
    assert unknown["status"] == "FAILED"
    assert unknown["exitCode"] == 64
    assert unknown["details"]["error"]["code"] == "UNKNOWN_UI_PREVIEW_VIEW"


def test_ui_rendering_escapes_html_and_redacts_secret_like_values() -> None:
    from token_payments.ui import operator_dashboard_from_api_payload, render_operator_dashboard

    view = operator_dashboard_from_api_payload(
        {
            "workers": [
                {
                    "component": 'worker<script>alert("x")</script>',
                    "state": "UNAVAILABLE",
                    "checkedAt": "2026-05-10T10:00:00+00:00",
                    "details": {
                        "privateKey": "0x" + "11" * 32,
                        "seedPhrase": "never render this phrase",
                    },
                }
            ]
        },
        detail={
            "aggregateId": 'order<script>alert("order")</script>',
            "private_key": "do-not-render",
            "latestEvent": "PaymentFailedEvent",
        },
    )

    html = render_operator_dashboard(view).html

    assert "<script>" not in html
    assert "alert(&quot;x&quot;)" in html
    assert "alert(&quot;order&quot;)" in html
    assert "privateKey=REDACTED" in html
    assert "seedPhrase=REDACTED" in html
    assert "private_key" in html
    assert "do-not-render" not in html
    assert "never render this phrase" not in html


def test_ui_package_import_boundary_stays_framework_and_infrastructure_neutral() -> None:
    ui_files = sorted((ROOT / "app/token_payments/ui").glob("*.py"))
    assert ui_files

    for path in ui_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append("." * node.level + (node.module or ""))

        lowered = "\n".join(imports).lower()
        for forbidden in FORBIDDEN_IMPORT_PARTS:
            assert forbidden not in lowered, f"{path} imports forbidden boundary {forbidden}"


def test_css_tokens_match_ui_guide_and_avoid_banned_visual_patterns() -> None:
    from token_payments.ui.renderers import DEFAULT_CSS

    css = DEFAULT_CSS.lower()

    for token in ("#f7f8fa", "#ffffff", "#d5dbe3", "#111827", "#15803d", "#2563eb", "#b45309", "#b91c1c"):
        assert token in css
    for banned in BANNED_CSS_PATTERNS:
        assert banned not in css
    assert ".tp-table tr" in DEFAULT_CSS
    assert "height: 48px" in DEFAULT_CSS
    assert "@media (max-width: 860px)" in DEFAULT_CSS


def test_cli_preview_outputs_json_without_long_running_server_or_secret_material() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")
    result = subprocess.run(
        [sys.executable, "-m", "token_payments", "ui", "operator"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    output = result.stdout.lower()

    assert payload["command"] == "ui"
    assert payload["details"]["preview"]["view"] == "operator"
    assert "http.server" not in output
    assert "uvicorn" not in output
    for forbidden in ("private_key", "seed phrase", "mnemonic", "secret"):
        assert forbidden not in output


def test_readmes_document_final_ui_verification_and_next_e2e_phase_candidates() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    app_readme = (ROOT / "app/README.md").read_text(encoding="utf-8")

    for text in (
        "scripts/test_ui_public_contracts.py",
        "docker compose integration smoke",
        "happy-path e2e checkout",
        "compensation e2e checkout",
    ):
        assert text in readme
        assert text in app_readme

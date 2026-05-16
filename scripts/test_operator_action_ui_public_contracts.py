from __future__ import annotations

import ast
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


PHASE_8_ACTION_OPERATION_IDS = {
    "cancelOperatorOrder",
    "retryOperatorOutboxMessage",
    "replayOperatorMessage",
}

UI_PUBLIC_ACTION_EXPORTS = {
    "OperatorActionIntent",
    "OperatorDashboardViewModel",
    "operator_dashboard_from_api_payload",
    "render_operator_dashboard",
    "render_ui_preview",
}

FORBIDDEN_UI_IMPORT_ROOTS = {
    "asyncpg",
    "confluent_kafka",
    "docker",
    "dotenv",
    "httpx",
    "kafka",
    "psycopg",
    "psycopg2",
    "requests",
    "sqlalchemy",
    "web3",
}

FORBIDDEN_UI_IMPORTS = {
    "os",
    "socket",
    "subprocess",
    "urllib.request",
    "token_payments.shared.adapter",
    "token_payments.runtime.observability",
}

FORBIDDEN_UI_CALL_NAMES = {
    "open",
    "urlopen",
}

FORBIDDEN_UI_ATTRIBUTE_CALLS = {
    ("os", "getenv"),
    ("os", "environ"),
    ("socket", "create_connection"),
    ("subprocess", "run"),
    ("subprocess", "Popen"),
}

OPERATOR_ACTION_UI_DOC_PHRASES = (
    "Operator Action UI Wiring",
    "operator action UI wiring phase",
    "cancel/retry/replay controls are UI intents",
    "existing framework-neutral operator action endpoint contract",
    "no live operator action execution",
    "does not open DB, Kafka, Docker, Blockchain RPC, or local `.env`",
    "http://127.0.0.1:8765/operator",
    "PYTHONPATH=app python3 scripts/browser_preview_smoke.py",
    "python3 -m pytest scripts/test_operator_action_ui_public_contracts.py scripts/test_operator_action_ui_controls.py scripts/test_operator_action_ui_intents.py scripts/test_operator_action_public_contracts.py scripts/test_browser_preview_public_contracts.py scripts/test_ui_public_contracts.py",
    "python3 scripts/validate_phases.py",
    "ASGI/FastAPI thin adapter",
    "approved live Docker e2e",
    "operator action execution audit persistence",
    "advanced operator filters",
)


def test_ui_public_exports_include_operator_action_intents_and_rendering_surface() -> None:
    import token_payments.ui as ui
    from token_payments.ui import OperatorActionIntent

    exported = set(ui.__all__)

    assert UI_PUBLIC_ACTION_EXPORTS <= exported
    assert ui.OperatorActionIntent is OperatorActionIntent
    assert callable(ui.operator_dashboard_from_api_payload)
    assert callable(ui.render_operator_dashboard)
    assert callable(ui.render_ui_preview)


def test_operator_preview_controls_expose_existing_action_route_manifest_operations() -> None:
    from token_payments.api import OPERATOR_ACTION_HTTP_ROUTES, http_route_manifest
    from token_payments.ui import render_ui_preview

    manifest_by_operation = {entry["operationId"]: entry for entry in http_route_manifest()}
    action_routes = {
        route.operation_id: route
        for route in OPERATOR_ACTION_HTTP_ROUTES.values()
    }
    preview = render_ui_preview("operator")
    controls = _action_controls(str(preview["html"]))

    assert set(action_routes) == PHASE_8_ACTION_OPERATION_IDS
    assert {control["data-operation-id"] for control in controls} == PHASE_8_ACTION_OPERATION_IDS

    for control in controls:
        operation_id = control["data-operation-id"]
        route = action_routes[operation_id]
        manifest_entry = manifest_by_operation[operation_id]

        assert manifest_entry == {
            "method": route.method,
            "path": route.path,
            "operationId": operation_id,
        }
        assert control["data-method"] == route.method
        assert _matches_route_template(control["data-endpoint"], route.path)

        body_template = json.loads(control["data-body-template"])
        assert body_template["reason"]
        assert body_template["idempotencyKey"]
        assert body_template["parameters"]["source"] == "operator-dashboard"


def test_operator_browser_preview_html_has_action_controls_without_auto_execution_or_external_origins() -> None:
    from token_payments.runtime.browser_preview import render_browser_preview_document

    html = render_browser_preview_document("operator")
    controls = _action_controls(html)

    assert controls
    assert {control["data-operation-id"] for control in controls} == PHASE_8_ACTION_OPERATION_IDS
    assert 'data-region="operator-actions"' in html
    assert 'type="button"' in html
    assert "<script" not in html.lower()
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "EventSource",
        "navigator.sendBeacon",
        "action=",
        "formaction=",
        "http://",
        "https://",
        "ws://",
        "wss://",
    ):
        assert forbidden not in html


def test_ui_source_stays_inside_preview_boundary_without_live_infrastructure_access() -> None:
    ui_files = sorted((ROOT / "app/token_payments/ui").glob("*.py"))
    assert ui_files

    violations: dict[str, list[str]] = {}
    for path in ui_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = sorted(
            _forbidden_imports(tree)
            | _forbidden_calls(tree)
            | _forbidden_adapter_imports(tree)
        )
        if found:
            violations[str(path.relative_to(ROOT))] = found

    assert violations == {}


def test_readmes_document_operator_action_ui_wiring_scope_commands_and_no_live_boundary() -> None:
    for path in (ROOT / "README.md", ROOT / "app" / "README.md"):
        text = path.read_text(encoding="utf-8")
        section = _section(text, "## Operator Action UI Wiring")

        assert section, f"{path.relative_to(ROOT)} must document Operator Action UI Wiring"
        for phrase in OPERATOR_ACTION_UI_DOC_PHRASES:
            assert phrase in section, f"{path.relative_to(ROOT)} missing {phrase!r}"


def test_phase_12_metadata_closes_operator_action_ui_wiring_public_contracts() -> None:
    from scripts.validate_phases import validate

    phase_index = json.loads((ROOT / "phases/12-operator-action-ui-wiring/index.json").read_text(encoding="utf-8"))
    top_index = json.loads((ROOT / "phases/index.json").read_text(encoding="utf-8"))
    step2 = next(step for step in phase_index["steps"] if step["step"] == 2)
    phase12 = next(phase for phase in top_index["phases"] if phase["dir"] == "12-operator-action-ui-wiring")

    assert validate(ROOT) == []
    assert step2["status"] == "completed"
    summary = step2.get("summary", "")
    assert len(summary) >= 80
    for term in (
        "Operator Action UI Wiring",
        "public contract",
        "README",
        "scripts/test_operator_action_ui_public_contracts.py",
        "no-live execution boundary",
    ):
        assert term in summary

    assert phase12["status"] == "completed"
    assert phase12.get("completed_at")


def _matches_route_template(endpoint: str, template: str) -> bool:
    pattern = "^" + re.escape(template).replace(re.escape("{orderId}"), "[^/]+").replace(
        re.escape("{messageId}"),
        "[^/]+",
    ) + "$"
    return bool(re.match(pattern, endpoint))


def _forbidden_imports(tree: ast.AST) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add("." * node.level + node.module)

    forbidden: set[str] = set()
    for module in imported:
        root = module.split(".", 1)[0]
        if root in FORBIDDEN_UI_IMPORT_ROOTS or module in FORBIDDEN_UI_IMPORTS:
            forbidden.add(f"import:{module}")
    return forbidden


def _forbidden_adapter_imports(tree: ast.AST) -> set[str]:
    forbidden: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            if module.startswith("token_payments.contexts.") and ".adapter" in module:
                forbidden.add(f"import:{module}")
    return forbidden


def _forbidden_calls(tree: ast.AST) -> set[str]:
    forbidden: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call = node.func
        if isinstance(call, ast.Name) and call.id in FORBIDDEN_UI_CALL_NAMES:
            forbidden.add(f"call:{call.id}")
        elif isinstance(call, ast.Attribute):
            owner = call.value
            if isinstance(owner, ast.Name) and (owner.id, call.attr) in FORBIDDEN_UI_ATTRIBUTE_CALLS:
                forbidden.add(f"call:{owner.id}.{call.attr}")
    return forbidden


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start == -1:
        return ""
    next_heading = text.find("\n## ", start + len(heading))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]


def _action_controls(html: str) -> list[dict[str, str]]:
    parser = _ControlParser()
    parser.feed(html)
    return [
        attrs
        for attrs in parser.controls
        if attrs.get("data-operation-id") in PHASE_8_ACTION_OPERATION_IDS
    ]


class _ControlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.controls: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "button":
            return
        mapped = {key: value if value is not None else "" for key, value in attrs}
        if "data-action-id" in mapped:
            self.controls.append(mapped)

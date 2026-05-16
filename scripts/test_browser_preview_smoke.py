from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "browser_preview_smoke.py"
sys.path.insert(0, str(ROOT / "app"))


def test_browser_preview_smoke_script_uses_only_stdlib_and_local_runtime() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    stdlib_paths = {Path(sysconfig.get_path(name)).resolve() for name in ("stdlib", "platstdlib")}
    third_party_imports: set[str] = set()

    for module in _imported_modules(tree):
        root = module.split(".", 1)[0]
        if root == "token_payments":
            continue
        try:
            spec = __import__(root).__spec__
        except ModuleNotFoundError:
            third_party_imports.add(module)
            continue
        if spec is None or spec.origin in {None, "built-in", "frozen"}:
            continue
        origin = Path(spec.origin).resolve()
        if not any(origin.is_relative_to(path) for path in stdlib_paths):
            third_party_imports.add(module)

    assert third_party_imports == set()

    source = SCRIPT.read_text(encoding="utf-8").lower()
    for blocked in _blocked_terms():
        assert blocked not in source


def test_default_cli_starts_ephemeral_preview_server_and_outputs_manual_checklist() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        env={"PYTHONPATH": "app"},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    payload = json.loads(completed.stdout)

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert payload["contract"] == "token-payments.browser-preview-smoke.v1"
    assert payload["status"] == "PASSED"
    assert isinstance(payload["serverStarted"], bool)
    assert payload["browserReady"] is True
    assert payload["openBrowserRequested"] is False
    assert payload["baseUrl"].startswith("http://127.0.0.1:")
    assert set(payload["manualBrowserUrls"]) == {"customer", "operator", "health", "routes"}
    assert len(completed.stdout) < 12000

    for url in payload["manualBrowserUrls"].values():
        parsed = urlparse(url)
        assert parsed.scheme == "http"
        assert parsed.hostname in {"127.0.0.1", "localhost"}
        assert parsed.port is not None

    checks = {check["name"]: check for check in payload["checks"]}
    assert set(checks) == {"root-html", "customer-html", "operator-html", "health-json", "routes-json"}
    for check in checks.values():
        assert set(check) == {"name", "url", "statusCode", "passed", "summary"}
        assert check["url"].startswith(payload["baseUrl"])
        assert check["statusCode"] == 200
        assert check["passed"] is True
        assert check["summary"]

    assert "data-view=\"checkout\"" in checks["customer-html"]["summary"]
    assert "Checkout" in checks["customer-html"]["summary"]
    assert "Sign Payment" in checks["customer-html"]["summary"]
    assert "data-view=\"operator\"" in checks["operator-html"]["summary"]
    assert "Operator Dashboard" in checks["operator-html"]["summary"]
    assert "Retry candidate" in checks["operator-html"]["summary"]
    assert "cancelOperatorOrder" in checks["operator-html"]["summary"]
    assert "retryOperatorOutboxMessage" in checks["operator-html"]["summary"]
    assert "replayOperatorMessage" in checks["operator-html"]["summary"]
    assert "localEnv" not in json.dumps(payload)


def test_base_url_mode_uses_existing_server_without_starting_a_new_one(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_smoke_module()

    def fail_build(*_args: Any, **_kwargs: Any) -> object:
        raise AssertionError("base-url mode must not start a new preview server")

    base_url = "http://127.0.0.1:9999"
    monkeypatch.setattr(module, "build_browser_preview_server", fail_build)
    monkeypatch.setattr(module, "_fetch", _passing_fetch)
    exit_code, payload = module.run_smoke(base_url=base_url)

    assert exit_code == 0
    assert payload["status"] == "PASSED"
    assert payload["serverStarted"] is False
    assert payload["baseUrl"] == base_url
    assert all(check["passed"] is True for check in payload["checks"])


def test_open_browser_mode_uses_injected_opener_without_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_smoke_module()

    opened_urls: list[str] = []

    def fake_open(url: str) -> bool:
        opened_urls.append(url)
        return True

    monkeypatch.setattr(module, "_fetch", _passing_fetch)
    exit_code, payload = module.run_smoke(
        base_url="http://127.0.0.1:9999",
        open_browser=True,
        browser_open=fake_open,
    )

    assert exit_code == 0
    assert payload["status"] == "PASSED"
    assert payload["openBrowserRequested"] is True
    assert opened_urls == [payload["manualBrowserUrls"]["customer"], payload["manualBrowserUrls"]["operator"]]


def test_open_browser_errors_do_not_hide_smoke_results(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_smoke_module()

    def fail_open(_url: str) -> bool:
        raise RuntimeError("window manager unavailable")

    monkeypatch.setattr(module, "_fetch", _passing_fetch)
    exit_code, payload = module.run_smoke(
        base_url="http://127.0.0.1:9999",
        open_browser=True,
        browser_open=fail_open,
    )

    assert exit_code == 0
    assert payload["status"] == "PASSED"
    assert payload["browserReady"] is True
    assert payload["openBrowserRequested"] is True
    assert payload["browserOpenErrors"] == 2


def test_failed_route_contract_returns_exit_code_one_and_failed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_smoke_module()

    def fake_fetch(url: str) -> dict[str, object]:
        if url.endswith("/customer"):
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "text/html; charset=utf-8"},
                "body": "<!doctype html><main><h1>Checkout</h1></main>",
            }
        if url.endswith("/operator"):
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "text/html; charset=utf-8"},
                "body": '<!doctype html><main data-view="operator"><h1>Operator Dashboard</h1></main>',
            }
        if url.endswith("/healthz"):
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json; charset=utf-8"},
                "body": '{"component":"browser-preview","status":"ok","views":["customer","operator"]}',
            }
        if url.endswith("/api/routes"):
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json; charset=utf-8"},
                "body": '[{"method":"GET","path":"/healthz"}]',
            }
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "body": '<!doctype html><main data-view="checkout"><h1>Checkout</h1></main>',
        }

    monkeypatch.setattr(module, "_fetch", fake_fetch)
    exit_code, payload = module.run_smoke(base_url="http://127.0.0.1:9999")

    assert exit_code == 1
    assert payload["status"] == "FAILED"
    assert payload["browserReady"] is False
    customer_check = next(check for check in payload["checks"] if check["name"] == "customer-html")
    assert customer_check["passed"] is False
    assert "data-view=\"checkout\"" in customer_check["summary"]


def _load_smoke_module() -> Any:
    spec = importlib.util.spec_from_file_location("browser_preview_smoke_under_test", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _blocked_terms() -> tuple[str, ...]:
    return (
        "docker",
        "kafka",
        "postgres",
        "blockchain rpc",
        ".env",
        "cla" + "ude",
        "anth" + "ropic",
        "private" + "_key",
        "seed" + " phrase",
    )


def _passing_fetch(url: str) -> dict[str, object]:
    if url.endswith("/operator"):
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "body": (
                '<!doctype html><main data-view="operator"><h1>Operator Dashboard</h1>'
                "Retry candidate cancelOperatorOrder retryOperatorOutboxMessage "
                "replayOperatorMessage outbox-relay</main>"
            ),
        }
    if url.endswith("/healthz"):
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": '{"component":"browser-preview","status":"ok","views":["customer","operator"]}',
        }
    if url.endswith("/api/routes"):
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": '[{"method":"POST","path":"/orders"},{"method":"GET","path":"/operator/dashboard"}]',
        }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": (
            '<!doctype html><main data-view="checkout"><h1>Checkout</h1>Sign Payment '
            "PaymentConfirmedEvent PaymentFailedEvent PaymentExpiredEvent</main>"
        ),
    }

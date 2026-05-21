from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

FORBIDDEN_SERVER_IMPORT_ROOTS = {
    "asyncpg",
    "confluent_kafka",
    "docker",
    "dotenv",
    "kafka",
    "psycopg",
    "psycopg2",
    "requests",
    "socket",
    "starlette",
    "uvicorn",
    "web3",
}


def test_default_serve_api_still_returns_bounded_preview_without_starting_server() -> None:
    payload = _run_cli("serve-api")
    http = payload["details"]["http"]

    assert payload["status"] == "SUCCEEDED"
    assert payload["summary"].endswith("server was not started")
    assert http["serverStarted"] is False
    assert http["longRunning"] is False
    assert http["routeCount"] == 33


def test_live_dry_run_returns_server_plan_without_binding_network_port() -> None:
    payload = _run_cli("serve-api", "--live", "--dry-run")
    plan = payload["details"]["liveApiServer"]

    assert payload["status"] == "SUCCEEDED"
    assert "dry run" in payload["summary"]
    assert plan["contract"] == "token-payments.live-api-server.plan.v1"
    assert plan["host"] == "0.0.0.0"
    assert plan["port"] == 8000
    assert plan["appFactory"] == "token_payments.runtime.api_server.build_live_asgi_application"
    assert plan["routeCount"] == 33
    assert plan["requiresConfirmation"] is True
    assert plan["serverStarted"] is False
    assert plan["longRunning"] is True
    assert plan["session"]["envBackedValidationStatus"] == "valid"
    assert plan["session"]["activeKeyId"] == "<redacted>"
    assert plan["guards"] == {
        "cookieSession": True,
        "csrf": True,
        "cors": True,
        "requestBodyLimit": True,
    }
    assert plan["redaction"] == {
        "secretsRedacted": True,
        "tokenAddressesRedacted": True,
    }
    assert "postgres" in {group["name"] for group in plan["requiredDependencyGroups"]}
    assert "uvicornAvailable" in plan["optionalDependencies"]
    assert "fastapiAvailable" in plan["optionalDependencies"]


def test_live_without_confirmation_returns_bounded_refusal_json_and_starts_no_server() -> None:
    payload = _run_cli("serve-api", "--live")
    result = payload["details"]["liveApiServer"]

    assert payload["status"] == "FAILED"
    assert payload["exitCode"] == 0
    assert "confirmation required" in payload["summary"]
    assert result["status"] == "refused"
    assert result["serverStarted"] is False
    assert result["longRunning"] is True
    assert result["error"]["code"] == "LIVE_API_CONFIRMATION_REQUIRED"


def test_confirmed_live_path_uses_injected_runner_and_does_not_import_uvicorn() -> None:
    from token_payments.runtime import LiveRuntimeConfig, LiveRuntimeDependencies
    from token_payments.runtime.api_server import run_live_api_server

    calls: list[dict[str, Any]] = []

    def fake_runner(app: Any, *, host: str, port: int) -> dict[str, Any]:
        calls.append({"app": app, "host": host, "port": port})
        return {"serverStarted": True, "runner": "fake"}

    before_modules = set(sys.modules)
    result = run_live_api_server(
        config=LiveRuntimeConfig.from_env(_live_env()),
        dependencies=_live_dependencies(),
        confirmed=True,
        runner=fake_runner,
    )
    imported_roots = {name.partition(".")[0] for name in set(sys.modules) - before_modules}

    assert result.status == "started"
    assert result.server_started is True
    assert result.long_running is True
    assert calls and calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 9001
    assert "uvicorn" not in imported_roots


def test_live_server_entrypoint_source_avoids_eager_drivers_frameworks_and_sockets() -> None:
    imported_roots = _imported_roots(ROOT / "app/token_payments/runtime/api_server.py")

    assert imported_roots.isdisjoint(FORBIDDEN_SERVER_IMPORT_ROOTS)


def _run_cli(*args: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")
    completed = subprocess.run(
        [sys.executable, "-m", "token_payments", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    return json.loads(completed.stdout)


def _live_env() -> dict[str, str]:
    return {
        "RUNTIME_API_HOST": "127.0.0.1",
        "RUNTIME_API_PORT": "9001",
        "RUNTIME_ENVIRONMENT": "live",
        "SESSION_ACTIVE_KEY_ID": "live-key-1",
        "SESSION_SIGNING_KEYS": "live-key-1=this_is_a_live_session_signing_secret_32_bytes",
        "CSRF_ACTIVE_KEY_ID": "csrf-live-1",
        "CSRF_SIGNING_KEY": "this_is_a_live_csrf_signing_secret_32_bytes",
    }


def _live_dependencies() -> Any:
    from token_payments.runtime import LiveRuntimeDependencies

    return LiveRuntimeDependencies(
        postgres_session_factory=lambda: object(),
        kafka_producer=object(),
        wallet_signature_client=object(),
        blockchain_client=object(),
        clock=_Clock(),
        id_generator=_IdGenerator(),
    )


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".", 1)[0])
    return roots


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 5, 17, 10, 0, tzinfo=UTC)


class _IdGenerator:
    def new_id(self) -> str:
        return "generated-id"

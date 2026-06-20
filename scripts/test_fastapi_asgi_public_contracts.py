from __future__ import annotations

import ast
import builtins
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

ASGI_FASTAPI_EXPORTS = {
    "AsgiApplication",
    "AsgiReceive",
    "AsgiScope",
    "AsgiSend",
    "FastApiAdapterUnavailable",
    "build_asgi_app",
    "build_fastapi_app",
    "is_fastapi_available",
}

OPERATOR_ACTION_OPERATION_IDS = {
    "cancelOperatorOrder",
    "retryOperatorOutboxMessage",
    "replayOperatorMessage",
}

FORBIDDEN_RUNTIME_IMPORT_ROOTS = {
    "asyncpg",
    "confluent_kafka",
    "docker",
    "dotenv",
    "fastapi",
    "kafka",
    "psycopg",
    "psycopg2",
    "requests",
    "socket",
    "sqlalchemy",
    "starlette",
    "uvicorn",
    "web3",
}

ASGI_FASTAPI_DOC_PHRASES = (
    "ASGI/FastAPI Thin Adapter",
    "existing route manifest",
    "facade contract",
    "optional FastAPI dependency",
    "build_asgi_app",
    "build_fastapi_app",
    "does not start a server",
    "no-server-start boundary",
    "manual production serve",
    "python3 -m pytest scripts/test_fastapi_asgi_public_contracts.py scripts/test_fastapi_thin_adapter.py scripts/test_asgi_adapter_contract_foundation.py scripts/test_wsgi_runtime_preview.py scripts/test_api_worker_runtime_public_contracts.py scripts/test_backend_only_public_contracts.py",
    "PYTHONPATH=app python3 -m token_payments api",
    "PYTHONPATH=app python3 -m token_payments serve-api",
    "python3 scripts/validate_phases.py",
    "live API runtime composition",
    "Postman Docker API readiness",
    "FastAPI optional dependency live smoke",
)


def test_api_public_exports_include_asgi_fastapi_adapter_surface() -> None:
    import token_payments.api as api

    exported = set(api.__all__)

    assert ASGI_FASTAPI_EXPORTS <= exported
    assert all(hasattr(api, name) for name in ASGI_FASTAPI_EXPORTS)
    assert api.build_asgi_app.__module__ == "token_payments.api.asgi"
    assert api.build_fastapi_app.__module__ == "token_payments.api.fastapi"


def test_api_and_serve_api_previews_include_asgi_fastapi_metadata_and_existing_manifest() -> None:
    from token_payments.api import http_route_manifest

    expected_manifest = list(http_route_manifest())
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")

    for command in ("api", "serve-api"):
        completed = subprocess.run(
            [sys.executable, "-m", "token_payments", command],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )

        assert completed.returncode == 0, completed.stderr
        assert completed.stderr == ""
        payload = json.loads(completed.stdout)
        http = payload["details"]["http"]

        assert payload["command"] == command
        assert payload["status"] == "SUCCEEDED"
        assert "server was not started" in payload["summary"]
        assert http["adapter"] == "framework-neutral-wsgi"
        assert http["longRunning"] is False
        assert http["serverStarted"] is False
        assert http["routeCount"] == 57
        assert http["routes"] == expected_manifest
        assert http["wsgiFactory"] == "token_payments.api.build_wsgi_app"
        assert http["asgiFactory"] == "token_payments.api.build_asgi_app"
        assert http["fastapiFactory"] == "token_payments.api.build_fastapi_app"
        assert isinstance(http["fastapiAvailable"], bool)

        if http["fastapiAvailable"]:
            assert http["fastapiUnavailableReason"] is None
        else:
            assert "optional dependency `fastapi` is not installed" in http["fastapiUnavailableReason"]
            assert "pip install fastapi" in http["fastapiUnavailableReason"]

        assert {entry["operationId"] for entry in http["routes"][-3:]} == OPERATOR_ACTION_OPERATION_IDS


def test_preview_reports_fastapi_unavailable_without_building_or_starting_an_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import token_payments.api.fastapi as fastapi_adapter
    from token_payments.runtime import ContractRuntimeContainer

    real_find_spec = fastapi_adapter.importlib.util.find_spec

    def fake_find_spec(name: str, package: str | None = None) -> Any:
        if name == "fastapi":
            return None
        return real_find_spec(name, package)

    def fail_build_fastapi_app(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("preview must not build a FastAPI app")

    monkeypatch.setattr(fastapi_adapter.importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(fastapi_adapter, "build_fastapi_app", fail_build_fastapi_app)

    payload = ContractRuntimeContainer().dispatch_command("api").to_dict()
    http = payload["details"]["http"]

    assert payload["status"] == "SUCCEEDED"
    assert http["serverStarted"] is False
    assert http["fastapiAvailable"] is False
    assert "optional dependency `fastapi` is not installed" in http["fastapiUnavailableReason"]
    assert "pip install fastapi" in http["fastapiUnavailableReason"]


def test_api_preview_and_smoke_registry_avoid_live_infrastructure_access(monkeypatch: pytest.MonkeyPatch) -> None:
    import token_payments.api  # noqa: F401
    import token_payments.runtime.smoke  # noqa: F401
    from token_payments.runtime import dispatch_runtime_command

    real_open = builtins.open
    real_path_read_text = Path.read_text

    def guarded_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if _is_live_infrastructure_path(file):
            raise AssertionError(f"preview must not read live infrastructure file {file!r}")
        return real_open(file, *args, **kwargs)

    def guarded_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if _is_live_infrastructure_path(self):
            raise AssertionError(f"preview must not read live infrastructure file {str(self)!r}")
        return real_path_read_text(self, *args, **kwargs)

    def fail_socket(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("preview must not create or bind network sockets")

    def fail_subprocess(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("preview must not execute Docker, Kafka, database, or RPC commands")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(socket, "socket", fail_socket)
    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    monkeypatch.setattr(subprocess, "Popen", fail_subprocess)

    api_preview = dispatch_runtime_command(["api"]).to_dict()
    smoke_registry = dispatch_runtime_command(["smoke"]).to_dict()

    assert api_preview["details"]["http"]["serverStarted"] is False
    assert api_preview["details"]["http"]["longRunning"] is False
    assert smoke_registry["details"]["smoke"]["availableScenarios"]
    assert smoke_registry["summary"].startswith("listed ")


def test_runtime_preview_source_has_no_server_or_external_client_imports() -> None:
    imported = _external_imported_modules(ROOT / "app/token_payments/runtime/entrypoint.py")

    assert imported.isdisjoint(FORBIDDEN_RUNTIME_IMPORT_ROOTS)


def test_readmes_document_asgi_fastapi_thin_adapter_scope_commands_and_next_candidates() -> None:
    for path in (ROOT / "app" / "README.md",):
        section = _section(path.read_text(encoding="utf-8"), "## ASGI/FastAPI Thin Adapter")

        assert section, f"{path.relative_to(ROOT)} must document ASGI/FastAPI Thin Adapter"
        for phrase in ASGI_FASTAPI_DOC_PHRASES:
            assert phrase in section, f"{path.relative_to(ROOT)} missing {phrase!r}"


def test_phase_13_metadata_closes_fastapi_asgi_public_contracts() -> None:
    from scripts.validate_phases import validate

    phase_index = json.loads((ROOT / "phases/13-fastapi-asgi-adapter/index.json").read_text(encoding="utf-8"))
    top_index = json.loads((ROOT / "phases/index.json").read_text(encoding="utf-8"))
    step2 = next(step for step in phase_index["steps"] if step["step"] == 2)
    phase13 = next(phase for phase in top_index["phases"] if phase["dir"] == "13-fastapi-asgi-adapter")

    assert validate(ROOT) == []
    assert step2["status"] == "completed"
    summary = step2.get("summary", "")
    assert len(summary) >= 80
    for term in (
        "ASGI/FastAPI",
        "runtime preview",
        "public contract",
        "README",
        "scripts/test_fastapi_asgi_public_contracts.py",
        "no-server-start",
    ):
        assert term in summary

    assert phase13["status"] == "completed"
    assert phase13.get("completed_at")


def _is_live_infrastructure_path(value: Any) -> bool:
    try:
        text = str(value)
    except Exception:
        return False
    return any(
        marker in text
        for marker in (
            "/.env",
            ".env",
            "docker-compose.yml",
            "app/postgres/",
            "test_network",
        )
    )


def _external_imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start == -1:
        return ""
    next_heading = text.find("\n## ", start + len(heading))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]

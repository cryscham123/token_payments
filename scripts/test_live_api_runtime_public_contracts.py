from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

RUNTIME_LIVE_EXPORTS = {
    "LiveRuntimeConfig",
    "LiveRuntimeDependencies",
    "build_live_api_router",
    "build_live_asgi_application",
    "build_live_system_router",
    "describe_live_api_server_plan",
    "run_live_api_server",
    "CookieSessionTransport",
    "SessionKeyRing",
    "CorsPolicy",
    "CsrfTokenService",
    "RequestGuard",
    "ReadinessProbeResult",
    "RuntimeReadinessStatus",
    "AccessLogEvent",
}

FORBIDDEN_RUNTIME_IMPORT_ROOTS = {
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


def test_runtime_public_exports_include_live_cookie_security_server_and_readiness_surface() -> None:
    import token_payments.runtime as runtime

    exported = set(runtime.__all__)

    assert RUNTIME_LIVE_EXPORTS <= exported
    assert all(hasattr(runtime, name) for name in RUNTIME_LIVE_EXPORTS)
    assert runtime.build_live_asgi_application.__module__ == "token_payments.runtime.api_server"
    assert runtime.ReadinessProbeResult.__module__ == "token_payments.runtime.observability"
    assert runtime.RequestGuard.__module__ == "token_payments.runtime.security"


def test_runtime_commands_keep_bounded_json_no_server_contracts() -> None:
    api = _run_cli("api")
    serve = _run_cli("serve-api")
    dry_run = _run_cli("serve-api", "--live", "--dry-run")
    refused = _run_cli("serve-api", "--live")

    assert api["details"]["http"]["serverStarted"] is False
    assert api["details"]["http"]["longRunning"] is False
    assert serve["details"]["http"]["routeCount"] == 55
    assert dry_run["details"]["liveApiServer"]["routeCount"] == 55
    assert dry_run["details"]["liveApiServer"]["appFactory"] == (
        "token_payments.runtime.api_server.build_live_asgi_application"
    )
    assert dry_run["details"]["liveApiServer"]["guards"] == {
        "cookieSession": True,
        "csrf": True,
        "cors": True,
        "requestBodyLimit": True,
    }
    assert dry_run["details"]["liveApiServer"]["readiness"]["healthRoute"] == "/healthz"
    assert dry_run["details"]["liveApiServer"]["readiness"]["readinessRoute"] == "/readyz"
    assert dry_run["details"]["liveApiServer"]["readiness"]["idempotencyHeader"] == "Idempotency-Key"
    assert dry_run["details"]["liveApiServer"]["session"]["activeKeyId"] == "<redacted>"
    assert dry_run["details"]["liveApiServer"]["session"]["envBackedValidationStatus"] == "valid"
    assert dry_run["details"]["liveApiServer"]["requiresConfirmation"] is True
    assert dry_run["details"]["liveApiServer"]["serverStarted"] is False
    assert dry_run["details"]["liveApiServer"]["redaction"] == {
        "secretsRedacted": True,
        "tokenAddressesRedacted": True,
        "clientIpLogged": False,
        "forwardedClientIpHeaders": False,
        "nonIpProxyMetadataAccepted": True,
    }
    assert "postgres" in {group["name"] for group in dry_run["details"]["liveApiServer"]["requiredDependencyGroups"]}
    assert refused["status"] == "FAILED"
    assert refused["exitCode"] == 0
    assert refused["details"]["liveApiServer"]["status"] == "refused"
    assert refused["details"]["liveApiServer"]["error"]["code"] == "LIVE_API_CONFIRMATION_REQUIRED"


def test_live_config_rejects_placeholder_session_keys_and_dry_run_redacts_validation_details() -> None:
    from token_payments.runtime import LiveRuntimeConfig, describe_live_api_server_plan

    with pytest.raises(ValueError, match="placeholder"):
        LiveRuntimeConfig.from_env(
            {
                "RUNTIME_ENVIRONMENT": "live",
                "SESSION_ACTIVE_KEY_ID": "placeholder",
                "SESSION_SIGNING_KEYS": "placeholder=replace_with_local_dev_only_session_signing_key",
            }
        )

    plan = describe_live_api_server_plan(
        env={
            "RUNTIME_ENVIRONMENT": "live",
            "SESSION_ACTIVE_KEY_ID": "placeholder",
            "SESSION_SIGNING_KEYS": "placeholder=replace_with_local_dev_only_session_signing_key",
        }
    ).to_dict()
    encoded = json.dumps(plan, sort_keys=True)

    assert plan["session"]["envBackedValidationStatus"] == "invalid"
    assert plan["session"]["activeKeyId"] == "<redacted>"
    assert "replace_with_local_dev_only_session_signing_key" not in encoded


def test_runtime_sources_keep_driver_framework_and_socket_imports_lazy() -> None:
    for path in (
        ROOT / "app/token_payments/runtime/api_server.py",
        ROOT / "app/token_payments/runtime/entrypoint.py",
        ROOT / "app/token_payments/runtime/composition.py",
        ROOT / "app/token_payments/runtime/security.py",
        ROOT / "app/token_payments/runtime/session_transport.py",
    ):
        assert _imported_roots(path).isdisjoint(FORBIDDEN_RUNTIME_IMPORT_ROOTS), path


def test_readmes_and_api_spec_document_live_runtime_boundaries_and_next_phase() -> None:
    required_phrases = (
        "Live API Runtime Composition",
        "serve-api --live --dry-run",
        "serve-api --live --confirm-live-api",
        "no-server-start",
        "/healthz",
        "/readyz",
        "Idempotency-Key",
        "Postman",
    )

    for path in (ROOT / "app/README.md", ROOT / "docs/API_SPEC.md"):
        text = path.read_text(encoding="utf-8")
        for phrase in required_phrases:
            assert phrase in text, f"{path.relative_to(ROOT)} missing {phrase!r}"


def test_phase_14_metadata_closes_live_api_runtime_composition_public_contracts() -> None:
    from scripts.validate_phases import validate

    phase_index = json.loads((ROOT / "phases/14-live-api-runtime-composition/index.json").read_text(encoding="utf-8"))
    top_index = json.loads((ROOT / "phases/index.json").read_text(encoding="utf-8"))
    phase14 = next(phase for phase in top_index["phases"] if phase["dir"] == "14-live-api-runtime-composition")

    assert validate(ROOT) == []
    assert phase14["status"] == "completed"
    assert all(step["status"] == "completed" for step in phase_index["steps"])
    for step in phase_index["steps"]:
        assert len(step.get("summary", "")) >= 80
    assert "public contract" in phase_index["steps"][-1]["summary"]


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


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".", 1)[0])
    return roots

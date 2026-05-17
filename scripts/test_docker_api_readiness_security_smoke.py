from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))

import docker_live_smoke


EXPECTED_API_READINESS_ORDER = [
    "api-compose-config",
    "build-api-service",
    "start-infrastructure",
    "start-api-service",
    "validate-session-signing-keys",
    "healthz",
    "readyz",
    "auth-cookie-flow",
    "expired-token-rejected",
    "invalid-signature-rejected",
    "csrf-failure",
    "csrf-success",
    "cors-preflight",
    "oversized-body",
    "malformed-json",
    "idempotency-duplicate",
    "checkout-happy-path",
    "operator-action-smoke",
]
REDACTED_SESSION_KEY = "local-session-signing-secret"
REDACTED_CSRF_KEY = "local-csrf-signing-secret"
REDACTED_SIGNED_TOKEN = "aaaaaaaaaa.bbbbbbbbbb.cccccccccc"
REDACTED_CSRF_HEADER = "csrf-secret-header-value"


def test_api_readiness_plan_has_bounded_security_order_and_no_live_side_effects() -> None:
    payload = docker_live_smoke.build_api_readiness_plan()

    assert payload["contract"] == "token-payments.postman-docker-api-readiness.plan.v1"
    assert payload["scenario"] == "postman-docker-api-readiness"
    assert payload["mode"] == "plan"
    assert payload["status"] == "planned"
    assert payload["dockerStarted"] is False
    assert payload["networkCalls"] is False
    assert payload["requiredServices"] == ["postgres", "kafka", "test_network", "token_payments_api"]

    commands = payload["commandSequence"]
    assert [command["name"] for command in commands] == EXPECTED_API_READINESS_ORDER
    for command in commands:
        assert isinstance(command["argv"], list)
        assert command["argv"]
        assert command["display"] == shlex.join(command["argv"])
        assert command["shell"] is False
        assert command["category"] in {"docker", "security", "http", "postman"}

    cleanup = payload["cleanupCommand"]
    assert cleanup["argv"] == ["docker", "compose", "--env-file", ".env", "down"]
    assert cleanup["shell"] is False
    assert payload["redactionPolicy"]["rawSecretValuesCommitted"] is False
    assert {"session signing key", "signed session token", "cookie header", "CSRF token"} <= set(
        payload["redactionPolicy"]["redacts"]
    )


def test_api_readiness_execute_without_confirmation_rejects_before_subprocess(
    monkeypatch: Any, capsys: Any
) -> None:
    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess.run must not be called without explicit live confirmation")

    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fail_run)

    exit_code = docker_live_smoke.main(["--api-readiness", "--execute"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["contract"] == "token-payments.postman-docker-api-readiness.plan.v1"
    assert payload["mode"] == "execute"
    assert payload["status"] == "error"
    assert payload["dockerStarted"] is False
    assert payload["networkCalls"] is False
    assert payload["error"]["code"] == "LIVE_API_SMOKE_CONFIRMATION_REQUIRED"


def test_api_readiness_live_execution_path_is_injectable_bounded_and_redacted(
    tmp_path: Path, monkeypatch: Any
) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            (
                f"SESSION_SIGNING_KEYS=local-dev:{REDACTED_SESSION_KEY}",
                f"CSRF_SIGNING_KEY={REDACTED_CSRF_KEY}",
            )
        ),
        encoding="utf-8",
    )
    docker_calls: list[str] = []
    http_calls: list[str] = []

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("test must use injected runners instead of real Docker/API/network")

    def fake_command_runner(name: str, argv: tuple[str, ...], *_args: Any) -> dict[str, Any]:
        docker_calls.append(name)
        return {
            "exitCode": 0,
            "stdout": (
                f"{name} ok {REDACTED_SESSION_KEY} access_token={REDACTED_SIGNED_TOKEN}; "
                f"csrf_token={REDACTED_CSRF_HEADER}"
            ),
            "stderr": "",
            "timedOut": False,
            "argvEcho": list(argv),
        }

    def fake_http_client(name: str, argv: tuple[str, ...], *_args: Any) -> dict[str, Any]:
        http_calls.append(name)
        return {
            "exitCode": 0,
            "stdout": (
                f"{name} ok {REDACTED_CSRF_KEY} X-CSRF-Token: {REDACTED_CSRF_HEADER}\n"
                f"Cookie: access_token={REDACTED_SIGNED_TOKEN}; csrf_token={REDACTED_CSRF_HEADER}"
            ),
            "stderr": f"token {REDACTED_SIGNED_TOKEN}",
            "timedOut": False,
            "argvEcho": list(argv),
        }

    monkeypatch.setattr(docker_live_smoke, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fail_run)

    exit_code, payload = docker_live_smoke.run_api_readiness_execution(
        ".env",
        confirmed=True,
        command_runner=fake_command_runner,
        http_client=fake_http_client,
    )
    payload_text = json.dumps(payload, sort_keys=True)

    assert exit_code == 0
    assert payload["status"] == "success"
    assert payload["dockerStarted"] is True
    assert payload["networkCalls"] is True
    assert payload["executedSteps"] == EXPECTED_API_READINESS_ORDER
    assert payload["cleanupExecuted"] is True
    assert docker_calls == [
        "api-compose-config",
        "build-api-service",
        "start-infrastructure",
        "start-api-service",
        "validate-session-signing-keys",
        "cleanup",
    ]
    assert http_calls == EXPECTED_API_READINESS_ORDER[5:]

    for raw_secret in (
        REDACTED_SESSION_KEY,
        REDACTED_CSRF_KEY,
        REDACTED_SIGNED_TOKEN,
        REDACTED_CSRF_HEADER,
    ):
        assert raw_secret not in payload_text
    assert "[REDACTED]" in payload_text


def test_runtime_smoke_registry_exposes_postman_docker_api_readiness_plan() -> None:
    from token_payments.runtime.smoke import describe_smoke_registry, run_smoke_scenario

    registry = describe_smoke_registry()
    result = run_smoke_scenario("postman-docker-api-readiness").to_dict()
    details = result["details"]

    assert "postman-docker-api-readiness" in registry["availableScenarios"]
    assert result["status"] == "passed"
    assert details["dockerStarted"] is False
    assert details["networkCalls"] is False
    assert details["planCommand"] == "python3 scripts/docker_live_smoke.py --api-readiness --plan"
    assert details["refusalCommand"] == "python3 scripts/docker_live_smoke.py --api-readiness --execute"
    assert details["confirmedLiveCommand"] == (
        "python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker"
    )
    assert details["commandSequence"] == EXPECTED_API_READINESS_ORDER


def test_readmes_document_manual_docker_api_readiness_security_smoke_order() -> None:
    for path in (ROOT / "README.md", ROOT / "app" / "README.md"):
        text = path.read_text(encoding="utf-8")
        assert "Postman Docker API readiness/security smoke" in text
        assert "python3 scripts/docker_live_smoke.py --api-readiness --plan" in text
        assert "python3 scripts/docker_live_smoke.py --api-readiness --execute" in text
        assert "python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker" in text
        assert "session signing key validation" in text
        assert "invalid/expired signature rejection" in text
        assert "oversized body" in text
        assert "malformed JSON" in text
        assert "operator action smoke" in text

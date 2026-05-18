from __future__ import annotations

import json
import os
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
    "seed-local-fixtures",
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
    auth_command = next(command for command in commands if command["name"] == "auth-cookie-flow")
    auth_body = json.loads(auth_command["argv"][auth_command["argv"].index("--data") + 1])
    assert auth_body == {
        "walletAddress": "0x1111111111111111111111111111111111111111",
        "domain": "token-payments.local",
        "uri": "https://token-payments.local",
        "chainId": 1337,
    }
    cors_command = next(command for command in commands if command["name"] == "cors-preflight")
    assert "Origin: http://localhost:5173" in cors_command["argv"]
    idempotency_command = next(command for command in commands if command["name"] == "idempotency-duplicate")
    idempotency_body = json.loads(idempotency_command["argv"][idempotency_command["argv"].index("--data") + 1])
    assert idempotency_body["idempotencyKey"] != "postman-duplicate-checkout"
    assert "X-User-Id: 11111111-1111-4111-8111-111111111111" in idempotency_command["argv"]
    checkout_command = next(command for command in commands if command["name"] == "checkout-happy-path")
    checkout_body = json.loads(checkout_command["argv"][checkout_command["argv"].index("--data") + 1])
    assert checkout_body["storeId"] == "44444444-4444-4444-8444-444444444444"
    assert checkout_body["items"][0]["productId"] == "55555555-5555-4555-8555-555555555555"
    assert "X-User-Id: 11111111-1111-4111-8111-111111111111" in checkout_command["argv"]
    operator_command = next(command for command in commands if command["name"] == "operator-action-smoke")
    assert "Cookie: access_token=<operator-session-token>; csrf_token=<csrf-token>" not in operator_command["argv"]
    assert "X-User-Role: ADMIN" in operator_command["argv"]
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
        "seed-local-fixtures",
        "validate-session-signing-keys",
        "cleanup",
    ]
    assert http_calls == EXPECTED_API_READINESS_ORDER[6:]

    for raw_secret in (
        REDACTED_SESSION_KEY,
        REDACTED_CSRF_KEY,
        REDACTED_SIGNED_TOKEN,
        REDACTED_CSRF_HEADER,
    ):
        assert raw_secret not in payload_text
    assert "[REDACTED]" in payload_text


def test_api_readiness_session_key_validation_runs_with_app_pythonpath(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setenv("PYTHONPATH", "existing-pythonpath")

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fake_run)

    result = docker_live_smoke._run_api_smoke_command(
        "validate-session-signing-keys",
        ("python3", "-m", "token_payments", "serve-api", "--live", "--dry-run"),
        "security",
        tmp_path,
        (),
        None,
    )

    assert result["exitCode"] == 0
    assert calls[0]["cwd"] == tmp_path
    assert calls[0]["env"]["PYTHONPATH"].split(os.pathsep) == [
        str(tmp_path / "app"),
        "existing-pythonpath",
    ]


def test_api_readiness_health_probe_retries_transient_connection_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if len(calls) == 1:
            return subprocess.CompletedProcess(argv, 56, stdout="", stderr="connection reset")
        return subprocess.CompletedProcess(argv, 0, stdout='{"state":"OK"}', stderr="")

    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fake_run)
    monkeypatch.setattr(docker_live_smoke, "sleep", lambda _seconds: None)

    result = docker_live_smoke._run_api_smoke_command(
        "healthz",
        ("curl", "--fail-with-body", "http://localhost:8000/healthz"),
        "http",
        tmp_path,
        (),
        None,
    )

    assert result["exitCode"] == 0
    assert result["attempts"] == 2
    assert len(calls) == 2


def test_api_readiness_expected_security_rejection_counts_as_success(
    tmp_path: Path, monkeypatch: Any
) -> None:
    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            argv,
            22,
            stdout='{"error":{"code":"INVALID_AUTH_TOKEN","message":"bad token"}}',
            stderr="curl: (22) The requested URL returned error: 401\n",
        )

    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fake_run)

    result = docker_live_smoke._run_api_smoke_command(
        "expired-token-rejected",
        ("curl", "--fail-with-body", "http://localhost:8000/auth/me"),
        "security",
        tmp_path,
        (),
        None,
    )

    assert result["exitCode"] == 0
    assert result["expectedHttpStatus"] == 401
    assert result["expectedErrorCode"] == "INVALID_AUTH_TOKEN"


def test_api_readiness_csrf_success_uses_cookie_jar_token_without_echoing_it(
    tmp_path: Path, monkeypatch: Any
) -> None:
    cookie_path = tmp_path / "csrf.cookies"
    cookie_path.write_text(
        "# Netscape HTTP Cookie File\nlocalhost\tFALSE\t/\tFALSE\t0\tcsrf_token\treal-csrf-token\n",
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        assert "X-CSRF-Token: real-csrf-token" in argv
        assert any("csrf_token=real-csrf-token" in value for value in argv)
        return subprocess.CompletedProcess(
            argv,
            22,
            stdout='{"error":{"code":"INVALID_AUTH_TOKEN","message":"bad token"}}',
            stderr="curl: (22) The requested URL returned error: 401\n",
        )

    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fake_run)
    monkeypatch.setattr(docker_live_smoke, "API_COOKIE_JAR_PATH", cookie_path)

    result = docker_live_smoke._run_api_smoke_command(
        "csrf-success",
        (
            "curl",
            "--request",
            "POST",
            "http://localhost:8000/auth/sessions/refresh",
            "--header",
            "Cookie: access_token=<valid-session-token>; refresh_token=<valid-refresh-token>; csrf_token=<csrf-token>",
            "--header",
            "X-CSRF-Token: <csrf-token>",
        ),
        "security",
        tmp_path,
        (),
        None,
    )
    payload_text = json.dumps(result, sort_keys=True)

    assert result["exitCode"] == 0
    assert result["expectedHttpStatus"] == 401
    assert result["expectedErrorCode"] == "INVALID_AUTH_TOKEN"
    assert "real-csrf-token" not in payload_text
    assert len(calls) == 1


def test_api_readiness_oversized_body_generates_runtime_payload_without_echoing_it(
    tmp_path: Path, monkeypatch: Any
) -> None:
    oversized_path = tmp_path / "oversized-body.bin"
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        body = argv[argv.index("--data-binary") + 1]
        assert body == f"@{oversized_path}"
        assert oversized_path.read_text(encoding="utf-8") == "x" * 16
        return subprocess.CompletedProcess(
            argv,
            22,
            stdout='{"error":{"code":"REQUEST_BODY_TOO_LARGE","message":"too large"}}',
            stderr="curl: (22) The requested URL returned error: 413\n",
        )

    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fake_run)
    monkeypatch.setattr(docker_live_smoke, "API_OVERSIZED_BODY_BYTES", 16)
    monkeypatch.setattr(docker_live_smoke, "API_OVERSIZED_BODY_PATH", oversized_path)

    result = docker_live_smoke._run_api_smoke_command(
        "oversized-body",
        (
            "curl",
            "--request",
            "POST",
            "http://localhost:8000/orders",
            "--data-binary",
            "<oversized-body-generated-by-runner>",
        ),
        "security",
        tmp_path,
        (),
        None,
    )
    payload_text = json.dumps(result, sort_keys=True)

    assert result["exitCode"] == 0
    assert result["expectedHttpStatus"] == 413
    assert result["expectedErrorCode"] == "REQUEST_BODY_TOO_LARGE"
    assert str(oversized_path) not in payload_text
    assert len(calls) == 1


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

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import docker_live_smoke


EXPECTED_SEQUENCE = [
    (
        "compose-config",
        ["docker", "compose", "--env-file", ".env", "--profile", "runtime", "config", "--services"],
    ),
    (
        "build-runtime-image",
        ["docker", "compose", "--env-file", ".env", "--profile", "runtime", "build", "token_payments_health"],
    ),
    (
        "start-infrastructure",
        ["docker", "compose", "--env-file", ".env", "up", "-d", "postgres", "kafka", "kafka-ui", "pgweb", "test_network"],
    ),
    (
        "runtime-health",
        ["docker", "compose", "--env-file", ".env", "--profile", "runtime", "run", "--rm", "token_payments_health"],
    ),
    (
        "runtime-worker",
        ["docker", "compose", "--env-file", ".env", "--profile", "runtime", "run", "--rm", "token_payments_worker"],
    ),
    (
        "runtime-smoke",
        ["docker", "compose", "--env-file", ".env", "--profile", "smoke", "run", "--rm", "token_payments_smoke"],
    ),
]
CLEANUP_COMMAND = ["docker", "compose", "--env-file", ".env", "down"]


def test_execute_without_confirmation_rejects_before_subprocess(monkeypatch: Any, capsys: Any) -> None:
    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess.run must not be called without explicit live confirmation")

    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fail_run)

    exit_code = docker_live_smoke.main(["--execute"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["mode"] == "execute"
    assert payload["status"] == "error"
    assert payload["dockerStarted"] is False
    assert payload["networkCalls"] is False
    assert payload["error"]["code"] == "LIVE_DOCKER_CONFIRMATION_REQUIRED"


def test_live_execution_runs_sequence_with_bounded_subprocess_guardrails(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    secret_value = "local-secret-password"
    (tmp_path / ".env").write_text(f"POSTGRES_PASSWORD={secret_value}\n", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, 0, stdout=f"ok {secret_value}", stderr=f"warn {secret_value}")

    monkeypatch.setattr(docker_live_smoke, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fake_run)

    exit_code = docker_live_smoke.main(["--execute", "--confirm-live-docker"])
    payload_text = capsys.readouterr().out
    payload = json.loads(payload_text)

    assert exit_code == 0
    assert payload["mode"] == "execute"
    assert payload["status"] == "success"
    assert payload["dockerStarted"] is True
    assert payload["networkCalls"] is True
    assert payload["executedSteps"] == [name for name, _argv in EXPECTED_SEQUENCE]
    assert payload["commandCount"] == len(EXPECTED_SEQUENCE) + 1
    assert payload["cleanupExecuted"] is True
    assert secret_value not in payload_text

    assert [call["argv"] for call in calls] == [*[_argv for _name, _argv in EXPECTED_SEQUENCE], CLEANUP_COMMAND]
    for call in calls:
        assert call["cwd"] == tmp_path
        assert call["shell"] is False
        assert call["text"] is True
        assert call["capture_output"] is True
        assert isinstance(call["timeout"], int)
        assert 1 <= call["timeout"] <= 300


def test_live_execution_rejects_env_example_before_subprocess(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    (tmp_path / ".env.example").write_text("POSTGRES_PASSWORD=template-secret\n", encoding="utf-8")

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess.run must not be called with .env.example as live env file")

    monkeypatch.setattr(docker_live_smoke, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fail_run)

    exit_code = docker_live_smoke.main(["--execute", "--confirm-live-docker", "--env-file", ".env.example"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "error"
    assert payload["envFile"] == ".env.example"
    assert payload["dockerStarted"] is False
    assert payload["networkCalls"] is False
    assert payload["error"]["code"] == "LIVE_DOCKER_ENV_FILE_FORBIDDEN"


def test_live_execution_requires_existing_default_env_file(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess.run must not be called when .env is missing")

    monkeypatch.setattr(docker_live_smoke, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fail_run)

    exit_code = docker_live_smoke.main(["--execute", "--confirm-live-docker"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["status"] == "error"
    assert payload["envFile"] == ".env"
    assert payload["dockerStarted"] is False
    assert payload["networkCalls"] is False
    assert payload["error"]["code"] == "LIVE_DOCKER_ENV_FILE_REQUIRED"


def test_live_execution_failure_after_infrastructure_start_runs_cleanup_once(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    secret_value = "runtime-secret-token"
    (tmp_path / ".env").write_text(f"ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS={secret_value}\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if "run" in argv and "token_payments_health" in argv:
            return subprocess.CompletedProcess(argv, 23, stdout=f"failed {secret_value}", stderr=f"stderr {secret_value}")
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(docker_live_smoke, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(docker_live_smoke.subprocess, "run", fake_run)

    exit_code = docker_live_smoke.main(["--execute", "--confirm-live-docker"])
    payload_text = capsys.readouterr().out
    payload = json.loads(payload_text)

    assert exit_code == 1
    assert payload["status"] == "error"
    assert payload["failedStep"] == "runtime-health"
    assert payload["exitCode"] == 23
    assert payload["cleanupExecuted"] is True
    assert payload["commandCount"] == 5
    assert secret_value not in payload_text
    assert calls == [
        EXPECTED_SEQUENCE[0][1],
        EXPECTED_SEQUENCE[1][1],
        EXPECTED_SEQUENCE[2][1],
        EXPECTED_SEQUENCE[3][1],
        CLEANUP_COMMAND,
    ]

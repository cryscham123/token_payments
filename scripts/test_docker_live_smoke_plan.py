from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docker_live_smoke.py"

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


def test_plan_cli_outputs_bounded_json_contract_without_live_docker() -> None:
    payload = _run_plan("--plan")

    assert payload["contract"] == "token-payments.docker-live-smoke.plan.v1"
    assert payload["mode"] == "plan"
    assert payload["status"] == "planned"
    assert payload["dockerStarted"] is False
    assert payload["networkCalls"] is False
    assert payload["envFile"] == ".env"
    assert payload["requiredServices"] == [
        "postgres",
        "kafka",
        "kafka-ui",
        "pgweb",
        "test_network",
        "token_payments_health",
        "token_payments_worker",
        "token_payments_smoke",
    ]

    assert [(item["name"], item["argv"]) for item in payload["commandSequence"]] == EXPECTED_SEQUENCE
    assert payload["cleanupCommand"]["argv"] == CLEANUP_COMMAND
    assert payload["cleanupCommand"]["display"] == "docker compose --env-file .env down"
    assert _contains_only_json_primitives(payload)
    assert len(json.dumps(payload)) < 12000


def test_default_cli_is_dry_run_plan_and_does_not_create_env_file() -> None:
    env_path = ROOT / ".env"
    before_exists = env_path.exists()
    before_mtime = env_path.stat().st_mtime_ns if before_exists else None

    default_payload = _run_plan()
    explicit_payload = _run_plan("--plan")

    assert default_payload == explicit_payload
    assert env_path.exists() is before_exists
    if before_exists:
        assert env_path.stat().st_mtime_ns == before_mtime


def test_plan_commands_are_argv_based_and_do_not_assume_shell_true() -> None:
    payload = _run_plan("--plan")

    for command in [*payload["commandSequence"], payload["cleanupCommand"]]:
        assert isinstance(command["argv"], list)
        assert command["argv"]
        assert command["display"] == " ".join(command["argv"])
        assert command.get("shell") in (None, False)
        assert "shell=True" not in json.dumps(command)


def test_plan_payload_does_not_expose_sensitive_or_claude_values() -> None:
    payload_text = json.dumps(_run_plan("--plan"), sort_keys=True)
    env_example_text = (ROOT / ".env.example").read_text(encoding="utf-8")

    sensitive_values = [
        line.split("=", 1)[1].strip()
        for line in env_example_text.splitlines()
        if line.startswith(
            (
                "TEST_NETWORK_PRIVATE_KEY=",
                "TEST_NETWORK_ACCOUNT=",
                "POSTGRES_PASSWORD=",
                "ADAPTER_POSTGRES_DSN=",
            )
        )
    ]
    assert sensitive_values
    for value in sensitive_values:
        assert value not in payload_text

    forbidden_fragments = [
        "private_key",
        "private key",
        "seed phrase",
        "claude",
        "CLAUDE.md",
    ]
    lower_payload = payload_text.lower()
    for fragment in forbidden_fragments:
        assert fragment.lower() not in lower_payload


def test_execute_mode_is_rejected_as_bounded_json_error() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--execute"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    payload = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert completed.stderr == ""
    assert payload["contract"] == "token-payments.docker-live-smoke.plan.v1"
    assert payload["mode"] == "execute"
    assert payload["status"] == "error"
    assert payload["dockerStarted"] is False
    assert payload["networkCalls"] is False
    assert payload["error"]["code"] == "LIVE_DOCKER_CONFIRMATION_REQUIRED"


def _run_plan(*args: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    return json.loads(completed.stdout)


def _contains_only_json_primitives(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_contains_only_json_primitives(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _contains_only_json_primitives(item) for key, item in value.items())
    return False

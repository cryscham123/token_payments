from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

INFRASTRUCTURE_SERVICES = {"postgres", "kafka", "kafka-ui", "pgweb", "test_network"}
RUNTIME_ONE_SHOT_SERVICES = {
    "token_payments_health",
    "token_payments_worker",
    "token_payments_smoke",
}
CONFIG_SERVICES_COMMAND = (
    "docker",
    "compose",
    "--env-file",
    ".env.example",
    "config",
    "--services",
)
RUNTIME_PROFILE_CONFIG_SERVICES_COMMAND = (
    "docker",
    "compose",
    "--env-file",
    ".env.example",
    "--profile",
    "runtime",
    "config",
    "--services",
)
FORBIDDEN_DAEMON_COMMANDS = {"up", "run", "build"}
SKIP_REASON = (
    "Docker Compose CLI is not installed or unavailable; "
    "static tests in scripts/test_docker_compose_runtime_services.py validate the committed compose contract"
)


def test_compose_config_services_resolves_committed_stack_without_daemon() -> None:
    _require_docker_compose_cli()

    services = _compose_config_services(CONFIG_SERVICES_COMMAND)

    assert INFRASTRUCTURE_SERVICES | RUNTIME_ONE_SHOT_SERVICES <= services


def test_runtime_profile_config_services_includes_runtime_one_shot_services() -> None:
    _require_docker_compose_cli()

    services = _compose_config_services(RUNTIME_PROFILE_CONFIG_SERVICES_COMMAND)

    assert RUNTIME_ONE_SHOT_SERVICES <= services


def test_compose_config_validation_commands_are_daemonless_and_bounded() -> None:
    for command in (CONFIG_SERVICES_COMMAND, RUNTIME_PROFILE_CONFIG_SERVICES_COMMAND):
        assert command[:2] == ("docker", "compose")
        assert "config" in command
        assert "--services" in command
        assert FORBIDDEN_DAEMON_COMMANDS.isdisjoint(command)


def _require_docker_compose_cli() -> None:
    if shutil.which("docker") is None:
        pytest.skip(SKIP_REASON)

    completed = subprocess.run(
        ["docker", "compose", "version"],
        cwd=ROOT,
        env=_daemonless_env(),
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip(SKIP_REASON)


def _compose_config_services(command: tuple[str, ...]) -> set[str]:
    assert FORBIDDEN_DAEMON_COMMANDS.isdisjoint(command)

    completed = subprocess.run(
        list(command),
        cwd=ROOT,
        env=_daemonless_env(),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}


def _daemonless_env() -> dict[str, str]:
    env = os.environ.copy()
    env["DOCKER_HOST"] = "unix:///tmp/token-payments-compose-config-validation-no-daemon.sock"
    return env

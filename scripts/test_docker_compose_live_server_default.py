from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_SERVICE = "token_payments_api"
DEFAULT_CONFIG_COMMAND = ("docker", "compose", "--env-file", ".env.example", "config", "--services")
EXPECTED_API_COMMAND = ["python", "-m", "token_payments", "serve-api", "--live", "--confirm-live-api"]
EXPECTED_DEPENDENCIES = {
    "postgres": "service_healthy",
    "kafka": "service_started",
    "test_network": "service_started",
}
REQUIRED_API_ENV = {
    "PYTHONPATH": "/workspace/app",
    "RUNTIME_API_HOST": "0.0.0.0",
    "RUNTIME_API_PORT": "8000",
    "ADAPTER_POSTGRES_DSN": "${ADAPTER_POSTGRES_DSN}",
    "ADAPTER_KAFKA_BOOTSTRAP_SERVERS": "${ADAPTER_KAFKA_BOOTSTRAP_SERVERS}",
    "ADAPTER_BLOCKCHAIN_RPC_SCHEME": "${ADAPTER_BLOCKCHAIN_RPC_SCHEME}",
    "ADAPTER_BLOCKCHAIN_RPC_HOST": "${ADAPTER_BLOCKCHAIN_RPC_HOST}",
    "ADAPTER_BLOCKCHAIN_RPC_PORT": "${ADAPTER_BLOCKCHAIN_RPC_PORT}",
    "ADAPTER_BLOCKCHAIN_RPC_PATH": "${ADAPTER_BLOCKCHAIN_RPC_PATH:-}",
    "ADAPTER_BLOCKCHAIN_RPC_URL": "${ADAPTER_BLOCKCHAIN_RPC_URL:-}",
    "SESSION_SIGNING_KEYS": "${SESSION_SIGNING_KEYS}",
    "CSRF_SIGNING_KEY": "${CSRF_SIGNING_KEY}",
}
SECRET_MARKERS = (
    "local_dev_only_session_signing_key",
    "local_dev_only_csrf_signing_key",
    "replace_with_local_dev_only_session_signing_key",
    "replace_with_local_dev_only_csrf_signing_key",
)
FORBIDDEN_DAEMON_COMMANDS = {"up", "run", "build"}


def test_env_profiles_make_api_service_part_of_default_compose_config() -> None:
    env = _env_values()

    assert "api" in {profile.strip() for profile in env["COMPOSE_PROFILES"].split(",")}
    assert "runtime" in env["COMPOSE_PROFILES"]
    assert "smoke" in env["COMPOSE_PROFILES"]
    assert FORBIDDEN_DAEMON_COMMANDS.isdisjoint(DEFAULT_CONFIG_COMMAND)


def test_default_compose_api_service_contract_is_live_and_env_backed() -> None:
    service = _compose_services()[API_SERVICE]
    environment = _environment_pairs(service)

    assert _scalar_for_key(service, "image") == "token_payments_runtime"
    assert _nested_scalar(service, "build", "context") == "."
    assert _nested_scalar(service, "build", "dockerfile") == "Dockerfile"
    assert _list_for_key(service, "env_file") == [".env"]
    assert _json_list_for_key(service, "command") == EXPECTED_API_COMMAND
    assert _scalar_for_key(service, "restart") == "unless-stopped"
    assert _list_for_key(service, "ports") == ["8000:8000"]

    for key, expected in REQUIRED_API_ENV.items():
        assert environment[key] == expected

    block_text = "\n".join(service)
    for marker in SECRET_MARKERS:
        assert marker not in block_text


def test_default_compose_api_service_waits_for_required_infrastructure_and_has_healthcheck() -> None:
    service = _compose_services()[API_SERVICE]

    assert _depends_on_conditions(service) == EXPECTED_DEPENDENCIES
    assert _nested_scalar(service, "healthcheck", "interval") == "5s"
    assert _nested_scalar(service, "healthcheck", "timeout") == "3s"
    assert _nested_scalar(service, "healthcheck", "retries") == "12"
    assert _nested_scalar(service, "healthcheck", "start_period") == "10s"
    assert "http://127.0.0.1:8000/healthz" in "\n".join(_nested_list(service, "healthcheck", "test"))


def test_default_compose_config_services_resolves_api_without_profile_flag() -> None:
    _require_docker_compose_cli()

    services = _compose_config_services(DEFAULT_CONFIG_COMMAND)

    assert API_SERVICE in services


def _compose_services() -> dict[str, tuple[str, ...]]:
    path = ROOT / "docker-compose.yml"
    assert path.exists(), "docker-compose.yml must exist"

    services: dict[str, list[str]] = {}
    in_services = False
    current_service: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = _indent_width(raw_line)
        if indent == 0 and stripped == "services:":
            in_services = True
            current_service = None
            continue
        if not in_services:
            continue
        if indent == 0:
            break
        if indent == 2 and stripped.endswith(":") and not stripped.startswith("- "):
            current_service = stripped[:-1]
            services[current_service] = []
            continue
        if current_service is not None:
            services[current_service].append(raw_line)

    assert API_SERVICE in services, f"docker-compose.yml must define {API_SERVICE}"
    return {name: tuple(block) for name, block in services.items()}


def _env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _environment_pairs(block: tuple[str, ...]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for item in _list_for_key(block, "environment"):
        assert "=" in item, f"environment item must be KEY=VALUE syntax: {item}"
        key, value = item.split("=", 1)
        pairs[key] = value
    return pairs


def _base_indent(block: tuple[str, ...]) -> int | None:
    indents = [
        _indent_width(line)
        for line in block
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("- ")
    ]
    return min(indents) if indents else None


def _scalar_for_key(block: tuple[str, ...], key: str) -> str | None:
    base_indent = _base_indent(block)
    if base_indent is None:
        return None
    prefix = f"{key}:"
    for line in block:
        stripped = line.strip()
        if _indent_width(line) == base_indent and stripped.startswith(prefix):
            value = stripped[len(prefix) :].strip()
            return _unquote(value) if value else None
    return None


def _list_for_key(block: tuple[str, ...], key: str) -> list[str]:
    base_indent = _base_indent(block)
    if base_indent is None:
        return []
    return _list_for_key_at_indent(block, key, base_indent)


def _list_for_key_at_indent(block: tuple[str, ...], key: str, expected_indent: int) -> list[str]:
    prefix = f"{key}:"
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != expected_indent or not stripped.startswith(prefix):
            continue
        scalar_value = stripped[len(prefix) :].strip()
        if scalar_value:
            parsed = json.loads(scalar_value) if scalar_value.startswith("[") else [_unquote(scalar_value)]
            return [str(value) for value in parsed]

        values: list[str] = []
        for nested in block[index + 1 :]:
            nested_stripped = nested.strip()
            if not nested_stripped or nested_stripped.startswith("#"):
                continue
            nested_indent = _indent_width(nested)
            if nested_indent <= indent:
                break
            if nested_stripped.startswith("- "):
                values.append(_list_item_value(nested_stripped[2:].strip()))
        return values
    return []


def _nested_list(block: tuple[str, ...], parent_key: str, child_key: str) -> list[str]:
    base_indent = _base_indent(block)
    if base_indent is None:
        return []
    parent_prefix = f"{parent_key}:"
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith(parent_prefix):
            continue
        child_indent = indent + 2
        return _list_for_key_at_indent(block[index + 1 :], child_key, child_indent)
    return []


def _list_item_value(value: str) -> str:
    if value.startswith("path:"):
        return _unquote(value[len("path:") :].strip())
    return _unquote(value)


def _json_list_for_key(block: tuple[str, ...], key: str) -> list[str]:
    value = _scalar_for_key(block, key)
    assert value is not None, f"{key} must be present"
    parsed = json.loads(value)
    assert isinstance(parsed, list)
    return [str(item) for item in parsed]


def _nested_scalar(block: tuple[str, ...], parent_key: str, child_key: str) -> str | None:
    base_indent = _base_indent(block)
    if base_indent is None:
        return None
    parent_prefix = f"{parent_key}:"
    child_prefix = f"{child_key}:"
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith(parent_prefix):
            continue
        for nested in block[index + 1 :]:
            nested_stripped = nested.strip()
            if not nested_stripped or nested_stripped.startswith("#"):
                continue
            nested_indent = _indent_width(nested)
            if nested_indent <= indent:
                break
            if nested_stripped.startswith(child_prefix):
                return _unquote(nested_stripped[len(child_prefix) :].strip())
    return None


def _depends_on_conditions(block: tuple[str, ...]) -> dict[str, str | None]:
    base_indent = _base_indent(block)
    if base_indent is None:
        return {}
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith("depends_on:"):
            continue

        dependencies: dict[str, str | None] = {}
        current_dependency: str | None = None
        for nested in block[index + 1 :]:
            nested_stripped = nested.strip()
            if not nested_stripped or nested_stripped.startswith("#"):
                continue
            nested_indent = _indent_width(nested)
            if nested_indent <= indent:
                break
            if nested_stripped.endswith(":") and not nested_stripped.startswith("- "):
                current_dependency = nested_stripped[:-1]
                dependencies[current_dependency] = None
                continue
            if current_dependency and nested_stripped.startswith("condition:"):
                dependencies[current_dependency] = _unquote(nested_stripped[len("condition:") :].strip())
        return dependencies
    return {}


def _require_docker_compose_cli() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI is unavailable; static tests validate the committed default contract")

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
        pytest.skip("Docker Compose CLI is unavailable; static tests validate the committed default contract")


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
    env["DOCKER_HOST"] = "unix:///tmp/token-payments-default-config-no-daemon.sock"
    return env


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value

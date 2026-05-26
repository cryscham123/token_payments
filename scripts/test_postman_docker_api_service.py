from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

API_SERVICE = "token_payments_api"
API_PROFILE_CONFIG_COMMAND = (
    "docker",
    "compose",
    "--env-file",
    ".env.example",
    "config",
    "--services",
)
EXPECTED_API_COMMAND = ["python", "-m", "token_payments", "serve-api", "--live", "--confirm-live-api"]
EXPECTED_DEPENDENCIES = {
    "postgres": "service_healthy",
    "kafka": "service_started",
    "test_network": "service_started",
    "token_payments_live_worker": "service_started",
}
REQUIRED_API_ENV_KEYS = {
    "LOCAL_API_ORIGIN",
    "API_PUBLIC_BASE_URL",
    "RUNTIME_API_HOST",
    "RUNTIME_API_PORT",
    "RUNTIME_REQUEST_TIMEOUT_SECONDS",
    "REQUEST_BODY_MAX_BYTES",
    "CORS_ALLOWED_ORIGINS",
    "CORS_ALLOW_CREDENTIALS",
    "CORS_MAX_AGE_SECONDS",
    "COOKIE_SECURE",
    "COOKIE_SAMESITE",
    "CSRF_ACTIVE_KEY_ID",
    "CSRF_SIGNING_KEY",
    "CSRF_MAX_AGE_SECONDS",
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "SESSION_ACTIVE_KEY_ID",
    "SESSION_SIGNING_KEYS",
    "SESSION_ACCESS_TTL_SECONDS",
    "SESSION_REFRESH_TTL_SECONDS",
    "ADAPTER_POSTGRES_DSN",
    "ADAPTER_KAFKA_BOOTSTRAP_SERVERS",
    "ADAPTER_BLOCKCHAIN_RPC_SCHEME",
    "ADAPTER_BLOCKCHAIN_RPC_HOST",
    "ADAPTER_BLOCKCHAIN_RPC_PORT",
    "ADAPTER_BLOCKCHAIN_RPC_PATH",
    "ADAPTER_BLOCKCHAIN_RPC_URL",
}
SECRET_ENV_KEYS = {"SESSION_SIGNING_KEYS", "CSRF_SIGNING_KEY"}
FORBIDDEN_COMPOSE_SECRET_MARKERS = (
    "replace_with_local_dev_only_session_signing_key",
    "replace_with_local_dev_only_csrf_signing_key",
    "local_dev_only_session_signing_key",
    "local_dev_only_csrf_signing_key",
)
FORBIDDEN_DAEMON_COMMANDS = {"up", "run", "build"}


def test_compose_defines_postman_api_service_contract() -> None:
    services = _compose_services()
    service = services[API_SERVICE]
    environment = _environment_pairs(service)

    assert _scalar_for_key(service, "image") == "token_payments_runtime"
    assert _nested_scalar(service, "build", "context") == "."
    assert _nested_scalar(service, "build", "dockerfile") == "Dockerfile"
    assert _list_for_key(service, "env_file") == [".env"]
    assert _list_for_key(service, "profiles") == ["api"]
    assert _json_list_for_key(service, "command") == EXPECTED_API_COMMAND
    assert _scalar_for_key(service, "restart") == "unless-stopped"
    assert _list_for_key(service, "ports") == []
    assert _list_for_key(service, "expose") == ["8000"]

    assert environment["PYTHONPATH"] == "/workspace/app"
    assert environment["RUNTIME_API_HOST"] == "0.0.0.0"
    assert environment["RUNTIME_API_PORT"] == "8000"
    for key in REQUIRED_API_ENV_KEYS:
        assert key in environment, f"{API_SERVICE} must pass through {key}"
    for key in SECRET_ENV_KEYS:
        assert environment[key] == f"${{{key}}}", f"{key} must be environment-backed, not hard-coded"

    block_text = "\n".join(service)
    for marker in FORBIDDEN_COMPOSE_SECRET_MARKERS:
        assert marker not in block_text


def test_postman_api_service_waits_for_required_local_infrastructure() -> None:
    dependencies = _depends_on_conditions(_compose_services()[API_SERVICE])

    assert dependencies == EXPECTED_DEPENDENCIES


def test_env_example_documents_postman_api_cookie_csrf_cors_and_session_placeholders() -> None:
    env = _env_values()

    for key in REQUIRED_API_ENV_KEYS:
        assert key in env, f".env.example must document {key}"

    assert env["LOCAL_API_ORIGIN"] == "https://localhost"
    assert env["API_PUBLIC_BASE_URL"] == "https://localhost"
    assert env["RUNTIME_API_HOST"] == "0.0.0.0"
    assert env["RUNTIME_API_PORT"] == "8000"
    assert env["COOKIE_SECURE"].lower() == "false"
    assert env["COOKIE_SAMESITE"] == "Lax"
    assert env["CSRF_COOKIE_NAME"] == "csrf_token"
    assert env["CSRF_HEADER_NAME"] == "X-CSRF-Token"
    assert env["COMPOSE_PROFILES"] == "runtime,smoke,api"
    assert env["ADAPTER_BLOCKCHAIN_RPC_URL"] == ""
    assert env["ADAPTER_BLOCKCHAIN_RPC_HOST"] == "test_network"
    assert env["ADAPTER_BLOCKCHAIN_RPC_PORT"] == "8545"
    assert env["SESSION_ACTIVE_KEY_ID"] == "local-dev-2026"
    assert "local_dev_only_session_signing_key" in env["SESSION_SIGNING_KEYS"]
    assert env["CSRF_SIGNING_KEY"].startswith("local_dev_only_csrf_signing_key")


def test_docker_runtime_smoke_exposes_postman_api_manual_sequence_without_starting_docker() -> None:
    from token_payments.runtime.smoke import run_smoke_scenario

    result = run_smoke_scenario("docker-runtime-readiness").to_dict()
    details = result["details"]
    postman_api = details["postmanApi"]

    assert details["dockerStarted"] is False
    assert details["networkCalls"] is False
    assert postman_api["service"] == {
        "image": "token_payments_runtime",
        "buildContext": ".",
        "dockerfile": "Dockerfile",
        "envFile": [".env"],
        "pythonPath": "/workspace/app",
        "command": EXPECTED_API_COMMAND,
        "restart": "unless-stopped",
        "profiles": ["api"],
        "ports": [],
        "expose": ["8000"],
        "environmentKeys": ["PYTHONPATH", *sorted(REQUIRED_API_ENV_KEYS)],
        "dependsOn": EXPECTED_DEPENDENCIES,
    }
    assert postman_api["composeConfigValidationCommand"] == {
        "command": "docker compose --env-file .env.example config --services",
        "daemonless": True,
        "usesDockerSocket": False,
        "forbiddenCommands": ["up", "run", "build"],
        "expectedServices": [API_SERVICE],
    }
    assert postman_api["manualLiveCommands"] == [
        "cp .env.example .env",
        "docker compose --env-file .env config --services",
        "docker compose --env-file .env build token_payments_api nginx",
        "docker compose up -d",
        "curl --fail --insecure https://localhost/healthz",
        "curl --fail --insecure https://localhost/readyz",
        "docker compose down",
    ]
    json.dumps(result)


def test_api_profile_config_services_resolves_api_service_without_daemon() -> None:
    _require_docker_compose_cli()

    services = _compose_config_services(API_PROFILE_CONFIG_COMMAND)

    assert API_SERVICE in services


def test_api_profile_config_command_is_daemonless_and_bounded() -> None:
    assert API_PROFILE_CONFIG_COMMAND[:2] == ("docker", "compose")
    assert "config" in API_PROFILE_CONFIG_COMMAND
    assert "--services" in API_PROFILE_CONFIG_COMMAND
    assert FORBIDDEN_DAEMON_COMMANDS.isdisjoint(API_PROFILE_CONFIG_COMMAND)


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

    assert in_services, "docker-compose.yml must have a services block"
    assert API_SERVICE in services, f"docker-compose.yml must define {API_SERVICE}"
    return {name: tuple(block) for name, block in services.items()}


def _env_values() -> dict[str, str]:
    path = ROOT / ".env.example"
    assert path.exists(), ".env.example must exist"
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        assert "=" in line, f".env.example:{line_number} must be KEY=VALUE syntax"
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
    prefix = f"{key}:"
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith(prefix):
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
        pytest.skip("Docker Compose CLI is unavailable; static tests validate the committed API service contract")

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
        pytest.skip("Docker Compose CLI is unavailable; static tests validate the committed API service contract")


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
    env["DOCKER_HOST"] = "unix:///tmp/token-payments-postman-api-config-no-daemon.sock"
    return env


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value

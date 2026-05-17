from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

LIVE_RUNTIME_EXPORTS = {
    "LiveApiComposition",
    "LiveRuntimeConfig",
    "LiveRuntimeDependencies",
    "LiveRuntimeDependencyError",
    "describe_live_runtime_dependencies",
}

FORBIDDEN_LIVE_IMPORT_ROOTS = {
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
    "starlette",
    "uvicorn",
    "web3",
}

REQUIRED_DEPENDENCIES = {
    "postgres_session_factory",
    "kafka_producer",
    "wallet_signature_client",
    "blockchain_client",
    "clock",
    "id_generator",
}


def test_runtime_public_exports_include_live_api_composition_contracts() -> None:
    runtime = importlib.import_module("token_payments.runtime")
    exported = set(getattr(runtime, "__all__", ()))

    assert LIVE_RUNTIME_EXPORTS <= exported
    assert all(hasattr(runtime, name) for name in LIVE_RUNTIME_EXPORTS)
    assert runtime.LiveRuntimeConfig.__module__ == "token_payments.runtime.composition"
    assert runtime.LiveApiComposition.__module__ == "token_payments.runtime.composition"


def test_live_runtime_config_from_env_parses_api_and_adapter_settings_with_redacted_debug_payload() -> None:
    from token_payments.runtime import LiveRuntimeConfig

    env_values = _parse_env_example()
    config = LiveRuntimeConfig.from_env(env_values)

    assert config.api_host == "0.0.0.0"
    assert config.api_port == 8000
    assert config.request_timeout_seconds == 30.0
    assert config.postgres_dsn == env_values["ADAPTER_POSTGRES_DSN"]
    assert config.kafka_bootstrap_servers == ("kafka:9092",)
    assert config.kafka_client_id == "token-payments-local"
    assert config.wallet_signature_domain == "token-payments.local"
    assert config.blockchain_rpc_url == "http://test_network:8545"
    assert env_values["ADAPTER_BLOCKCHAIN_RPC_URL"] == ""
    assert env_values["ADAPTER_BLOCKCHAIN_RPC_HOST"] == "test_network"
    assert env_values["ADAPTER_BLOCKCHAIN_RPC_PORT"] == "8545"
    assert config.blockchain_chain_id == 1337
    assert config.blockchain_native_symbol == "ETH"
    assert config.blockchain_native_decimals == 18
    assert config.blockchain_token_address == env_values["ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS"]
    assert str(config.blockchain_gas_buffer_rate) == "0.10"
    assert config.cookie_secure is False
    assert config.cookie_samesite == "Lax"
    assert config.csrf_cookie_name == "csrf_token"
    assert config.csrf_header_name == "X-CSRF-Token"

    debug_payload = config.to_redacted_dict()
    encoded = json.dumps(debug_payload, ensure_ascii=True, sort_keys=True)

    assert "replace_with_local_dev_only_password" not in encoded
    assert "replace_with_local_dev_only_token_address" not in encoded
    assert env_values["ADAPTER_POSTGRES_DSN"] not in encoded
    assert env_values["ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS"] not in encoded
    assert debug_payload["adapters"]["postgres"]["dsn"].endswith("@postgres:5432/token_payments")
    assert debug_payload["adapters"]["postgres"]["dsn"].count("<redacted>") == 1
    assert debug_payload["adapters"]["blockchain"]["tokenAddress"] == "<redacted>"


def test_live_dependency_description_is_json_safe_redacted_and_reports_missing_dependencies() -> None:
    from token_payments.runtime import LiveRuntimeConfig, LiveRuntimeDependencies, describe_live_runtime_dependencies

    config = LiveRuntimeConfig.from_env(_parse_env_example())
    description = describe_live_runtime_dependencies(config=config, dependencies=LiveRuntimeDependencies())
    encoded = json.dumps(description, ensure_ascii=True, sort_keys=True)

    assert description["runtime"] == "live-api"
    assert description["longRunning"] is False
    assert description["externalConnectionsOpened"] is False
    assert set(description["dependencies"]["missing"]) == REQUIRED_DEPENDENCIES
    assert description["dependencies"]["valid"] is False
    assert "replace_with_local_dev_only_password" not in encoded
    assert "replace_with_local_dev_only_token_address" not in encoded
    assert "private_key" not in encoded.lower()
    assert "seed_phrase" not in encoded.lower()


def test_live_api_composition_requires_explicit_injected_dependencies_without_opening_connections() -> None:
    from token_payments.runtime import LiveApiComposition, LiveRuntimeConfig, LiveRuntimeDependencies

    config = LiveRuntimeConfig.from_env(_parse_env_example())
    postgres_factory = _FailIfCalled("postgres")
    kafka_producer = _FailIfCalled("kafka")
    wallet_client = _FailIfCalled("wallet")
    blockchain_client = _FailIfCalled("blockchain")
    clock = _FailIfCalled("clock")
    id_generator = _FailIfCalled("id-generator")

    composition = LiveApiComposition(
        config=config,
        dependencies=LiveRuntimeDependencies(
            postgres_session_factory=postgres_factory,
            kafka_producer=kafka_producer,
            wallet_signature_client=wallet_client,
            blockchain_client=blockchain_client,
            clock=clock,
            id_generator=id_generator,
        ),
    )

    description = composition.describe()

    assert description["dependencies"]["valid"] is True
    assert description["dependencies"]["missing"] == []
    assert description["dependencies"]["provided"]["postgres_session_factory"] == "_FailIfCalled"
    assert description["dependencies"]["provided"]["kafka_producer"] == "_FailIfCalled"
    assert postgres_factory.calls == 0
    assert kafka_producer.calls == 0
    assert wallet_client.calls == 0
    assert blockchain_client.calls == 0
    assert clock.calls == 0
    assert id_generator.calls == 0


def test_live_dependency_validation_uses_bounded_error_contract() -> None:
    from token_payments.runtime import LiveRuntimeDependencies, LiveRuntimeDependencyError

    dependencies = LiveRuntimeDependencies(clock=_FailIfCalled("clock"))

    with pytest.raises(LiveRuntimeDependencyError) as exc_info:
        dependencies.validate()

    error = exc_info.value.to_error()
    assert error["code"] == "LIVE_RUNTIME_DEPENDENCY_MISSING"
    assert set(error["missingDependencies"]) == REQUIRED_DEPENDENCIES - {"clock"}
    assert "missing live runtime dependencies" in error["message"]
    assert json.loads(json.dumps(error)) == error


def test_live_composition_source_and_import_path_avoid_drivers_frameworks_and_sockets() -> None:
    imported_roots = _imported_roots(ROOT / "app/token_payments/runtime/composition.py")

    assert imported_roots.isdisjoint(FORBIDDEN_LIVE_IMPORT_ROOTS)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")
    code = """
import importlib
import json
import sys

forbidden = {
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
    "starlette",
    "uvicorn",
    "web3",
}
before = set(sys.modules)
module = importlib.import_module("token_payments.runtime.composition")
module.describe_live_runtime_dependencies()
after_roots = {name.partition(".")[0] for name in set(sys.modules) - before}
print(json.dumps(sorted(forbidden & after_roots)))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == []


def _parse_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".", 1)[0])
    return roots


class _FailIfCalled:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        self.calls += 1
        raise AssertionError(f"{self.name} must be injected but not called during composition")

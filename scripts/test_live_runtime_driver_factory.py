from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

FORBIDDEN_EAGER_IMPORT_ROOTS = {
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
REQUIRED_RUNTIME_REQUIREMENTS = {
    "uvicorn",
    "psycopg[binary]",
    "kafka-python",
    "eth-account",
}


def test_driver_factory_builds_all_live_dependency_wrappers_without_opening_connections() -> None:
    from token_payments.runtime import build_live_runtime_dependencies_from_env, describe_live_runtime_dependencies

    before = set(sys.modules)
    dependencies = build_live_runtime_dependencies_from_env(_factory_env())
    imported_roots = {name.partition(".")[0] for name in set(sys.modules) - before}
    description = describe_live_runtime_dependencies(dependencies=dependencies)

    assert dependencies.missing_dependencies() == ()
    assert description["dependencies"]["valid"] is True
    assert description["externalConnectionsOpened"] is False
    assert description["dependencies"]["provided"] == {
        "postgres_session_factory": "PsycopgPostgresSessionFactory",
        "kafka_producer": "LazyKafkaProducerClient",
        "wallet_signature_client": "EthAccountWalletSignatureClient",
        "blockchain_client": "JsonRpcBlockchainClient",
        "clock": "SystemClock",
        "id_generator": "UuidIdGenerator",
    }
    assert imported_roots.isdisjoint(FORBIDDEN_EAGER_IMPORT_ROOTS)


def test_driver_factory_reports_bounded_configuration_errors_for_missing_env_values() -> None:
    from token_payments.runtime import LiveRuntimeDriverConfigurationError, build_live_runtime_dependencies_from_env

    env = _factory_env() | {"ADAPTER_POSTGRES_DSN": " "}

    with pytest.raises(LiveRuntimeDriverConfigurationError) as exc_info:
        build_live_runtime_dependencies_from_env(env)

    error = exc_info.value.to_error()
    assert error["code"] == "LIVE_RUNTIME_DRIVER_CONFIGURATION_INVALID"
    assert error["field"] == "ADAPTER_POSTGRES_DSN"
    assert "ADAPTER_POSTGRES_DSN" in error["message"]
    assert json.loads(json.dumps(error)) == error


def test_driver_factory_summary_redacts_dsn_tokens_rpc_credentials_and_addresses() -> None:
    from token_payments.runtime import LiveRuntimeConfig, build_live_runtime_dependencies_from_env, describe_live_runtime_dependencies

    env = _factory_env() | {
        "ADAPTER_POSTGRES_DSN": "postgresql://token_payments:super-secret-password@postgres:5432/token_payments",
        "ADAPTER_BLOCKCHAIN_RPC_URL": "https://rpc.local/path?token=paid-secret",
        "ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS": "0x3333333333333333333333333333333333333333",
    }
    config = LiveRuntimeConfig.from_env(env)
    dependencies = build_live_runtime_dependencies_from_env(env, config=config)
    payload = describe_live_runtime_dependencies(config=config, dependencies=dependencies)
    encoded = json.dumps(payload, sort_keys=True)

    assert "super-secret-password" not in encoded
    assert "paid-secret" not in encoded
    assert "0x3333333333333333333333333333333333333333" not in encoded
    assert payload["config"]["adapters"]["postgres"]["dsn"] == (
        "postgresql://token_payments:<redacted>@postgres:5432/token_payments"
    )
    assert payload["config"]["adapters"]["blockchain"]["rpcUrl"] == "https://rpc.local/path?<redacted>"
    assert payload["config"]["adapters"]["blockchain"]["tokenAddress"] == "<redacted>"


def test_docker_image_contract_installs_live_runtime_dependencies_reproducibly() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements-runtime.txt").read_text(encoding="utf-8")

    assert "COPY requirements-runtime.txt /workspace/requirements-runtime.txt" in dockerfile
    assert "python -m pip install --no-cache-dir -r /workspace/requirements-runtime.txt" in dockerfile
    for package in REQUIRED_RUNTIME_REQUIREMENTS:
        assert any(line.startswith(f"{package}==") for line in requirements.splitlines()), package
    assert "kafka-python==2.3.1" in requirements


def test_live_driver_factory_source_and_import_path_keep_driver_imports_lazy() -> None:
    imported_roots = _imported_roots(ROOT / "app/token_payments/runtime/composition.py")
    assert imported_roots.isdisjoint(FORBIDDEN_EAGER_IMPORT_ROOTS)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")
    code = """
import json
import sys
from token_payments.runtime import build_live_runtime_dependencies_from_env

forbidden = {
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
before = set(sys.modules)
build_live_runtime_dependencies_from_env({
    "ADAPTER_POSTGRES_DSN": "postgresql://u:p@postgres:5432/token_payments",
    "ADAPTER_KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
    "ADAPTER_KAFKA_CLIENT_ID": "token-payments-local",
    "ADAPTER_WALLET_SIGNATURE_DOMAIN": "token-payments.local",
    "ADAPTER_BLOCKCHAIN_RPC_URL": "http://localhost:8545",
    "ADAPTER_BLOCKCHAIN_CHAIN_ID": "1337",
})
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


def _factory_env() -> dict[str, str]:
    return {
        "RUNTIME_ENVIRONMENT": "local",
        "ADAPTER_POSTGRES_DSN": "postgresql://token_payments:local_dev_only_password@postgres:5432/token_payments",
        "ADAPTER_KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
        "ADAPTER_KAFKA_CLIENT_ID": "token-payments-local",
        "ADAPTER_WALLET_SIGNATURE_DOMAIN": "token-payments.local",
        "ADAPTER_BLOCKCHAIN_RPC_URL": "http://localhost:8545",
        "ADAPTER_BLOCKCHAIN_CHAIN_ID": "1337",
        "ADAPTER_BLOCKCHAIN_NATIVE_SYMBOL": "ETH",
        "ADAPTER_BLOCKCHAIN_NATIVE_DECIMALS": "18",
        "ADAPTER_BLOCKCHAIN_GAS_BUFFER_RATE": "0.10",
        "SESSION_ACTIVE_KEY_ID": "local-dev-2026",
        "SESSION_SIGNING_KEYS": "local-dev-2026=local_dev_only_session_signing_key_32_bytes_for_tests",
        "CSRF_ACTIVE_KEY_ID": "local-dev-csrf-2026",
        "CSRF_SIGNING_KEY": "local_dev_only_csrf_signing_key_32_bytes_for_tests",
    }


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".", 1)[0])
    return roots

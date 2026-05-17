from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

ENV_PATH = ROOT / ".env.example"
SEED_PLAN_PATH = ROOT / "postman" / "fixtures" / "token-payments.local.seed-plan.json"
SCHEMA_PATH = ROOT / "app" / "postgres" / "init.d" / "001-token-payments-schema.sql"
FORBIDDEN_SECRET_PATTERNS = (
    re.compile(r"\b(seed phrase|mnemonic|production credential|prod token|mainnet private)\b", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b0x[a-fA-F0-9]{64}\b"),
)


def test_env_example_provides_local_dev_signing_material_but_live_prod_rejects_it() -> None:
    from token_payments.runtime import LiveRuntimeConfig

    env = _env_values()
    local_config = LiveRuntimeConfig.from_env(env)

    assert local_config.runtime_environment == "local"
    assert env["SESSION_ACTIVE_KEY_ID"] == "local-dev-2026"
    assert env["SESSION_SIGNING_KEYS"].startswith("local-dev-2026=local_dev_only_session_signing_key")
    assert env["CSRF_SIGNING_KEY"].startswith("local_dev_only_csrf_signing_key")
    assert "replace_with" not in env["SESSION_SIGNING_KEYS"]
    assert "replace_with" not in env["CSRF_SIGNING_KEY"]

    with pytest.raises(ValueError, match="local dev|placeholder"):
        LiveRuntimeConfig.from_env(env | {"RUNTIME_ENVIRONMENT": "live"})


def test_env_example_wires_api_postgres_kafka_blockchain_cors_csrf_and_seed_names_consistently() -> None:
    env = _env_values()
    seed = _read_json(SEED_PLAN_PATH)

    assert env["COMPOSE_PROFILES"] == "runtime,smoke,api"
    assert env["LOCAL_API_ORIGIN"] == env["API_PUBLIC_BASE_URL"] == "http://localhost:8000"
    assert env["RUNTIME_API_HOST"] == "0.0.0.0"
    assert env["RUNTIME_API_PORT"] == "8000"
    assert env["ADAPTER_KAFKA_BOOTSTRAP_SERVERS"] == "kafka:9092"
    assert env["ADAPTER_POSTGRES_DSN"].startswith(
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}@postgres:5432/{env['POSTGRES_DB']}"
    )
    assert env["TEST_NETWORK_NETWORK_ID"] == env["ADAPTER_BLOCKCHAIN_CHAIN_ID"] == str(seed["ids"]["testNetworkChainId"])
    assert env["ADAPTER_BLOCKCHAIN_RPC_URL"] == ""
    assert env["ADAPTER_BLOCKCHAIN_RPC_SCHEME"] == "http"
    assert env["ADAPTER_BLOCKCHAIN_RPC_HOST"] == "test_network"
    assert env["ADAPTER_BLOCKCHAIN_RPC_PORT"] == "8545"
    assert env["CSRF_COOKIE_NAME"] == "csrf_token"
    assert env["CSRF_HEADER_NAME"] == "X-CSRF-Token"
    assert "http://localhost:5173" in env["CORS_ALLOWED_ORIGINS"]


def test_env_example_does_not_commit_real_secrets_or_paid_rpc_credentials() -> None:
    text = ENV_PATH.read_text(encoding="utf-8")
    env = _env_values()

    for pattern in FORBIDDEN_SECRET_PATTERNS:
        assert not pattern.search(text)
    assert env["TEST_NETWORK_PRIVATE_KEY"] == "0xreplace_with_local_dev_only_private_key"
    assert env["ADAPTER_BLOCKCHAIN_RPC_URL"] == ""
    assert "api_key" not in text.lower()
    assert "mainnet" not in text.lower()


def test_seed_plan_matches_schema_columns_and_local_test_network_env_values() -> None:
    env = _env_values()
    seed = _read_json(SEED_PLAN_PATH)
    schema = _schema_tables()

    assert seed["manualOnly"] is True
    assert seed["defaultInitMutation"] is False
    assert seed["ids"]["testNetworkChainId"] == int(env["ADAPTER_BLOCKCHAIN_CHAIN_ID"])
    assert seed["ids"]["testNetworkNetworkId"] == env["TEST_NETWORK_NETWORK_ID"]
    assert seed["ids"]["testNetworkAccountPlaceholder"] == "${TEST_NETWORK_ACCOUNT}"
    assert seed["ids"]["testNetworkRpcUrlPlaceholder"] == (
        "${ADAPTER_BLOCKCHAIN_RPC_SCHEME}://${ADAPTER_BLOCKCHAIN_RPC_HOST}:${ADAPTER_BLOCKCHAIN_RPC_PORT}"
    )
    assert seed["ids"]["paymentDestinationWallet"].startswith("0x")

    for record in seed["records"]:
        table = record["table"]
        assert table in schema
        assert set(record["columns"]) <= schema[table], f"{table} seed must use committed schema columns"
        assert set(record["values"]) == set(record["columns"])


def _env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(ENV_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        assert "=" in line, f".env.example:{line_number} must be KEY=VALUE syntax"
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _read_json(path: Path) -> Any:
    assert path.exists(), f"{path.relative_to(ROOT)} must exist"
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_tables() -> dict[str, set[str]]:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    tables: dict[str, set[str]] = {}
    for match in re.finditer(
        r"CREATE TABLE IF NOT EXISTS (?P<table>[a-z_]+) \((?P<body>.*?)\n\);",
        schema_text,
        flags=re.DOTALL,
    ):
        columns: set[str] = set()
        for raw_line in match.group("body").splitlines():
            stripped = raw_line.strip().rstrip(",")
            if not stripped or stripped.startswith(("PRIMARY ", "UNIQUE ", "FOREIGN ", "CHECK ", "CONSTRAINT ")):
                continue
            columns.add(stripped.split()[0])
        tables[match.group("table")] = columns
    return tables

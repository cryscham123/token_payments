from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


REQUIRED_ENV_KEYS = [
    "COMPOSE_PROFILES",
    "TEST_NETWORK_PRIVATE_KEY",
    "TEST_NETWORK_ACCOUNT",
    "TEST_NETWORK_NETWORK_ID",
    "TEST_NETWORK_DB_PATH",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "TZ",
    "RUNTIME_API_HOST",
    "RUNTIME_API_PORT",
    "RUNTIME_REQUEST_TIMEOUT_SECONDS",
    "RUNTIME_WORKER_BATCH_SIZE",
    "RUNTIME_WORKER_POLL_INTERVAL_SECONDS",
    "RUNTIME_RECEIPT_POLL_INTERVAL_SECONDS",
    "ADAPTER_POSTGRES_DSN",
    "ADAPTER_KAFKA_BOOTSTRAP_SERVERS",
    "ADAPTER_KAFKA_CLIENT_ID",
    "ADAPTER_OUTBOX_BATCH_SIZE",
    "ADAPTER_OUTBOX_POLL_INTERVAL_SECONDS",
    "ADAPTER_OUTBOX_RETRY_MAX_ATTEMPTS",
    "ADAPTER_OUTBOX_RETRY_INITIAL_DELAY_SECONDS",
    "ADAPTER_OUTBOX_RETRY_MAX_DELAY_SECONDS",
    "ADAPTER_WALLET_SIGNATURE_DOMAIN",
    "ADAPTER_BLOCKCHAIN_RPC_SCHEME",
    "ADAPTER_BLOCKCHAIN_RPC_HOST",
    "ADAPTER_BLOCKCHAIN_RPC_PORT",
    "ADAPTER_BLOCKCHAIN_RPC_PATH",
    "ADAPTER_BLOCKCHAIN_RPC_URL",
    "ADAPTER_BLOCKCHAIN_CHAIN_ID",
    "ADAPTER_BLOCKCHAIN_NATIVE_SYMBOL",
    "ADAPTER_BLOCKCHAIN_NATIVE_DECIMALS",
    "ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS",
    "ADAPTER_BLOCKCHAIN_GAS_BUFFER_RATE",
]

REQUIRED_SERVICES = ["postgres", "kafka", "kafka-ui", "pgweb", "test_network"]
READINESS_COMMAND_SEQUENCE = [
    "health",
    "worker",
    "smoke happy-path-checkout",
    "smoke compensation-checkout",
]


def test_compose_readiness_smoke_validates_committed_contracts_without_docker() -> None:
    from token_payments.runtime.smoke import run_smoke_scenario

    result = run_smoke_scenario("compose-readiness").to_dict()

    assert result["scenario"] == "compose-readiness"
    assert result["status"] == "passed"
    assert result["summary"] == (
        "compose readiness validated committed env, compose, path, and runtime command contracts "
        "without starting Docker"
    )
    assert [step["name"] for step in result["steps"]] == [
        ".env.example contract",
        "docker-compose service contract",
        "compose path references",
        "runtime command readiness chain",
    ]

    details = result["details"]
    assert details["dockerStarted"] is False
    assert details["networkCalls"] is False
    assert details["envExample"]["path"] == ".env.example"
    assert details["envExample"]["requiredKeys"] == REQUIRED_ENV_KEYS
    assert details["envExample"]["placeholderSafe"] is True
    assert details["envExample"]["sensitivePlaceholderKeys"] == [
        "TEST_NETWORK_PRIVATE_KEY",
        "TEST_NETWORK_ACCOUNT",
        "POSTGRES_PASSWORD",
        "ADAPTER_POSTGRES_DSN",
        "ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS",
    ]
    assert details["compose"]["path"] == "docker-compose.yml"
    assert details["compose"]["requiredServices"] == REQUIRED_SERVICES
    assert details["compose"]["serviceNames"] == REQUIRED_SERVICES
    assert details["compose"]["serviceContracts"]["postgres"]["envFile"] == [".env"]
    assert details["compose"]["serviceContracts"]["postgres"]["initDirectoryMounted"] is True
    assert details["compose"]["serviceContracts"]["test_network"]["envFile"] == [".env"]
    assert details["compose"]["serviceContracts"]["test_network"]["buildContext"] == "app/test_network"
    assert details["paths"] == {
        "postgresInitScript": "app/postgres/init.d/001-token-payments-schema.sql",
        "testNetworkDockerfile": "app/test_network/Dockerfile",
    }
    assert details["runtimeCommandChain"] == [
        {
            "command": command,
            "boundedJson": True,
            "startsLongRunningProcess": False,
        }
        for command in READINESS_COMMAND_SEQUENCE
    ]
    json.dumps(result)


def test_compose_readiness_smoke_cli_outputs_bounded_json() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")

    completed = subprocess.run(
        [sys.executable, "-m", "token_payments", "smoke", "compose-readiness"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert payload["command"] == "smoke"
    assert payload["status"] == "SUCCEEDED"
    assert payload["details"]["smoke"]["scenario"] == "compose-readiness"
    assert payload["details"]["smoke"]["status"] == "passed"
    assert payload["details"]["smoke"]["details"]["runtimeCommandChain"][-1]["command"] == (
        "smoke compensation-checkout"
    )
    assert payload["details"]["smoke"]["details"]["dockerStarted"] is False
    assert len(completed.stdout) < 16000

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

SCENARIO = "docker-runtime-readiness"
RUN_COMMANDS = [
    "docker compose --env-file .env --profile runtime run --rm token_payments_health",
    "docker compose --env-file .env --profile runtime run --rm token_payments_worker",
    "docker compose --env-file .env --profile smoke run --rm token_payments_smoke",
]
BUILD_COMMAND = "docker compose --env-file .env --profile runtime build token_payments_health"
COMPOSE_CONFIG_VALIDATION_COMMAND = "docker compose --env-file .env.example config --services"


def test_docker_runtime_readiness_scenario_is_registered() -> None:
    from token_payments.runtime.smoke import AVAILABLE_SMOKE_SCENARIOS, describe_smoke_registry

    assert SCENARIO in AVAILABLE_SMOKE_SCENARIOS

    registry = describe_smoke_registry()
    assert SCENARIO in registry["availableScenarios"]
    assert registry["runnerCount"] == len(registry["availableScenarios"])
    json.dumps(registry)


def test_docker_runtime_readiness_smoke_validates_static_contracts_without_docker() -> None:
    from token_payments.runtime.smoke import run_smoke_scenario

    result = run_smoke_scenario(SCENARIO).to_dict()

    assert result["scenario"] == SCENARIO
    assert result["status"] == "passed"
    assert result["summary"] == (
        "docker runtime readiness validated image, dockerignore, env path, compose config command, "
        "and compose one-shot commands without starting Docker"
    )
    assert [step["name"] for step in result["steps"]] == [
        "Dockerfile runtime image contract",
        ".dockerignore runtime context contract",
        "compose runtime service contract",
        "manual live command contract",
    ]

    details = result["details"]
    assert details["dockerStarted"] is False
    assert details["networkCalls"] is False

    assert details["image"]["contract"] == {
        "dockerfile": "Dockerfile",
        "baseImage": "python:3.12-slim",
        "workdir": "/workspace",
        "pythonPath": "/workspace/app",
        "packageCopySource": "app/token_payments",
        "packageCopyDestination": "/workspace/app/token_payments",
        "supportCopySources": [
            "Dockerfile",
            ".dockerignore",
            "docker-compose.yml",
            ".env.example",
            "app/postgres/init.d/001-token-payments-schema.sql",
            "app/test_network/Dockerfile",
        ],
        "cmd": ["python", "-m", "token_payments", "health"],
    }
    assert details["image"]["dockerignore"] == {
        "path": ".dockerignore",
        "excludesLocalEnv": True,
        "excludesGit": True,
        "excludesCache": True,
        "excludesPhaseOutputs": True,
    }
    assert details["image"]["envExamplePath"] == ".env.example"

    assert details["compose"]["runtimeServices"] == {
        "token_payments_health": {
            "image": "token_payments_runtime",
            "buildContext": ".",
            "dockerfile": "Dockerfile",
            "envFile": [".env"],
            "pythonPath": "/workspace/app",
            "command": ["python", "-m", "token_payments", "health"],
            "restart": "no",
            "profiles": ["runtime"],
            "dependsOn": {
                "postgres": "service_healthy",
                "kafka": "service_started",
                "test_network": "service_started",
            },
        },
        "token_payments_worker": {
            "image": "token_payments_runtime",
            "buildContext": ".",
            "dockerfile": "Dockerfile",
            "envFile": [".env"],
            "pythonPath": "/workspace/app",
            "command": ["python", "-m", "token_payments", "worker"],
            "restart": "no",
            "profiles": ["runtime"],
            "dependsOn": {
                "postgres": "service_healthy",
                "kafka": "service_started",
                "test_network": "service_started",
            },
        },
        "token_payments_smoke": {
            "image": "token_payments_runtime",
            "buildContext": ".",
            "dockerfile": "Dockerfile",
            "envFile": [".env"],
            "pythonPath": "/workspace/app",
            "command": ["python", "-m", "token_payments", "smoke", "compose-readiness"],
            "restart": "no",
            "profiles": ["runtime", "smoke"],
            "dependsOn": {
                "postgres": "service_healthy",
                "kafka": "service_started",
                "test_network": "service_started",
            },
        },
    }
    assert details["compose"]["buildCommand"] == BUILD_COMMAND
    assert details["compose"]["runCommands"] == RUN_COMMANDS
    assert details["compose"]["composeConfigValidationCommand"] == {
        "command": COMPOSE_CONFIG_VALIDATION_COMMAND,
        "daemonless": True,
        "usesDockerSocket": False,
        "forbiddenCommands": ["up", "run", "build"],
    }
    assert "docker compose --env-file .env down" in details["manualLiveCommands"]
    assert _contains_only_json_primitives(result)
    json.dumps(result)


def test_docker_runtime_readiness_cli_outputs_bounded_json() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")

    completed = subprocess.run(
        [sys.executable, "-m", "token_payments", "smoke", SCENARIO],
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
    assert payload["details"]["smoke"]["scenario"] == SCENARIO
    assert payload["details"]["smoke"]["status"] == "passed"
    assert payload["details"]["smoke"]["details"]["dockerStarted"] is False
    assert payload["details"]["smoke"]["details"]["networkCalls"] is False
    assert payload["details"]["smoke"]["details"]["compose"]["runCommands"] == RUN_COMMANDS
    assert (
        payload["details"]["smoke"]["details"]["compose"]["composeConfigValidationCommand"]["command"]
        == COMPOSE_CONFIG_VALIDATION_COMMAND
    )
    assert len(completed.stdout) < 20000


def _contains_only_json_primitives(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_contains_only_json_primitives(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _contains_only_json_primitives(item) for key, item in value.items())
    return False

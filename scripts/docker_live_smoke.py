#!/usr/bin/env python3
"""Dry-run planner for the live Docker compose smoke sequence."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any


CONTRACT = "token-payments.docker-live-smoke.plan.v1"
ENV_FILE = ".env"
REQUIRED_SERVICES = (
    "postgres",
    "kafka",
    "kafka-ui",
    "pgweb",
    "test_network",
    "token_payments_health",
    "token_payments_worker",
    "token_payments_smoke",
)
COMMAND_SEQUENCE: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "compose-config",
        ("docker", "compose", "--env-file", ENV_FILE, "--profile", "runtime", "config", "--services"),
    ),
    (
        "start-infrastructure",
        ("docker", "compose", "--env-file", ENV_FILE, "up", "-d", "postgres", "kafka", "kafka-ui", "pgweb", "test_network"),
    ),
    (
        "runtime-health",
        ("docker", "compose", "--env-file", ENV_FILE, "--profile", "runtime", "run", "--rm", "token_payments_health"),
    ),
    (
        "runtime-worker",
        ("docker", "compose", "--env-file", ENV_FILE, "--profile", "runtime", "run", "--rm", "token_payments_worker"),
    ),
    (
        "runtime-smoke",
        ("docker", "compose", "--env-file", ENV_FILE, "--profile", "smoke", "run", "--rm", "token_payments_smoke"),
    ),
)
CLEANUP_COMMAND = ("docker", "compose", "--env-file", ENV_FILE, "down")


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_plan() -> dict[str, Any]:
    repository_root()
    return {
        "contract": CONTRACT,
        "mode": "plan",
        "status": "planned",
        "dockerStarted": False,
        "networkCalls": False,
        "envFile": ENV_FILE,
        "requiredServices": list(REQUIRED_SERVICES),
        "commandSequence": [_command_payload(name, argv) for name, argv in COMMAND_SEQUENCE],
        "cleanupCommand": _command_payload("cleanup", CLEANUP_COMMAND),
    }


def build_execute_error() -> dict[str, Any]:
    return {
        "contract": CONTRACT,
        "mode": "execute",
        "status": "error",
        "dockerStarted": False,
        "networkCalls": False,
        "envFile": ENV_FILE,
        "requiredServices": list(REQUIRED_SERVICES),
        "commandSequence": [_command_payload(name, argv) for name, argv in COMMAND_SEQUENCE],
        "cleanupCommand": _command_payload("cleanup", CLEANUP_COMMAND),
        "error": {
            "code": "LIVE_DOCKER_EXECUTION_NOT_IMPLEMENTED",
            "message": "Live Docker execution is intentionally unavailable in this step; use --plan for the dry-run contract.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the live Docker smoke dry-run plan as bounded JSON.")
    parser.add_argument("--plan", action="store_true", help="Print the dry-run plan without starting Docker.")
    parser.add_argument("--execute", action="store_true", help="Reject live execution for this step as JSON.")
    args = parser.parse_args(argv)

    if args.execute:
        _print_json(build_execute_error())
        return 2

    _print_json(build_plan())
    return 0


def _command_payload(name: str, argv: tuple[str, ...]) -> dict[str, Any]:
    return {
        "name": name,
        "argv": list(argv),
        "display": shlex.join(argv),
        "shell": False,
    }


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    raise SystemExit(main())

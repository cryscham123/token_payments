#!/usr/bin/env python3
"""Plan and explicitly approved live runner for Docker compose smoke checks."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


CONTRACT = "token-payments.docker-live-smoke.plan.v1"
ENV_FILE = ".env"
ENV_EXAMPLE_FILE = ".env.example"
MAX_OUTPUT_CHARS = 1200
SECRET_KEY_PATTERN = re.compile(r"(account|api[_-]?key|dsn|key|password|private|secret|seed|token)", re.IGNORECASE)
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
COMMAND_TIMEOUT_SECONDS = {
    "compose-config": 30,
    "build-runtime-image": 240,
    "start-infrastructure": 180,
    "runtime-health": 120,
    "runtime-worker": 120,
    "runtime-smoke": 120,
    "cleanup": 90,
}


def _build_command_sequence(env_file: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        (
            "compose-config",
            ("docker", "compose", "--env-file", env_file, "--profile", "runtime", "config", "--services"),
        ),
        (
            "build-runtime-image",
            ("docker", "compose", "--env-file", env_file, "--profile", "runtime", "build", "token_payments_health"),
        ),
        (
            "start-infrastructure",
            (
                "docker",
                "compose",
                "--env-file",
                env_file,
                "up",
                "-d",
                "postgres",
                "kafka",
                "kafka-ui",
                "pgweb",
                "test_network",
            ),
        ),
        (
            "runtime-health",
            ("docker", "compose", "--env-file", env_file, "--profile", "runtime", "run", "--rm", "token_payments_health"),
        ),
        (
            "runtime-worker",
            ("docker", "compose", "--env-file", env_file, "--profile", "runtime", "run", "--rm", "token_payments_worker"),
        ),
        (
            "runtime-smoke",
            ("docker", "compose", "--env-file", env_file, "--profile", "smoke", "run", "--rm", "token_payments_smoke"),
        ),
    )


def _build_cleanup_command(env_file: str) -> tuple[str, ...]:
    return ("docker", "compose", "--env-file", env_file, "down")


COMMAND_SEQUENCE = _build_command_sequence(ENV_FILE)
CLEANUP_COMMAND = _build_cleanup_command(ENV_FILE)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build_plan(env_file: str = ENV_FILE) -> dict[str, Any]:
    repository_root()
    command_sequence = _build_command_sequence(env_file)
    cleanup_command = _build_cleanup_command(env_file)
    return {
        "contract": CONTRACT,
        "mode": "plan",
        "status": "planned",
        "dockerStarted": False,
        "networkCalls": False,
        "envFile": env_file,
        "requiredServices": list(REQUIRED_SERVICES),
        "commandSequence": [_command_payload(name, argv) for name, argv in command_sequence],
        "cleanupCommand": _command_payload("cleanup", cleanup_command),
    }


def build_execute_error(
    code: str = "LIVE_DOCKER_CONFIRMATION_REQUIRED",
    message: str = "Live Docker execution requires both --execute and --confirm-live-docker.",
    env_file: str = ENV_FILE,
    *,
    docker_started: bool = False,
    network_calls: bool = False,
) -> dict[str, Any]:
    command_sequence = _build_command_sequence(env_file)
    cleanup_command = _build_cleanup_command(env_file)
    return {
        "contract": CONTRACT,
        "mode": "execute",
        "status": "error",
        "dockerStarted": docker_started,
        "networkCalls": network_calls,
        "envFile": env_file,
        "requiredServices": list(REQUIRED_SERVICES),
        "commandSequence": [_command_payload(name, argv) for name, argv in command_sequence],
        "cleanupCommand": _command_payload("cleanup", cleanup_command),
        "error": {
            "code": code,
            "message": message,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print or explicitly run the live Docker smoke sequence as bounded JSON.")
    parser.add_argument("--plan", action="store_true", help="Print the dry-run plan without starting Docker.")
    parser.add_argument("--execute", action="store_true", help="Run the live Docker smoke sequence only with explicit confirmation.")
    parser.add_argument(
        "--confirm-live-docker",
        action="store_true",
        help="Required with --execute to acknowledge live Docker daemon/container execution.",
    )
    parser.add_argument("--env-file", default=ENV_FILE, help="Docker compose env file for plan or live execution.")
    args = parser.parse_args(argv)

    if args.execute:
        if not args.confirm_live_docker:
            _print_json(build_execute_error(env_file=args.env_file))
            return 2
        exit_code, payload = run_live_execution(args.env_file)
        _print_json(payload)
        return exit_code

    _print_json(build_plan(args.env_file))
    return 0


def run_live_execution(env_file: str) -> tuple[int, dict[str, Any]]:
    root = repository_root()
    env_path = _resolve_env_path(root, env_file)

    if Path(env_file).name == ENV_EXAMPLE_FILE:
        return (
            2,
            build_execute_error(
                "LIVE_DOCKER_ENV_FILE_FORBIDDEN",
                ".env.example is a template and must not be used for live Docker execution.",
                env_file,
            ),
        )
    if not env_path.is_file():
        return (
            2,
            build_execute_error(
                "LIVE_DOCKER_ENV_FILE_REQUIRED",
                f"Live Docker execution requires an existing env file at {_display_path(root, env_path)}.",
                env_file,
            ),
        )

    try:
        redactions = _load_sensitive_values(env_path)
    except OSError as exc:
        return (
            2,
            build_execute_error(
                "LIVE_DOCKER_ENV_FILE_UNREADABLE",
                f"Live Docker env file could not be read for output redaction: {exc}",
                env_file,
            ),
        )

    command_sequence = _build_command_sequence(env_file)
    cleanup_command = _build_cleanup_command(env_file)
    command_results: list[dict[str, Any]] = []
    cleanup_result: dict[str, Any] | None = None
    cleanup_required = False
    docker_started = False
    network_calls = False
    failed_result: dict[str, Any] | None = None

    for name, argv in command_sequence:
        if name == "build-runtime-image":
            network_calls = True
        if name == "start-infrastructure":
            cleanup_required = True
            docker_started = True
            network_calls = True
        result = _run_docker_command(name, argv, root, redactions)
        command_results.append(result)
        if _command_failed(result):
            failed_result = result
            break

    if cleanup_required:
        cleanup_result = _run_docker_command("cleanup", cleanup_command, root, redactions)
        if failed_result is None and _command_failed(cleanup_result):
            failed_result = cleanup_result

    if failed_result is not None:
        payload = _execution_payload(
            env_file=env_file,
            status="error",
            docker_started=docker_started,
            network_calls=network_calls,
            command_results=command_results,
            cleanup_result=cleanup_result,
        )
        payload["failedStep"] = failed_result["name"]
        payload["exitCode"] = failed_result["exitCode"]
        payload["error"] = {
            "code": "DOCKER_COMMAND_FAILED",
            "message": f"Docker live smoke command failed at step {failed_result['name']}.",
            "failedStep": failed_result["name"],
            "exitCode": failed_result["exitCode"],
        }
        return 1, payload

    payload = _execution_payload(
        env_file=env_file,
        status="success",
        docker_started=True,
        network_calls=True,
        command_results=command_results,
        cleanup_result=cleanup_result,
    )
    return 0, payload


def _execution_payload(
    *,
    env_file: str,
    status: str,
    docker_started: bool,
    network_calls: bool,
    command_results: list[dict[str, Any]],
    cleanup_result: dict[str, Any] | None,
) -> dict[str, Any]:
    command_sequence = _build_command_sequence(env_file)
    cleanup_command = _build_cleanup_command(env_file)
    return {
        "contract": CONTRACT,
        "mode": "execute",
        "status": status,
        "dockerStarted": docker_started,
        "networkCalls": network_calls,
        "envFile": env_file,
        "requiredServices": list(REQUIRED_SERVICES),
        "commandSequence": [_command_payload(name, argv) for name, argv in command_sequence],
        "cleanupCommand": _command_payload("cleanup", cleanup_command),
        "executedSteps": [result["name"] for result in command_results],
        "commandCount": len(command_results) + (1 if cleanup_result is not None else 0),
        "cleanupExecuted": cleanup_result is not None,
        "commandResults": command_results,
        "cleanupResult": cleanup_result,
    }


def _run_docker_command(name: str, argv: tuple[str, ...], root: Path, redactions: tuple[str, ...]) -> dict[str, Any]:
    timeout = COMMAND_TIMEOUT_SECONDS[name]
    try:
        completed = subprocess.run(
            list(argv),
            cwd=root,
            shell=False,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            **_command_payload(name, argv),
            "timeoutSeconds": timeout,
            "exitCode": completed.returncode,
            "stdout": _sanitize_output(completed.stdout, redactions),
            "stderr": _sanitize_output(completed.stderr, redactions),
            "timedOut": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            **_command_payload(name, argv),
            "timeoutSeconds": timeout,
            "exitCode": None,
            "stdout": _sanitize_output(_to_text(exc.stdout), redactions),
            "stderr": _sanitize_output(_to_text(exc.stderr), redactions),
            "timedOut": True,
        }


def _command_failed(result: dict[str, Any]) -> bool:
    return result["timedOut"] or result["exitCode"] != 0


def _command_payload(name: str, argv: tuple[str, ...]) -> dict[str, Any]:
    return {
        "name": name,
        "argv": list(argv),
        "display": shlex.join(argv),
        "shell": False,
    }


def _resolve_env_path(root: Path, env_file: str) -> Path:
    path = Path(env_file)
    if path.is_absolute():
        return path
    return root / path


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _load_sensitive_values(env_path: Path) -> tuple[str, ...]:
    values: set[str] = set()
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip().strip("\"'")
        if len(value) >= 4 and SECRET_KEY_PATTERN.search(key):
            values.add(value)
    return tuple(sorted(values, key=len, reverse=True))


def _sanitize_output(value: str | None, redactions: tuple[str, ...]) -> str:
    text = value or ""
    for secret in redactions:
        text = text.replace(secret, "[REDACTED]")
    if len(text) > MAX_OUTPUT_CHARS:
        return f"{text[:MAX_OUTPUT_CHARS]}...[truncated {len(text) - MAX_OUTPUT_CHARS} chars]"
    return text


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    raise SystemExit(main())

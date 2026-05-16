from __future__ import annotations

import ast
import importlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


REQUIRED_DOCKER_PHASE_ARTIFACTS = (
    "Dockerfile",
    ".dockerignore",
    "docker-compose.yml",
    ".env.example",
    "app/token_payments/runtime/smoke.py",
    "app/token_payments/runtime/__init__.py",
    "scripts/test_docker_runtime_image_contracts.py",
    "scripts/test_docker_compose_runtime_services.py",
    "scripts/test_docker_runtime_smoke.py",
    "scripts/test_docker_compose_config_validation.py",
)
SMOKE_SCENARIOS = (
    "happy-path-checkout",
    "compensation-checkout",
    "compose-readiness",
    "docker-runtime-readiness",
)
FORBIDDEN_SMOKE_IMPORT_ROOTS = {
    "aiohttp",
    "asyncpg",
    "confluent_kafka",
    "docker",
    "fastapi",
    "flask",
    "httpx",
    "kafka",
    "psycopg",
    "psycopg2",
    "requests",
    "sqlalchemy",
    "starlette",
    "urllib3",
    "uvicorn",
    "web3",
}
FORBIDDEN_SMOKE_IMPORT_MODULES = {
    "http.client",
    "urllib.request",
}
DOCUMENTED_DOCKER_COMMANDS = (
    "PYTHONPATH=app python3 -m token_payments smoke docker-runtime-readiness",
    "docker compose --env-file .env.example --profile runtime config --services",
    "cp .env.example .env",
    "docker compose --env-file .env --profile runtime config --services",
    "docker compose --env-file .env --profile runtime build token_payments_health",
    "docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network",
    "docker compose --env-file .env --profile runtime run --rm token_payments_health",
    "docker compose --env-file .env --profile runtime run --rm token_payments_worker",
    "docker compose --env-file .env --profile smoke run --rm token_payments_smoke",
    "docker compose --env-file .env down",
)
MANUAL_LIVE_COMMANDS = DOCUMENTED_DOCKER_COMMANDS[2:]
DOCUMENTED_DOCKER_PHRASES = (
    "Docker runtime image",
    "compose one-shot services",
    "docker-runtime-readiness",
    "daemon-less compose config validation",
    "static/config/smoke contract",
    "Docker daemon/socket",
    "Postman-ready API roadmap",
    "live API runtime composition",
    "Postman Docker API readiness",
)


def test_docker_phase_public_artifacts_exist() -> None:
    for relative_path in REQUIRED_DOCKER_PHASE_ARTIFACTS:
        path = ROOT / relative_path

        assert path.exists(), f"{relative_path} must exist"
        assert path.stat().st_size > 0, f"{relative_path} must not be empty"


def test_runtime_smoke_public_registry_imports_and_executes_all_scenarios() -> None:
    runtime = importlib.import_module("token_payments.runtime")
    smoke = importlib.import_module("token_payments.runtime.smoke")

    assert smoke.AVAILABLE_SMOKE_SCENARIOS == SMOKE_SCENARIOS
    assert runtime.AVAILABLE_SMOKE_SCENARIOS == SMOKE_SCENARIOS
    assert smoke.describe_smoke_registry() == {
        "contract": "CommandDispatchResult.details.smoke",
        "availableScenarios": list(SMOKE_SCENARIOS),
        "runnerCount": len(SMOKE_SCENARIOS),
    }

    for scenario in SMOKE_SCENARIOS:
        result = runtime.run_smoke_scenario(scenario).to_dict()

        assert result["scenario"] == scenario
        assert result["status"] == "passed"
        assert _contains_only_json_primitives(result)
        json.dumps(result)

    docker_result = runtime.run_smoke_scenario("docker-runtime-readiness").to_dict()
    assert docker_result["details"]["dockerStarted"] is False
    assert docker_result["details"]["networkCalls"] is False
    assert docker_result["details"]["manualLiveCommands"] == list(MANUAL_LIVE_COMMANDS)


def test_runtime_smoke_module_avoids_live_clients_frameworks_and_network_imports() -> None:
    smoke_path = ROOT / "app/token_payments/runtime/smoke.py"
    imported_modules = _imported_modules(smoke_path)
    imported_roots = {module.split(".", 1)[0] for module in imported_modules}

    assert imported_roots.isdisjoint(FORBIDDEN_SMOKE_IMPORT_ROOTS)
    assert imported_modules.isdisjoint(FORBIDDEN_SMOKE_IMPORT_MODULES)


def test_dockerfile_compose_and_public_docs_have_no_claude_specific_commands() -> None:
    command_sources = (
        ROOT / "Dockerfile",
        ROOT / "docker-compose.yml",
        ROOT / "README.md",
        ROOT / "app/README.md",
        ROOT / "docs/ADR.md",
        ROOT / "docs/ARCHITECTURE.md",
        ROOT / "docs/HARNESS.md",
        ROOT / "docs/PRD.md",
    )
    violations: dict[str, list[str]] = {}

    for path in command_sources:
        lines = _configuration_lines(path) if path.name in {"Dockerfile", "docker-compose.yml"} else _fenced_code_lines(path)
        bad_lines = [line for line in lines if _has_claude_specific_command(line)]
        if bad_lines:
            violations[str(path.relative_to(ROOT))] = bad_lines

    assert violations == {}


def test_readmes_document_docker_phase_public_verification_and_manual_live_order() -> None:
    readmes = (
        ROOT / "README.md",
        ROOT / "app/README.md",
    )

    for path in readmes:
        text = path.read_text(encoding="utf-8")

        for phrase in DOCUMENTED_DOCKER_PHRASES:
            assert phrase in text, f"{path.relative_to(ROOT)} must document {phrase!r}"
        for command in DOCUMENTED_DOCKER_COMMANDS:
            assert command in text, f"{path.relative_to(ROOT)} must document {command!r}"


def test_phase_9_completed_step_summaries_reference_concrete_docker_artifacts() -> None:
    phase_index = json.loads((ROOT / "phases/9-live-docker-compose-integration/index.json").read_text(encoding="utf-8"))
    top_index = json.loads((ROOT / "phases/index.json").read_text(encoding="utf-8"))
    expected_summary_terms = {
        0: ("Docker runtime image", "Dockerfile"),
        1: ("Docker Compose", "runtime service"),
        2: ("docker-runtime-readiness", "smoke scenario"),
        3: ("Docker Compose", "config validation"),
        4: (
            "public contract",
            "README",
            "Docker runtime image",
            "compose runtime service",
            "smoke scenario",
            "compose config validation",
        ),
    }

    for step in phase_index["steps"]:
        if step["status"] != "completed":
            continue

        summary = step.get("summary", "")
        assert len(summary) >= 40
        for term in expected_summary_terms[step["step"]]:
            assert term in summary

    phase9 = next(phase for phase in top_index["phases"] if phase["dir"] == "9-live-docker-compose-integration")
    assert phase9["status"] == "completed"


def _contains_only_json_primitives(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_contains_only_json_primitives(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _contains_only_json_primitives(item) for key, item in value.items())
    return False


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _configuration_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _fenced_code_lines(path: Path) -> list[str]:
    lines: list[str] = []
    in_fence = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _has_claude_specific_command(line: str) -> bool:
    lowered = line.lower()
    return any(term in lowered for term in ("claude", ".claude", "anthropic"))

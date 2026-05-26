from __future__ import annotations

import ast
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docker_live_smoke.py"
PLAN_TEST = ROOT / "scripts" / "test_docker_live_smoke_plan.py"
EXECUTION_TEST = ROOT / "scripts" / "test_docker_live_smoke_execution.py"

sys.path.insert(0, str(ROOT / "app"))


FORBIDDEN_IMPORT_ROOTS = {
    "aiohttp",
    "docker",
    "httpx",
    "requests",
    "urllib3",
}
FORBIDDEN_IMPORT_MODULES = {
    "http.client",
    "urllib.request",
}
DOCUMENTED_RUNNER_COMMANDS = (
    "python3 scripts/docker_live_smoke.py --plan",
    "python3 scripts/docker_live_smoke.py --execute",
    "cp .env.example .env",
    "python3 scripts/docker_live_smoke.py --execute --confirm-live-docker",
)
DOCUMENTED_RUNNER_PHRASES = (
    "Docker live smoke runner",
    "Automated harness commands",
    "`--execute` by itself returns bounded refusal JSON",
    "does not start Docker",
    "cleanup command is attempted even when a live step fails",
)


def test_live_smoke_runner_public_artifacts_exist() -> None:
    for path in (SCRIPT, PLAN_TEST, EXECUTION_TEST):
        assert path.exists(), f"{path.relative_to(ROOT)} must exist"
        assert path.stat().st_size > 0, f"{path.relative_to(ROOT)} must not be empty"


def test_plan_payload_matches_docker_runtime_readiness_manual_live_order() -> None:
    from token_payments.runtime import run_smoke_scenario

    docker_runtime_readiness = run_smoke_scenario("docker-runtime-readiness").to_dict()
    manual_live_commands = docker_runtime_readiness["details"]["manualLiveCommands"]
    payload = _run_plan()

    planned_commands = [command["display"] for command in payload["commandSequence"]]
    planned_argv = [command["argv"] for command in payload["commandSequence"]]

    assert manual_live_commands[0] == "cp .env.example .env"
    assert planned_commands == manual_live_commands[1:-1]
    assert payload["cleanupCommand"]["display"] == manual_live_commands[-1]
    assert planned_argv == [shlex.split(command) for command in manual_live_commands[1:-1]]
    assert payload["cleanupCommand"]["argv"] == shlex.split(manual_live_commands[-1])
    assert payload["dockerStarted"] is False
    assert payload["networkCalls"] is False


def test_live_smoke_runner_source_avoids_disallowed_execution_dependencies() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    imported_modules = _imported_modules(SCRIPT)
    imported_roots = {module.split(".", 1)[0] for module in imported_modules}

    assert imported_roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS)
    assert imported_modules.isdisjoint(FORBIDDEN_IMPORT_MODULES)

    lower_source = source.lower()
    forbidden_fragments = (
        "shell=true",
        "docker.from_env",
        "docker.client",
        "claude",
        "claude.md",
        ".claude",
        "anthropic",
    )
    for fragment in forbidden_fragments:
        assert fragment not in lower_source


def test_readmes_document_live_smoke_runner_commands_and_refusal_behavior() -> None:
    for path in (ROOT / "app" / "README.md",):
        text = path.read_text(encoding="utf-8")

        for command in DOCUMENTED_RUNNER_COMMANDS:
            assert command in text, f"{path.relative_to(ROOT)} must document {command!r}"
        for phrase in DOCUMENTED_RUNNER_PHRASES:
            assert phrase in text, f"{path.relative_to(ROOT)} must document {phrase!r}"


def test_phase_10_metadata_closes_public_verification_and_top_level_completion() -> None:
    phase_index = json.loads((ROOT / "phases/10-docker-live-smoke-runner/index.json").read_text(encoding="utf-8"))
    top_index = json.loads((ROOT / "phases/index.json").read_text(encoding="utf-8"))
    step2 = next(step for step in phase_index["steps"] if step["step"] == 2)

    assert step2["status"] == "completed"
    summary = step2.get("summary", "")
    assert len(summary) >= 80
    for term in (
        "plan contract",
        "execution guardrail",
        "public verification",
        "docker-runtime-readiness",
        "README",
        "scripts/test_docker_live_smoke_public_contracts.py",
    ):
        assert term in summary

    completed_summary_text = " ".join(
        step.get("summary", "") for step in phase_index["steps"] if step["status"] == "completed"
    ).lower()
    for term in ("plan contract", "execution guardrail", "public verification"):
        assert term in completed_summary_text

    phase10 = next(phase for phase in top_index["phases"] if phase["dir"] == "10-docker-live-smoke-runner")
    assert phase10["status"] == "completed"
    assert phase10.get("completed_at")


def _run_plan() -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--plan"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    return json.loads(completed.stdout)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules

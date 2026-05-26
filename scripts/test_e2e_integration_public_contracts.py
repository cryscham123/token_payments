from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


SMOKE_EXPORTS = {
    "AVAILABLE_SMOKE_SCENARIOS",
    "SMOKE_CONTRACT",
    "UNKNOWN_SMOKE_SCENARIO_ERROR",
    "JsonValue",
    "SmokeResult",
    "SmokeScenarioResult",
    "SmokeStatus",
    "SmokeStep",
    "UnknownSmokeScenario",
    "describe_smoke_registry",
    "run_smoke_scenario",
}
SCENARIOS = (
    "happy-path-checkout",
    "compensation-checkout",
    "compose-readiness",
    "docker-runtime-readiness",
    "postman-docker-api-readiness",
)
EXTERNAL_CLIENT_IMPORT_ROOTS = {
    "aiohttp",
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
    "uvicorn",
    "web3",
}


def test_smoke_public_exports_and_registry_are_stable() -> None:
    runtime = importlib.import_module("token_payments.runtime")
    smoke = importlib.import_module("token_payments.runtime.smoke")

    assert SMOKE_EXPORTS <= set(smoke.__all__)
    assert SMOKE_EXPORTS - {"JsonValue"} <= set(runtime.__all__)
    assert smoke.AVAILABLE_SMOKE_SCENARIOS == SCENARIOS
    assert smoke.SMOKE_CONTRACT == "CommandDispatchResult.details.smoke"
    assert smoke.UNKNOWN_SMOKE_SCENARIO_ERROR == "UNKNOWN_SMOKE_SCENARIO"

    registry = smoke.describe_smoke_registry()
    assert registry == {
        "contract": "CommandDispatchResult.details.smoke",
        "availableScenarios": list(SCENARIOS),
        "runnerCount": len(SCENARIOS),
    }
    json.dumps(registry)


def test_smoke_dispatch_and_cli_cover_registry_all_scenarios_and_unknown_errors() -> None:
    from token_payments.runtime import dispatch_runtime_command

    listed = dispatch_runtime_command(["smoke"]).to_dict()
    unknown = dispatch_runtime_command(["smoke", "not-registered"]).to_dict()

    assert listed["status"] == "SUCCEEDED"
    assert listed["details"]["smoke"]["availableScenarios"] == list(SCENARIOS)
    assert unknown["status"] == "FAILED"
    assert unknown["exitCode"] == 64
    assert unknown["details"]["error"]["code"] == "UNKNOWN_SMOKE_SCENARIO"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")
    commands = [
        [sys.executable, "-m", "token_payments", "smoke"],
        *([sys.executable, "-m", "token_payments", "smoke", scenario] for scenario in SCENARIOS),
    ]

    for command in commands:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        payload = json.loads(result.stdout)
        assert payload["command"] == "smoke"
        assert payload["status"] == "SUCCEEDED"
        assert payload["exitCode"] == 0
        assert _contains_only_json_primitives(payload)
        assert not _contains_secret_or_live_client_terms(result.stdout)


def test_all_smoke_scenario_results_are_json_primitive_payloads() -> None:
    from token_payments.runtime.smoke import SmokeResult, SmokeScenarioResult, SmokeStatus, SmokeStep, run_smoke_scenario

    synthetic = SmokeScenarioResult(
        scenario="serialization-contract",
        result=SmokeResult(
            status=SmokeStatus.PASSED,
            summary="result payloads are converted to JSON primitives",
            details={
                "tupleValue": ("a", "b"),
                "nested": {"ok": True, "count": 1},
            },
        ),
        steps=(
            SmokeStep(
                name="primitive-step",
                result=SmokeResult(
                    status="passed",
                    summary="step details are primitive",
                    details={"items": (1, 2, 3)},
                ),
            ),
        ),
    ).to_dict()

    assert _contains_only_json_primitives(synthetic)
    json.dumps(synthetic)

    for scenario in SCENARIOS:
        payload = run_smoke_scenario(scenario).to_dict()
        assert payload["contract"] == "CommandDispatchResult.details.smoke"
        assert payload["status"] == "passed"
        assert _contains_only_json_primitives(payload)
        json.dumps(payload)


def test_smoke_runtime_import_boundary_avoids_external_clients_and_third_party_dependencies() -> None:
    smoke_path = ROOT / "app/token_payments/runtime/smoke.py"
    imported_modules = _imported_modules(smoke_path)
    stdlib_paths = {Path(sysconfig.get_path(name)).resolve() for name in ("stdlib", "platstdlib")}
    third_party_imports: set[str] = set()

    assert {module.split(".", 1)[0] for module in imported_modules}.isdisjoint(EXTERNAL_CLIENT_IMPORT_ROOTS)

    for module in imported_modules:
        root = module.split(".", 1)[0]
        if root == "token_payments":
            continue
        try:
            spec = __import__(root).__spec__
        except ModuleNotFoundError:
            third_party_imports.add(module)
            continue
        if spec is None or spec.origin in {None, "built-in", "frozen"}:
            continue
        origin = Path(spec.origin).resolve()
        if not any(origin.is_relative_to(path) for path in stdlib_paths):
            third_party_imports.add(module)

    assert third_party_imports == set()


def test_readmes_document_e2e_smokes_manual_compose_and_next_phase_candidates() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    app_readme = (ROOT / "app/README.md").read_text(encoding="utf-8")

    assert "app/README.md" in readme
    assert "phase별 완료 로그" in readme

    for text in (
        "scripts/test_e2e_integration_public_contracts.py",
        "PYTHONPATH=app python3 -m token_payments smoke",
        "PYTHONPATH=app python3 -m token_payments smoke happy-path-checkout",
        "PYTHONPATH=app python3 -m token_payments smoke compensation-checkout",
        "PYTHONPATH=app python3 -m token_payments smoke compose-readiness",
        "docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network",
        "real docker compose integration",
        "DB schema applied by app/postgres/init.d/001-token-payments-schema.sql",
        "Kafka topic publish/consume",
        "HTTP framework adapter",
        "ASGI/WSGI route",
        "order status projection/handler gap",
        "CancelOrderCommand",
        "order status update handler",
    ):
        assert text in app_readme


def test_e2e_phase_metadata_records_completed_readiness_with_concrete_summaries() -> None:
    phase_index = json.loads((ROOT / "phases/5-e2e-integration-readiness/index.json").read_text(encoding="utf-8"))
    top_index = json.loads((ROOT / "phases/index.json").read_text(encoding="utf-8"))

    assert all(step["status"] == "completed" for step in phase_index["steps"])
    for step in phase_index["steps"]:
        assert len(step.get("summary", "")) >= 40
        assert "running" not in step

    step4 = next(step for step in phase_index["steps"] if step["step"] == 4)
    assert "public contract" in step4["summary"]
    assert "README" in step4["summary"]
    assert "Docker compose" in step4["summary"]
    assert "HTTP" in step4["summary"]
    assert "CancelOrderCommand" in step4["summary"]

    phase5 = next(phase for phase in top_index["phases"] if phase["dir"] == "5-e2e-integration-readiness")
    assert phase5["status"] == "completed"


def _contains_only_json_primitives(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(_contains_only_json_primitives(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _contains_only_json_primitives(item) for key, item in value.items())
    return False


def _contains_secret_or_live_client_terms(output: str) -> bool:
    lowered = output.lower()
    return any(
        term in lowered
        for term in (
            "seed phrase",
            "mnemonic",
            "psycopg",
            "confluent_kafka",
            "web3",
        )
    )


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules

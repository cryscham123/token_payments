from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


RESERVED_SCENARIOS = (
    "happy-path-checkout",
    "compensation-checkout",
    "compose-readiness",
    "docker-runtime-readiness",
)


def test_smoke_public_contract_exports_serializable_result_types() -> None:
    import token_payments.runtime as runtime
    from token_payments.runtime.smoke import (
        AVAILABLE_SMOKE_SCENARIOS,
        SMOKE_CONTRACT,
        SmokeResult,
        SmokeScenarioResult,
        SmokeStatus,
        SmokeStep,
    )

    assert RESERVED_SCENARIOS == AVAILABLE_SMOKE_SCENARIOS
    assert SMOKE_CONTRACT == "CommandDispatchResult.details.smoke"
    assert {"SmokeResult", "SmokeScenarioResult", "SmokeStatus", "SmokeStep"} <= set(runtime.__all__)

    step = SmokeStep(
        name="registry-loaded",
        result=SmokeResult(
            status=SmokeStatus.PASSED,
            summary="reserved smoke scenarios are registered",
            details={"scenarioCount": len(AVAILABLE_SMOKE_SCENARIOS)},
        ),
    )
    scenario = SmokeScenarioResult(
        scenario="happy-path-checkout",
        result=SmokeResult(status="skipped", summary="runner not implemented yet"),
        steps=(step,),
        details={"availableScenarios": AVAILABLE_SMOKE_SCENARIOS},
    )

    payload = scenario.to_dict()

    assert payload == {
        "contract": "CommandDispatchResult.details.smoke",
        "scenario": "happy-path-checkout",
        "status": "skipped",
        "summary": "runner not implemented yet",
        "steps": [
            {
                "name": "registry-loaded",
                "status": "passed",
                "summary": "reserved smoke scenarios are registered",
                "details": {"scenarioCount": len(RESERVED_SCENARIOS)},
            }
        ],
        "details": {"availableScenarios": list(AVAILABLE_SMOKE_SCENARIOS)},
    }
    json.dumps(payload)


def test_smoke_registry_lists_reserved_scenarios_without_running_infrastructure() -> None:
    from token_payments.runtime.smoke import describe_smoke_registry, run_smoke_scenario

    registry = describe_smoke_registry()

    assert registry["contract"] == "CommandDispatchResult.details.smoke"
    assert registry["availableScenarios"] == list(RESERVED_SCENARIOS)
    assert isinstance(registry["runnerCount"], int)
    assert 0 <= registry["runnerCount"] <= len(RESERVED_SCENARIOS)

    result = run_smoke_scenario("happy-path-checkout").to_dict()
    assert result["scenario"] == "happy-path-checkout"
    assert result["status"] in {"passed", "failed", "skipped"}
    assert isinstance(result["summary"], str) and result["summary"]
    json.dumps(result)
    if result["status"] == "skipped":
        assert result["details"]["runnerImplemented"] is False


def test_unknown_smoke_scenario_returns_structured_error_from_dispatcher() -> None:
    from token_payments.runtime import dispatch_runtime_command

    result = dispatch_runtime_command(["smoke", "unknown"])
    payload = result.to_dict()

    assert result.success is False
    assert payload["command"] == "smoke"
    assert payload["exitCode"] == 64
    assert payload["details"]["error"] == {
        "code": "UNKNOWN_SMOKE_SCENARIO",
        "scenario": "unknown",
        "availableScenarios": list(RESERVED_SCENARIOS),
    }


def test_smoke_cli_outputs_bounded_json_and_unknown_scenario_exit_code() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")

    listed = subprocess.run(
        [sys.executable, "-m", "token_payments", "smoke"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    unknown = subprocess.run(
        [sys.executable, "-m", "token_payments", "smoke", "unknown"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    listed_payload = json.loads(listed.stdout)
    unknown_payload = json.loads(unknown.stdout)

    assert listed.returncode == 0
    assert listed_payload["command"] == "smoke"
    assert listed_payload["status"] == "SUCCEEDED"
    assert listed_payload["details"]["smoke"]["availableScenarios"] == list(RESERVED_SCENARIOS)
    assert isinstance(listed_payload["details"]["smoke"]["runnerCount"], int)

    assert unknown.returncode == 64
    assert unknown_payload["command"] == "smoke"
    assert unknown_payload["status"] == "FAILED"
    assert unknown_payload["details"]["error"]["code"] == "UNKNOWN_SMOKE_SCENARIO"

    output = listed.stdout + unknown.stdout
    for forbidden in ("docker compose", "postgres", "kafka", "blockchain rpc", "private_key", "seed phrase"):
        assert forbidden not in output.lower()


def test_smoke_contract_import_boundary_uses_no_third_party_dependencies() -> None:
    smoke_path = ROOT / "app/token_payments/runtime/smoke.py"
    stdlib_paths = {Path(sysconfig.get_path(name)).resolve() for name in ("stdlib", "platstdlib")}
    third_party_imports: set[str] = set()

    tree = ast.parse(smoke_path.read_text(encoding="utf-8"))
    for module in _imported_modules(tree):
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


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules

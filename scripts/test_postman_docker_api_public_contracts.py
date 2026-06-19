from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))

import docker_live_smoke


COLLECTION_PATH = ROOT / "postman" / "token-payments.local.postman_collection.json"
EXPECTED_RESPONSES_PATH = ROOT / "postman" / "expected" / "token-payments.api.expected.json"
DOC_PATHS = (ROOT / "app" / "README.md", ROOT / "docs" / "API_SPEC.md")
NEGATIVE_COLLECTION_IDS = {"expiredAccessTokenRejected", "invalidSignatureAccessTokenRejected"}
REQUIRED_SECURITY_CASES = {
    "expired access token rejected",
    "invalid signature access token rejected",
    "missing csrf token rejected",
    "duplicate idempotency conflict",
    "oversized body rejected",
    "malformed json rejected",
}
REQUIRED_DOC_TERMS = (
    "token_payments_api",
    "SESSION_SIGNING_KEYS",
    "SESSION_ACTIVE_KEY_ID",
    "previous key",
    "key rotation",
    "postman/token-payments.local.postman_collection.json",
    "postman/token-payments.local.postman_environment.json",
    "cookie jar",
    "X-CSRF-Token",
    "CORS_ALLOW_CREDENTIALS=true",
    "token-payments.local.seed-plan.json",
    "token-payments.api.expected.json",
    "Postman Docker API readiness/security smoke",
)
FINAL_LOCAL_ORDER = (
    "cp .env.example .env",
    "docker compose --env-file .env config --services",
    "docker compose --env-file .env build token_payments_api token_payments_web nginx",
    "docker compose up -d",
    "postman/fixtures/token-payments.local.seed-plan.json",
    "postman/token-payments.local.postman_collection.json",
    "python3 scripts/docker_live_smoke.py --api-readiness --plan",
    "python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker",
    "docker compose down",
)


def test_public_docs_cover_api_service_auth_seed_expected_and_smoke_contracts() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        normalized = text.lower()
        for term in REQUIRED_DOC_TERMS:
            assert term in text, f"{path.relative_to(ROOT)} must document {term!r}"
        for command in FINAL_LOCAL_ORDER:
            assert command in text, f"{path.relative_to(ROOT)} must document final local order command {command!r}"

        assert "automated" in normalized
        assert "does not start docker" in normalized or "does not start a server" in normalized
        assert (
            "bearer" not in normalized
            or "non-browser fallback" in normalized
            or "do not add" in normalized
            or "do not use" in normalized
            or "omit" in normalized
        )
        assert "localstorage" not in normalized or "do not" in normalized or "not use" in normalized
        assert "sessionstorage" not in normalized or "do not" in normalized or "not use" in normalized


def test_postman_collection_covers_route_manifest_and_api_spec_route_summary() -> None:
    from token_payments.api import http_route_manifest

    collection = _read_json(COLLECTION_PATH)
    docs_text = (ROOT / "docs" / "API_SPEC.md").read_text(encoding="utf-8")
    items = _operation_items(collection)
    manifest = list(http_route_manifest())

    assert {route["operationId"] for route in manifest} <= set(items)
    assert NEGATIVE_COLLECTION_IDS <= set(items)

    for route in manifest:
        operation_id = route["operationId"]
        request = items[operation_id]["request"]
        assert request["method"] == route["method"]
        assert _normalize_postman_path(request["url"]["raw"]) == route["path"]
        assert f"| `{operation_id}` | `{route['method']}` | `{route['path']}` |" in docs_text


def test_expected_response_fixtures_cover_route_status_and_security_cases() -> None:
    from token_payments.api import http_route_manifest

    expected = _read_json(EXPECTED_RESPONSES_PATH)
    manifest_ids = {route["operationId"] for route in http_route_manifest()}
    route_examples = {route["operationId"]: route for route in expected["routes"]}

    assert expected["contract"] == "token-payments.postman.expected-responses.v1"
    assert set(route_examples) == manifest_ids
    assert set(expected["collectionRequestIds"]) >= manifest_ids | NEGATIVE_COLLECTION_IDS

    for operation_id, route in route_examples.items():
        assert 200 <= int(route["status"]) <= 599, operation_id
        assert isinstance(route["body"], dict), operation_id
        assert route["body"], operation_id

    security_cases = {case["name"]: case for case in expected["securityCases"]}
    assert REQUIRED_SECURITY_CASES <= set(security_cases)
    for name, case in security_cases.items():
        assert 400 <= int(case["status"]) <= 499, name
        assert case["body"]["error"]["code"], name
        assert case["rawSecretMaterialCommitted"] is False


def test_smoke_registry_and_runner_plan_expose_api_readiness_contract() -> None:
    from token_payments.runtime.smoke import describe_smoke_registry, run_smoke_scenario

    registry = describe_smoke_registry()
    scenario = run_smoke_scenario("postman-docker-api-readiness").to_dict()
    plan = docker_live_smoke.build_api_readiness_plan()

    assert "postman-docker-api-readiness" in registry["availableScenarios"]
    assert scenario["status"] == "passed"
    assert scenario["details"]["dockerStarted"] is False
    assert scenario["details"]["networkCalls"] is False
    assert plan["contract"] == scenario["details"]["contract"]
    assert plan["dockerStarted"] is False
    assert plan["networkCalls"] is False
    assert [command["name"] for command in plan["commandSequence"]] == scenario["details"]["commandSequence"]
    for command in plan["commandSequence"]:
        assert command["display"] == shlex.join(command["argv"])
        assert command["shell"] is False


def test_phase_15_metadata_closes_all_steps_and_top_level_phase() -> None:
    phase_index = _read_json(ROOT / "phases" / "15-postman-docker-api-readiness" / "index.json")
    top_index = _read_json(ROOT / "phases" / "index.json")

    assert {step["status"] for step in phase_index["steps"]} == {"completed"}
    for step in phase_index["steps"]:
        assert step.get("completed_at"), step
        assert len(step.get("summary", "")) >= 80, step

    completed_summary = " ".join(step["summary"] for step in phase_index["steps"])
    for term in (
        "compose API service",
        "Postman cookie auth",
        "seed",
        "expected response",
        "readiness/security smoke",
        "public contract",
    ):
        assert term.lower() in completed_summary.lower()

    phase15 = next(phase for phase in top_index["phases"] if phase["dir"] == "15-postman-docker-api-readiness")
    assert phase15["status"] == "completed"
    assert phase15.get("completed_at")


def _read_json(path: Path) -> Any:
    assert path.exists(), f"{path.relative_to(ROOT)} must exist"
    return json.loads(path.read_text(encoding="utf-8"))


def _operation_items(collection: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    flattened: dict[str, Mapping[str, Any]] = {}

    def visit(items: Iterable[Mapping[str, Any]]) -> None:
        for item in items:
            if "request" in item and "id" in item:
                flattened[str(item["id"])] = item
            visit(item.get("item", []))

    visit(collection.get("item", []))
    return flattened


def _normalize_postman_path(raw_url: str) -> str:
    path = raw_url.replace("{{baseUrl}}", "")
    path = re.sub(r"\{\{([A-Za-z][A-Za-z0-9_]*)\}\}", r"{\1}", path)
    return re.sub(r":([A-Za-z][A-Za-z0-9_]*)", r"{\1}", path)

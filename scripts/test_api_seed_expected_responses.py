from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

SEED_PLAN_PATH = ROOT / "postman" / "fixtures" / "token-payments.local.seed-plan.json"
EXPECTED_RESPONSES_PATH = ROOT / "postman" / "expected" / "token-payments.api.expected.json"
COLLECTION_PATH = ROOT / "postman" / "token-payments.local.postman_collection.json"
SCHEMA_PATH = ROOT / "app" / "postgres" / "init.d" / "001-token-payments-schema.sql"
DOCS_API_SPEC_PATH = ROOT / "docs" / "API_SPEC.md"

REQUIRED_SEED_TABLES = {
    "auth_groups",
    "auth_group_invitations",
    "auth_group_memberships",
    "auth_permissions",
    "auth_role_permissions",
    "auth_roles",
    "auth_users",
    "store_catalog_stores",
    "store_catalog_store_memberships",
    "store_catalog_products",
    "order_customers",
    "order_stores",
    "order_store_products",
    "product_inventory",
    "store_approval_stores",
    "store_approval_products",
}
REQUIRED_SEED_FIELDS = {
    "demoCustomerUserId",
    "demoCustomerWallet",
    "demoStoreId",
    "demoProductId",
    "demoInventoryAvailableStock",
    "paymentDestinationWallet",
    "testNetworkChainId",
    "testNetworkAccountPlaceholder",
}
REQUIRED_HEADER_EXAMPLES = {
    "Set-Cookie",
    "X-CSRF-Token",
    "Idempotency-Key",
    "X-Request-Id",
}
REQUIRED_FLOW_NAMES = {
    "happyPathCheckout",
    "compensationCheckout",
    "operatorActionRecovery",
}
FORBIDDEN_SECRET_PATTERNS = (
    re.compile(r"\b(seed phrase|mnemonic|production token|prod token|private_key|refresh_token_hash|refresh_token_salt)\b", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b0x[a-fA-F0-9]{64}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
)


def test_seed_plan_is_explicit_manual_contract_using_existing_schema_tables_and_columns() -> None:
    seed = _read_json(SEED_PLAN_PATH)
    schema = _schema_tables()

    assert seed["contract"] == "token-payments.postman.seed-plan.v1"
    assert seed["defaultInitMutation"] is False
    assert seed["manualOnly"] is True
    assert seed["execution"]["startsDocker"] is False
    assert seed["execution"]["opensDatabase"] is False
    assert seed["execution"]["command"]["shell"] is False
    assert seed["execution"]["command"]["argv"][:5] == ["docker", "compose", "--env-file", ".env", "exec"]
    assert "psql" in seed["execution"]["command"]["argv"]

    assert REQUIRED_SEED_FIELDS <= set(seed["ids"])
    assert seed["ids"]["testNetworkChainId"] == 1337
    assert seed["ids"]["testNetworkAccountPlaceholder"] == "${TEST_NETWORK_ACCOUNT}"
    assert seed["ids"]["paymentDestinationWallet"].startswith("0x")

    records = seed["records"]
    assert REQUIRED_SEED_TABLES <= {record["table"] for record in records}
    for record in records:
        table = record["table"]
        assert table in schema
        assert set(record["columns"]) <= schema[table], f"{table} seed must use committed schema columns"
        assert set(record["values"]) == set(record["columns"])


def test_expected_response_fixtures_cover_route_manifest_docs_and_postman_requests() -> None:
    from token_payments.api import http_route_manifest

    expected = _read_json(EXPECTED_RESPONSES_PATH)
    collection = _read_json(COLLECTION_PATH)
    docs_text = DOCS_API_SPEC_PATH.read_text(encoding="utf-8")
    manifest = list(http_route_manifest())

    assert expected["contract"] == "token-payments.postman.expected-responses.v1"
    assert expected["routeSummarySource"] == "docs/API_SPEC.md"

    route_examples = {route["operationId"]: route for route in expected["routes"]}
    assert set(route_examples) == {route["operationId"] for route in manifest}
    for route in manifest:
        example = route_examples[route["operationId"]]
        assert example["method"] == route["method"]
        assert example["path"] == route["path"]
        assert f"| `{route['operationId']}` | `{route['method']}` | `{route['path']}` |" in docs_text
        assert 200 <= int(example["status"]) <= 599
        assert example["body"], f"{route['operationId']} must include a bounded body fixture"

    collection_request_ids = set(_operation_items(collection))
    assert collection_request_ids <= set(expected["collectionRequestIds"])
    assert collection_request_ids <= set(route_examples) | {"expiredAccessTokenRejected", "invalidSignatureAccessTokenRejected"}


def test_expected_response_security_headers_flows_and_redaction_are_public_safe() -> None:
    expected = _read_json(EXPECTED_RESPONSES_PATH)
    combined = json.dumps(expected, sort_keys=True)

    assert REQUIRED_HEADER_EXAMPLES <= set(expected["headerExamples"])
    assert expected["headerExamples"]["Set-Cookie"]["rawValuesCommitted"] is False
    assert expected["headerExamples"]["Set-Cookie"]["accessToken"] == "<redacted-signed-session-token>"
    assert expected["headerExamples"]["X-CSRF-Token"] == "{{csrfToken}}"
    assert expected["headerExamples"]["Idempotency-Key"].startswith("postman-")
    assert expected["headerExamples"]["X-Request-Id"].startswith("postman-")

    assert set(expected["flows"]) == REQUIRED_FLOW_NAMES
    assert expected["flows"]["happyPathCheckout"]["finalOrderStatus"] == "APPROVED"
    assert expected["flows"]["compensationCheckout"]["finalOrderStatus"] == "CANCELLED"
    assert {"cancelOperatorOrder", "retryOperatorOutboxMessage", "replayOperatorMessage"} <= set(
        expected["flows"]["operatorActionRecovery"]["operations"]
    )

    security_cases = {case["name"]: case for case in expected["securityCases"]}
    assert {"expired access token rejected", "invalid signature access token rejected"} <= set(security_cases)
    for case in security_cases.values():
        assert case["status"] in {400, 401, 403, 409, 413}
        assert case["body"]["error"]["code"]
        assert case["rawSecretMaterialCommitted"] is False

    for pattern in FORBIDDEN_SECRET_PATTERNS:
        assert not pattern.search(combined)
    assert "Authorization: Bearer" not in combined
    assert "localStorage" not in combined
    assert "sessionStorage" not in combined


def test_readmes_and_api_spec_document_seed_and_expected_response_flow() -> None:
    for path in (ROOT / "app" / "README.md", DOCS_API_SPEC_PATH):
        text = path.read_text(encoding="utf-8")
        assert "token-payments.local.seed-plan.json" in text
        assert "token-payments.api.expected.json" in text
        assert "manual seed" in text.lower()
        assert "expected response" in text.lower()


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


def _operation_items(collection: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    flattened: dict[str, Mapping[str, Any]] = {}

    def visit(items: list[Mapping[str, Any]]) -> None:
        for item in items:
            if "request" in item and "id" in item:
                flattened[str(item["id"])] = item
            visit(list(item.get("item", [])))

    visit(list(collection.get("item", [])))
    return flattened

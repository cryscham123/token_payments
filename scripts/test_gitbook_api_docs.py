from __future__ import annotations

import json
import sys
import re
from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_root_summary_exposes_docs_for_gitbook_repository_imports() -> None:
    summary = _read("SUMMARY.md")

    assert "# 목차" in summary
    for label, link in (
        ("PRD", "docs/PRD.md"),
        ("아키텍처", "docs/ARCHITECTURE.md"),
        ("API 명세", "docs/API_SPEC.md"),
        ("API 개요", "docs/api/README.md"),
        ("공통 계약", "docs/api/runtime-contract.md"),
        ("전체 Route Summary", "docs/api/route-summary.md"),
    ):
        assert label in summary
        assert f"]({link})" in summary


def test_gitbook_summary_exposes_korean_api_spec_pages() -> None:
    summary = _read("docs/SUMMARY.md")

    assert "# 목차" in summary
    for label, link in (
        ("API 명세", "API_SPEC.md"),
        ("API 개요", "api/README.md"),
        ("공통 계약", "api/runtime-contract.md"),
        ("전체 Route Summary", "api/route-summary.md"),
        ("인증과 OAuth", "api/auth.md"),
        ("주문, 체크아웃, 결제", "api/orders-checkout-payments.md"),
        ("상점과 상품 카탈로그", "api/catalog-inventory.md"),
        ("머천트, 관리자, RBAC", "api/merchant-admin-rbac.md"),
        ("운영자와 런타임", "api/operator-runtime.md"),
    ):
        assert label in summary
        assert f"]({link})" in summary


def test_api_directory_can_be_used_as_standalone_gitbook_root() -> None:
    summary = _read("docs/api/SUMMARY.md")

    assert "# API 문서 목차" in summary
    for label, link in (
        ("API 개요", "README.md"),
        ("OpenAPI Reference", "openapi.yaml"),
        ("공통 계약", "runtime-contract.md"),
        ("전체 Route Summary", "route-summary.md"),
        ("인증과 OAuth", "auth.md"),
        ("주문, 체크아웃, 결제", "orders-checkout-payments.md"),
        ("상점과 상품 카탈로그", "catalog-inventory.md"),
        ("머천트, 관리자, RBAC", "merchant-admin-rbac.md"),
        ("운영자와 런타임", "operator-runtime.md"),
    ):
        assert label in summary
        assert f"]({link})" in summary


def test_api_spec_is_gitbook_ready_without_losing_route_manifest_contract() -> None:
    from token_payments.api import http_route_manifest

    api_spec = _read("docs/API_SPEC.md")
    auth_page = _read("docs/api/auth.md")

    assert api_spec.startswith("---\n")
    assert "# Token Payments API 명세" in api_spec
    assert "## GitBook 탐색" in api_spec
    for link in (
        "api/README.md",
        "api/openapi.yaml",
        "api/runtime-contract.md",
        "api/route-summary.md",
        "api/auth.md",
        "api/orders-checkout-payments.md",
        "api/catalog-inventory.md",
        "api/merchant-admin-rbac.md",
        "api/operator-runtime.md",
    ):
        assert f"]({link})" in api_spec

    assert "Public HTTP route surface is exactly the current 55-route manifest" in api_spec
    for entry in http_route_manifest():
        route_row = f"| `{entry['operationId']}` | `{entry['method']}` | `{entry['path']}` |"
        assert route_row in api_spec

    logout_section = _bounded_section(api_spec, "### `DELETE /auth/sessions`", "### `GET /auth/me`")
    assert "Request: body 없음" in logout_section
    assert "public GitBook/OpenAPI reference에는 DELETE request body를 노출하지 않는다" in logout_section
    assert '"sessionId": "session-001"' not in logout_section
    assert "| `DELETE /auth/sessions` | active session | no JSON body;" in auth_page
    assert "| `DELETE /auth/sessions` | active session | optional body `sessionId`" not in auth_page


def test_gitbook_openapi_reference_uses_project_template_and_manifest_routes() -> None:
    from token_payments.api import http_route_manifest

    openapi = yaml.safe_load(_read("docs/api/openapi.yaml"))
    openapi_text = _read("docs/api/openapi.yaml")

    assert openapi["openapi"] == "3.0.3"
    assert openapi["info"]["title"] == "Token Payments API"
    assert "Token Payments public HTTP API" in openapi["info"]["description"]
    assert "{% tabs %}" in openapi["info"]["description"]
    assert "{% stepper %}" in openapi["info"]["description"]
    assert "{% hint style=\"warning\" %}" in openapi["info"]["description"]
    assert openapi["servers"][0]["url"] == "http://127.0.0.1:8000"
    assert "cookieAuth" in openapi["components"]["securitySchemes"]
    assert "bearerAuth" in openapi["components"]["securitySchemes"]

    tag_titles = {tag["name"]: tag.get("x-page-title") for tag in openapi["tags"]}
    assert tag_titles["auth"] == "Auth"
    assert tag_titles["checkout"] == "Checkout"
    assert tag_titles["merchant"] == "Merchant"
    assert tag_titles["operator"] == "Operator"
    assert any(tag.get("x-parent") == "commerce" for tag in openapi["tags"])

    for entry in http_route_manifest():
        operation = openapi["paths"][entry["path"]][entry["method"].lower()]
        assert operation["operationId"] == entry["operationId"]
        assert operation["tags"], entry["operationId"]
        assert "summary" in operation
        assert "responses" in operation

    for operation_id in (
        "requestLoginChallenge",
        "createOrder",
        "submitTransactionHash",
        "listPublicStores",
        "getOperatorDashboard",
    ):
        assert f"operationId: {operation_id}" in openapi_text
        operation = _find_openapi_operation(openapi, operation_id)
        assert operation.get("x-codeSamples"), operation_id


def test_gitbook_openapi_reference_documents_route_inputs_and_responses() -> None:
    from token_payments.api import http_route_manifest

    openapi = yaml.safe_load(_read("docs/api/openapi.yaml"))
    expected = json.loads(_read("postman/expected/token-payments.api.expected.json"))
    expected_status_by_operation = {route["operationId"]: str(route["status"]) for route in expected["routes"]}

    request_body_operations = {
        "requestLoginChallenge",
        "loginWithMetaMask",
        "requestOAuthAuthorization",
        "completeOAuthSession",
        "linkOAuthIdentity",
        "requestWalletLinkChallenge",
        "linkWallet",
        "refreshSession",
        "updateCurrentUserProfile",
        "createOrder",
        "submitTransactionHash",
        "updateStoreProfile",
        "createOrReuseStoreUser",
        "createStore",
        "grantStoreMembership",
        "registerStoreProduct",
        "updateStoreProduct",
        "increaseStoreOwnerInventoryStock",
        "correctStoreOwnerInventoryStock",
        "pauseStoreOwnerInventorySales",
        "resumeStoreOwnerInventorySales",
        "createMerchantStoreInvitation",
        "acceptMerchantInvitation",
        "updateMerchantStoreMemberRole",
        "cancelOperatorOrder",
        "retryOperatorOutboxMessage",
        "replayOperatorMessage",
    }

    for entry in http_route_manifest():
        operation = openapi["paths"][entry["path"]][entry["method"].lower()]
        operation_id = entry["operationId"]
        parameters = [_resolve_ref(openapi, parameter) for parameter in operation.get("parameters", [])]
        parameter_names = {(parameter["in"], parameter["name"]) for parameter in parameters}

        if entry["method"] in {"GET", "HEAD", "DELETE"}:
            assert "requestBody" not in operation, operation_id

        assert ("header", "X-Request-Id") in parameter_names, operation_id
        for path_param in re.findall(r"{([^}]+)}", entry["path"]):
            assert ("path", path_param) in parameter_names, operation_id
        for parameter in parameters:
            assert parameter.get("description"), (operation_id, parameter["name"])
            assert "schema" in parameter, (operation_id, parameter["name"])

        if operation_id in request_body_operations:
            request_body = _resolve_ref(openapi, operation["requestBody"])
            media = request_body["content"]["application/json"]
            schema = _resolve_ref(openapi, media["schema"])
            assert schema.get("properties"), operation_id
            assert set(schema.get("required", [])) <= set(schema["properties"]), operation_id
            for property_name, property_schema in schema["properties"].items():
                resolved_property = _resolve_ref(openapi, property_schema) if "$ref" in property_schema else property_schema
                assert resolved_property.get("description") or resolved_property.get("properties"), (
                    operation_id,
                    property_name,
                )
        else:
            assert "requestBody" not in operation, operation_id

        assert "default" not in operation["responses"], operation_id
        assert expected_status_by_operation[operation_id] in operation["responses"], operation_id
        for status, response in operation["responses"].items():
            assert response.get("description"), (operation_id, status)
            if status != "204":
                media = response.get("content", {}).get("application/json")
                assert media and "schema" in media, (operation_id, status)

        documented_error_statuses = {str(error["status"]) for error in operation.get("x-errorCodes", [])}
        assert documented_error_statuses <= set(operation["responses"]), operation_id

    openapi_text = _read("docs/api/openapi.yaml")
    refs = Counter(re.findall(r"#/components/([^/]+)/([^'\"\s]+)", openapi_text))
    for section, values in openapi["components"].items():
        if section == "securitySchemes":
            continue
        for name in values:
            assert refs[(section, name)] > 0, (section, name)


def test_korean_gitbook_pages_cover_every_api_spec_endpoint_heading() -> None:
    api_spec = _read("docs/API_SPEC.md")
    api_pages = _read_api_pages()
    endpoint_headings = re.findall(r"^### (`[^`]+`)", api_spec, flags=re.MULTILINE)

    assert endpoint_headings
    for heading in endpoint_headings:
        assert heading in api_pages


def test_gitbook_route_summary_covers_every_public_manifest_route() -> None:
    from token_payments.api import http_route_manifest

    route_summary = _read("docs/api/route-summary.md")

    assert "# 전체 Route Summary" in route_summary
    for entry in http_route_manifest():
        assert f"`{entry['operationId']}`" in route_summary
        assert f"`{entry['method']} {entry['path']}`" in route_summary


def test_gitbook_runtime_contract_covers_common_api_spec_sections() -> None:
    runtime_contract = _read("docs/api/runtime-contract.md")

    for phrase in (
        "API Evolution Guardrail",
        "Route Surface Contract",
        "Runtime Assumptions",
        "Common Headers",
        "Cookie And CSRF Policy",
        "Live System Routes And Observability",
        "Common Error Shape",
        "State Values",
        "Postman Flow",
    ):
        assert phrase in runtime_contract


def test_api_directory_docs_are_self_contained_for_integrators() -> None:
    api_pages = _read_api_pages()

    assert "API_SPEC.md" not in api_pages
    assert "../API_SPEC.md" not in api_pages
    for phrase in (
        "Base URL",
        "인증",
        "권한",
        "요청",
        "응답",
        "오류",
        "Idempotency-Key",
        "X-CSRF-Token",
        "Postman",
    ):
        assert phrase in api_pages


def test_each_domain_page_has_endpoint_detail_contracts() -> None:
    for relative_path in (
        "docs/api/auth.md",
        "docs/api/orders-checkout-payments.md",
        "docs/api/catalog-inventory.md",
        "docs/api/merchant-admin-rbac.md",
        "docs/api/operator-runtime.md",
    ):
        text = _read(relative_path)
        assert "## Endpoint 상세" in text
        for heading in ("Endpoint", "인증/권한", "요청", "성공 응답", "오류"):
            assert heading in text


def test_korean_gitbook_api_pages_cover_public_route_groups() -> None:
    required_phrases_by_page = {
        "docs/api/auth.md": (
            "인증",
            "`POST /auth/oauth/{provider}/authorize`",
            "`DELETE /auth/oauth/identities/{oauthIdentityId}`",
            "providerSubject",
        ),
        "docs/api/orders-checkout-payments.md": (
            "주문",
            "`POST /orders`",
            "`GET /checkouts/tracking/{trackingId}`",
            "`GET /payments`",
            "`POST /payments/transaction-hashes`",
        ),
        "docs/api/catalog-inventory.md": (
            "카탈로그",
            "`GET /stores`",
            "`POST /merchant/stores/{publicStoreId}/products`",
            "`POST /store-owner/stores/{storeId}/inventory/{productId}/intake`",
        ),
        "docs/api/merchant-admin-rbac.md": (
            "RBAC",
            "`POST /admin/stores`",
            "`GET /merchant/role-catalog`",
            "`POST /merchant/stores/{storeId}/invitations`",
        ),
        "docs/api/operator-runtime.md": (
            "운영자",
            "`GET /operator/dashboard`",
            "`POST /operator/outbox/{messageId}/retry`",
            "no-server-start",
        ),
    }

    for relative_path, phrases in required_phrases_by_page.items():
        text = _read(relative_path)
        assert text.startswith("# ")
        assert "요청" in text or "권한" in text
        for phrase in phrases:
            assert phrase in text


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _find_openapi_operation(openapi: dict[str, object], operation_id: str) -> dict[str, object]:
    for path_item in openapi["paths"].values():  # type: ignore[index, union-attr]
        for method, operation in path_item.items():
            if method == "parameters":
                continue
            if operation.get("operationId") == operation_id:
                return operation
    raise AssertionError(f"{operation_id} operation not found")


def _resolve_ref(openapi: dict[str, object], value: dict[str, object]) -> dict[str, object]:
    ref = value.get("$ref")
    if not isinstance(ref, str):
        return value
    current: object = openapi
    for part in ref.removeprefix("#/").split("/"):
        current = current[part]  # type: ignore[index]
    assert isinstance(current, dict)
    return current


def _bounded_section(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


def _read_api_pages() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "docs" / "api").glob("*.md"))
    )

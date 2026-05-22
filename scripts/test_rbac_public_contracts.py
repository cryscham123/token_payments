from __future__ import annotations

import json
import re
import sys
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

SEED_PATH = ROOT / "postman" / "fixtures" / "token-payments.local.seed-plan.json"
EXPECTED_PATH = ROOT / "postman" / "expected" / "token-payments.api.expected.json"
COLLECTION_PATH = ROOT / "postman" / "token-payments.local.postman_collection.json"
SCHEMA_PATH = ROOT / "app" / "postgres" / "init.d" / "001-token-payments-schema.sql"

REQUIRED_ROLE_IDS = {
    "PERSONAL_CUSTOMER",
    "MERCHANT_OWNER",
    "MERCHANT_MANAGER",
    "MERCHANT_STAFF",
    "PLATFORM_OPERATOR",
    "PLATFORM_ADMIN",
}
REQUIRED_PERMISSION_NAMES = {
    "user:self",
    "store:read",
    "store:write",
    "merchant_member:read",
    "merchant_member:invite",
    "merchant_member:manage",
    "product:write",
    "inventory:read",
    "inventory:write",
    "operator:read",
    "operator:action",
    "outbox:retry",
    "rbac:manage",
    "admin:provision",
}
MERCHANT_ROUTE_IDS = {
    "listMerchantStoreMembers",
    "listMerchantStoreInvitations",
    "createMerchantStoreInvitation",
    "acceptMerchantInvitation",
    "revokeMerchantInvitation",
    "updateMerchantStoreMemberRole",
    "removeMerchantStoreMember",
    "getMerchantRoleCatalog",
}


def test_manual_seed_plan_contains_static_rbac_catalog_groups_and_memberships() -> None:
    seed = _read_json(SEED_PATH)
    records = seed["records"]
    ids = seed["ids"]

    roles = {record["values"]["role_id"]: record["values"] for record in _records(records, "auth_roles")}
    permissions = {record["values"]["permission_name"] for record in _records(records, "auth_permissions")}
    role_permissions = {
        (record["values"]["role_id"], record["values"]["permission_name"])
        for record in _records(records, "auth_role_permissions")
    }
    groups = {record["values"]["group_id"]: record["values"] for record in _records(records, "auth_groups")}
    memberships = {
        (record["values"]["group_id"], record["values"]["user_id"]): record["values"]
        for record in _records(records, "auth_group_memberships")
    }
    store = _single_record(records, "store_catalog_stores")["values"]

    assert REQUIRED_ROLE_IDS <= set(roles)
    assert REQUIRED_PERMISSION_NAMES <= permissions
    assert roles["MERCHANT_OWNER"]["owner_role"] is True
    assert roles["MERCHANT_OWNER"]["merchant_assignable"] is False
    assert {role_id for role_id, role in roles.items() if role["merchant_assignable"] is True} == {
        "MERCHANT_MANAGER",
        "MERCHANT_STAFF",
    }
    assert ("MERCHANT_OWNER", "merchant_member:manage") in role_permissions
    assert ("MERCHANT_MANAGER", "merchant_member:invite") in role_permissions
    assert ("MERCHANT_STAFF", "inventory:read") in role_permissions
    assert ("PLATFORM_OPERATOR", "operator:read") in role_permissions
    assert ("PLATFORM_ADMIN", "rbac:manage") in role_permissions
    assert ("PLATFORM_ADMIN", "admin:provision") in role_permissions

    assert groups[ids["demoCustomerPersonalGroupId"]]["group_type"] == "PERSONAL"
    assert groups[ids["demoCustomerPersonalGroupId"]]["resource_id"] == ids["demoCustomerUserId"]
    assert groups[ids["demoMerchantGroupId"]]["group_type"] == "MERCHANT"
    assert groups[ids["demoMerchantGroupId"]]["resource_type"] == "store"
    assert groups[ids["demoMerchantGroupId"]]["resource_id"] == ids["demoStoreId"]
    assert groups[ids["demoPlatformGroupId"]]["group_type"] == "PLATFORM"
    assert store["group_id"] == ids["demoMerchantGroupId"]

    assert memberships[(ids["demoCustomerPersonalGroupId"], ids["demoCustomerUserId"])]["role_id"] == "PERSONAL_CUSTOMER"
    assert memberships[(ids["demoMerchantGroupId"], ids["demoStoreOwnerUserId"])]["role_id"] == "MERCHANT_OWNER"
    assert memberships[(ids["demoPlatformGroupId"], ids["demoPlatformAdminUserId"])]["role_id"] == "PLATFORM_ADMIN"


def test_user_session_and_auth_context_do_not_use_global_role_as_new_authority() -> None:
    from token_payments.api import ApiAuthContext
    from token_payments.contexts.auth.domain import User
    from token_payments.runtime.session_transport import SessionClaims

    assert "role" not in {field.name for field in fields(User)}
    assert "role" not in {field.name for field in fields(ApiAuthContext)}
    assert "role" not in {field.name for field in fields(SessionClaims)}

    claims = SessionClaims(
        user_id="user-001",
        session_id="session-001",
        wallet_address="0x1111111111111111111111111111111111111111",
        issued_at=datetime.fromtimestamp(1, tz=UTC),
        expires_at=datetime.fromtimestamp(2, tz=UTC),
        token_type="access",
        jti="jti-001",
        active_group_id="group-001",
        scopes=("user:self",),
    )
    assert "role" not in claims.to_payload()
    assert claims.to_payload()["activeGroupId"] == "group-001"
    assert claims.to_payload()["scopes"] == ["user:self"]


def test_docs_and_schema_define_rbac_public_boundary_and_audit_fields() -> None:
    from token_payments.contexts.store_catalog.application import CatalogAuditRecord

    api_spec = _read_text(ROOT / "docs" / "API_SPEC.md")
    domain_model = _read_text(ROOT / "docs" / "DOMAIN_MODEL.md")
    schema = _read_text(SCHEMA_PATH)
    audit_fields = {field.name for field in fields(CatalogAuditRecord)}

    for phrase in (
        "Phase 22 removes global account-role authorization from new execution paths",
        "`GroupMembership` connects a user to a `PERSONAL`, `MERCHANT`, or `PLATFORM` group with a role",
        "Role and permission definitions start as seed/static catalog data",
        "Full role/permission CRUD APIs are future surface",
        "MERCHANT_OWNER assignment or transfer is not merchant-facing",
        "auth_users.role column is legacy compatibility only",
    ):
        assert phrase in f"{api_spec}\n{domain_model}"

    assert "role/permission full CRUD" in api_spec
    assert "platform group CRUD" in api_spec
    assert "personal group CRUD" in api_spec
    assert "owner transfer" in api_spec
    assert "not part of the 47-route public facade manifest" in api_spec

    for table in (
        "auth_groups",
        "auth_roles",
        "auth_permissions",
        "auth_role_permissions",
        "auth_group_memberships",
        "auth_group_invitations",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
    for column in ("group_id", "permission", "resource_type", "resource_id"):
        assert column in audit_fields
        assert re.search(rf"\b{column}\b", schema), f"schema must preserve audit column {column}"


def test_postman_public_fixtures_do_not_depend_on_role_headers_or_role_escalation_requests() -> None:
    expected = _read_json(EXPECTED_PATH)
    collection = _read_json(COLLECTION_PATH)
    combined = json.dumps({"expected": expected, "collection": collection}, sort_keys=True)

    assert "X-User-Role" not in combined
    assert "STORE_OWNER" not in combined
    assert "ADMIN role" not in combined
    assert MERCHANT_ROUTE_IDS <= set(expected["collectionRequestIds"])
    assert MERCHANT_ROUTE_IDS <= {route["operationId"] for route in expected["routes"]}

    merchant_catalog = _route_body(expected, "getMerchantRoleCatalog")["roles"]
    assert {role["roleId"] for role in merchant_catalog} == {"MERCHANT_MANAGER", "MERCHANT_STAFF"}
    assert all(role["rawPermissionMutationAllowed"] is False for role in merchant_catalog)
    assert all(role["roleId"] != "MERCHANT_OWNER" for role in merchant_catalog)

    for item in _operation_items(collection).values():
        request = item.get("request", {})
        body = request.get("body", {}) if isinstance(request, Mapping) else {}
        raw = body.get("raw") if isinstance(body, Mapping) else None
        if not isinstance(raw, str) or not raw.strip().startswith("{"):
            continue
        assert '"permissions"' not in raw
        assert '"role"' not in raw
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        assert "permissions" not in payload
        assert payload.get("role") is None
        if "roleId" in payload:
            assert str(payload["roleId"]).startswith("MERCHANT_")
            assert payload["roleId"] != "MERCHANT_OWNER"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _records(records: list[Mapping[str, Any]], table: str) -> list[Mapping[str, Any]]:
    return [record for record in records if record["table"] == table]


def _single_record(records: list[Mapping[str, Any]], table: str) -> Mapping[str, Any]:
    matches = _records(records, table)
    assert len(matches) == 1
    return matches[0]


def _route_body(expected: Mapping[str, Any], operation_id: str) -> Mapping[str, Any]:
    for route in expected["routes"]:
        if route["operationId"] == operation_id:
            return route["body"]
    raise AssertionError(f"missing route fixture for {operation_id}")


def _operation_items(collection: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    flattened: dict[str, Mapping[str, Any]] = {}

    def visit(items: list[Mapping[str, Any]]) -> None:
        for item in items:
            if "request" in item and "id" in item:
                flattened[str(item["id"])] = item
            visit(list(item.get("item", [])))

    visit(list(collection.get("item", [])))
    return flattened

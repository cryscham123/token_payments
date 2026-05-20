from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


ADMIN_STORE_CATALOG_OPERATIONS = {
    "createOrReuseStoreUser",
    "createStore",
    "grantStoreMembership",
    "registerStoreProduct",
}


def test_route_manifest_api_spec_and_postman_cover_admin_store_catalog_operations() -> None:
    from token_payments.api import http_route_manifest

    manifest = {route["operationId"]: route for route in http_route_manifest()}
    api_spec = _read("docs/API_SPEC.md")
    expected = _read_json("postman/expected/token-payments.api.expected.json")
    collection = _read_json("postman/token-payments.local.postman_collection.json")

    assert ADMIN_STORE_CATALOG_OPERATIONS <= set(manifest)
    assert ADMIN_STORE_CATALOG_OPERATIONS <= {route["operationId"] for route in expected["routes"]}
    assert ADMIN_STORE_CATALOG_OPERATIONS <= set(expected["collectionRequestIds"])
    assert ADMIN_STORE_CATALOG_OPERATIONS <= set(_operation_items(collection))

    for operation_id in ADMIN_STORE_CATALOG_OPERATIONS:
        route = manifest[operation_id]
        assert f"| `{operation_id}` | `{route['method']}` | `{route['path']}` |" in api_spec


def test_docs_define_admin_provisioning_customer_wallet_reuse_and_store_membership_authorization() -> None:
    combined = "\n".join(
        _read(path)
        for path in (
            "README.md",
            "app/README.md",
            "docs/API_SPEC.md",
            "docs/DOMAIN_MODEL.md",
            "docs/ARCHITECTURE.md",
        )
    )

    assert "Initial `ADMIN` bootstrap is local/manual seed only" in combined
    assert "public customer login never grants a global `STORE_OWNER` role" in combined
    assert "store ownership/membership, not a global STORE_OWNER account role" in combined
    assert "same `auth_users.user_id`" in combined
    assert "checkout history is preserved" in combined
    assert "Store wallet and supported chains live on the store profile" in combined
    assert "description/category/search metadata is future scope" in combined
    assert "store_catalog_products" in combined
    assert "order_store_products" in combined
    assert "store_approval_products" in combined
    assert "product_inventory" in combined


def test_postman_seed_plan_keeps_canonical_catalog_and_runtime_projection_references_consistent() -> None:
    seed = _read_json("postman/fixtures/token-payments.local.seed-plan.json")
    by_table = {record["table"]: record for record in seed["records"]}
    ids = seed["ids"]

    customer_user = [
        record for record in seed["records"]
        if record["table"] == "auth_users" and record["values"]["user_id"] == ids["demoCustomerUserId"]
    ][0]
    assert customer_user["values"]["role"] == "CUSTOMER"
    owner_user = [
        record for record in seed["records"]
        if record["table"] == "auth_users" and record["values"]["user_id"] == ids["demoStoreOwnerUserId"]
    ][0]
    assert owner_user["values"]["role"] == "CUSTOMER"
    assert by_table["store_catalog_stores"]["values"]["owner_user_id"] == ids["demoStoreOwnerUserId"]
    assert by_table["store_catalog_store_memberships"]["values"] == {
        "store_id": ids["demoStoreId"],
        "user_id": ids["demoStoreOwnerUserId"],
        "role": "OWNER",
        "active": True,
    }
    for table in (
        "store_catalog_products",
        "order_store_products",
        "store_approval_products",
        "product_inventory",
    ):
        assert by_table[table]["values"]["store_id"] == ids["demoStoreId"]
        assert by_table[table]["values"]["product_id"] == ids["demoProductId"]


def test_phase_metadata_reflects_completed_admin_store_catalog_phase() -> None:
    phase = _read_json("phases/21-admin-store-catalog-provisioning/index.json")
    top = _read_json("phases/index.json")
    top_entry = next(item for item in top["phases"] if item["dir"] == "21-admin-store-catalog-provisioning")

    assert all(step["status"] == "completed" for step in phase["steps"])
    assert all(step.get("summary") for step in phase["steps"])
    assert phase.get("completed_at")
    assert top_entry["status"] == "completed"
    assert top_entry.get("completed_at")


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _read_json(relative_path: str):
    return json.loads(_read(relative_path))


def _operation_items(collection: dict[str, object]) -> dict[str, dict[str, object]]:
    flattened: dict[str, dict[str, object]] = {}

    def visit(items: list[dict[str, object]]) -> None:
        for item in items:
            if "request" in item and "id" in item:
                flattened[str(item["id"])] = item
            nested = item.get("item", [])
            if isinstance(nested, list):
                visit(nested)  # type: ignore[arg-type]

    items = collection.get("item", [])
    assert isinstance(items, list)
    visit(items)  # type: ignore[arg-type]
    return flattened

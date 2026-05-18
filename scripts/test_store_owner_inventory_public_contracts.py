from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


STORE_OWNER_INVENTORY_OPERATIONS = {
    "listStoreOwnerInventory",
    "increaseStoreOwnerInventoryStock",
    "correctStoreOwnerInventoryStock",
    "pauseStoreOwnerInventorySales",
    "resumeStoreOwnerInventorySales",
}


def test_route_manifest_api_spec_and_postman_cover_store_owner_inventory_operations() -> None:
    from token_payments.api import http_route_manifest

    manifest = {route["operationId"]: route for route in http_route_manifest()}
    api_spec = (ROOT / "docs" / "API_SPEC.md").read_text(encoding="utf-8")
    expected = _read_json(ROOT / "postman" / "expected" / "token-payments.api.expected.json")
    collection = _read_json(ROOT / "postman" / "token-payments.local.postman_collection.json")

    assert STORE_OWNER_INVENTORY_OPERATIONS <= set(manifest)
    assert STORE_OWNER_INVENTORY_OPERATIONS <= {route["operationId"] for route in expected["routes"]}
    assert STORE_OWNER_INVENTORY_OPERATIONS <= set(expected["collectionRequestIds"])
    assert STORE_OWNER_INVENTORY_OPERATIONS <= set(_operation_items(collection))

    for operation_id in STORE_OWNER_INVENTORY_OPERATIONS:
        route = manifest[operation_id]
        assert f"| `{operation_id}` | `{route['method']}` | `{route['path']}` |" in api_spec


def test_docs_distinguish_store_owner_admin_inventory_permissions_and_scope_exclusions() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "docs" / "API_SPEC.md",
            ROOT / "docs" / "DOMAIN_MODEL.md",
            ROOT / "docs" / "UI_GUIDE.md",
            ROOT / "README.md",
            ROOT / "app" / "README.md",
        )
    )

    assert "STORE_OWNER" in combined
    assert "ADMIN" in combined
    assert "own store inventory" in combined
    assert "admin can query or mutate any store inventory" in combined
    assert "manual order approval HTTP API is not in current scope" in combined
    assert "UI implementation remains a separate phase" in combined


def test_phase_metadata_reflects_completed_store_owner_inventory_phase() -> None:
    phase = _read_json(ROOT / "phases" / "20-store-owner-inventory-api" / "index.json")
    top = _read_json(ROOT / "phases" / "index.json")
    top_entry = next(item for item in top["phases"] if item["dir"] == "20-store-owner-inventory-api")

    assert all(step["status"] == "completed" for step in phase["steps"])
    assert all(step.get("summary") for step in phase["steps"])
    assert phase.get("completed_at")
    assert top_entry["status"] == "completed"
    assert top_entry.get("completed_at")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


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

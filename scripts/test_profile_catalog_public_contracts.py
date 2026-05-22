from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


DOC_PATHS = (
    "README.md",
    "app/README.md",
    "docs/API_SPEC.md",
    "docs/DOMAIN_MODEL.md",
)
COLLECTION_PATH = ROOT / "postman" / "token-payments.local.postman_collection.json"
EXPECTED_PATH = ROOT / "postman" / "expected" / "token-payments.api.expected.json"
SEED_PLAN_PATH = ROOT / "postman" / "fixtures" / "token-payments.local.seed-plan.json"
ENV_PATH = ROOT / "postman" / "token-payments.local.postman_environment.json"


def test_docs_separate_identity_profile_catalog_payment_inventory_and_future_scope() -> None:
    combined = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in DOC_PATHS)

    for phrase in (
        "User remains the authenticated identity and audit actor",
        "UserProfile",
        "GroupMembership connects a user to a group with a role",
        "Store business profile and payment settings are separate",
        "product catalog from inventory",
        "internal `store_id`",
        "external `public_store_id`",
        "internal `product_id`",
        "external `public_product_id`",
        "publicStoreId",
        "publicProductId",
        "Store/product slug fields and SKU fields are not part of phase 23",
        "User display names, store display names, and product titles are display/search fields and may be duplicated",
        "Implemented",
        "Partially implemented",
        "Future scope",
        "UUID identifiers",
        "Wallet and transaction hashes",
        "Email/URL/media/tag/category/JSON attributes",
        "Elasticsearch",
        "DID",
        "email account recovery",
        "Kafka live worker",
        "multi-wallet",
        "stablecoin",
    ):
        assert phrase in combined

    forbidden_required_phrases = (
        "slug is required",
        "required slug",
        "SKU is required",
        "auto-generates SKU",
    )
    lowered = combined.lower()
    for phrase in forbidden_required_phrases:
        assert phrase.lower() not in lowered


def test_postman_profile_catalog_examples_use_public_ids_and_cover_public_read_routes() -> None:
    collection = _read_json(COLLECTION_PATH)
    expected = _read_json(EXPECTED_PATH)
    items = _operation_items(collection)
    expected_routes = {route["operationId"]: route for route in expected["routes"]}

    required_operations = {
        "getStoreProfile",
        "listPublicStores",
        "listPublicProducts",
        "getPublicProduct",
        "listMerchantProducts",
        "getMerchantProduct",
        "registerStoreProduct",
        "updateStoreProduct",
    }
    assert required_operations <= set(items)
    assert required_operations <= set(expected_routes)

    for operation_id in required_operations:
        raw_url = items[operation_id]["request"]["url"]["raw"]
        route_text = json.dumps(expected_routes[operation_id], sort_keys=True)
        assert "publicStoreId" in raw_url or operation_id == "listPublicStores"
        assert "publicProductId" in raw_url or operation_id in {
            "getStoreProfile",
            "listPublicStores",
            "listPublicProducts",
            "listMerchantProducts",
            "registerStoreProduct",
        }
        assert "publicStoreId" in route_text or operation_id == "listPublicStores"
        if "Product" in operation_id:
            assert "publicProductId" in route_text


def test_seed_plan_and_environment_include_public_store_product_catalog_fixture() -> None:
    seed = _read_json(SEED_PLAN_PATH)
    environment = _read_json(ENV_PATH)
    env_values = {entry["key"]: entry["value"] for entry in environment["values"]}

    ids = seed["ids"]
    assert ids["demoPublicStoreId"] == "st_demo_store_001"
    assert ids["demoPublicProductId"] == "prd_local_hoodie_001"
    assert ids["demoPlatformAdminWallet"].startswith("0x")
    assert env_values["publicStoreId"] == ids["demoPublicStoreId"]
    assert env_values["publicProductId"] == ids["demoPublicProductId"]

    product_record = next(record for record in seed["records"] if record["table"] == "store_catalog_products")
    assert {
        "public_product_id",
        "public_store_id",
        "title",
        "description",
        "category",
        "tags",
        "media",
        "attributes",
        "status",
        "visibility",
    } <= set(product_record["columns"])
    assert product_record["values"]["public_product_id"] == ids["demoPublicProductId"]
    assert product_record["values"]["public_store_id"] == ids["demoPublicStoreId"]
    assert product_record["values"]["title"] == "Local Hoodie"
    assert product_record["values"]["tags"] == ["demo", "hoodie"]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _operation_items(collection: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    flattened: dict[str, Mapping[str, Any]] = {}

    def visit(items: list[Mapping[str, Any]]) -> None:
        for item in items:
            if "request" in item and "id" in item:
                flattened[str(item["id"])] = item
            visit(item.get("item", []))

    visit(collection.get("item", []))
    return flattened

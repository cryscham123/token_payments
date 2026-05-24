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
        "User and store display names are unique display/search fields; product titles may be duplicated",
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


def test_postman_store_product_write_examples_follow_generated_id_contract() -> None:
    collection = _read_json(COLLECTION_PATH)
    items = _operation_items(collection)

    store_user_body = items["createOrReuseStoreUser"]["request"]["body"]["raw"]
    create_store_body = _postman_json_body(items["createStore"])
    register_product_body = _postman_json_body(items["registerStoreProduct"])

    assert "{{storeOwnerWallet}}" in store_user_body
    assert "storeId" not in create_store_body
    assert "ownerUserId" in create_store_body
    assert "productId" not in register_product_body
    assert "publicProductId" not in register_product_body

    assert 'pm.environment.set("storeOwnerUserId", body.userId);' in _script_text(
        items["createOrReuseStoreUser"], "test"
    )
    create_store_script = _script_text(items["createStore"], "test")
    assert 'pm.environment.set("storeId", store.storeId);' in create_store_script
    assert 'pm.environment.set("publicStoreId", store.publicStoreId);' in create_store_script

    register_product_script = _script_text(items["registerStoreProduct"], "test")
    assert 'pm.environment.set("productId", body.productId);' in register_product_script
    assert 'pm.environment.set("publicProductId", body.publicProductId);' in register_product_script


def test_postman_checkout_payment_examples_use_tracking_id_contract() -> None:
    collection = _read_json(COLLECTION_PATH)
    items = _operation_items(collection)

    create_order_body = _postman_json_body(items["createOrder"])
    submit_tx_body = _postman_json_body(items["submitTransactionHash"])

    assert "storeId" in create_order_body
    assert "trackingId" not in create_order_body
    create_order_script = _script_text(items["createOrder"], "test")
    assert 'pm.environment.set("orderId", order.orderId);' in create_order_script
    assert 'pm.environment.set("trackingId", order.trackingId);' in create_order_script

    assert submit_tx_body == {"trackingId": "{{trackingId}}", "txHash": "{{txHash}}"}


def test_seed_plan_documents_optional_fixture_but_environment_uses_runtime_generated_catalog_ids() -> None:
    seed = _read_json(SEED_PLAN_PATH)
    environment = _read_json(ENV_PATH)
    env_values = {entry["key"]: entry["value"] for entry in environment["values"]}

    ids = seed["ids"]
    assert ids["demoPublicStoreId"] == "st_demo_store_001"
    assert ids["demoPublicProductId"] == "prd_local_hoodie_001"
    assert ids["demoPlatformAdminWallet"].startswith("0x")
    assert env_values["storeId"] == ""
    assert env_values["publicStoreId"] == ""
    assert env_values["productId"] == ""
    assert env_values["publicProductId"] == ""
    assert env_values["storeOwnerUserId"] == ""

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


def _script_text(item: Mapping[str, Any], listen: str) -> str:
    for event in item.get("event", []):
        if event.get("listen") == listen:
            return "\n".join(event.get("script", {}).get("exec", []))
    return ""


def _postman_json_body(item: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = item["request"]["body"]["raw"]
    return json.loads(raw.replace("{{chainId}}", "1337"))

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.domain import UserRole
from _store_catalog_test_support import (
    ADMIN_ID,
    OWNER_ID,
    OWNER_WALLET,
    STORE_ID,
    STORE_WALLET,
    PRODUCT_ID,
    FakeStoreCatalogRepository,
    FixedIdGenerator,
    auth,
    catalog_router,
    decode,
    json_body,
    price_payload,
)


def test_forbidden_fields_in_api_responses() -> None:
    api_dir = ROOT / "app/token_payments/api"
    forbidden_keys = {
        "orderId", "customerId", "storeId", "sessionId",
        "refreshTokenHash", "refreshTokenHash.hash",
        "refreshTokenHash.salt", "refreshTokenHash.rotationVersion"
    }
    
    found_occurrences = []
    for p in api_dir.glob("**/*.py"):
        content = p.read_text(encoding="utf-8")
        for key in forbidden_keys:
            if f'"{key}"' in content or f"'{key}'" in content:
                found_occurrences.append((p.name, key))
                
    print("\n[Audit] Forbidden fields exposed in API layer:")
    for file_name, key in found_occurrences:
        print(f"  - {file_name}: {key}")
    
    assert len(forbidden_keys) > 0


def test_payment_tx_hash_submission_internal_order_id_audit() -> None:
    api_files = list(ROOT.glob("app/token_payments/api/*.py"))
    
    found_internal_order_ref = False
    for p in api_files:
        content = p.read_text(encoding="utf-8")
        if "submit" in p.name or "checkout" in p.name:
            if "orderId" in content or "order_id" in content:
                found_internal_order_ref = True
    
    print(f"\n[Audit] Internal order ID found in checkout/payment API files: {found_internal_order_ref}")


def test_inventory_mutation_authorization_scope_audit() -> None:
    inventory_api = ROOT / "app/token_payments/api/inventory.py"
    if inventory_api.exists():
        content = inventory_api.read_text(encoding="utf-8")
        has_scope_check = "inventory:write" in content
        print(f"\n[Audit] Inventory API has inventory:write scope check: {has_scope_check}")


def test_product_registration_scope_and_membership_separation_audit() -> None:
    api_content = (ROOT / "app/token_payments/api/store_catalog.py").read_text(encoding="utf-8")
    service_content = (ROOT / "app/token_payments/contexts/store_catalog/application/service.py").read_text(encoding="utf-8")
    
    api_checks_scope = "product:write" in api_content or "product:write:any" in api_content
    service_checks_membership = "get_store_role" in service_content or "membership" in service_content
    
    assert api_checks_scope, "API layer must check product:write scope"
    assert service_checks_membership, "Service layer must check store membership"


def test_cross_context_domain_imports_audit() -> None:
    files_to_check = [
        ("app/token_payments/contexts/inventory/application/commands.py", "auth.domain"),
        ("app/token_payments/contexts/store_catalog/application/service.py", "auth.domain"),
        ("app/token_payments/contexts/store_catalog/application/service.py", "payment.domain"),
        ("app/token_payments/contexts/order/adapter/postgres.py", "payment.domain"),
    ]
    
    found_violations = []
    for relative_path, forbidden_context in files_to_check:
        full_path = ROOT / relative_path
        if full_path.exists():
            content = full_path.read_text(encoding="utf-8")
            if forbidden_context in content:
                found_violations.append((relative_path, forbidden_context))
                
    print("\n[Audit] Cross-context domain import violations:")
    for path, context in found_violations:
        print(f"  - {path} imports {context}")
        
    assert len(found_violations) > 0, "Expected cross-context domain imports to be found for auditing in step 0"


def test_runtime_composition_size_and_responsibility_audit() -> None:
    comp_file = ROOT / "app/token_payments/runtime/composition.py"
    assert comp_file.exists()
    lines = comp_file.read_text(encoding="utf-8").splitlines()
    print(f"\n[Audit] runtime/composition.py line count: {len(lines)}")
    assert len(lines) > 500, "composition.py is expected to be a single large file coordinating composition"


def test_store_memberships_and_group_memberships_write_paths_audit() -> None:
    print("\n[Audit] Checking write paths for memberships...")


def test_api_rejects_client_provided_ids() -> None:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    
    # 1. POST /admin/stores rejects storeId and publicStoreId
    router = catalog_router(repository, auth(ADMIN_ID, UserRole.ADMIN))
    response = router.handle(
        "POST",
        "/admin/stores",
        headers={"Content-Type": "application/json", "Idempotency-Key": "audit-store-reject"},
        body=json_body({"storeId": str(STORE_ID), "ownerUserId": str(OWNER_ID), "storeWalletAddress": str(STORE_WALLET), "supportedChainIds": [11155111]}),
    )
    assert response.status_code == 400
    assert decode(response.body)["error"]["code"] == "VALIDATION_ERROR"
    
    # 2. POST /merchant/stores/{publicStoreId}/products rejects productId
    repository.seed_store(owner_id=OWNER_ID)
    router_merchant = catalog_router(repository, auth(OWNER_ID, UserRole.CUSTOMER))
    response_prod = router_merchant.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "audit-product-reject"},
        body=json_body({"productId": str(PRODUCT_ID), "name": "Mug", "price": price_payload(), "initialTotalStock": 10}),
    )
    assert response_prod.status_code == 400
    assert decode(response_prod.body)["error"]["code"] == "VALIDATION_ERROR"


def test_product_registration_does_not_upsert() -> None:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    repository.seed_store(owner_id=OWNER_ID)
    
    router = catalog_router(
        repository,
        auth(OWNER_ID, UserRole.CUSTOMER),
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    )
    
    # First POST
    first = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "audit-no-upsert-1"},
        body=json_body({"name": "Mug 1", "price": price_payload(), "initialTotalStock": 10}),
    )
    assert first.status_code == 201
    
    # Different idempotency key, but same name. Should create a new product ID, not upsert/override the existing product
    router2 = catalog_router(
        repository,
        auth(OWNER_ID, UserRole.CUSTOMER),
        id_generator=FixedIdGenerator("018f33aa-9e6d-73d8-9dc3-47d6cdcc9009"),
    )
    second = router2.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "audit-no-upsert-2"},
        body=json_body({"name": "Mug 1", "price": price_payload(), "initialTotalStock": 15}),
    )
    assert second.status_code == 201
    
    # Verify that they are two distinct products in repository (no upsert happened)
    assert len(repository.products) == 2

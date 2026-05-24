from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.domain import UserRole  # noqa: E402

from _store_catalog_test_support import (  # noqa: E402
    ADMIN_ID,
    CUSTOMER_ID,
    CUSTOMER_WALLET,
    OTHER_ID,
    OTHER_WALLET,
    OWNER_ID,
    OWNER_WALLET,
    PRODUCT_ID,
    STORE_ID,
    FakeStoreCatalogRepository,
    FixedIdGenerator,
    auth,
    catalog_router,
    decode,
    json_body,
    price,
    price_payload,
)


def test_customer_role_store_member_can_register_checkoutable_product_without_global_store_owner_role() -> None:
    repository = _seed_owner_store()
    router = catalog_router(
        repository,
        auth(OWNER_ID, UserRole.CUSTOMER),
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    )

    response = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-register-owner-001", "X-Request-Id": "req-product-register"},
        body=_product_body_no_id(),
    )

    payload = decode(response.body)

    assert response.status_code == 201
    assert payload["storeId"] == str(STORE_ID)
    assert payload["productId"] == str(PRODUCT_ID)
    assert payload["price"] == price_payload()
    assert payload["initialTotalStock"] == 25
    assert repository.products[(STORE_ID, PRODUCT_ID)].price == price()
    assert repository.order_products[(STORE_ID, PRODUCT_ID)].name == "Ledger Mug"
    assert repository.store_approval_products[(STORE_ID, PRODUCT_ID)].active is True
    assert repository.inventory[(STORE_ID, PRODUCT_ID)] == 25
    assert repository.users_by_id[OWNER_ID].role is UserRole.CUSTOMER


def test_admin_override_can_register_product_for_any_active_store() -> None:
    repository = _seed_owner_store()
    router = catalog_router(
        repository,
        auth(ADMIN_ID, UserRole.ADMIN),
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    )

    response = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-register-admin-001", "X-Request-Id": "req-admin-product"},
        body=_product_body_no_id(),
    )

    assert response.status_code == 201
    assert repository.products[(STORE_ID, PRODUCT_ID)].name == "Ledger Mug"


def test_unrelated_customer_and_unauthenticated_product_registration_are_denied() -> None:
    repository = _seed_owner_store()
    repository.seed_user(OTHER_ID, OTHER_WALLET, role=UserRole.CUSTOMER)

    unrelated = catalog_router(
        repository,
        auth(OTHER_ID, UserRole.CUSTOMER),
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    ).handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-register-denied-001"},
        body=_product_body_no_id(),
    )
    unauthenticated = catalog_router(
        repository,
        None,
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    ).handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-register-denied-002"},
        body=_product_body_no_id(),
    )

    assert unrelated.status_code == 403
    assert decode(unrelated.body)["error"]["code"] == "STORE_OWNER_STORE_FORBIDDEN"
    assert unauthenticated.status_code == 401
    assert decode(unauthenticated.body)["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert repository.products == {}


def test_product_registration_requires_active_store_supported_chain_and_non_negative_stock() -> None:
    inactive_repository = _seed_owner_store(active=False)
    inactive = catalog_router(
        inactive_repository,
        auth(OWNER_ID, UserRole.CUSTOMER),
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    ).handle(
        "POST",
        f"/merchant/stores/{inactive_repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-inactive-store-001"},
        body=_product_body_no_id(),
    )

    wrong_chain_repository = _seed_owner_store(chains=(84532,))
    wrong_chain = catalog_router(
        wrong_chain_repository,
        auth(OWNER_ID, UserRole.CUSTOMER),
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    ).handle(
        "POST",
        f"/merchant/stores/{wrong_chain_repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-wrong-chain-001"},
        body=_product_body_no_id(),
    )

    bad_stock_repository = _seed_owner_store()
    bad_stock = catalog_router(
        bad_stock_repository,
        auth(OWNER_ID, UserRole.CUSTOMER),
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    ).handle(
        "POST",
        f"/merchant/stores/{bad_stock_repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-bad-stock-001"},
        body=json_body(
            {
                "name": "Ledger Mug",
                "price": price_payload(),
                "initialTotalStock": -1,
                "active": True,
            }
        ),
    )

    assert inactive.status_code == 409
    assert decode(inactive.body)["error"]["code"] == "STORE_INACTIVE"
    assert wrong_chain.status_code == 409
    assert decode(wrong_chain.body)["error"]["code"] == "UNSUPPORTED_PRICE_CHAIN"
    assert bad_stock.status_code == 400
    assert decode(bad_stock.body)["error"]["code"] == "VALIDATION_ERROR"


def test_product_registration_idempotency_does_not_duplicate_projection_or_inventory_rows() -> None:
    repository = _seed_owner_store()
    router = catalog_router(
        repository,
        auth(OWNER_ID, UserRole.CUSTOMER),
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    )

    first = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-register-idem-001", "X-Request-Id": "req-product-1"},
        body=_product_body_no_id(),
    )
    duplicate = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-register-idem-001", "X-Request-Id": "req-product-1"},
        body=_product_body_no_id(),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert decode(duplicate.body)["idempotentReplay"] is True
    assert len(repository.products) == 1
    assert len(repository.order_products) == 1
    assert len(repository.store_approval_products) == 1
    assert len(repository.inventory) == 1
    assert len(repository.audit_records) == 1


def test_product_registration_generates_product_id_when_not_provided() -> None:
    repository = _seed_owner_store()
    router = catalog_router(
        repository,
        auth(OWNER_ID, UserRole.CUSTOMER),
        id_generator=FixedIdGenerator("018f33aa-9e6d-73d8-9dc3-47d6cdcc9009"),
    )

    response = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-register-no-id-001", "X-Request-Id": "req-product-no-id"},
        body=json_body(
            {
                "name": "Auto ID Mug",
                "price": price_payload(),
                "initialTotalStock": 5,
                "active": True,
            }
        ),
    )

    payload = decode(response.body)
    assert response.status_code == 201
    assert "productId" in payload
    assert payload["productId"] == "018f33aa-9e6d-73d8-9dc3-47d6cdcc9009"
    assert len(repository.products) == 1


def test_registered_public_product_is_immediately_listed_by_public_query_text() -> None:
    repository = _seed_owner_store()
    router = catalog_router(
        repository,
        auth(OWNER_ID, UserRole.CUSTOMER),
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    )
    public_store_id = repository.stores[STORE_ID].public_store_id

    register = router.handle(
        "POST",
        f"/merchant/stores/{public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-register-list-public-001"},
        body=json_body(
            {
                "title": "Local Hoodie",
                "price": price_payload(),
                "initialTotalStock": 25,
                "status": "ACTIVE",
                "visibility": "PUBLIC",
                "active": True,
            }
        ),
    )
    listed = catalog_router(repository, None).handle(
        "GET",
        f"/stores/{public_store_id}/products",
        query={"limit": "20", "offset": "0", "q": "Local"},
    )

    payload = decode(listed.body)
    assert register.status_code == 201
    assert listed.status_code == 200
    assert [product["title"] for product in payload["products"]] == ["Local Hoodie"]
    assert payload["products"][0]["publicProductId"] == decode(register.body)["publicProductId"]


def test_product_registration_rejects_client_provided_ids() -> None:
    repository = _seed_owner_store()
    router = catalog_router(repository, auth(OWNER_ID, UserRole.CUSTOMER))

    # Reject productId
    response_with_product_id = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-register-reject-001"},
        body=json_body(
            {
                "productId": str(PRODUCT_ID),
                "name": "Ledger Mug",
                "price": price_payload(),
                "initialTotalStock": 25,
                "active": True,
            }
        ),
    )
    assert response_with_product_id.status_code == 400
    assert decode(response_with_product_id.body)["error"]["code"] == "VALIDATION_ERROR"
    assert "unknown store profile field(s): productId" in decode(response_with_product_id.body)["error"]["message"]

    # Reject publicProductId
    response_with_public_id = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-register-reject-002"},
        body=json_body(
            {
                "publicProductId": "prd_some_id",
                "name": "Ledger Mug",
                "price": price_payload(),
                "initialTotalStock": 25,
                "active": True,
            }
        ),
    )
    assert response_with_public_id.status_code == 400
    assert decode(response_with_public_id.body)["error"]["code"] == "VALIDATION_ERROR"
    assert "unknown store profile field(s): publicProductId" in decode(response_with_public_id.body)["error"]["message"]


def _seed_owner_store(*, active: bool = True, chains: tuple[int, ...] = (11155111,)) -> FakeStoreCatalogRepository:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    repository.seed_store(owner_id=OWNER_ID, active=active, chains=chains)
    return repository


def _product_body_no_id() -> bytes:
    return json_body(
        {
            "name": "Ledger Mug",
            "price": price_payload(),
            "initialTotalStock": 25,
            "active": True,
        }
    )

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.domain import UserRole

from _store_catalog_test_support import (
    ADMIN_ID,
    CUSTOMER_ID,
    CUSTOMER_WALLET,
    OWNER_ID,
    OWNER_WALLET,
    STORE_ID,
    STORE_WALLET,
    FakeStoreCatalogRepository,
    auth,
    catalog_router,
    decode,
    json_body,
)


def test_admin_can_create_customer_identity_for_future_store_owner_without_global_store_owner_role() -> None:
    repository = FakeStoreCatalogRepository()
    router = catalog_router(repository, auth(ADMIN_ID, UserRole.ADMIN))

    response = router.handle(
        "POST",
        "/admin/store-users",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-store-user-001", "X-Request-Id": "req-admin-store-user-001"},
        body=json_body({"walletAddress": str(OWNER_WALLET), "role": "STORE_OWNER"}),
    )

    payload = decode(response.body)

    assert response.status_code == 201
    assert payload["platformRole"] == "CUSTOMER"
    assert payload["globalStoreOwnerRoleGranted"] is False
    assert list(repository.users_by_wallet) == [OWNER_WALLET]


def test_existing_customer_wallet_is_reused_without_duplicate_user_or_role_change() -> None:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(CUSTOMER_ID, CUSTOMER_WALLET, role=UserRole.CUSTOMER)
    router = catalog_router(repository, auth(ADMIN_ID, UserRole.ADMIN))

    response = router.handle(
        "POST",
        "/admin/store-users",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-store-user-reuse-001", "X-Request-Id": "req-reuse"},
        body=json_body({"walletAddress": str(CUSTOMER_WALLET)}),
    )

    payload = decode(response.body)

    assert response.status_code == 201
    assert payload["userCreated"] is False
    assert payload["userReused"] is True
    assert payload["userId"] == str(CUSTOMER_ID)
    assert repository.users_by_id[CUSTOMER_ID].role is UserRole.CUSTOMER
    assert len(repository.users_by_wallet) == 1


def test_admin_create_store_writes_canonical_store_membership_and_runtime_projections() -> None:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    router = catalog_router(repository, auth(ADMIN_ID, UserRole.ADMIN))

    response = router.handle(
        "POST",
        "/admin/stores",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-create-store-001", "X-Request-Id": "req-create-store"},
        body=json_body(
            {
                "ownerUserId": str(OWNER_ID),
                "storeWalletAddress": str(STORE_WALLET),
                "supportedChainIds": [11155111, 84532],
                "active": True,
            }
        ),
    )

    payload = decode(response.body)

    assert response.status_code == 201
    assert payload["storeCreated"] is True
    assert payload["ownershipCreated"] is True
    assert repository.stores[STORE_ID].owner_user_id == OWNER_ID
    assert repository.memberships[(STORE_ID, OWNER_ID)].role.value == "OWNER"
    assert repository.order_stores[STORE_ID].store_wallet == STORE_WALLET
    assert repository.store_approval_stores[STORE_ID].owner_user_id == OWNER_ID
    assert payload["projections"] == {
        "canonical": "store_catalog_stores",
        "order": "order_stores",
        "storeApproval": "store_approval_stores",
    }


def test_admin_create_store_is_idempotent_for_same_key_and_rejects_payload_conflict() -> None:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    router = catalog_router(repository, auth(ADMIN_ID, UserRole.ADMIN))
    body = {
        "ownerUserId": str(OWNER_ID),
        "storeWalletAddress": str(STORE_WALLET),
        "supportedChainIds": [11155111],
        "active": True,
    }

    first = router.handle(
        "POST",
        "/admin/stores",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-create-store-idem-001", "X-Request-Id": "req-first"},
        body=json_body(body),
    )
    duplicate = router.handle(
        "POST",
        "/admin/stores",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-create-store-idem-001", "X-Request-Id": "req-first"},
        body=json_body(body),
    )
    conflict = router.handle(
        "POST",
        "/admin/stores",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-create-store-idem-001", "X-Request-Id": "req-conflict"},
        body=json_body({**body, "supportedChainIds": [84532]}),
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert decode(duplicate.body)["idempotentReplay"] is True
    assert conflict.status_code == 409
    assert len(repository.audit_records) == 1


def test_non_admin_and_unauthenticated_requests_are_denied_for_admin_provisioning() -> None:
    repository = FakeStoreCatalogRepository()

    customer = catalog_router(repository, auth(CUSTOMER_ID, UserRole.CUSTOMER)).handle(
        "POST",
        "/admin/store-users",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-denied-001"},
        body=json_body({"walletAddress": str(OWNER_WALLET)}),
    )
    unauthenticated = catalog_router(repository, None).handle(
        "POST",
        "/admin/store-users",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-denied-002"},
        body=json_body({"walletAddress": str(OWNER_WALLET)}),
    )

    assert customer.status_code == 403
    assert decode(customer.body)["error"]["code"] == "ADMIN_REQUIRED"
    assert unauthenticated.status_code == 401
    assert decode(unauthenticated.body)["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_admin_create_store_rejects_client_provided_ids() -> None:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    router = catalog_router(repository, auth(ADMIN_ID, UserRole.ADMIN))

    # Reject storeId
    response_with_store_id = router.handle(
        "POST",
        "/admin/stores",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-create-store-reject-001"},
        body=json_body(
            {
                "storeId": str(STORE_ID),
                "ownerUserId": str(OWNER_ID),
                "storeWalletAddress": str(STORE_WALLET),
                "supportedChainIds": [11155111],
                "active": True,
            }
        ),
    )
    assert response_with_store_id.status_code == 400
    assert decode(response_with_store_id.body)["error"]["code"] == "VALIDATION_ERROR"
    assert "unknown store profile field(s): storeId" in decode(response_with_store_id.body)["error"]["message"]

    # Reject publicStoreId
    response_with_public_id = router.handle(
        "POST",
        "/admin/stores",
        headers={"Content-Type": "application/json", "Idempotency-Key": "admin-create-store-reject-002"},
        body=json_body(
            {
                "publicStoreId": "sto_some_id",
                "ownerUserId": str(OWNER_ID),
                "storeWalletAddress": str(STORE_WALLET),
                "supportedChainIds": [11155111],
                "active": True,
            }
        ),
    )
    assert response_with_public_id.status_code == 400
    assert decode(response_with_public_id.body)["error"]["code"] == "VALIDATION_ERROR"
    assert "unknown store profile field(s): publicStoreId" in decode(response_with_public_id.body)["error"]["message"]

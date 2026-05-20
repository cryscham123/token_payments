from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.domain import User, UserRole  # noqa: E402
from token_payments.contexts.store_catalog.domain import (  # noqa: E402
    StoreCatalog,
    StoreMembership,
    StoreMembershipRole,
    StoreProduct,
    StoreProfile,
)
from token_payments.shared.domain import ProductId, StoreId, UserId  # noqa: E402

from _store_catalog_test_support import CUSTOMER_WALLET, OWNER_WALLET, PRODUCT_ID, STORE_ID, STORE_WALLET, price  # noqa: E402


def test_store_ownership_is_store_scoped_not_global_store_owner_role() -> None:
    customer_user = User.register_by_wallet(
        UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9101"),
        CUSTOMER_WALLET,
        role=UserRole.CUSTOMER,
    )
    profile = StoreProfile(
        store_id=STORE_ID,
        owner_user_id=customer_user.user_id,
        active=True,
        store_wallet=STORE_WALLET,
        supported_chain_ids=(11155111,),
    )
    membership = StoreMembership.owner(STORE_ID, customer_user.user_id)

    assert customer_user.role is UserRole.CUSTOMER
    assert membership.role is StoreMembershipRole.OWNER
    assert profile.owner_user_id == customer_user.user_id


def test_same_wallet_reuses_one_auth_identity_for_customer_and_store_management() -> None:
    user = User.register_by_wallet(
        UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9102"),
        OWNER_WALLET,
        role=UserRole.CUSTOMER,
    )
    membership = StoreMembership.owner(STORE_ID, user.user_id)

    assert user.primary_wallet == OWNER_WALLET
    assert user.role is UserRole.CUSTOMER
    assert membership.user_id == user.user_id


def test_store_settings_live_on_store_profile_not_owner_account() -> None:
    profile = StoreProfile(
        store_id=STORE_ID,
        owner_user_id=UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9103"),
        active=True,
        store_wallet=STORE_WALLET,
        supported_chain_ids=(11155111, 84532),
    )

    assert str(profile.store_wallet) == str(STORE_WALLET)
    assert profile.supported_chain_ids == (11155111, 84532)
    assert profile.supports_chain(84532)


def test_minimal_product_contract_excludes_future_catalog_metadata() -> None:
    product = StoreProduct(
        store_id=STORE_ID,
        product_id=PRODUCT_ID,
        name="Ledger Mug",
        price=price(),
        active=True,
    )

    assert product.name == "Ledger Mug"
    assert product.active is True
    assert not hasattr(product, "description")
    assert not hasattr(product, "category")
    assert not hasattr(product, "tags")
    assert not hasattr(product, "search_metadata")


def test_store_catalog_disallows_duplicate_product_ids_within_one_store() -> None:
    profile = StoreProfile(
        store_id=STORE_ID,
        owner_user_id=UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9104"),
        active=True,
        store_wallet=STORE_WALLET,
        supported_chain_ids=(11155111,),
    )
    product = StoreProduct(store_id=STORE_ID, product_id=PRODUCT_ID, name="Ledger Mug", price=price(), active=True)

    try:
        StoreCatalog(store=profile, products=(product, product))
    except ValueError as exc:
        assert "duplicate product ids" in str(exc)
    else:
        raise AssertionError("duplicate products should be rejected")


def test_schema_adds_canonical_tables_without_removing_checkout_projections() -> None:
    schema = (ROOT / "app" / "postgres" / "init.d" / "001-token-payments-schema.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS store_catalog_stores" in schema
    assert "CREATE TABLE IF NOT EXISTS store_catalog_store_memberships" in schema
    assert "CREATE TABLE IF NOT EXISTS store_catalog_products" in schema
    assert "PRIMARY KEY (store_id, product_id)" in schema
    assert "CREATE TABLE IF NOT EXISTS order_stores" in schema
    assert "CREATE TABLE IF NOT EXISTS order_store_products" in schema
    assert "CREATE TABLE IF NOT EXISTS store_approval_stores" in schema
    assert "CREATE TABLE IF NOT EXISTS store_approval_products" in schema
    assert "actor_role TEXT NOT NULL CHECK (actor_role IN ('CUSTOMER', 'STORE_OWNER', 'ADMIN'))" in schema


def test_public_auth_flow_does_not_accept_store_owner_role_selection() -> None:
    auth_api = (ROOT / "app" / "token_payments" / "api" / "auth.py").read_text(encoding="utf-8")
    auth_service = (ROOT / "app" / "token_payments" / "contexts" / "auth" / "application" / "service.py").read_text(
        encoding="utf-8"
    )

    assert 'role=UserRole.CUSTOMER' not in auth_api
    assert "STORE_OWNER" not in auth_api
    assert "User.register_by_wallet" in auth_service
    assert "role=UserRole.STORE_OWNER" not in auth_service

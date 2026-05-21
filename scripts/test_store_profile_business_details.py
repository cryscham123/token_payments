from __future__ import annotations

import re
import sys
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiAuthContext, HttpRouter, StoreCatalogApi, http_route_manifest, register_store_catalog_routes  # noqa: E402
from token_payments.contexts.auth.domain import GroupId, UserRole  # noqa: E402
from token_payments.contexts.store_catalog.adapter import PostgresStoreCatalogRepository  # noqa: E402
from token_payments.contexts.store_catalog.application import StoreCatalogApplicationService  # noqa: E402
from token_payments.contexts.store_catalog.domain import (  # noqa: E402
    PublicStoreId,
    StoreMembership,
    StorePaymentSettings,
    StoreProfile,
    StoreStatus,
)
from _store_catalog_test_support import (  # noqa: E402
    OWNER_ID,
    OWNER_WALLET,
    STORE_ID,
    STORE_WALLET,
    FakeStoreCatalogRepository,
    auth,
    decode,
    json_body,
)


NOW = datetime(2026, 5, 22, 2, 0, tzinfo=UTC)
PUBLIC_STORE_ID = PublicStoreId("st_ledger_cafe_001")
GROUP_ID = GroupId("018f33aa-9e6d-73d8-9dc3-47d6cdcc2401")


def test_store_profile_business_identity_is_separate_from_payment_settings() -> None:
    profile = _profile(display_name="  Cafe\u0301 Store  ", support_email="SUPPORT@Example.COM")
    profile_fields = {field.name for field in fields(StoreProfile)}
    payment_fields = {field.name for field in fields(StorePaymentSettings)}

    assert {
        "store_id",
        "public_store_id",
        "group_id",
        "display_name",
        "description",
        "status",
        "support_email",
        "business_registration_label",
        "created_at",
        "updated_at",
    } <= profile_fields
    assert {"store_wallet", "supported_chain_ids"} <= payment_fields
    assert {"store_wallet", "supported_chain_ids"}.isdisjoint(profile_fields)
    assert profile.public_store_id == PUBLIC_STORE_ID
    assert profile.public_store_id != str(profile.store_id)
    assert _is_uuid(str(profile.store_id))
    assert not _is_uuid(str(profile.public_store_id))
    assert not str(profile.public_store_id).isdigit()
    assert profile.display_name == "Caf\u00e9 Store"
    assert profile.support_email == "support@example.com"
    assert profile.payment_settings is not None
    assert profile.payment_settings.supports_chain(11155111)


@pytest.mark.parametrize("public_store_id", [str(STORE_ID), "123456", "Store With Spaces", "st_\x00bad"])
def test_public_store_id_rejects_internal_uuid_sequential_and_untrusted_values(public_store_id: str) -> None:
    with pytest.raises(ValueError, match="public_store_id|PublicStoreId"):
        PublicStoreId(public_store_id)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"display_name": ""},
        {"display_name": "A\nB"},
        {"display_name": "A\x00B"},
        {"display_name": "=SUM(A1:A2)"},
        {"description": "x" * 2001},
        {"description": "@not a safe log prefix"},
        {"business_registration_label": "Bad\rLabel"},
        {"business_registration_label": "+CSV"},
        {"support_email": "not-an-email"},
        {"support_email": "a" * 245 + "@example.com"},
    ],
)
def test_store_profile_business_fields_are_bounded_untrusted_data(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        _profile(**kwargs)


def test_public_store_detail_uses_public_store_id_and_redacts_private_fields() -> None:
    repository = _seed_repository(
        _profile(
            display_name="<Ledger & Cafe>",
            description="Hardware wallets and coffee",
            support_email="owner@example.com",
            support_email_public=False,
            business_registration_label="BRN-1234",
        )
    )
    router = _router(repository, None)

    response = router.handle("GET", f"/stores/{PUBLIC_STORE_ID}", headers={"X-Request-Id": "req-public-store"})
    payload = decode(response.body)

    assert response.status_code == 200
    public_store = payload["store"]
    assert public_store["publicStoreId"] == str(PUBLIC_STORE_ID)
    assert public_store["displayName"] == "<Ledger & Cafe>"
    assert public_store["displayNameHtml"] == "&lt;Ledger &amp; Cafe&gt;"
    assert public_store["descriptionHtml"] == "Hardware wallets and coffee"
    assert "storeId" not in public_store
    assert "ownerUserId" not in public_store
    assert "groupId" not in public_store
    assert "storeWallet" not in public_store
    assert "supportedChainIds" not in public_store
    assert "supportEmail" not in public_store
    assert "businessRegistrationLabel" not in public_store


def test_update_store_profile_uses_store_write_and_cannot_mutate_status_membership_or_payment_settings() -> None:
    repository = _seed_repository(_profile(display_name="Old Name", support_email="private@example.com"))
    router = _router(repository, auth(OWNER_ID, UserRole.CUSTOMER, scopes=("store:write",)))
    before_settings = repository.stores[STORE_ID].payment_settings

    response = router.handle(
        "PATCH",
        f"/merchant/stores/{PUBLIC_STORE_ID}/profile",
        headers={"Content-Type": "application/json", "Idempotency-Key": "update-profile-001"},
        body=json_body(
            {
                "displayName": "New Store",
                "description": "New public description",
                "supportEmail": "team@example.com",
                "supportEmailPublic": True,
                "businessRegistrationLabel": "BRN-5678",
            }
        ),
    )
    payload = decode(response.body)

    assert response.status_code == 200
    assert payload["store"]["publicStoreId"] == str(PUBLIC_STORE_ID)
    assert payload["store"]["displayName"] == "New Store"
    assert payload["store"]["supportEmail"] == "team@example.com"
    assert repository.stores[STORE_ID].payment_settings == before_settings
    assert repository.audit_records[-1].permission == "store:write"

    forbidden = router.handle(
        "PATCH",
        f"/merchant/stores/{PUBLIC_STORE_ID}/profile",
        headers={"Content-Type": "application/json", "Idempotency-Key": "update-profile-002"},
        body=json_body({"status": "SUSPENDED", "storeWalletAddress": str(OWNER_WALLET), "ownerUserId": str(OWNER_ID)}),
    )

    assert forbidden.status_code == 400
    assert decode(forbidden.body)["error"]["code"] == "VALIDATION_ERROR"


def test_list_merchant_stores_returns_public_ids_without_internal_store_ids() -> None:
    repository = _seed_repository(_profile(display_name="Merchant Store", support_email_public=True))
    router = _router(repository, auth(OWNER_ID, UserRole.CUSTOMER, scopes=("store:read",)))

    response = router.handle("GET", "/merchant/stores", headers={"X-Request-Id": "req-list-stores"})
    payload = decode(response.body)

    assert response.status_code == 200
    assert payload["stores"] == [
        {
            "publicStoreId": str(PUBLIC_STORE_ID),
            "displayName": "Merchant Store",
            "displayNameHtml": "Merchant Store",
            "description": "Wallet-safe checkout store",
            "descriptionHtml": "Wallet-safe checkout store",
            "status": "ACTIVE",
            "supportEmail": "support@example.com",
        }
    ]
    assert "storeId" not in payload["stores"][0]


def test_store_profile_repository_uses_parameter_binding_for_business_text() -> None:
    connection = FakeProfileConnection()
    repository = PostgresStoreCatalogRepository(connection)
    profile = _profile(display_name="<Ledger & Cafe>", description="A <B> store")

    repository.save_store(profile)

    combined_sql = "\n".join(statement.sql for statement in connection.statements)
    assert "INSERT INTO store_catalog_stores" in combined_sql
    assert "%(public_store_id)s" in combined_sql
    assert "%(display_name)s" in combined_sql
    assert "%(description)s" in combined_sql
    assert profile.display_name not in combined_sql
    assert profile.description not in combined_sql
    assert connection.statements[-1].params["display_name"] == "<Ledger & Cafe>"
    assert connection.statements[-1].params["public_store_id"] == str(PUBLIC_STORE_ID)


def test_schema_docs_and_route_manifest_expose_public_store_profile_contract() -> None:
    schema = (ROOT / "app/postgres/init.d/001-token-payments-schema.sql").read_text(encoding="utf-8")
    api_spec = (ROOT / "docs/API_SPEC.md").read_text(encoding="utf-8")
    domain_model = (ROOT / "docs/DOMAIN_MODEL.md").read_text(encoding="utf-8")
    manifest = list(http_route_manifest())

    stores_block = re.search(r"CREATE TABLE IF NOT EXISTS store_catalog_stores \((.*?)\);", schema, re.DOTALL)
    assert stores_block is not None
    assert "public_store_id TEXT NOT NULL" in stores_block.group(1)
    assert "display_name TEXT NOT NULL" in stores_block.group(1)
    assert "support_email TEXT" in stores_block.group(1)
    assert "store_wallet_address TEXT NOT NULL" in stores_block.group(1)
    assert "supported_chain_ids JSONB NOT NULL" in stores_block.group(1)
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_store_catalog_stores_public_store_id" in schema
    assert "UPDATE store_catalog_stores" in schema
    assert "public_store_id" in api_spec
    assert "publicStoreId" in api_spec
    assert "StorePaymentSettings" in domain_model
    assert {"getStoreProfile", "updateStoreProfile", "listMerchantStores"} <= {
        route["operationId"] for route in manifest
    }


def _profile(**overrides: Any) -> StoreProfile:
    values = {
        "store_id": STORE_ID,
        "owner_user_id": OWNER_ID,
        "public_store_id": PUBLIC_STORE_ID,
        "group_id": GROUP_ID,
        "display_name": "Ledger Cafe",
        "description": "Wallet-safe checkout store",
        "status": StoreStatus.ACTIVE,
        "support_email": "support@example.com",
        "support_email_public": True,
        "business_registration_label": "BRN-0001",
        "payment_settings": StorePaymentSettings(
            store_id=STORE_ID,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(11155111,),
            active=True,
        ),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return StoreProfile(**values)


def _seed_repository(profile: StoreProfile) -> FakeStoreCatalogRepository:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    repository.save_store(profile)
    repository.save_membership(StoreMembership.owner(STORE_ID, OWNER_ID))
    return repository


def _router(repository: FakeStoreCatalogRepository, auth_context: ApiAuthContext | None) -> HttpRouter:
    service = StoreCatalogApplicationService(repository=repository)
    router = HttpRouter(auth_context_factory=lambda _request: auth_context, allow_dev_auth_headers=False)
    register_store_catalog_routes(router, StoreCatalogApi(service))
    return router


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class ExecutedStatement:
    sql: str
    params: Mapping[str, Any]


class FakeProfileConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
        self.statements.append(ExecutedStatement(sql=sql, params=dict(params or {})))
        return ()

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import HttpRouter, StoreCatalogApi, http_route_manifest, register_store_catalog_routes  # noqa: E402
from token_payments.contexts.auth.domain import UserRole  # noqa: E402
from token_payments.contexts.store_catalog.adapter import PostgresStoreCatalogRepository  # noqa: E402
from token_payments.contexts.store_catalog.application import StoreCatalogApplicationService  # noqa: E402
from token_payments.contexts.store_catalog.domain import (  # noqa: E402
    ProductStatus,
    ProductVisibility,
    PublicProductId,
    StoreProduct,
)
from token_payments.shared.domain import ProductId  # noqa: E402
from _store_catalog_test_support import (  # noqa: E402
    OWNER_ID,
    OWNER_WALLET,
    PRODUCT_ID,
    STORE_ID,
    FakeStoreCatalogRepository,
    auth,
    decode,
    price,
)


NOW = datetime(2026, 5, 22, 5, 30, tzinfo=UTC)
PUBLIC_PRODUCT_ID = PublicProductId("prd_ledger_mug_001")
PRIVATE_PRODUCT_ID = PublicProductId("prd_private_mug_001")
INACTIVE_PRODUCT_ID = PublicProductId("prd_inactive_mug_1")


def test_public_store_and_product_reads_use_public_ids_and_redact_internal_ids() -> None:
    repository = _seed_catalog()
    router = _router(repository, None)
    public_store_id = repository.stores[STORE_ID].public_store_id

    store_response = router.handle("GET", f"/stores/{public_store_id}", headers={"X-Request-Id": "req-store"})
    list_response = router.handle(
        "GET",
        f"/stores/{public_store_id}/products",
        query={"limit": "10", "offset": "0", "q": "Ledger"},
        headers={"X-Request-Id": "req-products"},
    )
    detail_response = router.handle(
        "GET",
        f"/stores/{public_store_id}/products/{PUBLIC_PRODUCT_ID}",
        headers={"X-Request-Id": "req-product-detail"},
    )

    store_payload = decode(store_response.body)["store"]
    list_payload = decode(list_response.body)
    detail_payload = decode(detail_response.body)["product"]

    assert store_response.status_code == 200
    assert store_payload["publicStoreId"] == str(public_store_id)
    assert store_payload["paymentCapability"]["supportedChainIds"] == [11155111]
    assert store_payload["paymentCapability"]["settlement"]["available"] is True
    assert "storeId" not in store_payload
    assert "ownerUserId" not in store_payload
    assert "storeWallet" not in store_payload

    assert list_response.status_code == 200
    assert [product["publicProductId"] for product in list_payload["products"]] == [str(PUBLIC_PRODUCT_ID)]
    listed_product = list_payload["products"][0]
    assert listed_product["title"] == "Ledger Mug"
    assert listed_product["displayPrice"]["symbol"] == "USDC"
    assert listed_product["availability"]["availableStock"] == 8
    assert listed_product["paymentCapability"]["supportedChainIds"] == [11155111]
    assert list_payload["pagination"] == {"limit": 10, "offset": 0, "nextOffset": None}
    assert "storeId" not in listed_product
    assert "productId" not in listed_product

    assert detail_response.status_code == 200
    assert detail_payload["publicProductId"] == str(PUBLIC_PRODUCT_ID)
    assert detail_payload["attributes"] == {"capacityMl": 350}
    assert detail_payload["availability"]["saleStatus"] == "ACTIVE"
    assert "productId" not in detail_payload
    assert "storeId" not in detail_payload


def test_merchant_product_listing_filters_private_catalog_with_bounded_query_inputs() -> None:
    repository = _seed_catalog()
    router = _router(repository, auth(OWNER_ID, UserRole.CUSTOMER, scopes=("product:read",)))
    public_store_id = repository.stores[STORE_ID].public_store_id

    response = router.handle(
        "GET",
        f"/merchant/stores/{public_store_id}/products",
        query={
            "status": "INACTIVE",
            "visibility": "PRIVATE",
            "category": "accessories",
            "tag": "internal",
            "q": "Private",
            "sort": "-updatedAt",
            "limit": "5",
            "offset": "0",
        },
    )
    invalid_sort = router.handle(
        "GET",
        f"/merchant/stores/{public_store_id}/products",
        query={"sort": "updated_at;drop"},
    )
    unknown_query = router.handle(
        "GET",
        f"/merchant/stores/{public_store_id}/products",
        query={"rawSql": "title"},
    )
    unrelated = _router(repository, auth(OWNER_ID, UserRole.CUSTOMER, scopes=("product:read",))).handle(
        "GET",
        "/merchant/stores/st_missing_store/products",
    )
    unauthenticated = _router(repository, None).handle("GET", f"/merchant/stores/{public_store_id}/products")

    payload = decode(response.body)

    assert response.status_code == 200
    assert [product["publicProductId"] for product in payload["products"]] == [str(PRIVATE_PRODUCT_ID)]
    assert payload["products"][0]["status"] == "INACTIVE"
    assert payload["products"][0]["visibility"] == "PRIVATE"
    assert "productId" not in payload["products"][0]
    assert invalid_sort.status_code == 400
    assert decode(invalid_sort.body)["error"]["code"] == "VALIDATION_ERROR"
    assert unknown_query.status_code == 400
    assert unrelated.status_code == 404
    assert unauthenticated.status_code == 401


def test_postgres_catalog_query_uses_parameter_binding_escape_policy_and_sort_allowlist() -> None:
    connection = FakeCatalogQueryConnection()
    repository = PostgresStoreCatalogRepository(connection)

    repository.list_products_for_store(
        STORE_ID,
        status=ProductStatus.ACTIVE,
        visibility=ProductVisibility.PUBLIC,
        category="accessories",
        tag="wallet-safe",
        query="Ledger%_Mug",
        sort_by="updatedAt",
        sort_direction="desc",
        limit=25,
        offset=50,
    )

    statement = connection.statements[-1]
    sql = statement.sql

    assert "ILIKE %(query)s ESCAPE '\\\\'" in sql
    assert "ORDER BY updated_at DESC" in sql
    assert "LIMIT %(limit)s OFFSET %(offset)s" in sql
    assert "Ledger%_Mug" not in sql
    assert statement.params["query"] == "%Ledger\\%\\_Mug%"
    assert statement.params["limit"] == 25
    assert statement.params["offset"] == 50
    assert "Elasticsearch" not in (ROOT / "app/token_payments/contexts/store_catalog/adapter/postgres.py").read_text(
        encoding="utf-8"
    )


def test_catalog_read_routes_are_documented_and_order_creation_revalidation_boundary_is_explicit() -> None:
    api_spec = (ROOT / "docs/API_SPEC.md").read_text(encoding="utf-8")
    manifest_ids = {route["operationId"] for route in http_route_manifest()}

    assert {
        "listPublicStores",
        "listPublicProducts",
        "getPublicProduct",
        "listMerchantProducts",
        "getMerchantProduct",
    } <= manifest_ids
    assert "server-side current store/product/price/inventory/payment capability" in api_spec
    assert "Elasticsearch" in api_spec and "future scope" in api_spec


def _seed_catalog() -> FakeStoreCatalogRepository:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    store = repository.seed_store(owner_id=OWNER_ID, active=True, chains=(11155111,))
    products = (
        _product(
            public_product_id=PUBLIC_PRODUCT_ID,
            public_store_id=store.public_store_id,
            title="Ledger Mug",
            status=ProductStatus.ACTIVE,
        ),
        _product(
            product_id=ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9108"),
            public_product_id=PRIVATE_PRODUCT_ID,
            public_store_id=store.public_store_id,
            title="Private Ledger Mug",
            status=ProductStatus.INACTIVE,
            visibility=ProductVisibility.PRIVATE,
            tags=("internal",),
        ),
        _product(
            product_id=ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9107"),
            public_product_id=INACTIVE_PRODUCT_ID,
            public_store_id=store.public_store_id,
            title="Inactive Ledger Mug",
            status=ProductStatus.ARCHIVED,
        ),
    )
    for product in products:
        repository.save_product(product)
    repository.inventory[(store.store_id, PRODUCT_ID)] = 8
    return repository


def _router(repository: FakeStoreCatalogRepository, auth_context) -> HttpRouter:
    service = StoreCatalogApplicationService(repository=repository)
    router = HttpRouter(auth_context_factory=lambda _request: auth_context, allow_dev_auth_headers=False)
    register_store_catalog_routes(router, StoreCatalogApi(service))
    return router


def _product(**overrides: Any) -> StoreProduct:
    values = {
        "store_id": STORE_ID,
        "product_id": PRODUCT_ID,
        "public_product_id": PUBLIC_PRODUCT_ID,
        "public_store_id": "st_ledger_cafe_001",
        "title": "Ledger Mug",
        "description": "Ceramic mug",
        "category": "accessories",
        "tags": ("wallet-safe",),
        "media": ("products/ledger-mug.png",),
        "attributes": {"capacityMl": 350},
        "status": ProductStatus.ACTIVE,
        "visibility": ProductVisibility.PUBLIC,
        "price": price(),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return StoreProduct(**values)


@dataclass(frozen=True)
class Statement:
    sql: str
    params: Mapping[str, Any]


class FakeCatalogQueryConnection:
    def __init__(self) -> None:
        self.statements: list[Statement] = []

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> tuple[()]:
        self.statements.append(Statement(sql=sql, params=params or {}))
        return ()

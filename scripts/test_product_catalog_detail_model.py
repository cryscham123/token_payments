from __future__ import annotations

import sys
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

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
    PublicStoreId,
    StoreMembership,
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
    json_body,
    price,
    price_payload,
    FixedIdGenerator,
)


NOW = datetime(2026, 5, 22, 4, 0, tzinfo=UTC)
PUBLIC_PRODUCT_ID = PublicProductId.for_product_id(PRODUCT_ID)


def test_product_catalog_detail_identity_separates_public_and_internal_ids() -> None:
    product = _product(title="Ledger Mug")
    product_fields = {field.name for field in fields(StoreProduct)}

    assert {
        "product_id",
        "public_product_id",
        "store_id",
        "public_store_id",
        "title",
        "description",
        "category",
        "tags",
        "media",
        "attributes",
        "status",
        "visibility",
        "created_at",
        "updated_at",
    } <= product_fields
    assert product.name == "Ledger Mug"
    assert product.public_product_id == PUBLIC_PRODUCT_ID
    assert product.public_product_id != str(product.product_id)
    assert _is_uuid(str(product.product_id))
    assert not _is_uuid(str(product.public_product_id))
    assert not str(product.public_product_id).isdigit()
    assert product.status is ProductStatus.ACTIVE
    assert product.visibility is ProductVisibility.PUBLIC
    assert product.active is True


@pytest.mark.parametrize("public_product_id", [str(PRODUCT_ID), "123456", "Product With Spaces", "prd_\x00bad"])
def test_public_product_id_rejects_internal_uuid_sequential_and_untrusted_values(public_product_id: str) -> None:
    with pytest.raises(ValueError, match="public_product_id|PublicProductId"):
        PublicProductId(public_product_id)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"title": ""},
        {"title": "A\nB"},
        {"title": "A\x00B"},
        {"title": "=SUM(A1:A2)"},
        {"description": "x" * 4001},
        {"category": "@unsafe"},
        {"tags": tuple(f"tag-{index}" for index in range(21))},
        {"tags": ("bad tag!",)},
        {"media": ("ftp://example.com/image.png",)},
        {"media": ("https://example.com/" + "x" * 2050,)},
        {"attributes": {"bad\nkey": "value"}},
        {"attributes": {"nested": {"level1": {"level2": {"level3": {"level4": "too deep"}}}}}},
        {"attributes": {"unsafe": "=csv"}},
    ],
)
def test_product_catalog_fields_are_bounded_untrusted_data(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _product(**kwargs)


def test_product_tags_accept_korean_unicode_tokens() -> None:
    product = _product(tags=("한글태그", "지갑-safe", "nft_굿즈"))

    assert product.tags == ("한글태그", "지갑-safe", "nft_굿즈")


def test_product_write_uses_public_ids_detail_metadata_and_payload_sensitive_idempotency() -> None:
    repository = _seed_owner_store()
    router = _router(
        repository,
        auth(OWNER_ID, UserRole.CUSTOMER, scopes=("product:write",)),
        id_generator=FixedIdGenerator(str(PRODUCT_ID)),
    )
    body = _product_body()

    response = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-detail-001"},
        body=body,
        received_at=NOW,
    )
    conflict = router.handle(
        "POST",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-detail-001"},
        body=json_body(_product_payload(title="Changed")),
        received_at=NOW,
    )

    payload = decode(response.body)
    product = repository.products[(STORE_ID, PRODUCT_ID)]

    assert response.status_code == 201
    assert conflict.status_code == 409
    assert payload["product"]["publicStoreId"] == str(repository.stores[STORE_ID].public_store_id)
    assert payload["product"]["publicProductId"] == str(PUBLIC_PRODUCT_ID)
    assert payload["product"]["title"] == "Ledger Mug"
    assert payload["product"]["titleHtml"] == "Ledger Mug"
    assert payload["product"]["tags"] == ["drinkware", "wallet-safe"]
    assert "productId" not in payload["product"]
    assert "storeId" not in payload["product"]
    assert product.description == "Ceramic mug for hardware wallet desks"
    assert product.category == "accessories"
    assert product.attributes["capacityMl"] == 350
    assert repository.order_products[(STORE_ID, PRODUCT_ID)].title == "Ledger Mug"
    assert repository.store_approval_products[(STORE_ID, PRODUCT_ID)].status is ProductStatus.ACTIVE
    assert repository.inventory[(STORE_ID, PRODUCT_ID)] == 25
    assert repository.audit_records[-1].permission == "product:write"


def test_update_product_detail_uses_public_store_and_product_ids_without_inventory_status_coupling() -> None:
    repository = _seed_owner_store()
    repository.save_product(_product(status=ProductStatus.INACTIVE, visibility=ProductVisibility.PRIVATE))
    router = _router(repository, auth(OWNER_ID, UserRole.CUSTOMER, scopes=("product:write",)))

    response = router.handle(
        "PATCH",
        f"/merchant/stores/{repository.stores[STORE_ID].public_store_id}/products/{PUBLIC_PRODUCT_ID}",
        headers={"Content-Type": "application/json", "Idempotency-Key": "product-detail-update-001"},
        body=json_body(
            {
                "title": "Ledger Mug v2",
                "description": "Updated detail",
                "category": "desk",
                "tags": ["desk"],
                "media": ["products/ledger-mug-v2.png"],
                "attributes": {"capacityMl": 400},
                "status": "ACTIVE",
                "visibility": "PUBLIC",
            }
        ),
        received_at=NOW,
    )

    payload = decode(response.body)
    product = repository.products[(STORE_ID, PRODUCT_ID)]

    assert response.status_code == 200
    assert payload["product"]["publicProductId"] == str(PUBLIC_PRODUCT_ID)
    assert payload["product"]["title"] == "Ledger Mug v2"
    assert product.status is ProductStatus.ACTIVE
    assert product.visibility is ProductVisibility.PUBLIC
    assert repository.inventory == {}
    assert product.status is not product.visibility


def test_product_repository_uses_parameter_binding_json_safe_metadata_and_public_indexes() -> None:
    connection = FakeProductConnection()
    repository = PostgresStoreCatalogRepository(connection)
    product = _product(title="<Ledger & Mug>")

    repository.save_product(product)

    combined_sql = "\n".join(statement.sql for statement in connection.statements)
    schema = (ROOT / "app/postgres/init.d/001-token-payments-schema.sql").read_text(encoding="utf-8")

    assert "INSERT INTO store_catalog_products" in combined_sql
    assert "%(public_product_id)s" in combined_sql
    assert "%(title)s" in combined_sql
    assert "%(attributes)s::jsonb" in combined_sql
    assert product.title not in combined_sql
    assert connection.statements[-1].params["public_product_id"] == str(PUBLIC_PRODUCT_ID)
    assert connection.statements[-1].params["title"] == "<Ledger & Mug>"
    assert connection.statements[-1].params["attributes"].startswith("{")
    assert "public_product_id TEXT NOT NULL" in schema
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_store_catalog_products_public_store_product" in schema
    assert "public_product_id" in (ROOT / "docs/API_SPEC.md").read_text(encoding="utf-8")
    assert {"registerStoreProduct", "updateStoreProduct"} <= {route["operationId"] for route in http_route_manifest()}


def _seed_owner_store() -> FakeStoreCatalogRepository:
    repository = FakeStoreCatalogRepository()
    repository.seed_user(OWNER_ID, OWNER_WALLET, role=UserRole.CUSTOMER)
    repository.seed_store(owner_id=OWNER_ID, active=True)
    return repository


def _router(repository: FakeStoreCatalogRepository, auth_context, id_generator: Any | None = None) -> HttpRouter:
    service = StoreCatalogApplicationService(repository=repository)
    router = HttpRouter(auth_context_factory=lambda _request: auth_context, allow_dev_auth_headers=False)
    register_store_catalog_routes(router, StoreCatalogApi(service, id_generator=id_generator))
    return router


def _product(**overrides: Any) -> StoreProduct:
    values = {
        "store_id": STORE_ID,
        "product_id": PRODUCT_ID,
        "public_product_id": PUBLIC_PRODUCT_ID,
        "public_store_id": PublicStoreId("st_ledger_cafe_001"),
        "title": "Ledger Mug",
        "description": "Ceramic mug for hardware wallet desks",
        "category": "accessories",
        "tags": ("drinkware", "wallet-safe"),
        "media": ("https://cdn.example.test/products/ledger-mug.png", "products/ledger-mug-alt.png"),
        "attributes": {"capacityMl": 350, "dishwasherSafe": True, "materials": ["ceramic"]},
        "status": ProductStatus.ACTIVE,
        "visibility": ProductVisibility.PUBLIC,
        "price": price(),
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return StoreProduct(**values)


def _product_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "title": "Ledger Mug",
        "description": "Ceramic mug for hardware wallet desks",
        "category": "accessories",
        "tags": ["drinkware", "wallet-safe"],
        "media": ["https://cdn.example.test/products/ledger-mug.png"],
        "attributes": {"capacityMl": 350, "dishwasherSafe": True},
        "status": "ACTIVE",
        "visibility": "PUBLIC",
        "price": price_payload(),
        "initialTotalStock": 25,
    }
    payload.update(overrides)
    return payload


def _product_body(**overrides: Any) -> bytes:
    return json_body(_product_payload(**overrides))


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


class FakeProductConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
        self.statements.append(ExecutedStatement(sql=sql, params=dict(params or {})))
        return ()

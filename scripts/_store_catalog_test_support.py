from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiAuthContext, HttpRouter, StoreCatalogApi, register_store_catalog_routes  # noqa: E402
from token_payments.contexts.auth.domain import User, UserRole  # noqa: E402
from token_payments.contexts.store_catalog.application import (  # noqa: E402
    CatalogAuditRecord,
    CatalogIdempotencyRecord,
    StoreCatalogApplicationService,
)
from token_payments.contexts.store_catalog.domain import (  # noqa: E402
    ProductStatus,
    ProductVisibility,
    PublicProductId,
    PublicStoreId,
    StoreMembership,
    StoreMembershipRole,
    StoreProduct,
    StoreProfile,
)
from token_payments.shared.domain import Crypto, ProductId, StoreId, UserId, WalletAddress  # noqa: E402


NOW = datetime(2026, 5, 20, 1, 0, tzinfo=UTC)
ADMIN_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9001")
OWNER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9002")
CUSTOMER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9003")
OTHER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9004")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9005")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9006")
PUBLIC_PRODUCT_ID = PublicProductId("prd_ledger_mug_001")
OWNER_WALLET = WalletAddress("0x1111111111111111111111111111111111111111")
CUSTOMER_WALLET = WalletAddress("0x2222222222222222222222222222222222222222")
OTHER_WALLET = WalletAddress("0x3333333333333333333333333333333333333333")
STORE_WALLET = WalletAddress("0x4444444444444444444444444444444444444444")
TOKEN_ADDRESS = WalletAddress("0x5555555555555555555555555555555555555555")


def price(*, chain_id: int = 11155111) -> Crypto:
    return Crypto(
        amount=Decimal("12.50"),
        symbol="USDC",
        chain_id=chain_id,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )


def price_payload(*, chain_id: int = 11155111) -> dict[str, Any]:
    value = price(chain_id=chain_id)
    return {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address),
        "decimals": value.decimals,
    }


def json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def decode(body: bytes) -> dict[str, Any]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


def auth(user_id: UserId, role: UserRole, *, scopes: tuple[str, ...] | None = None) -> ApiAuthContext:
    if scopes is None:
        scopes = (
            ("admin:provision", "rbac:manage", "product:write:any")
            if role is UserRole.ADMIN
            else ("product:write", "inventory:read", "inventory:write")
        )
    return ApiAuthContext(user_id=str(user_id), role=role.value, scopes=scopes, session_id="session-cookie")


def catalog_router(
    repository: "FakeStoreCatalogRepository",
    auth_context: ApiAuthContext | None,
    id_generator: Any | None = None,
) -> HttpRouter:
    if id_generator is None:
        id_generator = FixedIdGenerator(str(STORE_ID))
    service = StoreCatalogApplicationService(repository=repository, user_id_generator=FixedIdGenerator(str(OWNER_ID)))
    router = HttpRouter(auth_context_factory=lambda _request: auth_context, allow_dev_auth_headers=False)
    register_store_catalog_routes(router, StoreCatalogApi(service, id_generator=id_generator))
    return router


class FixedIdGenerator:
    def __init__(self, value: str) -> None:
        self.value = value

    def new_id(self) -> str:
        return self.value


class FakeStoreCatalogRepository:
    def __init__(self) -> None:
        self.idempotency_records: dict[tuple[str, str], CatalogIdempotencyRecord] = {}
        self.users_by_id: dict[UserId, User] = {}
        self.users_by_wallet: dict[WalletAddress, User] = {}
        self.stores: dict[StoreId, StoreProfile] = {}
        self.memberships: dict[tuple[StoreId, UserId], StoreMembership] = {}
        self.products: dict[tuple[StoreId, ProductId], StoreProduct] = {}
        self.order_stores: dict[StoreId, StoreProfile] = {}
        self.store_approval_stores: dict[StoreId, StoreProfile] = {}
        self.order_products: dict[tuple[StoreId, ProductId], StoreProduct] = {}
        self.store_approval_products: dict[tuple[StoreId, ProductId], StoreProduct] = {}
        self.inventory: dict[tuple[StoreId, ProductId], int] = {}
        self.audit_records: list[CatalogAuditRecord] = []

    def seed_user(
        self,
        user_id: UserId,
        wallet: WalletAddress,
        *,
        role: UserRole = UserRole.CUSTOMER,
    ) -> User:
        user = User.register_by_wallet(user_id, wallet, role=role)
        self.users_by_id[user.user_id] = user
        self.users_by_wallet[user.primary_wallet] = user
        return user

    def seed_store(self, *, owner_id: UserId = OWNER_ID, active: bool = True, chains: tuple[int, ...] = (11155111,)) -> StoreProfile:
        store = StoreProfile(
            store_id=STORE_ID,
            owner_user_id=owner_id,
            active=active,
            store_wallet=STORE_WALLET,
            supported_chain_ids=chains,
        )
        self.stores[STORE_ID] = store
        self.order_stores[STORE_ID] = store
        self.store_approval_stores[STORE_ID] = store
        self.memberships[(STORE_ID, owner_id)] = StoreMembership.owner(STORE_ID, owner_id)
        return store

    def get_idempotency_record(self, handler: str, idempotency_key: str) -> CatalogIdempotencyRecord | None:
        return self.idempotency_records.get((handler, idempotency_key))

    def save_idempotency_record(self, record: CatalogIdempotencyRecord) -> None:
        self.idempotency_records[(record.handler, record.idempotency_key)] = record

    def get_user_by_wallet(self, wallet: WalletAddress) -> User | None:
        return self.users_by_wallet.get(wallet)

    def get_user_by_id(self, user_id: UserId) -> User | None:
        return self.users_by_id.get(user_id)

    def save_user(self, user: User) -> None:
        if user.primary_wallet in self.users_by_wallet:
            return
        self.users_by_id[user.user_id] = user
        self.users_by_wallet[user.primary_wallet] = user

    def get_store(self, store_id: StoreId) -> StoreProfile | None:
        return self.stores.get(store_id)

    def get_store_by_public_id(self, public_store_id) -> StoreProfile | None:
        return next(
            (store for store in self.stores.values() if str(store.public_store_id) == str(public_store_id)),
            None,
        )

    def list_stores_for_member(self, user_id: UserId) -> tuple[StoreProfile, ...]:
        store_ids = {
            store_id
            for (store_id, member_user_id), membership in self.memberships.items()
            if member_user_id == user_id and membership.active
        }
        return tuple(store for store_id, store in self.stores.items() if store_id in store_ids)

    def list_public_stores(self, *, limit: int, offset: int) -> tuple[StoreProfile, ...]:
        stores = tuple(store for store in self.stores.values() if store.active)
        return tuple(sorted(stores, key=lambda store: str(store.public_store_id))[offset : offset + limit])

    def save_store(self, store: StoreProfile) -> None:
        self.stores[store.store_id] = store

    def save_order_store_projection(self, store: StoreProfile) -> None:
        self.order_stores[store.store_id] = store

    def save_store_approval_store_projection(self, store: StoreProfile) -> None:
        self.store_approval_stores[store.store_id] = store

    def get_membership(self, store_id: StoreId, user_id: UserId) -> StoreMembership | None:
        return self.memberships.get((store_id, user_id))

    def save_membership(self, membership: StoreMembership) -> None:
        self.memberships[(membership.store_id, membership.user_id)] = membership

    def get_store_role(self, store_id: StoreId, user_id: UserId) -> StoreMembershipRole | None:
        membership = self.memberships.get((store_id, user_id))
        if membership is None or not membership.active:
            return None
        return membership.role

    def get_product(self, store_id: StoreId, product_id: ProductId) -> StoreProduct | None:
        return self.products.get((store_id, product_id))

    def get_product_by_public_id(self, store_id: StoreId, public_product_id) -> StoreProduct | None:
        return next(
            (
                product
                for (stored_store_id, _product_id), product in self.products.items()
                if stored_store_id == store_id and str(product.public_product_id) == str(public_product_id)
            ),
            None,
        )

    def list_products_for_store(
        self,
        store_id: StoreId,
        *,
        status: ProductStatus | None,
        visibility: ProductVisibility | None,
        category: str | None,
        tag: str | None,
        query: str | None,
        sort_by: str,
        sort_direction: str,
        limit: int,
        offset: int,
    ) -> tuple[StoreProduct, ...]:
        products = tuple(
            product for (stored_store_id, _product_id), product in self.products.items() if stored_store_id == store_id
        )
        if status is not None:
            products = tuple(product for product in products if product.status is status)
        if visibility is not None:
            products = tuple(product for product in products if product.visibility is visibility)
        if category is not None:
            products = tuple(product for product in products if product.category == category)
        if tag is not None:
            products = tuple(product for product in products if tag in product.tags)
        if query is not None:
            lowered = query.lower()
            products = tuple(
                product
                for product in products
                if lowered in product.title.lower()
                or (product.description is not None and lowered in product.description.lower())
            )
        reverse = sort_direction == "desc"
        key_map = {
            "title": lambda product: product.title.lower(),
            "createdAt": lambda product: product.created_at,
            "updatedAt": lambda product: product.updated_at,
            "price": lambda product: product.price.amount,
        }
        products = tuple(sorted(products, key=key_map[sort_by], reverse=reverse))
        return products[offset : offset + limit]

    def get_product_availability(self, store_id: StoreId, product_id: ProductId) -> Mapping[str, Any] | None:
        available_stock = self.inventory.get((store_id, product_id))
        if available_stock is None:
            return None
        return {
            "availableStock": available_stock,
            "saleStatus": "ACTIVE" if available_stock > 0 else "UNAVAILABLE",
        }

    def save_product(self, product: StoreProduct) -> None:
        self.products[(product.store_id, product.product_id)] = product

    def save_order_product_projection(self, product: StoreProduct) -> None:
        self.order_products[(product.store_id, product.product_id)] = product

    def save_store_approval_product_projection(self, product: StoreProduct) -> None:
        self.store_approval_products[(product.store_id, product.product_id)] = product

    def save_inventory_projection(self, product: StoreProduct, initial_total_stock: int) -> None:
        self.inventory.setdefault((product.store_id, product.product_id), initial_total_stock)

    def record_audit(self, record: CatalogAuditRecord) -> str | None:
        self.audit_records.append(record)
        return f"audit-{len(self.audit_records)}"

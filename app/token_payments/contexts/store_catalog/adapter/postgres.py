"""PostgreSQL repository for canonical store catalog provisioning."""

from __future__ import annotations

import json
from typing import Any, Mapping

from token_payments.contexts.auth.domain import User, UserRole
from token_payments.contexts.store_catalog.application import CatalogAuditRecord, CatalogIdempotencyRecord
from token_payments.contexts.store_catalog.domain import StoreMembership, StoreMembershipRole, StoreProduct, StoreProfile
from token_payments.shared.adapter.postgres import PostgresConnection
from token_payments.shared.domain import Crypto, ProductId, StoreId, UserId, WalletAddress


SELECT_USER_BY_ID_SQL = """
SELECT user_id, wallet_address, role, active, last_login_at
FROM auth_users
WHERE user_id = %(user_id)s
"""

SELECT_USER_BY_WALLET_SQL = """
SELECT user_id, wallet_address, role, active, last_login_at
FROM auth_users
WHERE wallet_address = %(wallet_address)s
"""

INSERT_USER_SQL = """
INSERT INTO auth_users (
    user_id,
    wallet_address,
    role,
    active,
    last_login_at
) VALUES (
    %(user_id)s,
    %(wallet_address)s,
    %(role)s,
    %(active)s,
    %(last_login_at)s
)
ON CONFLICT (wallet_address) DO NOTHING
"""

SELECT_IDEMPOTENCY_SQL = """
SELECT handler, idempotency_key, payload_hash, response_payload, recorded_at
FROM store_catalog_idempotency
WHERE handler = %(handler)s
  AND idempotency_key = %(idempotency_key)s
"""

INSERT_IDEMPOTENCY_SQL = """
INSERT INTO store_catalog_idempotency (
    handler,
    idempotency_key,
    payload_hash,
    response_payload,
    recorded_at
) VALUES (
    %(handler)s,
    %(idempotency_key)s,
    %(payload_hash)s,
    %(response_payload)s::jsonb,
    %(recorded_at)s
)
ON CONFLICT (handler, idempotency_key) DO NOTHING
"""

SELECT_STORE_SQL = """
SELECT store_id, owner_user_id, active, store_wallet_address, supported_chain_ids
FROM store_catalog_stores
WHERE store_id = %(store_id)s
"""

UPSERT_STORE_SQL = """
INSERT INTO store_catalog_stores (
    store_id,
    owner_user_id,
    active,
    store_wallet_address,
    supported_chain_ids
) VALUES (
    %(store_id)s,
    %(owner_user_id)s,
    %(active)s,
    %(store_wallet_address)s,
    %(supported_chain_ids)s::jsonb
)
ON CONFLICT (store_id) DO UPDATE SET
    owner_user_id = EXCLUDED.owner_user_id,
    active = EXCLUDED.active,
    store_wallet_address = EXCLUDED.store_wallet_address,
    supported_chain_ids = EXCLUDED.supported_chain_ids,
    updated_at = now()
"""

UPSERT_ORDER_STORE_SQL = """
INSERT INTO order_stores (
    store_id,
    owner_user_id,
    active,
    store_wallet_address,
    supported_chain_ids
) VALUES (
    %(store_id)s,
    %(owner_user_id)s,
    %(active)s,
    %(store_wallet_address)s,
    %(supported_chain_ids)s::jsonb
)
ON CONFLICT (store_id) DO UPDATE SET
    owner_user_id = EXCLUDED.owner_user_id,
    active = EXCLUDED.active,
    store_wallet_address = EXCLUDED.store_wallet_address,
    supported_chain_ids = EXCLUDED.supported_chain_ids,
    updated_at = now()
"""

UPSERT_APPROVAL_STORE_SQL = """
INSERT INTO store_approval_stores (
    store_id,
    owner_user_id,
    active
) VALUES (
    %(store_id)s,
    %(owner_user_id)s,
    %(active)s
)
ON CONFLICT (store_id) DO UPDATE SET
    owner_user_id = EXCLUDED.owner_user_id,
    active = EXCLUDED.active,
    updated_at = now()
"""

SELECT_MEMBERSHIP_SQL = """
SELECT store_id, user_id, role, active
FROM store_catalog_store_memberships
WHERE store_id = %(store_id)s
  AND user_id = %(user_id)s
"""

UPSERT_MEMBERSHIP_SQL = """
INSERT INTO store_catalog_store_memberships (
    store_id,
    user_id,
    role,
    active
) VALUES (
    %(store_id)s,
    %(user_id)s,
    %(role)s,
    %(active)s
)
ON CONFLICT (store_id, user_id) DO UPDATE SET
    role = EXCLUDED.role,
    active = EXCLUDED.active,
    updated_at = now()
"""

SELECT_STORE_ROLE_SQL = """
SELECT role
FROM store_catalog_store_memberships
WHERE store_id = %(store_id)s
  AND user_id = %(user_id)s
  AND active = true
"""

SELECT_PRODUCT_SQL = """
SELECT
    store_id,
    product_id,
    name,
    price_numeric,
    price_symbol,
    price_chain_id,
    price_token_address,
    price_decimals,
    active
FROM store_catalog_products
WHERE store_id = %(store_id)s
  AND product_id = %(product_id)s
"""

UPSERT_PRODUCT_SQL = """
INSERT INTO store_catalog_products (
    store_id,
    product_id,
    name,
    price_numeric,
    price_symbol,
    price_chain_id,
    price_token_address,
    price_decimals,
    active
) VALUES (
    %(store_id)s,
    %(product_id)s,
    %(name)s,
    %(price_numeric)s,
    %(price_symbol)s,
    %(price_chain_id)s,
    %(price_token_address)s,
    %(price_decimals)s,
    %(active)s
)
ON CONFLICT (store_id, product_id) DO UPDATE SET
    name = EXCLUDED.name,
    price_numeric = EXCLUDED.price_numeric,
    price_symbol = EXCLUDED.price_symbol,
    price_chain_id = EXCLUDED.price_chain_id,
    price_token_address = EXCLUDED.price_token_address,
    price_decimals = EXCLUDED.price_decimals,
    active = EXCLUDED.active,
    updated_at = now()
"""

UPSERT_ORDER_PRODUCT_SQL = """
INSERT INTO order_store_products (
    store_id,
    product_id,
    name,
    price_numeric,
    price_symbol,
    price_chain_id,
    price_token_address,
    price_decimals
) VALUES (
    %(store_id)s,
    %(product_id)s,
    %(name)s,
    %(price_numeric)s,
    %(price_symbol)s,
    %(price_chain_id)s,
    %(price_token_address)s,
    %(price_decimals)s
)
ON CONFLICT (store_id, product_id) DO UPDATE SET
    name = EXCLUDED.name,
    price_numeric = EXCLUDED.price_numeric,
    price_symbol = EXCLUDED.price_symbol,
    price_chain_id = EXCLUDED.price_chain_id,
    price_token_address = EXCLUDED.price_token_address,
    price_decimals = EXCLUDED.price_decimals,
    updated_at = now()
"""

UPSERT_APPROVAL_PRODUCT_SQL = """
INSERT INTO store_approval_products (
    store_id,
    product_id,
    name,
    price_numeric,
    price_symbol,
    price_chain_id,
    price_token_address,
    price_decimals,
    available
) VALUES (
    %(store_id)s,
    %(product_id)s,
    %(name)s,
    %(price_numeric)s,
    %(price_symbol)s,
    %(price_chain_id)s,
    %(price_token_address)s,
    %(price_decimals)s,
    %(available)s
)
ON CONFLICT (store_id, product_id) DO UPDATE SET
    name = EXCLUDED.name,
    price_numeric = EXCLUDED.price_numeric,
    price_symbol = EXCLUDED.price_symbol,
    price_chain_id = EXCLUDED.price_chain_id,
    price_token_address = EXCLUDED.price_token_address,
    price_decimals = EXCLUDED.price_decimals,
    available = EXCLUDED.available,
    updated_at = now()
"""

INSERT_INITIAL_INVENTORY_SQL = """
INSERT INTO product_inventory (
    product_id,
    store_id,
    available_stock,
    reserved_stock,
    total_stock,
    sale_status
) VALUES (
    %(product_id)s,
    %(store_id)s,
    %(available_stock)s,
    0,
    %(total_stock)s,
    'ACTIVE'
)
ON CONFLICT (product_id, store_id) DO NOTHING
"""

INSERT_AUDIT_SQL = """
INSERT INTO store_catalog_audit_log (
    actor_user_id,
    action,
    store_id,
    product_id,
    target_user_id,
    request_id,
    idempotency_key,
    before_state,
    after_state,
    recorded_at,
    group_id,
    permission,
    resource_type,
    resource_id
) VALUES (
    %(actor_user_id)s,
    %(action)s,
    %(store_id)s,
    %(product_id)s,
    %(target_user_id)s,
    %(request_id)s,
    %(idempotency_key)s,
    %(before_state)s::jsonb,
    %(after_state)s::jsonb,
    %(recorded_at)s,
    %(group_id)s,
    %(permission)s,
    %(resource_type)s,
    %(resource_id)s
)
ON CONFLICT (idempotency_key, action) DO NOTHING
RETURNING audit_id
"""


class PostgresStoreCatalogRepository:
    """Persists canonical store catalog records and write-through projections."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get_idempotency_record(self, handler: str, idempotency_key: str) -> CatalogIdempotencyRecord | None:
        row = _fetch_one(
            self._connection.execute(
                SELECT_IDEMPOTENCY_SQL,
                {"handler": handler, "idempotency_key": idempotency_key},
            )
        )
        return _row_to_idempotency(row) if row is not None else None

    def save_idempotency_record(self, record: CatalogIdempotencyRecord) -> None:
        self._connection.execute(
            INSERT_IDEMPOTENCY_SQL,
            {
                "handler": record.handler,
                "idempotency_key": record.idempotency_key,
                "payload_hash": record.payload_hash,
                "response_payload": json.dumps(dict(record.response_payload)),
                "recorded_at": record.recorded_at,
            },
        )

    def get_user_by_wallet(self, wallet: WalletAddress) -> User | None:
        row = _fetch_one(
            self._connection.execute(SELECT_USER_BY_WALLET_SQL, {"wallet_address": str(wallet)})
        )
        return _row_to_user(row) if row is not None else None

    def get_user_by_id(self, user_id: UserId) -> User | None:
        row = _fetch_one(self._connection.execute(SELECT_USER_BY_ID_SQL, {"user_id": str(user_id)}))
        return _row_to_user(row) if row is not None else None

    def save_user(self, user: User) -> None:
        self._connection.execute(
            INSERT_USER_SQL,
            {
                "user_id": str(user.user_id),
                "wallet_address": str(user.primary_wallet),
                "role": UserRole.CUSTOMER.value,
                "active": user.active,
                "last_login_at": user.last_login_at,
            },
        )

    def get_store(self, store_id: StoreId) -> StoreProfile | None:
        row = _fetch_one(self._connection.execute(SELECT_STORE_SQL, {"store_id": str(store_id)}))
        return _row_to_store(row) if row is not None else None

    def save_store(self, store: StoreProfile) -> None:
        self._connection.execute(UPSERT_STORE_SQL, _store_params(store))

    def save_order_store_projection(self, store: StoreProfile) -> None:
        self._connection.execute(UPSERT_ORDER_STORE_SQL, _store_params(store))

    def save_store_approval_store_projection(self, store: StoreProfile) -> None:
        self._connection.execute(UPSERT_APPROVAL_STORE_SQL, _store_params(store))

    def get_membership(self, store_id: StoreId, user_id: UserId) -> StoreMembership | None:
        row = _fetch_one(
            self._connection.execute(
                SELECT_MEMBERSHIP_SQL,
                {"store_id": str(store_id), "user_id": str(user_id)},
            )
        )
        return _row_to_membership(row) if row is not None else None

    def save_membership(self, membership: StoreMembership) -> None:
        self._connection.execute(
            UPSERT_MEMBERSHIP_SQL,
            {
                "store_id": str(membership.store_id),
                "user_id": str(membership.user_id),
                "role": membership.role.value,
                "active": membership.active,
            },
        )

    def get_store_role(self, store_id: StoreId, user_id: UserId) -> StoreMembershipRole | None:
        row = _fetch_one(
            self._connection.execute(
                SELECT_STORE_ROLE_SQL,
                {"store_id": str(store_id), "user_id": str(user_id)},
            )
        )
        if row is None:
            return None
        return StoreMembershipRole(_row_value(row, "role"))

    def get_product(self, store_id: StoreId, product_id: ProductId) -> StoreProduct | None:
        row = _fetch_one(
            self._connection.execute(
                SELECT_PRODUCT_SQL,
                {"store_id": str(store_id), "product_id": str(product_id)},
            )
        )
        return _row_to_product(row) if row is not None else None

    def save_product(self, product: StoreProduct) -> None:
        self._connection.execute(UPSERT_PRODUCT_SQL, _product_params(product))

    def save_order_product_projection(self, product: StoreProduct) -> None:
        self._connection.execute(UPSERT_ORDER_PRODUCT_SQL, _product_params(product))

    def save_store_approval_product_projection(self, product: StoreProduct) -> None:
        params = _product_params(product)
        params["available"] = product.active
        self._connection.execute(UPSERT_APPROVAL_PRODUCT_SQL, params)

    def save_inventory_projection(self, product: StoreProduct, initial_total_stock: int) -> None:
        self._connection.execute(
            INSERT_INITIAL_INVENTORY_SQL,
            {
                "product_id": str(product.product_id),
                "store_id": str(product.store_id),
                "available_stock": initial_total_stock,
                "total_stock": initial_total_stock,
            },
        )

    def record_audit(self, record: CatalogAuditRecord) -> str | None:
        row = _fetch_one(
            self._connection.execute(
                INSERT_AUDIT_SQL,
                {
                    "actor_user_id": str(record.actor_user_id),
                    "action": record.action,
                    "store_id": str(record.store_id) if record.store_id is not None else None,
                    "product_id": str(record.product_id) if record.product_id is not None else None,
                    "target_user_id": str(record.target_user_id) if record.target_user_id is not None else None,
                    "request_id": record.request_id,
                    "idempotency_key": record.idempotency_key,
                    "before_state": json.dumps(dict(record.before)),
                    "after_state": json.dumps(dict(record.after)),
                    "recorded_at": record.recorded_at,
                    "group_id": record.group_id,
                    "permission": record.permission,
                    "resource_type": record.resource_type,
                    "resource_id": record.resource_id,
                },
            )
        )
        return str(_row_value(row, "audit_id")) if row is not None else None


def _row_to_user(row: Mapping[str, Any] | object) -> User:
    return User(
        user_id=UserId(_row_value(row, "user_id")),
        primary_wallet=WalletAddress(str(_row_value(row, "wallet_address"))),
        role=UserRole(_row_value(row, "role")),
        active=bool(_row_value(row, "active")),
        last_login_at=_optional_row_value(row, "last_login_at"),
    )


def _row_to_idempotency(row: Mapping[str, Any] | object) -> CatalogIdempotencyRecord:
    response_payload = _row_value(row, "response_payload")
    if isinstance(response_payload, str):
        try:
            response_payload = json.loads(response_payload)
        except json.JSONDecodeError as exc:
            raise ValueError("store_catalog_idempotency response_payload is not a valid JSON string") from exc
    return CatalogIdempotencyRecord(
        handler=str(_row_value(row, "handler")),
        idempotency_key=str(_row_value(row, "idempotency_key")),
        payload_hash=str(_row_value(row, "payload_hash")),
        response_payload=dict(response_payload),
        recorded_at=_row_value(row, "recorded_at"),
    )


def _row_to_store(row: Mapping[str, Any] | object) -> StoreProfile:
    return StoreProfile(
        store_id=StoreId(_row_value(row, "store_id")),
        owner_user_id=UserId(_row_value(row, "owner_user_id")),
        active=bool(_row_value(row, "active")),
        store_wallet=WalletAddress(str(_row_value(row, "store_wallet_address"))),
        supported_chain_ids=_chain_ids(_row_value(row, "supported_chain_ids")),
    )


def _row_to_membership(row: Mapping[str, Any] | object) -> StoreMembership:
    return StoreMembership(
        store_id=StoreId(_row_value(row, "store_id")),
        user_id=UserId(_row_value(row, "user_id")),
        role=StoreMembershipRole(_row_value(row, "role")),
        active=bool(_row_value(row, "active")),
    )


def _row_to_product(row: Mapping[str, Any] | object) -> StoreProduct:
    return StoreProduct(
        store_id=StoreId(_row_value(row, "store_id")),
        product_id=ProductId(_row_value(row, "product_id")),
        name=str(_row_value(row, "name")),
        price=Crypto(
            amount=_row_value(row, "price_numeric"),
            symbol=str(_row_value(row, "price_symbol")),
            chain_id=int(_row_value(row, "price_chain_id")),
            token_address=_optional_row_value(row, "price_token_address"),
            decimals=int(_row_value(row, "price_decimals")),
        ),
        active=bool(_row_value(row, "active")),
    )


def _store_params(store: StoreProfile) -> dict[str, Any]:
    return {
        "store_id": str(store.store_id),
        "owner_user_id": str(store.owner_user_id),
        "active": store.active,
        "store_wallet_address": str(store.store_wallet),
        "supported_chain_ids": json.dumps(list(store.supported_chain_ids)),
    }


def _product_params(product: StoreProduct) -> dict[str, Any]:
    return {
        "store_id": str(product.store_id),
        "product_id": str(product.product_id),
        "name": product.name,
        "price_numeric": product.price.amount,
        "price_symbol": product.price.symbol,
        "price_chain_id": product.price.chain_id,
        "price_token_address": str(product.price.token_address) if product.price.token_address is not None else None,
        "price_decimals": product.price.decimals,
        "active": product.active,
    }


def _chain_ids(value: Any) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("supported_chain_ids is not a valid JSON string") from exc
    if isinstance(value, list | tuple):
        return tuple(int(item) for item in value)
    raise ValueError("supported_chain_ids must be a sequence")


def _fetch_one(result: Any) -> Any:
    if result is None:
        return None
    fetchone = getattr(result, "fetchone", None)
    if callable(fetchone):
        return fetchone()
    iterator = iter(result)
    return next(iterator, None)


def _row_value(row: Mapping[str, Any] | object, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return getattr(row, key)


def _optional_row_value(row: Mapping[str, Any] | object, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)

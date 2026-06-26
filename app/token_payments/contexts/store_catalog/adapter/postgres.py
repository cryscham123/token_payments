"""PostgreSQL repository for canonical store catalog provisioning."""

from __future__ import annotations

import json
from typing import Any, Mapping

from token_payments.contexts.auth.domain import Group, GroupId, GroupType, User, UserRole
from token_payments.contexts.store_catalog.application import (
    CatalogAuditRecord,
    CatalogIdempotencyRecord,
    ProductAssetRecord,
)
from token_payments.contexts.store_catalog.domain import (
    ProductOption,
    ProductOptionValue,
    ProductStatus,
    ProductVariant,
    ProductVisibility,
    PublicProductId,
    PublicStoreId,
    PublicVariantId,
    StoreMembership,
    StoreMembershipRole,
    StorePaymentSettings,
    StoreProduct,
    StoreProfile,
    StoreStatus,
)
from token_payments.shared.adapter.postgres import PostgresConnection
from token_payments.shared.adapter.postgres import PostgresOutboxMessageRepository
from token_payments.shared.domain import (
    Money,
    OutboxMessage,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
    default_public_variant_id,
)


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
SELECT
    store_id,
    public_store_id,
    owner_user_id,
    group_id,
    display_name,
    description,
    status,
    support_email,
    support_email_public,
    business_registration_label,
    store_wallet_address,
    supported_chain_ids,
    supported_payment_asset_ids,
    created_at,
    updated_at
FROM store_catalog_stores
WHERE store_id = %(store_id)s
"""

SELECT_STORE_BY_PUBLIC_ID_SQL = """
SELECT
    store_id,
    public_store_id,
    owner_user_id,
    group_id,
    display_name,
    description,
    status,
    support_email,
    support_email_public,
    business_registration_label,
    store_wallet_address,
    supported_chain_ids,
    supported_payment_asset_ids,
    created_at,
    updated_at
FROM store_catalog_stores
WHERE public_store_id = %(public_store_id)s
"""

SELECT_STORE_BY_DISPLAY_NAME_SQL = """
SELECT
    store_id,
    public_store_id,
    owner_user_id,
    group_id,
    display_name,
    description,
    status,
    support_email,
    support_email_public,
    business_registration_label,
    store_wallet_address,
    supported_chain_ids,
    supported_payment_asset_ids,
    created_at,
    updated_at
FROM store_catalog_stores
WHERE lower(display_name) = lower(%(display_name)s)
LIMIT 1
"""

SELECT_STORES_FOR_MEMBER_SQL = """
SELECT
    s.store_id,
    s.public_store_id,
    s.owner_user_id,
    s.group_id,
    s.display_name,
    s.description,
    s.status,
    s.support_email,
    s.support_email_public,
    s.business_registration_label,
    s.store_wallet_address,
    s.supported_chain_ids,
    s.supported_payment_asset_ids,
    s.created_at,
    s.updated_at
FROM store_catalog_stores s
JOIN store_catalog_store_memberships m ON m.store_id = s.store_id
WHERE m.user_id = %(user_id)s
  AND m.active = true
ORDER BY s.display_name ASC, s.public_store_id ASC
"""

SELECT_ALL_PUBLIC_PRODUCTS_SQL = """
SELECT
    p.store_id,
    p.product_id,
    p.public_product_id,
    p.public_store_id,
    p.title,
    p.description,
    p.category,
    p.tags,
    p.media,
    p.attributes,
    p.status,
    p.visibility,
    p.price_amount,
    p.price_currency,
    p.active,
    p.created_at,
    p.updated_at
FROM store_catalog_products p
JOIN store_catalog_stores s ON s.store_id = p.store_id
WHERE p.status = 'ACTIVE'
  AND p.visibility = 'PUBLIC'
  AND p.active = true
  AND s.status = 'ACTIVE'
  AND s.active = true
"""

SELECT_PUBLIC_STORES_SQL = """
SELECT
    store_id,
    public_store_id,
    owner_user_id,
    group_id,
    display_name,
    description,
    status,
    support_email,
    support_email_public,
    business_registration_label,
    store_wallet_address,
    supported_chain_ids,
    supported_payment_asset_ids,
    created_at,
    updated_at
FROM store_catalog_stores
WHERE status = 'ACTIVE'
  AND active = true
ORDER BY public_store_id ASC
LIMIT %(limit)s OFFSET %(offset)s
"""

SELECT_MERCHANT_GROUP_FOR_STORE_SQL = """
SELECT group_id, group_type, name, active, resource_type, resource_id
FROM auth_groups
WHERE group_type = 'MERCHANT'
  AND resource_type = 'store'
  AND resource_id = %(store_id)s
ORDER BY created_at ASC, group_id ASC
LIMIT 1
"""

INSERT_MERCHANT_GROUP_SQL = """
INSERT INTO auth_groups (
    group_id,
    group_type,
    name,
    resource_type,
    resource_id,
    active
) VALUES (
    %(group_id)s,
    'MERCHANT',
    %(name)s,
    'store',
    %(store_id)s,
    true
)
ON CONFLICT (group_id) DO UPDATE SET
    name = EXCLUDED.name,
    resource_type = EXCLUDED.resource_type,
    resource_id = EXCLUDED.resource_id,
    active = true,
    updated_at = now()
"""

UPSERT_GROUP_MEMBERSHIP_SQL = """
INSERT INTO auth_group_memberships (
    group_id,
    user_id,
    role_id,
    active
) VALUES (
    %(group_id)s,
    %(user_id)s,
    %(role_id)s,
    %(active)s
)
ON CONFLICT (group_id, user_id) DO UPDATE SET
    role_id = EXCLUDED.role_id,
    active = EXCLUDED.active,
    updated_at = now()
"""

UPSERT_STORE_SQL = """
INSERT INTO store_catalog_stores (
    store_id,
    public_store_id,
    owner_user_id,
    group_id,
    display_name,
    description,
    status,
    support_email,
    support_email_public,
    business_registration_label,
    active,
    store_wallet_address,
    supported_chain_ids,
    supported_payment_asset_ids
) VALUES (
    %(store_id)s,
    %(public_store_id)s,
    %(owner_user_id)s,
    %(group_id)s,
    %(display_name)s,
    %(description)s,
    %(status)s,
    %(support_email)s,
    %(support_email_public)s,
    %(business_registration_label)s,
    %(active)s,
    %(store_wallet_address)s,
    %(supported_chain_ids)s::jsonb,
    %(supported_payment_asset_ids)s::jsonb
)
ON CONFLICT (store_id) DO UPDATE SET
    public_store_id = store_catalog_stores.public_store_id,
    owner_user_id = EXCLUDED.owner_user_id,
    group_id = COALESCE(EXCLUDED.group_id, store_catalog_stores.group_id),
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    status = EXCLUDED.status,
    support_email = EXCLUDED.support_email,
    support_email_public = EXCLUDED.support_email_public,
    business_registration_label = EXCLUDED.business_registration_label,
    active = EXCLUDED.active,
    store_wallet_address = EXCLUDED.store_wallet_address,
    supported_chain_ids = EXCLUDED.supported_chain_ids,
    supported_payment_asset_ids = EXCLUDED.supported_payment_asset_ids,
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
    public_product_id,
    public_store_id,
    title,
    name,
    description,
    category,
    tags,
    media,
    attributes,
    status,
    visibility,
    price_amount,
    price_currency,
    active,
    created_at,
    updated_at
FROM store_catalog_products
WHERE store_id = %(store_id)s
  AND product_id = %(product_id)s
"""

SELECT_PRODUCT_BY_PUBLIC_ID_SQL = """
SELECT
    store_id,
    product_id,
    public_product_id,
    public_store_id,
    title,
    description,
    category,
    tags,
    media,
    attributes,
    status,
    visibility,
    price_amount,
    price_currency,
    active,
    created_at,
    updated_at
FROM store_catalog_products
WHERE store_id = %(store_id)s
  AND public_product_id = %(public_product_id)s
"""

# Product-level availability is the sum of its variant inventory rows
# (stock is tracked per variant; option-less products use a default variant).
SELECT_PRODUCT_AVAILABILITY_SQL = """
SELECT
    COALESCE(SUM(piv.available_stock), 0) AS available_stock,
    COALESCE(SUM(piv.total_stock), 0) AS total_stock,
    pi.sale_status AS sale_status
FROM product_inventory pi
LEFT JOIN product_variant_inventory piv
  ON piv.product_id = pi.product_id
 AND piv.store_id = pi.store_id
WHERE pi.store_id = %(store_id)s
  AND pi.product_id = %(product_id)s
GROUP BY pi.sale_status
"""

SELECT_PRODUCT_OPTIONS_SQL = """
SELECT
    store_id,
    product_id,
    option_id,
    option_key,
    display_name,
    sort_order,
    required,
    selection_type,
    option_type,
    active
FROM store_catalog_product_options
WHERE store_id = %(store_id)s
  AND product_id = %(product_id)s
ORDER BY sort_order ASC, option_key ASC
"""

SELECT_PRODUCT_OPTION_VALUES_SQL = """
SELECT
    store_id,
    product_id,
    option_id,
    option_value_id,
    value_key,
    display_value,
    sort_order,
    price_delta_amount,
    price_delta_currency,
    active
FROM store_catalog_product_option_values
WHERE store_id = %(store_id)s
  AND product_id = %(product_id)s
  AND option_id = %(option_id)s
ORDER BY sort_order ASC, value_key ASC
"""

SELECT_PRODUCT_VARIANTS_SQL = """
SELECT
    variants.store_id AS store_id,
    variants.product_id AS product_id,
    variants.public_variant_id AS public_variant_id,
    variants.display_name AS display_name,
    COALESCE(canonical_option_values.option_values, variants.option_values) AS option_values,
    variants.sku AS sku,
    variants.status AS status,
    variants.active AS active,
    variants.sort_order AS sort_order,
    variants.price_delta_amount AS price_delta_amount,
    variants.price_delta_currency AS price_delta_currency
FROM store_catalog_product_variants variants
LEFT JOIN LATERAL (
    SELECT jsonb_object_agg(options.option_key, values.value_key ORDER BY options.sort_order ASC, values.sort_order ASC) AS option_values
    FROM store_catalog_product_variant_option_values links
    JOIN store_catalog_product_options options
      ON options.store_id = links.store_id
     AND options.product_id = links.product_id
     AND options.option_id = links.option_id
    JOIN store_catalog_product_option_values values
      ON values.store_id = links.store_id
     AND values.product_id = links.product_id
     AND values.option_id = links.option_id
     AND values.option_value_id = links.option_value_id
    WHERE links.store_id = variants.store_id
      AND links.product_id = variants.product_id
      AND links.public_variant_id = variants.public_variant_id
      AND options.active = true
      AND values.active = true
) canonical_option_values ON true
WHERE variants.store_id = %(store_id)s
  AND variants.product_id = %(product_id)s
ORDER BY variants.sort_order ASC, variants.public_variant_id ASC
"""

SELECT_PRODUCT_VARIANT_AVAILABILITY_SQL = """
SELECT available_stock, total_stock, sale_status
FROM product_variant_inventory
WHERE store_id = %(store_id)s
  AND product_id = %(product_id)s
  AND public_variant_id = %(public_variant_id)s
"""

DEACTIVATE_PRODUCT_OPTIONS_SQL = """
UPDATE store_catalog_product_options
SET active = false,
    updated_at = now()
WHERE store_id = %(store_id)s
  AND product_id = %(product_id)s
"""

DEACTIVATE_PRODUCT_OPTION_VALUES_SQL = """
UPDATE store_catalog_product_option_values
SET active = false,
    updated_at = now()
WHERE store_id = %(store_id)s
  AND product_id = %(product_id)s
"""

UPSERT_PRODUCT_OPTION_SQL = """
INSERT INTO store_catalog_product_options (
    store_id,
    product_id,
    option_id,
    option_key,
    display_name,
    sort_order,
    required,
    selection_type,
    option_type,
    active
) VALUES (
    %(store_id)s,
    %(product_id)s,
    %(option_id)s,
    %(option_key)s,
    %(display_name)s,
    %(sort_order)s,
    %(required)s,
    %(selection_type)s,
    %(option_type)s,
    %(active)s
)
ON CONFLICT (store_id, product_id, option_key) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    sort_order = EXCLUDED.sort_order,
    required = EXCLUDED.required,
    selection_type = EXCLUDED.selection_type,
    option_type = EXCLUDED.option_type,
    active = EXCLUDED.active,
    updated_at = now()
RETURNING option_id
"""

UPSERT_PRODUCT_OPTION_VALUE_SQL = """
INSERT INTO store_catalog_product_option_values (
    store_id,
    product_id,
    option_id,
    option_value_id,
    value_key,
    display_value,
    sort_order,
    price_delta_amount,
    price_delta_currency,
    active
) VALUES (
    %(store_id)s,
    %(product_id)s,
    %(option_id)s,
    %(option_value_id)s,
    %(value_key)s,
    %(display_value)s,
    %(sort_order)s,
    %(price_delta_amount)s,
    %(price_delta_currency)s,
    %(active)s
)
ON CONFLICT (store_id, product_id, option_id, value_key) DO UPDATE SET
    display_value = EXCLUDED.display_value,
    sort_order = EXCLUDED.sort_order,
    price_delta_amount = EXCLUDED.price_delta_amount,
    price_delta_currency = EXCLUDED.price_delta_currency,
    active = EXCLUDED.active,
    updated_at = now()
RETURNING option_value_id
"""

DEACTIVATE_PRODUCT_VARIANTS_SQL = """
UPDATE store_catalog_product_variants
SET active = false,
    updated_at = now()
WHERE store_id = %(store_id)s
  AND product_id = %(product_id)s
"""

UPSERT_PRODUCT_VARIANT_SQL = """
INSERT INTO store_catalog_product_variants (
    store_id,
    product_id,
    public_variant_id,
    display_name,
    option_values,
    sku,
    status,
    active,
    sort_order,
    price_delta_amount,
    price_delta_currency,
    price_delta_numeric
) VALUES (
    %(store_id)s,
    %(product_id)s,
    %(public_variant_id)s,
    %(display_name)s,
    %(option_values)s::jsonb,
    %(sku)s,
    %(status)s,
    %(active)s,
    %(sort_order)s,
    %(price_delta_amount)s,
    %(price_delta_currency)s,
    %(price_delta_numeric)s
)
ON CONFLICT (store_id, product_id, public_variant_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    option_values = EXCLUDED.option_values,
    sku = EXCLUDED.sku,
    status = EXCLUDED.status,
    active = EXCLUDED.active,
    sort_order = EXCLUDED.sort_order,
    price_delta_amount = EXCLUDED.price_delta_amount,
    price_delta_currency = EXCLUDED.price_delta_currency,
    price_delta_numeric = EXCLUDED.price_delta_numeric,
    updated_at = now()
"""

PRODUCT_LIST_SELECT_SQL = """
SELECT
    store_id,
    product_id,
    public_product_id,
    public_store_id,
    title,
    description,
    category,
    tags,
    media,
    attributes,
    status,
    visibility,
    price_amount,
    price_currency,
    active,
    created_at,
    updated_at
FROM store_catalog_products
"""

UPSERT_PRODUCT_SQL = """
INSERT INTO store_catalog_products (
    store_id,
    product_id,
    public_product_id,
    public_store_id,
    title,
    name,
    description,
    category,
    tags,
    media,
    attributes,
    status,
    visibility,
    price_amount,
    price_currency,
    active
) VALUES (
    %(store_id)s,
    %(product_id)s,
    %(public_product_id)s,
    %(public_store_id)s,
    %(title)s,
    %(name)s,
    %(description)s,
    %(category)s,
    %(tags)s::jsonb,
    %(media)s::jsonb,
    %(attributes)s::jsonb,
    %(status)s,
    %(visibility)s,
    %(price_amount)s,
    %(price_currency)s,
    %(active)s
)
ON CONFLICT (store_id, product_id) DO UPDATE SET
    public_product_id = store_catalog_products.public_product_id,
    public_store_id = EXCLUDED.public_store_id,
    title = EXCLUDED.title,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    tags = EXCLUDED.tags,
    media = EXCLUDED.media,
    attributes = EXCLUDED.attributes,
    status = EXCLUDED.status,
    visibility = EXCLUDED.visibility,
    price_amount = EXCLUDED.price_amount,
    price_currency = EXCLUDED.price_currency,
    active = EXCLUDED.active,
    updated_at = now()
"""

UPSERT_PRODUCT_ASSET_SQL = """
INSERT INTO store_catalog_product_assets (
    store_id,
    public_store_id,
    media_ref,
    asset_type,
    file_name,
    content_type,
    size_bytes,
    content_sha256,
    content,
    created_at
) VALUES (
    %(store_id)s,
    %(public_store_id)s,
    %(media_ref)s,
    %(asset_type)s,
    %(file_name)s,
    %(content_type)s,
    %(size_bytes)s,
    %(content_sha256)s,
    %(content)s,
    %(created_at)s
)
ON CONFLICT (media_ref) DO UPDATE SET
    file_name = EXCLUDED.file_name,
    content_type = EXCLUDED.content_type,
    size_bytes = EXCLUDED.size_bytes,
    content_sha256 = EXCLUDED.content_sha256,
    content = EXCLUDED.content,
    created_at = EXCLUDED.created_at
"""

SELECT_PRODUCT_ASSET_SQL = """
SELECT
    store_id,
    public_store_id,
    media_ref,
    asset_type,
    file_name,
    content_type,
    size_bytes,
    content_sha256,
    content,
    created_at
FROM store_catalog_product_assets
WHERE media_ref = %(media_ref)s
"""

UPSERT_ORDER_PRODUCT_SQL = """
INSERT INTO order_store_products (
    store_id,
    product_id,
    name,
    price_amount,
    price_currency
) VALUES (
    %(store_id)s,
    %(product_id)s,
    %(name)s,
    %(price_amount)s,
    %(price_currency)s
)
ON CONFLICT (store_id, product_id) DO UPDATE SET
    name = EXCLUDED.name,
    price_amount = EXCLUDED.price_amount,
    price_currency = EXCLUDED.price_currency,
    updated_at = now()
"""

UPSERT_APPROVAL_PRODUCT_SQL = """
INSERT INTO store_approval_products (
    store_id,
    product_id,
    name,
    available
) VALUES (
    %(store_id)s,
    %(product_id)s,
    %(name)s,
    %(available)s
)
ON CONFLICT (store_id, product_id) DO UPDATE SET
    name = EXCLUDED.name,
    available = EXCLUDED.available,
    updated_at = now()
"""

# product_inventory is a registry only; stock is seeded on the default variant below.
INSERT_INITIAL_INVENTORY_SQL = """
INSERT INTO product_inventory (
    product_id,
    store_id,
    sale_status
) VALUES (
    %(product_id)s,
    %(store_id)s,
    'ACTIVE'
)
ON CONFLICT (product_id, store_id) DO NOTHING
"""

# Newly registered products are option-less, so they get a hidden default variant
# that carries the product's stock (stock is tracked per variant).
INSERT_DEFAULT_VARIANT_SQL = """
INSERT INTO store_catalog_product_variants (
    store_id,
    product_id,
    public_variant_id,
    display_name,
    option_values,
    status,
    active,
    sort_order,
    price_delta_amount,
    price_delta_currency
) VALUES (
    %(store_id)s,
    %(product_id)s,
    %(public_variant_id)s,
    'Default',
    '{}'::jsonb,
    'ACTIVE',
    true,
    0,
    0,
    %(price_delta_currency)s
)
ON CONFLICT (store_id, product_id, public_variant_id) DO NOTHING
"""

INSERT_DEFAULT_VARIANT_INVENTORY_SQL = """
INSERT INTO product_variant_inventory (
    public_variant_id,
    product_id,
    store_id,
    available_stock,
    reserved_stock,
    total_stock,
    sale_status
) VALUES (
    %(public_variant_id)s,
    %(product_id)s,
    %(store_id)s,
    %(available_stock)s,
    0,
    %(total_stock)s,
    'ACTIVE'
)
ON CONFLICT (public_variant_id) DO NOTHING
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

    def get_store_by_public_id(self, public_store_id: PublicStoreId) -> StoreProfile | None:
        row = _fetch_one(
            self._connection.execute(
                SELECT_STORE_BY_PUBLIC_ID_SQL,
                {"public_store_id": str(public_store_id)},
            )
        )
        return _row_to_store(row) if row is not None else None

    def get_store_by_display_name(self, display_name: str) -> StoreProfile | None:
        row = _fetch_one(
            self._connection.execute(
                SELECT_STORE_BY_DISPLAY_NAME_SQL,
                {"display_name": str(display_name)},
            )
        )
        return _row_to_store(row) if row is not None else None

    def list_stores_for_member(self, user_id: UserId) -> tuple[StoreProfile, ...]:
        result = self._connection.execute(SELECT_STORES_FOR_MEMBER_SQL, {"user_id": str(user_id)})
        return tuple(_row_to_store(row) for row in result)

    def list_public_stores(self, *, limit: int, offset: int) -> tuple[StoreProfile, ...]:
        result = self._connection.execute(SELECT_PUBLIC_STORES_SQL, {"limit": int(limit), "offset": int(offset)})
        return tuple(_row_to_store(row) for row in result)

    def list_all_public_products(
        self,
        *,
        category: str | None,
        tag: str | None,
        query: str | None,
        sort_by: str,
        sort_direction: str,
        limit: int,
        offset: int,
    ) -> tuple[StoreProduct, ...]:
        order_columns = {
            "title": "p.title",
            "createdAt": "p.created_at",
            "updatedAt": "p.updated_at",
            "price": "p.price_amount",
        }
        if sort_by not in order_columns:
            raise ValueError("sort_by is not allowed")
        if sort_direction not in {"asc", "desc"}:
            raise ValueError("sort_direction is not allowed")
        params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
        extra_filters: list[str] = []
        if category is not None:
            extra_filters.append("p.category = %(category)s")
            params["category"] = category
        if tag is not None:
            extra_filters.append("p.tags ? %(tag)s")
            params["tag"] = tag
        if query is not None:
            extra_filters.append("(p.title ILIKE %(query)s ESCAPE '\\' OR p.description ILIKE %(query)s ESCAPE '\\')")
            params["query"] = _search_pattern(query)
        where_clause = ""
        if extra_filters:
            where_clause = "AND " + " AND ".join(extra_filters) + "\n"
        order_column = order_columns[sort_by]
        order_direction = sort_direction.upper()
        sql = (
            SELECT_ALL_PUBLIC_PRODUCTS_SQL
            + where_clause
            + f"ORDER BY {order_column} {order_direction}, p.public_product_id ASC\nLIMIT %(limit)s OFFSET %(offset)s"
        )
        result = self._connection.execute(sql, params)
        return tuple(_row_to_product(row) for row in result)

    def merchant_group_for_store(self, store_id: StoreId) -> Group | None:
        row = _fetch_one(
            self._connection.execute(
                SELECT_MERCHANT_GROUP_FOR_STORE_SQL,
                {"store_id": str(store_id)},
            )
        )
        return _row_to_group(row) if row is not None else None

    def ensure_merchant_group_for_store(self, store_id: StoreId) -> GroupId:
        existing = self.merchant_group_for_store(store_id)
        if existing is not None:
            return existing.group_id
        group_id = GroupId.new()
        self._connection.execute(
            INSERT_MERCHANT_GROUP_SQL,
            {
                "group_id": str(group_id),
                "name": f"Merchant store {store_id}",
                "store_id": str(store_id),
            },
        )
        return group_id

    def grant_group_membership(self, group_id: GroupId, user_id: UserId, role_id: str, *, active: bool) -> None:
        self._connection.execute(
            UPSERT_GROUP_MEMBERSHIP_SQL,
            {
                "group_id": str(group_id),
                "user_id": str(user_id),
                "role_id": str(role_id),
                "active": bool(active),
            },
        )

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

    def record_membership_projection_event(self, message: OutboxMessage) -> None:
        PostgresOutboxMessageRepository(self._connection).save(message)

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

    def get_product_by_public_id(self, store_id: StoreId, public_product_id: PublicProductId) -> StoreProduct | None:
        row = _fetch_one(
            self._connection.execute(
                SELECT_PRODUCT_BY_PUBLIC_ID_SQL,
                {"store_id": str(store_id), "public_product_id": str(public_product_id)},
            )
        )
        return _row_to_product(row) if row is not None else None

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
        order_columns = {
            "title": "title",
            "createdAt": "created_at",
            "updatedAt": "updated_at",
            "price": "price_amount",
        }
        if sort_by not in order_columns:
            raise ValueError("sort_by is not allowed")
        if sort_direction not in {"asc", "desc"}:
            raise ValueError("sort_direction is not allowed")
        params: dict[str, Any] = {
            "store_id": str(store_id),
            "limit": int(limit),
            "offset": int(offset),
        }
        filters = ["store_id = %(store_id)s"]
        if status is not None:
            filters.append("status = %(status)s")
            params["status"] = status.value
        if visibility is not None:
            filters.append("visibility = %(visibility)s")
            params["visibility"] = visibility.value
        if category is not None:
            filters.append("category = %(category)s")
            params["category"] = category
        if tag is not None:
            filters.append("tags ? %(tag)s")
            params["tag"] = tag
        if query is not None:
            filters.append("(title ILIKE %(query)s ESCAPE '\\' OR description ILIKE %(query)s ESCAPE '\\')")
            params["query"] = _search_pattern(query)
        order_column = order_columns[sort_by]
        order_direction = sort_direction.upper()
        sql = (
            PRODUCT_LIST_SELECT_SQL
            + "WHERE "
            + " AND ".join(filters)
            + f"\nORDER BY {order_column} {order_direction}, public_product_id ASC\nLIMIT %(limit)s OFFSET %(offset)s"
        )
        result = self._connection.execute(sql, params)
        return tuple(_row_to_product(row) for row in result)

    def get_product_availability(self, store_id: StoreId, product_id: ProductId) -> Mapping[str, Any] | None:
        row = _fetch_one(
            self._connection.execute(
                SELECT_PRODUCT_AVAILABILITY_SQL,
                {"store_id": str(store_id), "product_id": str(product_id)},
            )
        )
        if row is None:
            return None
        return {
            "availableStock": int(_row_value(row, "available_stock")),
            "totalStock": int(_row_value(row, "total_stock")),
            "saleStatus": str(_row_value(row, "sale_status")),
        }

    def list_product_options(self, store_id: StoreId, product_id: ProductId) -> tuple[ProductOption, ...]:
        result = self._connection.execute(
            SELECT_PRODUCT_OPTIONS_SQL,
            {"store_id": str(store_id), "product_id": str(product_id)},
        )
        return tuple(_row_to_product_option(row) for row in result)

    def list_product_option_values(
        self,
        store_id: StoreId,
        product_id: ProductId,
        option_id: str,
    ) -> tuple[ProductOptionValue, ...]:
        result = self._connection.execute(
            SELECT_PRODUCT_OPTION_VALUES_SQL,
            {"store_id": str(store_id), "product_id": str(product_id), "option_id": option_id},
        )
        return tuple(_row_to_product_option_value(row) for row in result)

    def list_product_variants(self, store_id: StoreId, product_id: ProductId) -> tuple[ProductVariant, ...]:
        result = self._connection.execute(
            SELECT_PRODUCT_VARIANTS_SQL,
            {"store_id": str(store_id), "product_id": str(product_id)},
        )
        return tuple(_row_to_product_variant(row) for row in result)

    def get_variant_availability(
        self,
        store_id: StoreId,
        product_id: ProductId,
        public_variant_id: PublicVariantId,
    ) -> Mapping[str, Any] | None:
        row = _fetch_one(
            self._connection.execute(
                SELECT_PRODUCT_VARIANT_AVAILABILITY_SQL,
                {
                    "store_id": str(store_id),
                    "product_id": str(product_id),
                    "public_variant_id": str(public_variant_id),
                },
            )
        )
        if row is None:
            return None
        return {
            "availableStock": int(_row_value(row, "available_stock")),
            "totalStock": int(_row_value(row, "total_stock")),
            "saleStatus": str(_row_value(row, "sale_status")),
        }

    def save_product(self, product: StoreProduct) -> None:
        self._connection.execute(UPSERT_PRODUCT_SQL, _product_params(product))

    def save_order_product_projection(self, product: StoreProduct) -> None:
        self._connection.execute(UPSERT_ORDER_PRODUCT_SQL, _product_params(product))

    def save_store_approval_product_projection(self, product: StoreProduct) -> None:
        # The approval read-model identifies products by id/name/availability only; it does not
        # use price, so the fiat catalog price is intentionally not projected here.
        self._connection.execute(
            UPSERT_APPROVAL_PRODUCT_SQL,
            {
                "store_id": str(product.store_id),
                "product_id": str(product.product_id),
                "name": product.name,
                "available": product.active,
            },
        )

    def save_inventory_projection(self, product: StoreProduct, initial_total_stock: int) -> None:
        product_id = str(product.product_id)
        store_id = str(product.store_id)
        # Registry row, then a hidden default variant that carries the stock.
        self._connection.execute(
            INSERT_INITIAL_INVENTORY_SQL,
            {"product_id": product_id, "store_id": store_id},
        )
        default_variant_id = default_public_variant_id(product.product_id)
        self._connection.execute(
            INSERT_DEFAULT_VARIANT_SQL,
            {
                "store_id": store_id,
                "product_id": product_id,
                "public_variant_id": default_variant_id,
                "price_delta_currency": product.price.currency,
            },
        )
        self._connection.execute(
            INSERT_DEFAULT_VARIANT_INVENTORY_SQL,
            {
                "public_variant_id": default_variant_id,
                "product_id": product_id,
                "store_id": store_id,
                "available_stock": initial_total_stock,
                "total_stock": initial_total_stock,
            },
        )

    def save_product_asset(self, asset: ProductAssetRecord) -> None:
        self._connection.execute(UPSERT_PRODUCT_ASSET_SQL, _product_asset_params(asset))

    def get_product_asset(self, media_ref: str) -> ProductAssetRecord | None:
        row = _fetch_one(self._connection.execute(SELECT_PRODUCT_ASSET_SQL, {"media_ref": media_ref}))
        return _row_to_product_asset(row) if row is not None else None

    def replace_product_options(
        self,
        store_id: StoreId,
        product_id: ProductId,
        options: tuple[ProductOption, ...],
        option_values: Mapping[str, tuple[ProductOptionValue, ...]],
    ) -> None:
        ids = {"store_id": str(store_id), "product_id": str(product_id)}
        self._connection.execute(DEACTIVATE_PRODUCT_OPTION_VALUES_SQL, ids)
        self._connection.execute(DEACTIVATE_PRODUCT_OPTIONS_SQL, ids)
        for option in options:
            option_row = _fetch_one(self._connection.execute(UPSERT_PRODUCT_OPTION_SQL, _product_option_params(option)))
            canonical_option_id = (
                str(_row_value(option_row, "option_id")) if option_row is not None else str(option.option_id)
            )
            for value in option_values.get(option.option_id, ()):
                value_params = _product_option_value_params(value)
                value_params["option_id"] = canonical_option_id
                self._connection.execute(UPSERT_PRODUCT_OPTION_VALUE_SQL, value_params)

    def replace_product_variants(
        self,
        store_id: StoreId,
        product_id: ProductId,
        variants: tuple[ProductVariant, ...],
    ) -> None:
        self._connection.execute(
            DEACTIVATE_PRODUCT_VARIANTS_SQL,
            {"store_id": str(store_id), "product_id": str(product_id)},
        )
        for variant in variants:
            self._connection.execute(UPSERT_PRODUCT_VARIANT_SQL, _product_variant_params(variant))

    def save_variant_inventory_projection(
        self,
        product: StoreProduct,
        public_variant_id: PublicVariantId,
        initial_total_stock: int,
    ) -> None:
        product_id = str(product.product_id)
        store_id = str(product.store_id)
        self._connection.execute(
            INSERT_INITIAL_INVENTORY_SQL,
            {"product_id": product_id, "store_id": store_id},
        )
        self._connection.execute(
            INSERT_DEFAULT_VARIANT_INVENTORY_SQL,
            {
                "public_variant_id": str(public_variant_id),
                "product_id": product_id,
                "store_id": store_id,
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


def _row_to_group(row: Mapping[str, Any] | object) -> Group:
    return Group(
        group_id=GroupId(_row_value(row, "group_id")),
        group_type=GroupType(_row_value(row, "group_type")),
        name=str(_row_value(row, "name")),
        active=bool(_row_value(row, "active")),
        resource_type=_optional_row_value(row, "resource_type"),
        resource_id=_optional_row_value(row, "resource_id"),
    )


def _row_to_store(row: Mapping[str, Any] | object) -> StoreProfile:
    store_id = StoreId(_row_value(row, "store_id"))
    return StoreProfile(
        store_id=store_id,
        public_store_id=_optional_row_value(row, "public_store_id") or PublicStoreId.for_store_id(store_id),
        owner_user_id=UserId(_row_value(row, "owner_user_id")),
        group_id=_optional_row_value(row, "group_id"),
        display_name=str(_optional_row_value(row, "display_name") or "Untitled Store"),
        description=_optional_row_value(row, "description"),
        status=StoreStatus(str(_optional_row_value(row, "status") or ("ACTIVE" if _optional_row_value(row, "active") is not False else "SUSPENDED"))),
        support_email=_optional_row_value(row, "support_email"),
        support_email_public=bool(_optional_row_value(row, "support_email_public") or False),
        business_registration_label=_optional_row_value(row, "business_registration_label"),
        created_at=_optional_row_value(row, "created_at"),
        updated_at=_optional_row_value(row, "updated_at"),
        payment_settings=StorePaymentSettings(
            store_id=store_id,
            store_wallet=WalletAddress(str(_row_value(row, "store_wallet_address"))),
            supported_chain_ids=_chain_ids(_row_value(row, "supported_chain_ids")),
            supported_payment_asset_ids=_json_sequence(_optional_row_value(row, "supported_payment_asset_ids")),
            active=bool(_optional_row_value(row, "active") if _optional_row_value(row, "active") is not None else True),
        ),
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
        public_product_id=_optional_row_value(row, "public_product_id"),
        public_store_id=_optional_row_value(row, "public_store_id"),
        title=str(_optional_row_value(row, "title") or _optional_row_value(row, "name")),
        description=_optional_row_value(row, "description"),
        category=_optional_row_value(row, "category"),
        tags=tuple(_json_sequence(_optional_row_value(row, "tags"))),
        media=tuple(_json_sequence(_optional_row_value(row, "media"))),
        attributes=dict(_json_mapping(_optional_row_value(row, "attributes"))),
        status=ProductStatus(str(_optional_row_value(row, "status") or ("ACTIVE" if _row_value(row, "active") else "INACTIVE"))),
        visibility=ProductVisibility(str(_optional_row_value(row, "visibility") or "PUBLIC")),
        price=Money(
            amount=_row_value(row, "price_amount"),
            currency=str(_row_value(row, "price_currency") or "USD"),
        ),
        active=bool(_row_value(row, "active")),
        created_at=_optional_row_value(row, "created_at"),
        updated_at=_optional_row_value(row, "updated_at"),
    )


def _row_to_product_option(row: Mapping[str, Any] | object) -> ProductOption:
    return ProductOption(
        store_id=StoreId(_row_value(row, "store_id")),
        product_id=ProductId(_row_value(row, "product_id")),
        option_id=str(_row_value(row, "option_id")),
        option_key=str(_row_value(row, "option_key")),
        display_name=str(_row_value(row, "display_name")),
        sort_order=int(_row_value(row, "sort_order")),
        required=bool(_row_value(row, "required")),
        selection_type=str(_row_value(row, "selection_type")),
        option_type=str(_row_value(row, "option_type")),
        active=bool(_row_value(row, "active")),
    )


def _row_to_product_option_value(row: Mapping[str, Any] | object) -> ProductOptionValue:
    return ProductOptionValue(
        store_id=StoreId(_row_value(row, "store_id")),
        product_id=ProductId(_row_value(row, "product_id")),
        option_id=str(_row_value(row, "option_id")),
        option_value_id=str(_row_value(row, "option_value_id")),
        value_key=str(_row_value(row, "value_key")),
        display_value=str(_row_value(row, "display_value")),
        sort_order=int(_row_value(row, "sort_order")),
        price_delta=_optional_money_from_row(row, "price_delta"),
        active=bool(_row_value(row, "active")),
    )


def _row_to_product_variant(row: Mapping[str, Any] | object) -> ProductVariant:
    return ProductVariant(
        store_id=StoreId(_row_value(row, "store_id")),
        product_id=ProductId(_row_value(row, "product_id")),
        public_variant_id=PublicVariantId(str(_row_value(row, "public_variant_id"))),
        display_name=str(_row_value(row, "display_name")),
        option_values=_json_mapping(_row_value(row, "option_values")),
        sku=_optional_row_value(row, "sku"),
        status=ProductStatus(str(_row_value(row, "status"))),
        active=bool(_row_value(row, "active")),
        sort_order=int(_row_value(row, "sort_order")),
        price_delta=Money(
            amount=_row_value(row, "price_delta_amount"),
            currency=str(_row_value(row, "price_delta_currency") or "USD"),
        ),
    )


def _store_params(store: StoreProfile) -> dict[str, Any]:
    return {
        "store_id": str(store.store_id),
        "public_store_id": str(store.public_store_id),
        "owner_user_id": str(store.owner_user_id),
        "group_id": str(store.group_id) if store.group_id is not None else None,
        "display_name": store.display_name,
        "description": store.description,
        "status": store.status.value,
        "support_email": store.support_email,
        "support_email_public": store.support_email_public,
        "business_registration_label": store.business_registration_label,
        "active": store.active,
        "store_wallet_address": str(store.store_wallet) if store.store_wallet is not None else None,
        "supported_chain_ids": json.dumps(list(store.supported_chain_ids)),
        "supported_payment_asset_ids": json.dumps(list(store.supported_payment_asset_ids)),
    }


def _product_params(product: StoreProduct) -> dict[str, Any]:
    return {
        "store_id": str(product.store_id),
        "product_id": str(product.product_id),
        "public_product_id": str(product.public_product_id),
        "public_store_id": str(product.public_store_id),
        "title": product.title,
        "name": product.name,
        "description": product.description,
        "category": product.category,
        "tags": json.dumps(list(product.tags)),
        "media": json.dumps(list(product.media)),
        "attributes": json.dumps(dict(product.attributes)),
        "status": product.status.value,
        "visibility": product.visibility.value,
        "price_amount": product.price.amount,
        "price_currency": product.price.currency,
        "active": product.active,
    }


def _product_asset_params(asset: ProductAssetRecord) -> dict[str, Any]:
    return {
        "store_id": str(asset.store_id),
        "public_store_id": str(asset.public_store_id),
        "media_ref": asset.media_ref,
        "asset_type": asset.asset_type,
        "file_name": asset.file_name,
        "content_type": asset.content_type,
        "size_bytes": asset.size_bytes,
        "content_sha256": asset.content_sha256,
        "content": asset.content,
        "created_at": asset.created_at,
    }


def _row_to_product_asset(row: Mapping[str, Any]) -> ProductAssetRecord:
    content = _row_value(row, "content")
    if isinstance(content, memoryview):
        content = content.tobytes()
    elif isinstance(content, bytearray):
        content = bytes(content)
    return ProductAssetRecord(
        store_id=StoreId(str(_row_value(row, "store_id"))),
        public_store_id=PublicStoreId(str(_row_value(row, "public_store_id"))),
        media_ref=str(_row_value(row, "media_ref")),
        asset_type=str(_row_value(row, "asset_type")),
        file_name=str(_row_value(row, "file_name")),
        content_type=str(_row_value(row, "content_type")),
        size_bytes=int(_row_value(row, "size_bytes")),
        content_sha256=str(_row_value(row, "content_sha256")),
        content=content,
        created_at=_row_value(row, "created_at"),
    )


def _product_option_params(option: ProductOption) -> dict[str, Any]:
    return {
        "store_id": str(option.store_id),
        "product_id": str(option.product_id),
        "option_id": option.option_id,
        "option_key": option.option_key,
        "display_name": option.display_name,
        "sort_order": option.sort_order,
        "required": option.required,
        "selection_type": option.selection_type,
        "option_type": option.option_type,
        "active": option.active,
    }


def _product_option_value_params(value: ProductOptionValue) -> dict[str, Any]:
    return {
        "store_id": str(value.store_id),
        "product_id": str(value.product_id),
        "option_id": value.option_id,
        "option_value_id": value.option_value_id,
        "value_key": value.value_key,
        "display_value": value.display_value,
        "sort_order": value.sort_order,
        "price_delta_amount": value.price_delta.amount if value.price_delta is not None else None,
        "price_delta_currency": value.price_delta.currency if value.price_delta is not None else None,
        "active": value.active,
    }


def _product_variant_params(variant: ProductVariant) -> dict[str, Any]:
    return {
        "store_id": str(variant.store_id),
        "product_id": str(variant.product_id),
        "public_variant_id": str(variant.public_variant_id),
        "display_name": variant.display_name,
        "option_values": json.dumps(dict(variant.option_values)),
        "sku": variant.sku,
        "status": variant.status.value,
        "active": variant.active,
        "sort_order": variant.sort_order,
        "price_delta_amount": variant.price_delta.amount,
        "price_delta_currency": variant.price_delta.currency,
        "price_delta_numeric": variant.price_delta.amount,
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


def _json_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON sequence column is not a valid JSON string") from exc
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    raise ValueError("JSON sequence column must be a sequence")


def _json_mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON object column is not a valid JSON string") from exc
    if isinstance(value, Mapping):
        return value
    raise ValueError("JSON object column must be a mapping")


def _optional_money_from_row(row: Mapping[str, Any] | object, prefix: str) -> Money | None:
    amount = _optional_row_value(row, f"{prefix}_amount")
    if amount is None:
        return None
    return Money(
        amount=amount,
        currency=str(_optional_row_value(row, f"{prefix}_currency") or "USD"),
    )


def _search_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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

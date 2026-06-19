#!/usr/bin/env sh
set -eu

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

BOOTSTRAP_POSTGRES_HOST="${BOOTSTRAP_POSTGRES_HOST:-}"
BOOTSTRAP_POSTGRES_PORT="${BOOTSTRAP_POSTGRES_PORT:-5432}"

PSQL_HOST_OPTION=""
PSQL_PORT_OPTION=""
if [ -n "$BOOTSTRAP_POSTGRES_HOST" ]; then
    PSQL_HOST_OPTION="--host=$BOOTSTRAP_POSTGRES_HOST"
    PSQL_PORT_OPTION="--port=$BOOTSTRAP_POSTGRES_PORT"
    if [ -z "${PGPASSWORD:-}" ] && [ -n "${POSTGRES_PASSWORD:-}" ]; then
        export PGPASSWORD="$POSTGRES_PASSWORD"
    fi
fi

psql -v ON_ERROR_STOP=1 \
    $PSQL_HOST_OPTION \
    $PSQL_PORT_OPTION \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" <<'SQL'
BEGIN;

-- Clean up any existing demo transactions/reservations to keep inventory consistent
DELETE FROM payment_authorizations WHERE payment_id IN (SELECT payment_id FROM payments WHERE order_id IN (SELECT order_id FROM orders WHERE store_id = '44444444-4444-4444-8444-444444444444'));
DELETE FROM payments WHERE order_id IN (SELECT order_id FROM orders WHERE store_id = '44444444-4444-4444-8444-444444444444');
DELETE FROM inventory_reservations WHERE store_id = '44444444-4444-4444-8444-444444444444';
DELETE FROM order_items WHERE order_id IN (SELECT order_id FROM orders WHERE store_id = '44444444-4444-4444-8444-444444444444');
DELETE FROM orders WHERE store_id = '44444444-4444-4444-8444-444444444444';

INSERT INTO auth_users (
    user_id,
    wallet_address,
    role,
    active
) VALUES
    ('11111111-1111-4111-8111-111111111111', '0x1111111111111111111111111111111111111111', 'CUSTOMER', true),
    ('33333333-3333-4333-8333-333333333333', '0x2222222222222222222222222222222222222222', 'CUSTOMER', true),
    ('99999999-9999-4999-8999-999999999999', '0x9999999999999999999999999999999999999999', 'CUSTOMER', true)
ON CONFLICT (user_id) DO UPDATE SET
    wallet_address = EXCLUDED.wallet_address,
    role = EXCLUDED.role,
    active = EXCLUDED.active,
    updated_at = now();

INSERT INTO auth_user_profiles (
    user_id,
    display_name,
    status
) VALUES
    ('11111111-1111-4111-8111-111111111111', 'Demo Customer', 'ACTIVE'),
    ('33333333-3333-4333-8333-333333333333', 'Demo Store Owner', 'ACTIVE'),
    ('99999999-9999-4999-8999-999999999999', 'Demo Platform Admin', 'ACTIVE')
ON CONFLICT (user_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    status = EXCLUDED.status,
    updated_at = now();

INSERT INTO auth_user_wallets (
    wallet_id,
    user_id,
    wallet_address,
    chain_id,
    wallet_type,
    verification_status,
    "primary",
    linked_at
) VALUES
    (
        '11111111-1111-4111-8111-111111111101',
        '11111111-1111-4111-8111-111111111111',
        '0x1111111111111111111111111111111111111111',
        1337,
        'EOA',
        'VERIFIED',
        true,
        '2026-05-22T00:00:00Z'
    ),
    (
        '11111111-1111-4111-8111-111111111102',
        '11111111-1111-4111-8111-111111111111',
        '0x4444444444444444444444444444444444444444',
        11155111,
        'EOA',
        'VERIFIED',
        false,
        '2026-05-22T00:00:00Z'
    ),
    (
        '33333333-3333-4333-8333-333333333301',
        '33333333-3333-4333-8333-333333333333',
        '0x2222222222222222222222222222222222222222',
        1337,
        'EOA',
        'VERIFIED',
        true,
        '2026-05-22T00:00:00Z'
    )
ON CONFLICT (wallet_id) DO UPDATE SET
    wallet_address = EXCLUDED.wallet_address,
    chain_id = EXCLUDED.chain_id,
    wallet_type = EXCLUDED.wallet_type,
    verification_status = EXCLUDED.verification_status,
    "primary" = EXCLUDED."primary",
    revoked_at = NULL,
    updated_at = now();

INSERT INTO auth_groups (
    group_id,
    group_type,
    name,
    resource_type,
    resource_id,
    active
) VALUES
    (
        '77777777-7777-4777-8777-777777777777',
        'PERSONAL',
        'Demo customer personal group',
        'user',
        '11111111-1111-4111-8111-111111111111',
        true
    ),
    (
        '66666666-6666-4666-8666-666666666666',
        'MERCHANT',
        'Demo merchant group',
        'store',
        '44444444-4444-4444-8444-444444444444',
        true
    ),
    (
        '88888888-8888-4888-8888-888888888888',
        'PLATFORM',
        'Demo platform group',
        NULL,
        NULL,
        true
    )
ON CONFLICT (group_id) DO UPDATE SET
    name = EXCLUDED.name,
    resource_type = EXCLUDED.resource_type,
    resource_id = EXCLUDED.resource_id,
    active = EXCLUDED.active,
    updated_at = now();

INSERT INTO auth_group_memberships (
    group_id,
    user_id,
    role_id,
    active
) VALUES
    (
        '77777777-7777-4777-8777-777777777777',
        '11111111-1111-4111-8111-111111111111',
        'PERSONAL_CUSTOMER',
        true
    ),
    (
        '66666666-6666-4666-8666-666666666666',
        '33333333-3333-4333-8333-333333333333',
        'MERCHANT_OWNER',
        true
    ),
    (
        '88888888-8888-4888-8888-888888888888',
        '99999999-9999-4999-8999-999999999999',
        'PLATFORM_ADMIN',
        true
    )
ON CONFLICT (group_id, user_id) DO UPDATE SET
    role_id = EXCLUDED.role_id,
    active = EXCLUDED.active,
    updated_at = now();

INSERT INTO auth_group_invitations (
    invitation_id,
    group_id,
    invited_role_id,
    invited_by_user_id,
    target_wallet_address,
    status
) VALUES (
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    '66666666-6666-4666-8666-666666666666',
    'MERCHANT_STAFF',
    '33333333-3333-4333-8333-333333333333',
    '0x5555555555555555555555555555555555555555',
    'PENDING'
)
ON CONFLICT (invitation_id) DO UPDATE SET
    invited_role_id = EXCLUDED.invited_role_id,
    target_wallet_address = EXCLUDED.target_wallet_address,
    status = EXCLUDED.status,
    updated_at = now();

INSERT INTO chains (
    chain_id,
    display_name,
    native_symbol,
    enabled
) VALUES
    (1337, 'Local Test Network', 'ETH', true),
    (11155111, 'Sepolia', 'ETH', true)
ON CONFLICT (chain_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    native_symbol = EXCLUDED.native_symbol,
    enabled = EXCLUDED.enabled,
    updated_at = now();

INSERT INTO payment_assets (
    asset_id,
    asset_type,
    chain_id,
    symbol,
    decimals,
    contract_address,
    enabled
) VALUES
    ('local-native-eth', 'NATIVE', 1337, 'ETH', 18, NULL, true),
    ('local-usdc', 'ERC20', 1337, 'USDC', 6, '0x4444444444444444444444444444444444444444', true),
    ('local-usdt', 'ERC20', 1337, 'USDT', 6, '0x5555555555555555555555555555555555555555', true),
    ('local-disabled-dai', 'ERC20', 1337, 'DAI', 18, '0x6666666666666666666666666666666666666666', false)
ON CONFLICT (asset_id) DO UPDATE SET
    chain_id = EXCLUDED.chain_id,
    symbol = EXCLUDED.symbol,
    decimals = EXCLUDED.decimals,
    contract_address = CASE
        WHEN payment_assets.contract_address IS NULL
          OR payment_assets.contract_address LIKE '$%'
          OR payment_assets.contract_address LIKE '0xreplace%'
        THEN EXCLUDED.contract_address
        ELSE payment_assets.contract_address
    END,
    enabled = EXCLUDED.enabled,
    updated_at = now();

INSERT INTO order_customers (
    customer_id,
    user_id
) VALUES (
    '22222222-2222-4222-8222-222222222222',
    '11111111-1111-4111-8111-111111111111'
)
ON CONFLICT (customer_id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    updated_at = now();

INSERT INTO store_catalog_stores (
    store_id,
    public_store_id,
    owner_user_id,
    group_id,
    display_name,
    description,
    status,
    support_email_public,
    active,
    store_wallet_address,
    supported_chain_ids,
    supported_payment_asset_ids
) VALUES (
    '44444444-4444-4444-8444-444444444444',
    'st_demo_store_001',
    '33333333-3333-4333-8333-333333333333',
    '66666666-6666-4666-8666-666666666666',
    'Demo Store',
    'Local token payments demo store',
    'ACTIVE',
    false,
    true,
    '0x2222222222222222222222222222222222222222',
    '[1337]'::jsonb,
    '["local-native-eth"]'::jsonb
)
ON CONFLICT (store_id) DO UPDATE SET
    public_store_id = EXCLUDED.public_store_id,
    owner_user_id = EXCLUDED.owner_user_id,
    group_id = EXCLUDED.group_id,
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    status = EXCLUDED.status,
    support_email_public = EXCLUDED.support_email_public,
    active = EXCLUDED.active,
    store_wallet_address = EXCLUDED.store_wallet_address,
    supported_chain_ids = EXCLUDED.supported_chain_ids,
    supported_payment_asset_ids = EXCLUDED.supported_payment_asset_ids,
    updated_at = now();

INSERT INTO store_catalog_store_memberships (
    store_id,
    user_id,
    role,
    active
) VALUES (
    '44444444-4444-4444-8444-444444444444',
    '33333333-3333-4333-8333-333333333333',
    'OWNER',
    true
)
ON CONFLICT (store_id, user_id) DO UPDATE SET
    role = EXCLUDED.role,
    active = EXCLUDED.active,
    updated_at = now();

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
    price_numeric,
    price_symbol,
    price_chain_id,
    price_token_address,
    price_decimals,
    active
) VALUES (
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'prd_local_hoodie_001',
    'st_demo_store_001',
    'Local Hoodie',
    'Local Hoodie',
    'Local checkout test hoodie',
    'apparel',
    '["demo","hoodie"]'::jsonb,
    '["products/local-hoodie.png","products/local-hoodie-back.png","products/local-hoodie-detail.png","products/local-hoodie-intro.pdf"]'::jsonb,
    '{"material":"cotton-blend","fit":"regular"}'::jsonb,
    'ACTIVE',
    'PUBLIC',
    0.010000000000000000,
    'ETH',
    1337,
    NULL,
    18,
    true
)
ON CONFLICT (store_id, product_id) DO UPDATE SET
    public_product_id = EXCLUDED.public_product_id,
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
    price_numeric = EXCLUDED.price_numeric,
    price_symbol = EXCLUDED.price_symbol,
    price_chain_id = EXCLUDED.price_chain_id,
    price_token_address = EXCLUDED.price_token_address,
    price_decimals = EXCLUDED.price_decimals,
    active = EXCLUDED.active,
    updated_at = now();

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
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'opt-size',
    'size',
    '사이즈',
    1,
    true,
    'SINGLE',
    'VARIANT',
    true
)
ON CONFLICT (store_id, product_id, option_id) DO UPDATE SET
    option_key = EXCLUDED.option_key,
    display_name = EXCLUDED.display_name,
    sort_order = EXCLUDED.sort_order,
    required = EXCLUDED.required,
    selection_type = EXCLUDED.selection_type,
    option_type = EXCLUDED.option_type,
    active = EXCLUDED.active,
    updated_at = now();

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
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'opt-gift-wrap',
    'giftWrap',
    '선택 포장',
    2,
    false,
    'MULTI',
    'ADD_ON',
    true
)
ON CONFLICT (store_id, product_id, option_id) DO UPDATE SET
    option_key = EXCLUDED.option_key,
    display_name = EXCLUDED.display_name,
    sort_order = EXCLUDED.sort_order,
    required = EXCLUDED.required,
    selection_type = EXCLUDED.selection_type,
    option_type = EXCLUDED.option_type,
    active = EXCLUDED.active,
    updated_at = now();

INSERT INTO store_catalog_product_option_values (
    store_id,
    product_id,
    option_id,
    option_value_id,
    value_key,
    display_value,
    sort_order,
    active
) VALUES
(
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'opt-size',
    'val-size-m',
    'M',
    'M',
    1,
    true
),
(
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'opt-size',
    'val-size-l',
    'L',
    'L',
    2,
    true
)
ON CONFLICT (store_id, product_id, option_id, option_value_id) DO UPDATE SET
    value_key = EXCLUDED.value_key,
    display_value = EXCLUDED.display_value,
    sort_order = EXCLUDED.sort_order,
    active = EXCLUDED.active,
    updated_at = now();

INSERT INTO store_catalog_product_option_values (
    store_id,
    product_id,
    option_id,
    option_value_id,
    value_key,
    display_value,
    sort_order,
    price_delta_numeric,
    price_delta_symbol,
    price_delta_chain_id,
    price_delta_token_address,
    price_delta_decimals,
    active
) VALUES (
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'opt-gift-wrap',
    'val-gift-wrap-premium',
    'premium',
    '프리미엄 포장',
    1,
    0.001,
    'ETH',
    1337,
    NULL,
    18,
    true
)
ON CONFLICT (store_id, product_id, option_id, option_value_id) DO UPDATE SET
    value_key = EXCLUDED.value_key,
    display_value = EXCLUDED.display_value,
    sort_order = EXCLUDED.sort_order,
    price_delta_numeric = EXCLUDED.price_delta_numeric,
    price_delta_symbol = EXCLUDED.price_delta_symbol,
    price_delta_chain_id = EXCLUDED.price_delta_chain_id,
    price_delta_token_address = EXCLUDED.price_delta_token_address,
    price_delta_decimals = EXCLUDED.price_delta_decimals,
    active = EXCLUDED.active,
    updated_at = now();

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
    price_delta_numeric,
    price_delta_symbol,
    price_delta_chain_id,
    price_delta_token_address,
    price_delta_decimals
) VALUES
(
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'var_local_hoodie_m',
    'M',
    '{"size":"M"}'::jsonb,
    'LOCAL-HOODIE-M',
    'ACTIVE',
    true,
    1,
    0.000000000000000000,
    'ETH',
    1337,
    NULL,
    18
),
(
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'var_local_hoodie_l',
    'L',
    '{"size":"L"}'::jsonb,
    'LOCAL-HOODIE-L',
    'ACTIVE',
    true,
    2,
    0.002000000000000000,
    'ETH',
    1337,
    NULL,
    18
)
ON CONFLICT (store_id, product_id, public_variant_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    option_values = EXCLUDED.option_values,
    sku = EXCLUDED.sku,
    status = EXCLUDED.status,
    active = EXCLUDED.active,
    sort_order = EXCLUDED.sort_order,
    price_delta_numeric = EXCLUDED.price_delta_numeric,
    price_delta_symbol = EXCLUDED.price_delta_symbol,
    price_delta_chain_id = EXCLUDED.price_delta_chain_id,
    price_delta_token_address = EXCLUDED.price_delta_token_address,
    price_delta_decimals = EXCLUDED.price_delta_decimals,
    updated_at = now();

INSERT INTO store_catalog_product_variant_option_values (
    store_id,
    product_id,
    public_variant_id,
    option_id,
    option_value_id
) VALUES
(
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'var_local_hoodie_m',
    'opt-size',
    'val-size-m'
),
(
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'var_local_hoodie_l',
    'opt-size',
    'val-size-l'
)
ON CONFLICT (store_id, product_id, public_variant_id, option_id) DO UPDATE SET
    option_value_id = EXCLUDED.option_value_id;

INSERT INTO order_stores (
    store_id,
    owner_user_id,
    active,
    store_address_id,
    store_address_street,
    store_wallet_address,
    supported_chain_ids,
    supported_payment_asset_ids
) VALUES (
    '44444444-4444-4444-8444-444444444444',
    '33333333-3333-4333-8333-333333333333',
    true,
    'store-address-001',
    '1 Local Demo Way',
    '0x2222222222222222222222222222222222222222',
    '[1337]'::jsonb,
    '["local-native-eth"]'::jsonb
)
ON CONFLICT (store_id) DO UPDATE SET
    owner_user_id = EXCLUDED.owner_user_id,
    active = EXCLUDED.active,
    store_address_id = EXCLUDED.store_address_id,
    store_address_street = EXCLUDED.store_address_street,
    store_wallet_address = EXCLUDED.store_wallet_address,
    supported_chain_ids = EXCLUDED.supported_chain_ids,
    supported_payment_asset_ids = EXCLUDED.supported_payment_asset_ids,
    updated_at = now();

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
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'Local Hoodie',
    0.010000000000000000,
    'ETH',
    1337,
    NULL,
    18
)
ON CONFLICT (store_id, product_id) DO UPDATE SET
    name = EXCLUDED.name,
    price_numeric = EXCLUDED.price_numeric,
    price_symbol = EXCLUDED.price_symbol,
    price_chain_id = EXCLUDED.price_chain_id,
    price_token_address = EXCLUDED.price_token_address,
    price_decimals = EXCLUDED.price_decimals,
    updated_at = now();

INSERT INTO product_inventory (
    product_id,
    store_id,
    available_stock,
    reserved_stock,
    total_stock,
    sale_status,
    version
) VALUES (
    '55555555-5555-4555-8555-555555555555',
    '44444444-4444-4444-8444-444444444444',
    25,
    0,
    25,
    'ACTIVE',
    0
)
ON CONFLICT (product_id, store_id) DO UPDATE SET
    available_stock = EXCLUDED.available_stock,
    reserved_stock = EXCLUDED.reserved_stock,
    total_stock = EXCLUDED.total_stock,
    sale_status = EXCLUDED.sale_status,
    version = EXCLUDED.version,
    updated_at = now();

INSERT INTO product_variant_inventory (
    public_variant_id,
    product_id,
    store_id,
    available_stock,
    reserved_stock,
    total_stock,
    sale_status,
    version
) VALUES
(
    'var_local_hoodie_m',
    '55555555-5555-4555-8555-555555555555',
    '44444444-4444-4444-8444-444444444444',
    14,
    0,
    14,
    'ACTIVE',
    0
),
(
    'var_local_hoodie_l',
    '55555555-5555-4555-8555-555555555555',
    '44444444-4444-4444-8444-444444444444',
    11,
    0,
    11,
    'ACTIVE',
    0
)
ON CONFLICT (public_variant_id) DO UPDATE SET
    product_id = EXCLUDED.product_id,
    store_id = EXCLUDED.store_id,
    available_stock = EXCLUDED.available_stock,
    reserved_stock = EXCLUDED.reserved_stock,
    total_stock = EXCLUDED.total_stock,
    sale_status = EXCLUDED.sale_status,
    version = EXCLUDED.version,
    updated_at = now();

INSERT INTO store_approval_stores (
    store_id,
    owner_user_id,
    active
) VALUES (
    '44444444-4444-4444-8444-444444444444',
    '33333333-3333-4333-8333-333333333333',
    true
)
ON CONFLICT (store_id) DO UPDATE SET
    owner_user_id = EXCLUDED.owner_user_id,
    active = EXCLUDED.active,
    updated_at = now();

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
    '44444444-4444-4444-8444-444444444444',
    '55555555-5555-4555-8555-555555555555',
    'Local Hoodie',
    0.010000000000000000,
    'ETH',
    1337,
    NULL,
    18,
    true
)
ON CONFLICT (store_id, product_id) DO UPDATE SET
    name = EXCLUDED.name,
    price_numeric = EXCLUDED.price_numeric,
    price_symbol = EXCLUDED.price_symbol,
    price_chain_id = EXCLUDED.price_chain_id,
    price_token_address = EXCLUDED.price_token_address,
    price_decimals = EXCLUDED.price_decimals,
    available = EXCLUDED.available,
    updated_at = now();

COMMIT;
SQL

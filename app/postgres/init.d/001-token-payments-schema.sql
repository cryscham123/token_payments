-- Token Payments adapter infrastructure schema draft.
-- This file is plain PostgreSQL SQL for docker-entrypoint-initdb.d.

CREATE TABLE IF NOT EXISTS outbox_messages (
    id BIGSERIAL PRIMARY KEY,
    message_identity TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('EVENT', 'COMMAND')),
    name TEXT NOT NULL,
    topic TEXT NOT NULL,
    message_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    headers JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (status IN ('READY', 'PUBLISHING', 'PUBLISHED', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    last_error TEXT,
    UNIQUE (kind, message_identity)
);

CREATE INDEX IF NOT EXISTS idx_outbox_messages_status_created_at
    ON outbox_messages (status, created_at);

CREATE INDEX IF NOT EXISTS idx_outbox_messages_topic_status
    ON outbox_messages (topic, status);

CREATE TABLE IF NOT EXISTS processed_messages (
    consumer TEXT NOT NULL,
    message_id UUID NOT NULL,
    order_id UUID,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, message_id)
);

CREATE INDEX IF NOT EXISTS idx_processed_messages_order_id
    ON processed_messages (order_id);

CREATE TABLE IF NOT EXISTS processed_commands (
    handler TEXT NOT NULL,
    command_id TEXT NOT NULL,
    order_id UUID,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (handler, command_id)
);

CREATE INDEX IF NOT EXISTS idx_processed_commands_order_id
    ON processed_commands (order_id);

CREATE TABLE IF NOT EXISTS auth_users (
    user_id UUID PRIMARY KEY,
    wallet_address TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('CUSTOMER', 'STORE_OWNER', 'ADMIN')),
    active BOOLEAN NOT NULL DEFAULT true,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_users_wallet_address
    ON auth_users (wallet_address);

CREATE TABLE IF NOT EXISTS auth_login_challenges (
    nonce_value TEXT PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    domain TEXT,
    uri TEXT,
    chain_id INTEGER CHECK (chain_id IS NULL OR chain_id > 0),
    expires_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ISSUED', 'VERIFIED', 'EXPIRED', 'REJECTED')),
    issued_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,
    rejected_reason TEXT CHECK (
        rejected_reason IS NULL OR rejected_reason IN (
            'INVALID_SIGNATURE',
            'EXPIRED_CHALLENGE',
            'REUSED_NONCE',
            'WALLET_MISMATCH',
            'SIWE_MESSAGE_MISMATCH'
        )
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_login_challenges_wallet_status
    ON auth_login_challenges (wallet_address, status, issued_at);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    wallet_address TEXT NOT NULL,
    refresh_token_hash TEXT NOT NULL,
    refresh_token_salt TEXT NOT NULL,
    refresh_token_rotation_version INTEGER NOT NULL CHECK (refresh_token_rotation_version >= 0),
    device_id TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (refresh_token_hash, refresh_token_salt, refresh_token_rotation_version)
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id
    ON auth_sessions (user_id);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at
    ON auth_sessions (expires_at);

CREATE TABLE IF NOT EXISTS order_customers (
    customer_id UUID PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE,
    wallet_address TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_order_customers_user_id
    ON order_customers (user_id);

CREATE TABLE IF NOT EXISTS order_stores (
    store_id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    store_address_id TEXT,
    store_address_street TEXT,
    store_wallet_address TEXT,
    supported_chain_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (store_address_id IS NULL AND store_address_street IS NULL)
        OR (store_address_id IS NOT NULL AND store_address_street IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_order_stores_owner_user_id
    ON order_stores (owner_user_id);

CREATE TABLE IF NOT EXISTS order_store_products (
    store_id UUID NOT NULL REFERENCES order_stores (store_id),
    product_id UUID NOT NULL,
    name TEXT NOT NULL,
    price_numeric NUMERIC(38, 18) NOT NULL CHECK (price_numeric >= 0),
    price_symbol TEXT NOT NULL,
    price_chain_id INTEGER NOT NULL CHECK (price_chain_id > 0),
    price_token_address TEXT,
    price_decimals INTEGER NOT NULL CHECK (price_decimals >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_order_store_products_store_id
    ON order_store_products (store_id);

CREATE TABLE IF NOT EXISTS orders (
    order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    store_id UUID NOT NULL,
    delivery_address_id TEXT NOT NULL,
    delivery_address_street TEXT NOT NULL,
    tracking_id UUID NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'PAID', 'APPROVED', 'CANCELLING', 'CANCELLED')),
    payment_id UUID,
    failure_messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_amount_numeric NUMERIC(38, 18) NOT NULL CHECK (total_amount_numeric >= 0),
    total_amount_symbol TEXT NOT NULL,
    total_amount_chain_id INTEGER NOT NULL CHECK (total_amount_chain_id > 0),
    total_amount_token_address TEXT,
    total_amount_decimals INTEGER NOT NULL CHECK (total_amount_decimals >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id
    ON orders (customer_id);

CREATE INDEX IF NOT EXISTS idx_orders_store_status
    ON orders (store_id, status);

CREATE INDEX IF NOT EXISTS idx_orders_tracking_id
    ON orders (tracking_id);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders (order_id),
    product_id UUID NOT NULL,
    product_snapshot_created_at TIMESTAMPTZ NOT NULL,
    product_snapshot_name TEXT NOT NULL,
    unit_price_numeric NUMERIC(38, 18) NOT NULL CHECK (unit_price_numeric >= 0),
    unit_price_symbol TEXT NOT NULL,
    unit_price_chain_id INTEGER NOT NULL CHECK (unit_price_chain_id > 0),
    unit_price_token_address TEXT,
    unit_price_decimals INTEGER NOT NULL CHECK (unit_price_decimals >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    subtotal_numeric NUMERIC(38, 18) NOT NULL CHECK (subtotal_numeric >= 0),
    subtotal_symbol TEXT NOT NULL,
    subtotal_chain_id INTEGER NOT NULL CHECK (subtotal_chain_id > 0),
    subtotal_token_address TEXT,
    subtotal_decimals INTEGER NOT NULL CHECK (subtotal_decimals >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id
    ON order_items (order_id);

CREATE TABLE IF NOT EXISTS product_inventory (
    product_id UUID NOT NULL,
    store_id UUID NOT NULL,
    available_stock INTEGER NOT NULL CHECK (available_stock >= 0),
    reserved_stock INTEGER NOT NULL DEFAULT 0 CHECK (reserved_stock >= 0),
    total_stock INTEGER NOT NULL CHECK (total_stock >= 0),
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, store_id),
    CHECK (available_stock + reserved_stock <= total_stock)
);

CREATE INDEX IF NOT EXISTS idx_product_inventory_store_id
    ON product_inventory (store_id);

CREATE TABLE IF NOT EXISTS inventory_reservations (
    reservation_id UUID PRIMARY KEY,
    product_id UUID NOT NULL,
    store_id UUID NOT NULL,
    order_id UUID NOT NULL,
    reserved_qty INTEGER NOT NULL CHECK (reserved_qty > 0),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (product_id, store_id, order_id),
    FOREIGN KEY (product_id, store_id)
        REFERENCES product_inventory (product_id, store_id)
);

CREATE INDEX IF NOT EXISTS idx_inventory_reservations_order_id
    ON inventory_reservations (order_id);

CREATE INDEX IF NOT EXISTS idx_inventory_reservations_status_created_at
    ON inventory_reservations (status, created_at);

CREATE TABLE IF NOT EXISTS payments (
    payment_id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    amount_numeric NUMERIC(38, 18) NOT NULL CHECK (amount_numeric >= 0),
    amount_symbol TEXT NOT NULL,
    amount_chain_id INTEGER NOT NULL CHECK (amount_chain_id > 0),
    amount_token_address TEXT,
    amount_decimals INTEGER NOT NULL CHECK (amount_decimals >= 0),
    status TEXT NOT NULL CHECK (
        status IN (
            'INITIATED',
            'AWAITING_SIGNATURE',
            'SUBMITTED',
            'CONFIRMING',
            'CONFIRMED',
            'FAILED',
            'EXPIRED',
            'REFUNDED'
        )
    ),
    wallet_from TEXT NOT NULL,
    wallet_to TEXT NOT NULL,
    chain_id INTEGER NOT NULL CHECK (chain_id > 0),
    chain_name TEXT NOT NULL,
    tx_hash TEXT,
    gas_estimated_fee NUMERIC(38, 18),
    gas_fee_symbol TEXT,
    gas_fee_chain_id INTEGER CHECK (gas_fee_chain_id IS NULL OR gas_fee_chain_id > 0),
    gas_fee_token_address TEXT,
    gas_fee_decimals INTEGER CHECK (gas_fee_decimals IS NULL OR gas_fee_decimals >= 0),
    gas_limit NUMERIC(38, 0),
    gas_buffer_rate NUMERIC(10, 6),
    gas_max_fee NUMERIC(38, 18),
    receipt_block_number INTEGER CHECK (receipt_block_number IS NULL OR receipt_block_number >= 0),
    receipt_gas_used INTEGER CHECK (receipt_gas_used IS NULL OR receipt_gas_used > 0),
    failure_reason TEXT,
    refund_tx_hash TEXT,
    refund_block_number INTEGER CHECK (refund_block_number IS NULL OR refund_block_number >= 0),
    refund_gas_used INTEGER CHECK (refund_gas_used IS NULL OR refund_gas_used > 0),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (order_id)
);

CREATE INDEX IF NOT EXISTS idx_payments_status_expires_at
    ON payments (status, expires_at);

CREATE INDEX IF NOT EXISTS idx_payments_order_id
    ON payments (order_id);

CREATE INDEX IF NOT EXISTS idx_payments_tx_hash
    ON payments (tx_hash);

CREATE TABLE IF NOT EXISTS payment_authorizations (
    payment_id UUID PRIMARY KEY REFERENCES payments (payment_id),
    user_id UUID NOT NULL,
    wallet_address TEXT NOT NULL,
    chain_id INTEGER NOT NULL CHECK (chain_id > 0),
    chain_name TEXT NOT NULL,
    request_id TEXT NOT NULL,
    amount_numeric NUMERIC(38, 18) NOT NULL CHECK (amount_numeric >= 0),
    amount_symbol TEXT NOT NULL,
    amount_chain_id INTEGER NOT NULL CHECK (amount_chain_id > 0),
    amount_token_address TEXT,
    amount_decimals INTEGER NOT NULL CHECK (amount_decimals >= 0),
    to_wallet_address TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('REQUESTED', 'AUTHORIZED', 'EXPIRED', 'REJECTED')),
    tx_hash TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    authorized_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (request_id)
);

CREATE INDEX IF NOT EXISTS idx_payment_authorizations_status_expires_at
    ON payment_authorizations (status, expires_at);

CREATE TABLE IF NOT EXISTS store_approval_stores (
    store_id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_store_approval_stores_owner_user_id
    ON store_approval_stores (owner_user_id);

CREATE TABLE IF NOT EXISTS store_approval_products (
    store_id UUID NOT NULL REFERENCES store_approval_stores (store_id),
    product_id UUID NOT NULL,
    name TEXT NOT NULL,
    price_numeric NUMERIC(38, 18) NOT NULL CHECK (price_numeric >= 0),
    price_symbol TEXT NOT NULL,
    price_chain_id INTEGER NOT NULL CHECK (price_chain_id > 0),
    price_token_address TEXT,
    price_decimals INTEGER NOT NULL CHECK (price_decimals >= 0),
    available BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_store_approval_products_store_available
    ON store_approval_products (store_id, available);

CREATE TABLE IF NOT EXISTS store_approval_order_details (
    order_id UUID PRIMARY KEY,
    store_id UUID NOT NULL,
    order_status TEXT NOT NULL,
    total_amount_numeric NUMERIC(38, 18) NOT NULL CHECK (total_amount_numeric >= 0),
    total_amount_symbol TEXT NOT NULL,
    total_amount_chain_id INTEGER NOT NULL CHECK (total_amount_chain_id > 0),
    total_amount_token_address TEXT,
    total_amount_decimals INTEGER NOT NULL CHECK (total_amount_decimals >= 0),
    product_snapshots JSONB NOT NULL,
    approval_status TEXT NOT NULL CHECK (approval_status IN ('PENDING', 'APPROVED', 'REJECTED')),
    rejection_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_store_approval_order_details_store_status
    ON store_approval_order_details (store_id, approval_status);

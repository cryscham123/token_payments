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
    gas_limit NUMERIC(38, 0),
    gas_buffer_rate NUMERIC(10, 6),
    gas_max_fee NUMERIC(38, 18),
    expires_at TIMESTAMPTZ,
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
    expires_at TIMESTAMPTZ NOT NULL,
    authorized_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (request_id)
);

CREATE INDEX IF NOT EXISTS idx_payment_authorizations_status_expires_at
    ON payment_authorizations (status, expires_at);

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

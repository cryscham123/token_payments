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

CREATE TABLE IF NOT EXISTS auth_user_wallets (
    wallet_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth_users (user_id),
    wallet_address TEXT NOT NULL,
    chain_id INTEGER NOT NULL CHECK (chain_id > 0),
    wallet_type TEXT NOT NULL CHECK (wallet_type IN ('EOA', 'SMART_WALLET')),
    verification_status TEXT NOT NULL CHECK (verification_status IN ('VERIFIED', 'PENDING', 'REVOKED')),
    "primary" BOOLEAN NOT NULL DEFAULT false,
    linked_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_user_wallets_user_chain_address
    ON auth_user_wallets (user_id, chain_id, wallet_address) WHERE (verification_status <> 'REVOKED');

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_user_wallets_active_chain_address
    ON auth_user_wallets (chain_id, wallet_address) WHERE (verification_status = 'VERIFIED' AND revoked_at IS NULL);

CREATE INDEX IF NOT EXISTS idx_auth_user_wallets_user_id
    ON auth_user_wallets (user_id);

CREATE TABLE IF NOT EXISTS auth_user_profiles (
    user_id UUID PRIMARY KEY REFERENCES auth_users (user_id),
    display_name TEXT,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        status <> 'DELETED'
        OR display_name IS NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_auth_user_profiles_status
    ON auth_user_profiles (status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_user_profiles_display_name_unique
    ON auth_user_profiles (lower(display_name)) WHERE status <> 'DELETED';

CREATE TABLE IF NOT EXISTS auth_oauth_identities (
    oauth_identity_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_subject TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES auth_users (user_id),
    wallet_id UUID REFERENCES auth_user_wallets (wallet_id),
    linked_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (provider <> ''),
    CHECK (provider_subject <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_oauth_identities_active_provider_subject
    ON auth_oauth_identities (provider, provider_subject) WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_auth_oauth_identities_user_active
    ON auth_oauth_identities (user_id, revoked_at);

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
    purpose TEXT NOT NULL DEFAULT 'LOGIN' CHECK (purpose IN ('LOGIN', 'WALLET_LINK')),
    target_user_id UUID REFERENCES auth_users (user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_login_challenges_wallet_status
    ON auth_login_challenges (wallet_address, status, issued_at);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    login_wallet_id UUID NOT NULL REFERENCES auth_user_wallets (wallet_id),
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

CREATE TABLE IF NOT EXISTS auth_groups (
    group_id UUID PRIMARY KEY,
    group_type TEXT NOT NULL CHECK (group_type IN ('PERSONAL', 'MERCHANT', 'PLATFORM')),
    name TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        group_type <> 'MERCHANT'
        OR (resource_type IS NOT NULL AND resource_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_auth_groups_resource
    ON auth_groups (group_type, resource_type, resource_id);

CREATE TABLE IF NOT EXISTS auth_roles (
    role_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    group_type TEXT NOT NULL CHECK (group_type IN ('PERSONAL', 'MERCHANT', 'PLATFORM')),
    active BOOLEAN NOT NULL DEFAULT true,
    merchant_assignable BOOLEAN NOT NULL DEFAULT false,
    owner_role BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (NOT (merchant_assignable AND owner_role))
);

CREATE INDEX IF NOT EXISTS idx_auth_roles_group_type_active
    ON auth_roles (group_type, active);

CREATE TABLE IF NOT EXISTS auth_permissions (
    permission_name TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_role_permissions (
    role_id TEXT NOT NULL REFERENCES auth_roles (role_id),
    permission_name TEXT NOT NULL REFERENCES auth_permissions (permission_name),
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (role_id, permission_name)
);

CREATE TABLE IF NOT EXISTS auth_group_memberships (
    group_id UUID NOT NULL REFERENCES auth_groups (group_id),
    user_id UUID NOT NULL REFERENCES auth_users (user_id),
    role_id TEXT NOT NULL REFERENCES auth_roles (role_id),
    active BOOLEAN NOT NULL DEFAULT true,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version INT NOT NULL DEFAULT 1,
    PRIMARY KEY (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_auth_group_memberships_user_active
    ON auth_group_memberships (user_id, active);

CREATE TABLE IF NOT EXISTS auth_group_invitations (
    invitation_id UUID PRIMARY KEY,
    group_id UUID NOT NULL REFERENCES auth_groups (group_id),
    invited_role_id TEXT NOT NULL REFERENCES auth_roles (role_id),
    invited_by_user_id UUID NOT NULL REFERENCES auth_users (user_id),
    target_user_id UUID REFERENCES auth_users (user_id),
    target_wallet_address TEXT,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'ACCEPTED', 'REVOKED', 'EXPIRED')),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        target_user_id IS NOT NULL
        OR target_wallet_address IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_auth_group_invitations_group_status
    ON auth_group_invitations (group_id, status, created_at);

CREATE TABLE IF NOT EXISTS store_catalog_stores (
    store_id UUID PRIMARY KEY,
    public_store_id TEXT NOT NULL,
    owner_user_id UUID NOT NULL REFERENCES auth_users (user_id),
    group_id UUID REFERENCES auth_groups (group_id),
    display_name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED')),
    support_email TEXT,
    support_email_public BOOLEAN NOT NULL DEFAULT false,
    business_registration_label TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    store_wallet_address TEXT NOT NULL,
    supported_chain_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    supported_payment_asset_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(public_store_id) BETWEEN 8 AND 64),
    CHECK (public_store_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    CHECK (length(display_name) BETWEEN 1 AND 120),
    CHECK (description IS NULL OR length(description) <= 2000),
    CHECK (support_email IS NULL OR length(support_email) <= 254),
    CHECK (business_registration_label IS NULL OR length(business_registration_label) <= 160)
);

ALTER TABLE IF EXISTS store_catalog_stores
    ADD COLUMN IF NOT EXISTS public_store_id TEXT;

ALTER TABLE IF EXISTS store_catalog_stores
    ADD COLUMN IF NOT EXISTS display_name TEXT;

ALTER TABLE IF EXISTS store_catalog_stores
    ADD COLUMN IF NOT EXISTS description TEXT;

ALTER TABLE IF EXISTS store_catalog_stores
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ACTIVE';

ALTER TABLE IF EXISTS store_catalog_stores
    ADD COLUMN IF NOT EXISTS support_email TEXT;

ALTER TABLE IF EXISTS store_catalog_stores
    ADD COLUMN IF NOT EXISTS support_email_public BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE IF EXISTS store_catalog_stores
    ADD COLUMN IF NOT EXISTS business_registration_label TEXT;

UPDATE store_catalog_stores
SET public_store_id = 'st_' || substr(md5(store_id::text), 1, 24)
WHERE public_store_id IS NULL;

UPDATE store_catalog_stores
SET display_name = 'Untitled Store'
WHERE display_name IS NULL;

UPDATE store_catalog_stores
SET status = 'ACTIVE'
WHERE status IS NULL;

ALTER TABLE IF EXISTS store_catalog_stores
    ALTER COLUMN public_store_id SET NOT NULL;

ALTER TABLE IF EXISTS store_catalog_stores
    ALTER COLUMN display_name SET NOT NULL;

ALTER TABLE IF EXISTS store_catalog_stores
    ALTER COLUMN status SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_store_catalog_stores_public_store_id
    ON store_catalog_stores (public_store_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_store_catalog_stores_display_name_unique
    ON store_catalog_stores (lower(display_name));

CREATE INDEX IF NOT EXISTS idx_store_catalog_stores_owner_user_id
    ON store_catalog_stores (owner_user_id);

CREATE INDEX IF NOT EXISTS idx_store_catalog_stores_group_id
    ON store_catalog_stores (group_id);

CREATE TABLE IF NOT EXISTS store_catalog_store_memberships (
    store_id UUID NOT NULL REFERENCES store_catalog_stores (store_id),
    user_id UUID NOT NULL REFERENCES auth_users (user_id),
    role TEXT NOT NULL CHECK (role IN ('OWNER', 'MANAGER')),
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_store_catalog_memberships_user_active
    ON store_catalog_store_memberships (user_id, active);

CREATE TABLE IF NOT EXISTS store_catalog_products (
    store_id UUID NOT NULL REFERENCES store_catalog_stores (store_id),
    product_id UUID NOT NULL,
    public_product_id TEXT NOT NULL,
    public_store_id TEXT NOT NULL,
    title TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    media JSONB NOT NULL DEFAULT '[]'::jsonb,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED')),
    visibility TEXT NOT NULL DEFAULT 'PUBLIC' CHECK (visibility IN ('PUBLIC', 'PRIVATE')),
    price_amount NUMERIC(38, 2) NOT NULL CHECK (price_amount >= 0),
    price_currency TEXT NOT NULL DEFAULT 'USD',
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, product_id)
);

ALTER TABLE IF EXISTS store_catalog_products
    ADD COLUMN IF NOT EXISTS public_product_id TEXT;

ALTER TABLE IF EXISTS store_catalog_products
    ADD COLUMN IF NOT EXISTS public_store_id TEXT;

ALTER TABLE IF EXISTS store_catalog_products
    ADD COLUMN IF NOT EXISTS title TEXT;

ALTER TABLE IF EXISTS store_catalog_products
    ADD COLUMN IF NOT EXISTS description TEXT;

ALTER TABLE IF EXISTS store_catalog_products
    ADD COLUMN IF NOT EXISTS category TEXT;

ALTER TABLE IF EXISTS store_catalog_products
    ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE IF EXISTS store_catalog_products
    ADD COLUMN IF NOT EXISTS media JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE IF EXISTS store_catalog_products
    ADD COLUMN IF NOT EXISTS attributes JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE IF EXISTS store_catalog_products
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ACTIVE';

ALTER TABLE IF EXISTS store_catalog_products
    ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'PUBLIC';

UPDATE store_catalog_products
SET public_product_id = COALESCE(public_product_id, 'prd_' || substr(md5(product_id::text), 1, 20));

UPDATE store_catalog_products p
SET public_store_id = COALESCE(p.public_store_id, s.public_store_id)
FROM store_catalog_stores s
WHERE p.store_id = s.store_id;

UPDATE store_catalog_products
SET title = COALESCE(title, name);

ALTER TABLE IF EXISTS store_catalog_products
    ALTER COLUMN public_product_id SET NOT NULL;

ALTER TABLE IF EXISTS store_catalog_products
    ALTER COLUMN public_store_id SET NOT NULL;

ALTER TABLE IF EXISTS store_catalog_products
    ALTER COLUMN title SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_store_catalog_products_store_active
    ON store_catalog_products (store_id, active);

CREATE UNIQUE INDEX IF NOT EXISTS idx_store_catalog_products_public_store_product
    ON store_catalog_products (public_store_id, public_product_id);

CREATE INDEX IF NOT EXISTS idx_store_catalog_products_store_status_visibility
    ON store_catalog_products (store_id, status, visibility);

CREATE TABLE IF NOT EXISTS store_catalog_product_options (
    store_id UUID NOT NULL,
    product_id UUID NOT NULL,
    option_id TEXT NOT NULL,
    option_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    required BOOLEAN NOT NULL DEFAULT true,
    selection_type TEXT NOT NULL DEFAULT 'SINGLE' CHECK (selection_type IN ('SINGLE', 'MULTI')),
    option_type TEXT NOT NULL DEFAULT 'VARIANT' CHECK (option_type IN ('VARIANT', 'ADD_ON')),
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, product_id, option_id),
    FOREIGN KEY (store_id, product_id) REFERENCES store_catalog_products (store_id, product_id),
    UNIQUE (store_id, product_id, option_key)
);

CREATE TABLE IF NOT EXISTS store_catalog_product_option_values (
    store_id UUID NOT NULL,
    product_id UUID NOT NULL,
    option_id TEXT NOT NULL,
    option_value_id TEXT NOT NULL,
    value_key TEXT NOT NULL,
    display_value TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    price_delta_amount NUMERIC(38, 2) CHECK (price_delta_amount IS NULL OR price_delta_amount >= 0),
    price_delta_currency TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, product_id, option_id, option_value_id),
    FOREIGN KEY (store_id, product_id, option_id)
        REFERENCES store_catalog_product_options (store_id, product_id, option_id),
    UNIQUE (store_id, product_id, option_id, value_key)
);

CREATE TABLE IF NOT EXISTS store_catalog_product_variants (
    store_id UUID NOT NULL,
    product_id UUID NOT NULL,
    public_variant_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    option_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    sku TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED')),
    active BOOLEAN NOT NULL DEFAULT true,
    sort_order INTEGER NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    price_delta_amount NUMERIC(38, 2) NOT NULL CHECK (price_delta_amount >= 0),
    price_delta_currency TEXT NOT NULL DEFAULT 'USD',
    price_delta_numeric NUMERIC(38, 2) NOT NULL DEFAULT 0 CHECK (price_delta_numeric >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, product_id, public_variant_id),
    FOREIGN KEY (store_id, product_id) REFERENCES store_catalog_products (store_id, product_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_store_catalog_product_variants_public
    ON store_catalog_product_variants (public_variant_id);

CREATE TABLE IF NOT EXISTS store_catalog_product_variant_option_values (
    store_id UUID NOT NULL,
    product_id UUID NOT NULL,
    public_variant_id TEXT NOT NULL,
    option_id TEXT NOT NULL,
    option_value_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, product_id, public_variant_id, option_id),
    FOREIGN KEY (store_id, product_id, public_variant_id)
        REFERENCES store_catalog_product_variants (store_id, product_id, public_variant_id),
    FOREIGN KEY (store_id, product_id, option_id, option_value_id)
        REFERENCES store_catalog_product_option_values (store_id, product_id, option_id, option_value_id)
);

CREATE TABLE IF NOT EXISTS store_catalog_idempotency (
    handler TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    response_payload JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (handler, idempotency_key)
);

CREATE TABLE IF NOT EXISTS store_catalog_audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    actor_user_id UUID NOT NULL REFERENCES auth_users (user_id),
    action TEXT NOT NULL,
    store_id UUID,
    product_id UUID,
    target_user_id UUID,
    group_id UUID,
    permission TEXT,
    resource_type TEXT,
    resource_id TEXT,
    request_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    before_state JSONB NOT NULL,
    after_state JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (idempotency_key, action)
);

CREATE INDEX IF NOT EXISTS idx_store_catalog_audit_store_recorded_at
    ON store_catalog_audit_log (store_id, recorded_at);

CREATE TABLE IF NOT EXISTS order_customers (
    customer_id UUID PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE,
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
    supported_payment_asset_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
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
    price_amount NUMERIC(38, 2) NOT NULL CHECK (price_amount >= 0),
    price_currency TEXT NOT NULL DEFAULT 'USD',
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
    public_variant_id TEXT,
    selected_options JSONB NOT NULL DEFAULT '{}'::jsonb,
    line_key TEXT NOT NULL DEFAULT '',
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
    media JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id
    ON order_items (order_id);

-- product_inventory is a per-(product, store) registry only. Stock is tracked
-- exclusively in product_variant_inventory at the variant (required-option) unit;
-- option-less products get a hidden default variant. This table remains because
-- product_variant_inventory and inventory_reservations FK-reference it.
CREATE TABLE IF NOT EXISTS product_inventory (
    product_id UUID NOT NULL,
    store_id UUID NOT NULL,
    sale_status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (sale_status IN ('ACTIVE', 'PAUSED')),
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, store_id)
);

CREATE INDEX IF NOT EXISTS idx_product_inventory_store_id
    ON product_inventory (store_id);

CREATE TABLE IF NOT EXISTS product_variant_inventory (
    public_variant_id TEXT PRIMARY KEY,
    product_id UUID NOT NULL,
    store_id UUID NOT NULL,
    available_stock INTEGER NOT NULL CHECK (available_stock >= 0),
    reserved_stock INTEGER NOT NULL DEFAULT 0 CHECK (reserved_stock >= 0),
    total_stock INTEGER NOT NULL CHECK (total_stock >= 0),
    sale_status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (sale_status IN ('ACTIVE', 'PAUSED')),
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (product_id, store_id, public_variant_id),
    CHECK (available_stock + reserved_stock = total_stock),
    FOREIGN KEY (product_id, store_id)
        REFERENCES product_inventory (product_id, store_id),
    FOREIGN KEY (store_id, product_id, public_variant_id)
        REFERENCES store_catalog_product_variants (store_id, product_id, public_variant_id)
);

CREATE INDEX IF NOT EXISTS idx_product_variant_inventory_store_product
    ON product_variant_inventory (store_id, product_id);

CREATE TABLE IF NOT EXISTS inventory_reservations (
    reservation_id UUID PRIMARY KEY,
    product_id UUID NOT NULL,
    store_id UUID NOT NULL,
    public_variant_id TEXT,
    order_id UUID NOT NULL,
    reserved_qty INTEGER NOT NULL CHECK (reserved_qty > 0),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (product_id, store_id)
        REFERENCES product_inventory (product_id, store_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_reservations_order_inventory_target
    ON inventory_reservations (product_id, store_id, order_id, COALESCE(public_variant_id, ''));

CREATE INDEX IF NOT EXISTS idx_inventory_reservations_order_id
    ON inventory_reservations (order_id);

CREATE INDEX IF NOT EXISTS idx_inventory_reservations_status_created_at
    ON inventory_reservations (status, created_at);

CREATE TABLE IF NOT EXISTS inventory_audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    actor_user_id UUID NOT NULL,
    actor_role TEXT NOT NULL CHECK (actor_role IN ('CUSTOMER', 'STORE_OWNER', 'ADMIN')),
    store_id UUID NOT NULL,
    product_id UUID NOT NULL,
    public_variant_id TEXT,
    action TEXT NOT NULL CHECK (action IN ('increaseStock', 'correctStock', 'pauseSales', 'resumeSales')),
    before_available_stock INTEGER NOT NULL CHECK (before_available_stock >= 0),
    before_reserved_stock INTEGER NOT NULL CHECK (before_reserved_stock >= 0),
    before_total_stock INTEGER NOT NULL CHECK (before_total_stock >= 0),
    before_sale_status TEXT NOT NULL CHECK (before_sale_status IN ('ACTIVE', 'PAUSED')),
    after_available_stock INTEGER NOT NULL CHECK (after_available_stock >= 0),
    after_reserved_stock INTEGER NOT NULL CHECK (after_reserved_stock >= 0),
    after_total_stock INTEGER NOT NULL CHECK (after_total_stock >= 0),
    after_sale_status TEXT NOT NULL CHECK (after_sale_status IN ('ACTIVE', 'PAUSED')),
    reason TEXT NOT NULL,
    request_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    actor_store_role TEXT CHECK (actor_store_role IS NULL OR actor_store_role IN ('OWNER', 'MANAGER')),
    recorded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (product_id, store_id)
        REFERENCES product_inventory (product_id, store_id)
);

CREATE INDEX IF NOT EXISTS idx_inventory_audit_store_recorded_at
    ON inventory_audit_log (store_id, recorded_at);

CREATE TABLE IF NOT EXISTS chains (
    chain_id INTEGER PRIMARY KEY CHECK (chain_id > 0),
    display_name TEXT NOT NULL,
    native_symbol TEXT NOT NULL,
    explorer_url_template TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payment_assets (
    asset_id TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL CHECK (asset_type IN ('NATIVE', 'ERC20')),
    chain_id INTEGER NOT NULL REFERENCES chains (chain_id),
    symbol TEXT NOT NULL,
    decimals INTEGER NOT NULL CHECK (decimals >= 0),
    contract_address TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (asset_type = 'NATIVE' AND contract_address IS NULL)
        OR (asset_type = 'ERC20' AND contract_address IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_payment_assets_chain_enabled
    ON payment_assets (chain_id, enabled);

INSERT INTO chains (chain_id, display_name, native_symbol, enabled)
VALUES
    (1337, 'Local Test Network', 'ETH', true),
    (11155111, 'Sepolia', 'ETH', true)
ON CONFLICT (chain_id) DO NOTHING;

INSERT INTO payment_assets (asset_id, asset_type, chain_id, symbol, decimals, contract_address, enabled)
VALUES
    ('local-native-eth', 'NATIVE', 1337, 'ETH', 18, NULL, true),
    ('sepolia-native-eth', 'NATIVE', 11155111, 'ETH', 18, NULL, true)
ON CONFLICT (asset_id) DO NOTHING;

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
            'CANCELLED',
            'REFUNDED'
        )
    ),
    wallet_from TEXT NOT NULL,
    wallet_to TEXT NOT NULL,
    chain_id INTEGER NOT NULL CHECK (chain_id > 0),
    payer_wallet_id UUID REFERENCES auth_user_wallets (wallet_id),
    payment_asset_id TEXT REFERENCES payment_assets (asset_id),
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
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
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
    payer_wallet_id UUID REFERENCES auth_user_wallets (wallet_id),
    wallet_address TEXT NOT NULL,
    chain_id INTEGER NOT NULL CHECK (chain_id > 0),
    payment_asset_id TEXT REFERENCES payment_assets (asset_id),
    expected_amount_minor_units NUMERIC(78, 0),
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

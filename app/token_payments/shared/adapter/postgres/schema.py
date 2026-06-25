"""PostgreSQL schema compatibility helpers for live local runtimes."""

from __future__ import annotations

from typing import Any


POSTGRES_SCHEMA_COMPATIBILITY_SQL: tuple[str, ...] = (
    """
    ALTER TABLE IF EXISTS auth_users
        ADD COLUMN IF NOT EXISTS user_id UUID
    """,
    """
    ALTER TABLE IF EXISTS auth_users
        ADD COLUMN IF NOT EXISTS wallet_address TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_users
        ADD COLUMN IF NOT EXISTS role TEXT
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_user_profiles (
        user_id UUID PRIMARY KEY,
        display_name TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED', 'DELETED')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK (
            status <> 'DELETED'
            OR display_name IS NULL
        )
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auth_user_profiles_status
        ON auth_user_profiles (status)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_user_profiles_display_name_unique
        ON auth_user_profiles (lower(display_name)) WHERE status <> 'DELETED'
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_oauth_identities (
        oauth_identity_id UUID PRIMARY KEY,
        provider TEXT NOT NULL,
        provider_subject TEXT NOT NULL,
        user_id UUID NOT NULL,
        wallet_id UUID,
        linked_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK (provider <> ''),
        CHECK (provider_subject <> '')
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_oauth_identities_active_provider_subject
        ON auth_oauth_identities (provider, provider_subject) WHERE revoked_at IS NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auth_oauth_identities_user_active
        ON auth_oauth_identities (user_id, revoked_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_groups (
        group_id UUID PRIMARY KEY,
        group_type TEXT NOT NULL CHECK (group_type IN ('PERSONAL', 'MERCHANT', 'PLATFORM')),
        name TEXT NOT NULL,
        resource_type TEXT,
        resource_id TEXT,
        active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_roles (
        role_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        group_type TEXT NOT NULL CHECK (group_type IN ('PERSONAL', 'MERCHANT', 'PLATFORM')),
        active BOOLEAN NOT NULL DEFAULT true,
        merchant_assignable BOOLEAN NOT NULL DEFAULT false,
        owner_role BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_permissions (
        permission_name TEXT PRIMARY KEY,
        description TEXT NOT NULL DEFAULT '',
        active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_role_permissions (
        role_id TEXT NOT NULL,
        permission_name TEXT NOT NULL,
        active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (role_id, permission_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_group_memberships (
        group_id UUID NOT NULL,
        user_id UUID NOT NULL,
        role_id TEXT NOT NULL,
        active BOOLEAN NOT NULL DEFAULT true,
        joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (group_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_group_invitations (
        invitation_id UUID PRIMARY KEY,
        group_id UUID NOT NULL,
        invited_role_id TEXT NOT NULL,
        invited_by_user_id UUID NOT NULL,
        target_user_id UUID,
        target_wallet_address TEXT,
        status TEXT NOT NULL CHECK (status IN ('PENDING', 'ACCEPTED', 'REVOKED', 'EXPIRED')),
        expires_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE IF EXISTS auth_users
        ADD COLUMN IF NOT EXISTS active BOOLEAN
    """,
    """
    ALTER TABLE IF EXISTS auth_users
        ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS wallet_address TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS nonce_value TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS domain TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS uri TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS chain_id INTEGER
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS status TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS issued_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS rejected_reason TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS purpose TEXT NOT NULL DEFAULT 'LOGIN'
    """,
    """
    ALTER TABLE IF EXISTS auth_login_challenges
        ADD COLUMN IF NOT EXISTS target_user_id UUID
    """,
    """
    ALTER TABLE IF EXISTS auth_sessions
        ADD COLUMN IF NOT EXISTS session_id UUID
    """,
    """
    ALTER TABLE IF EXISTS auth_sessions
        ADD COLUMN IF NOT EXISTS user_id UUID
    """,
    """
    ALTER TABLE IF EXISTS auth_sessions
        ADD COLUMN IF NOT EXISTS wallet_address TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_sessions
        ADD COLUMN IF NOT EXISTS refresh_token_hash TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_sessions
        ADD COLUMN IF NOT EXISTS refresh_token_salt TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_sessions
        ADD COLUMN IF NOT EXISTS refresh_token_rotation_version INTEGER
    """,
    """
    ALTER TABLE IF EXISTS auth_sessions
        ADD COLUMN IF NOT EXISTS device_id TEXT
    """,
    """
    ALTER TABLE IF EXISTS auth_sessions
        ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE IF EXISTS auth_sessions
        ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ
    """,
    """
    CREATE TABLE IF NOT EXISTS store_catalog_stores (
        store_id UUID PRIMARY KEY,
        public_store_id TEXT NOT NULL,
        owner_user_id UUID NOT NULL,
        group_id UUID,
        display_name TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        support_email TEXT,
        support_email_public BOOLEAN NOT NULL DEFAULT false,
        business_registration_label TEXT,
        active BOOLEAN NOT NULL DEFAULT true,
        store_wallet_address TEXT NOT NULL,
        supported_chain_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        supported_payment_asset_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ADD COLUMN IF NOT EXISTS supported_payment_asset_ids JSONB NOT NULL DEFAULT '[]'::jsonb
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ADD COLUMN IF NOT EXISTS group_id UUID
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ADD COLUMN IF NOT EXISTS public_store_id TEXT
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ADD COLUMN IF NOT EXISTS display_name TEXT
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ADD COLUMN IF NOT EXISTS description TEXT
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ACTIVE'
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ADD COLUMN IF NOT EXISTS support_email TEXT
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ADD COLUMN IF NOT EXISTS support_email_public BOOLEAN NOT NULL DEFAULT false
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ADD COLUMN IF NOT EXISTS business_registration_label TEXT
    """,
    """
    UPDATE store_catalog_stores
    SET public_store_id = 'st_' || substr(md5(store_id::text), 1, 24)
    WHERE public_store_id IS NULL
    """,
    """
    UPDATE store_catalog_stores
    SET display_name = 'Untitled Store'
    WHERE display_name IS NULL
    """,
    """
    UPDATE store_catalog_stores
    SET status = 'ACTIVE'
    WHERE status IS NULL
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ALTER COLUMN public_store_id SET NOT NULL
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ALTER COLUMN display_name SET NOT NULL
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ALTER COLUMN status SET NOT NULL
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_store_catalog_stores_public_store_id
        ON store_catalog_stores (public_store_id)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_store_catalog_stores_display_name_unique
        ON store_catalog_stores (lower(display_name))
    """,
    """
    CREATE TABLE IF NOT EXISTS store_catalog_store_memberships (
        store_id UUID NOT NULL,
        user_id UUID NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('OWNER', 'MANAGER')),
        active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (store_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS store_catalog_products (
        store_id UUID NOT NULL,
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
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_store_catalog_products_public_store_product
        ON store_catalog_products (public_store_id, public_product_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_store_catalog_products_store_status_visibility
        ON store_catalog_products (store_id, status, visibility)
    """,
    """
    CREATE TABLE IF NOT EXISTS store_catalog_idempotency (
        handler TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        response_payload JSONB NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (handler, idempotency_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS store_catalog_audit_log (
        audit_id BIGSERIAL PRIMARY KEY,
        actor_user_id UUID NOT NULL,
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
    )
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_audit_log
        ADD COLUMN IF NOT EXISTS group_id UUID
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_audit_log
        ADD COLUMN IF NOT EXISTS permission TEXT
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_audit_log
        ADD COLUMN IF NOT EXISTS resource_type TEXT
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_audit_log
        ADD COLUMN IF NOT EXISTS resource_id TEXT
    """,
    """
    ALTER TABLE IF EXISTS inventory_audit_log
        ADD COLUMN IF NOT EXISTS actor_store_role TEXT
    """,
    """
    ALTER TABLE IF EXISTS inventory_audit_log
        DROP CONSTRAINT IF EXISTS inventory_audit_log_actor_role_check
    """,
    """
    ALTER TABLE IF EXISTS inventory_audit_log
        ADD CONSTRAINT inventory_audit_log_actor_role_check
        CHECK (actor_role IN ('CUSTOMER', 'STORE_OWNER', 'ADMIN'))
    """,
    """
    CREATE TABLE IF NOT EXISTS chains (
        chain_id INTEGER PRIMARY KEY,
        display_name TEXT NOT NULL,
        native_symbol TEXT NOT NULL,
        explorer_url_template TEXT,
        enabled BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
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
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_payment_assets_chain_enabled
        ON payment_assets (chain_id, enabled)
    """,
    """
    INSERT INTO chains (chain_id, display_name, native_symbol, enabled)
    VALUES (1337, 'Local', 'ETH', true), (11155111, 'Sepolia', 'ETH', true)
    ON CONFLICT (chain_id) DO NOTHING
    """,
    """
    INSERT INTO payment_assets (asset_id, asset_type, chain_id, symbol, decimals, contract_address, enabled)
    VALUES ('local-native-eth', 'NATIVE', 1337, 'ETH', 18, NULL, true),
           ('sepolia-native-eth', 'NATIVE', 11155111, 'ETH', 18, NULL, true)
    ON CONFLICT (asset_id) DO NOTHING
    """,
    """
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
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_user_wallets_user_chain_address
        ON auth_user_wallets (user_id, chain_id, wallet_address) WHERE (verification_status <> 'REVOKED')
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_user_wallets_active_chain_address
        ON auth_user_wallets (chain_id, wallet_address) WHERE (verification_status = 'VERIFIED' AND revoked_at IS NULL)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auth_user_wallets_user_id
        ON auth_user_wallets (user_id)
    """,
    """
    ALTER TABLE IF EXISTS payments
        ADD COLUMN IF NOT EXISTS payer_wallet_id UUID REFERENCES auth_user_wallets (wallet_id)
    """,
    """
    ALTER TABLE IF EXISTS payments
        ADD COLUMN IF NOT EXISTS payment_asset_id TEXT REFERENCES payment_assets (asset_id)
    """,
    """
    ALTER TABLE IF EXISTS payments
        ADD COLUMN IF NOT EXISTS items JSONB NOT NULL DEFAULT '[]'::jsonb
    """,
    """
    ALTER TABLE IF EXISTS payment_authorizations
        ADD COLUMN IF NOT EXISTS payer_wallet_id UUID REFERENCES auth_user_wallets (wallet_id)
    """,
    """
    ALTER TABLE IF EXISTS payment_authorizations
        ADD COLUMN IF NOT EXISTS payment_asset_id TEXT REFERENCES payment_assets (asset_id)
    """,
    """
    ALTER TABLE IF EXISTS payment_authorizations
        ADD COLUMN IF NOT EXISTS expected_amount_minor_units NUMERIC(78, 0)
    """,
    """
    ALTER TABLE IF EXISTS payments
        DROP COLUMN IF EXISTS chain_name
    """,
    """
    ALTER TABLE IF EXISTS payment_authorizations
        DROP COLUMN IF EXISTS chain_name
    """,
    """
    INSERT INTO auth_user_wallets (
        wallet_id,
        user_id,
        wallet_address,
        chain_id,
        wallet_type,
        verification_status,
        "primary",
        linked_at
    )
    SELECT
        gen_random_uuid(),
        user_id,
        wallet_address,
        1,
        'EOA',
        'VERIFIED',
        true,
        created_at
    FROM auth_users
    ON CONFLICT DO NOTHING
    """,
    """
    ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS login_wallet_id UUID REFERENCES auth_user_wallets (wallet_id)
    """,
    """
    UPDATE auth_sessions s
    SET login_wallet_id = w.wallet_id
    FROM auth_user_wallets w
    WHERE s.user_id = w.user_id AND s.wallet_address = w.wallet_address
      AND s.login_wallet_id IS NULL
    """,
    """
    UPDATE auth_sessions s
    SET login_wallet_id = w.wallet_id
    FROM auth_user_wallets w
    WHERE s.user_id = w.user_id AND w."primary" = true
      AND s.login_wallet_id IS NULL
    """,
    """
    DELETE FROM auth_sessions WHERE login_wallet_id IS NULL
    """,
    """
    ALTER TABLE auth_sessions ALTER COLUMN login_wallet_id SET NOT NULL
    """,
    """
    ALTER TABLE auth_sessions DROP COLUMN IF EXISTS wallet_address
    """,
    """
    ALTER TABLE order_customers DROP COLUMN IF EXISTS wallet_address
    """,
    """
    ALTER TABLE auth_group_memberships ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1
    """,
)


def ensure_postgres_schema_compatibility(connection: Any) -> None:
    """Apply bounded additive compatibility updates for pre-existing local DBs."""

    execute = getattr(connection, "execute", None)
    if not callable(execute):
        raise TypeError("postgres schema compatibility requires a connection with execute()")
    for sql in POSTGRES_SCHEMA_COMPATIBILITY_SQL:
        execute(sql)
    commit = getattr(connection, "commit", None)
    if callable(commit):
        commit()


__all__ = ["POSTGRES_SCHEMA_COMPATIBILITY_SQL", "ensure_postgres_schema_compatibility"]

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
        target_email TEXT,
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
        owner_user_id UUID NOT NULL,
        group_id UUID,
        active BOOLEAN NOT NULL DEFAULT true,
        store_wallet_address TEXT NOT NULL,
        supported_chain_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    ALTER TABLE IF EXISTS store_catalog_stores
        ADD COLUMN IF NOT EXISTS group_id UUID
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
        name TEXT NOT NULL,
        price_numeric NUMERIC(38, 18) NOT NULL CHECK (price_numeric >= 0),
        price_symbol TEXT NOT NULL,
        price_chain_id INTEGER NOT NULL CHECK (price_chain_id > 0),
        price_token_address TEXT,
        price_decimals INTEGER NOT NULL CHECK (price_decimals >= 0),
        active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (store_id, product_id)
    )
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

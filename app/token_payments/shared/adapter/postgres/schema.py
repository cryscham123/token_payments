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

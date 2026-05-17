"""PostgreSQL repositories for the authentication context."""

from __future__ import annotations

from typing import Any, Mapping

from token_payments.contexts.auth.domain import (
    AuthNonce,
    AuthSession,
    ChallengeStatus,
    LoginChallenge,
    LoginFailureReason,
    RefreshTokenHash,
    SessionId,
    User,
    UserRole,
)
from token_payments.shared.adapter.postgres import PostgresConnection
from token_payments.shared.domain import UserId, WalletAddress


SELECT_USER_BY_ID_SQL = """
SELECT
    user_id,
    wallet_address,
    role,
    active,
    last_login_at
FROM auth_users
WHERE user_id = %(user_id)s
"""

SELECT_USER_BY_WALLET_SQL = """
SELECT
    user_id,
    wallet_address,
    role,
    active,
    last_login_at
FROM auth_users
WHERE wallet_address = %(wallet_address)s
"""

UPSERT_USER_SQL = """
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
ON CONFLICT (user_id) DO UPDATE SET
    wallet_address = EXCLUDED.wallet_address,
    role = EXCLUDED.role,
    active = EXCLUDED.active,
    last_login_at = EXCLUDED.last_login_at,
    updated_at = now()
"""

SELECT_CHALLENGE_BY_NONCE_SQL = """
SELECT
    wallet_address,
    nonce_value,
    domain,
    uri,
    chain_id,
    expires_at,
    status,
    issued_at,
    verified_at,
    rejected_reason
FROM auth_login_challenges
WHERE nonce_value = %(nonce_value)s
"""

SELECT_ISSUED_CHALLENGE_BY_WALLET_SQL = """
SELECT
    wallet_address,
    nonce_value,
    domain,
    uri,
    chain_id,
    expires_at,
    status,
    issued_at,
    verified_at,
    rejected_reason
FROM auth_login_challenges
WHERE wallet_address = %(wallet_address)s
  AND status = 'ISSUED'
ORDER BY issued_at DESC, nonce_value DESC
LIMIT 1
"""

UPSERT_CHALLENGE_SQL = """
INSERT INTO auth_login_challenges (
    wallet_address,
    nonce_value,
    domain,
    uri,
    chain_id,
    expires_at,
    status,
    issued_at,
    verified_at,
    rejected_reason
) VALUES (
    %(wallet_address)s,
    %(nonce_value)s,
    %(domain)s,
    %(uri)s,
    %(chain_id)s,
    %(expires_at)s,
    %(status)s,
    %(issued_at)s,
    %(verified_at)s,
    %(rejected_reason)s
)
ON CONFLICT (nonce_value) DO UPDATE SET
    wallet_address = EXCLUDED.wallet_address,
    domain = EXCLUDED.domain,
    uri = EXCLUDED.uri,
    chain_id = EXCLUDED.chain_id,
    expires_at = EXCLUDED.expires_at,
    status = EXCLUDED.status,
    issued_at = EXCLUDED.issued_at,
    verified_at = EXCLUDED.verified_at,
    rejected_reason = EXCLUDED.rejected_reason,
    updated_at = now()
"""

SELECT_SESSION_BY_ID_SQL = """
SELECT
    session_id,
    user_id,
    wallet_address,
    refresh_token_hash,
    refresh_token_salt,
    refresh_token_rotation_version,
    device_id,
    expires_at,
    revoked_at
FROM auth_sessions
WHERE session_id = %(session_id)s
"""

SELECT_SESSION_BY_REFRESH_TOKEN_HASH_SQL = """
SELECT
    session_id,
    user_id,
    wallet_address,
    refresh_token_hash,
    refresh_token_salt,
    refresh_token_rotation_version,
    device_id,
    expires_at,
    revoked_at
FROM auth_sessions
WHERE refresh_token_hash = %(refresh_token_hash)s
  AND refresh_token_salt = %(refresh_token_salt)s
  AND refresh_token_rotation_version = %(refresh_token_rotation_version)s
"""

UPSERT_SESSION_SQL = """
INSERT INTO auth_sessions (
    session_id,
    user_id,
    wallet_address,
    refresh_token_hash,
    refresh_token_salt,
    refresh_token_rotation_version,
    device_id,
    expires_at,
    revoked_at
) VALUES (
    %(session_id)s,
    %(user_id)s,
    %(wallet_address)s,
    %(refresh_token_hash)s,
    %(refresh_token_salt)s,
    %(refresh_token_rotation_version)s,
    %(device_id)s,
    %(expires_at)s,
    %(revoked_at)s
)
ON CONFLICT (session_id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    wallet_address = EXCLUDED.wallet_address,
    refresh_token_hash = EXCLUDED.refresh_token_hash,
    refresh_token_salt = EXCLUDED.refresh_token_salt,
    refresh_token_rotation_version = EXCLUDED.refresh_token_rotation_version,
    device_id = EXCLUDED.device_id,
    expires_at = EXCLUDED.expires_at,
    revoked_at = EXCLUDED.revoked_at,
    updated_at = now()
"""


class PostgresUserRepository:
    """Persist auth users inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def save(self, user: User) -> None:
        if not isinstance(user, User):
            raise ValueError("PostgresUserRepository.save requires a User")
        self._connection.execute(
            UPSERT_USER_SQL,
            {
                "user_id": str(user.user_id),
                "wallet_address": str(user.primary_wallet),
                "role": user.role.value,
                "active": user.active,
                "last_login_at": user.last_login_at,
            },
        )

    def get_by_id(self, user_id: UserId) -> User | None:
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresUserRepository.get_by_id requires a UserId")
        row = _fetch_one(self._connection.execute(SELECT_USER_BY_ID_SQL, {"user_id": str(user_id)}))
        return _row_to_user(row) if row is not None else None

    def get_by_wallet(self, wallet: WalletAddress) -> User | None:
        if not isinstance(wallet, WalletAddress):
            raise ValueError("PostgresUserRepository.get_by_wallet requires a WalletAddress")
        row = _fetch_one(
            self._connection.execute(
                SELECT_USER_BY_WALLET_SQL,
                {"wallet_address": str(wallet)},
            )
        )
        return _row_to_user(row) if row is not None else None


class PostgresLoginChallengeRepository:
    """Persist MetaMask login challenges inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def save(self, challenge: LoginChallenge) -> None:
        if not isinstance(challenge, LoginChallenge):
            raise ValueError("PostgresLoginChallengeRepository.save requires a LoginChallenge")
        self._connection.execute(
            UPSERT_CHALLENGE_SQL,
            {
                "wallet_address": str(challenge.wallet),
                "nonce_value": challenge.nonce.value,
                "domain": challenge.domain,
                "uri": challenge.uri,
                "chain_id": challenge.chain_id,
                "expires_at": challenge.nonce.expires_at,
                "status": challenge.status.value,
                "issued_at": challenge.issued_at,
                "verified_at": challenge.verified_at,
                "rejected_reason": (
                    challenge.rejected_reason.value if challenge.rejected_reason is not None else None
                ),
            },
        )

    def get_by_nonce(self, nonce: AuthNonce) -> LoginChallenge | None:
        if not isinstance(nonce, AuthNonce):
            raise ValueError("PostgresLoginChallengeRepository.get_by_nonce requires an AuthNonce")
        row = _fetch_one(
            self._connection.execute(
                SELECT_CHALLENGE_BY_NONCE_SQL,
                {"nonce_value": nonce.value},
            )
        )
        return _row_to_challenge(row) if row is not None else None

    def get_issued_by_wallet(self, wallet: WalletAddress) -> LoginChallenge | None:
        if not isinstance(wallet, WalletAddress):
            raise ValueError("PostgresLoginChallengeRepository.get_issued_by_wallet requires a WalletAddress")
        row = _fetch_one(
            self._connection.execute(
                SELECT_ISSUED_CHALLENGE_BY_WALLET_SQL,
                {"wallet_address": str(wallet)},
            )
        )
        return _row_to_challenge(row) if row is not None else None


class PostgresAuthSessionRepository:
    """Persist auth sessions inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def save(self, session: AuthSession) -> None:
        if not isinstance(session, AuthSession):
            raise ValueError("PostgresAuthSessionRepository.save requires an AuthSession")
        self._connection.execute(
            UPSERT_SESSION_SQL,
            {
                "session_id": str(session.session_id),
                "user_id": str(session.user_id),
                "wallet_address": str(session.wallet),
                "refresh_token_hash": session.refresh_token_hash.hash,
                "refresh_token_salt": session.refresh_token_hash.salt,
                "refresh_token_rotation_version": session.refresh_token_hash.rotation_version,
                "device_id": session.device_id,
                "expires_at": session.expires_at,
                "revoked_at": session.revoked_at,
            },
        )

    def get_by_id(self, session_id: SessionId) -> AuthSession | None:
        if not isinstance(session_id, SessionId):
            raise ValueError("PostgresAuthSessionRepository.get_by_id requires a SessionId")
        row = _fetch_one(self._connection.execute(SELECT_SESSION_BY_ID_SQL, {"session_id": str(session_id)}))
        return _row_to_session(row) if row is not None else None

    def get_by_refresh_token_hash(self, refresh_token_hash: RefreshTokenHash) -> AuthSession | None:
        if not isinstance(refresh_token_hash, RefreshTokenHash):
            raise ValueError("PostgresAuthSessionRepository.get_by_refresh_token_hash requires a RefreshTokenHash")
        row = _fetch_one(
            self._connection.execute(
                SELECT_SESSION_BY_REFRESH_TOKEN_HASH_SQL,
                {
                    "refresh_token_hash": refresh_token_hash.hash,
                    "refresh_token_salt": refresh_token_hash.salt,
                    "refresh_token_rotation_version": refresh_token_hash.rotation_version,
                },
            )
        )
        return _row_to_session(row) if row is not None else None


def _row_to_user(row: Mapping[str, Any] | object) -> User:
    return User(
        user_id=UserId(_row_value(row, "user_id")),
        primary_wallet=WalletAddress(str(_row_value(row, "wallet_address"))),
        role=UserRole(_row_value(row, "role")),
        active=bool(_row_value(row, "active")),
        last_login_at=_row_value(row, "last_login_at"),
    )


def _row_to_challenge(row: Mapping[str, Any] | object) -> LoginChallenge:
    rejected_reason = _row_value(row, "rejected_reason")
    return LoginChallenge(
        wallet=WalletAddress(str(_row_value(row, "wallet_address"))),
        nonce=AuthNonce(
            value=str(_row_value(row, "nonce_value")),
            expires_at=_row_value(row, "expires_at"),
        ),
        status=ChallengeStatus(_row_value(row, "status")),
        issued_at=_row_value(row, "issued_at"),
        domain=_optional_row_value(row, "domain"),
        uri=_optional_row_value(row, "uri"),
        chain_id=_optional_int_row_value(row, "chain_id"),
        verified_at=_row_value(row, "verified_at"),
        rejected_reason=LoginFailureReason(rejected_reason) if rejected_reason is not None else None,
    )


def _row_to_session(row: Mapping[str, Any] | object) -> AuthSession:
    return AuthSession(
        session_id=SessionId(_row_value(row, "session_id")),
        user_id=UserId(_row_value(row, "user_id")),
        wallet=WalletAddress(str(_row_value(row, "wallet_address"))),
        refresh_token_hash=RefreshTokenHash(
            hash=str(_row_value(row, "refresh_token_hash")),
            salt=str(_row_value(row, "refresh_token_salt")),
            rotation_version=int(_row_value(row, "refresh_token_rotation_version")),
        ),
        device_id=str(_row_value(row, "device_id")),
        expires_at=_row_value(row, "expires_at"),
        revoked_at=_row_value(row, "revoked_at"),
    )


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


def _optional_row_value(row: Mapping[str, Any] | object, key: str) -> str | None:
    value = row.get(key) if isinstance(row, Mapping) else getattr(row, key, None)
    return str(value) if value is not None else None


def _optional_int_row_value(row: Mapping[str, Any] | object, key: str) -> int | None:
    value = row.get(key) if isinstance(row, Mapping) else getattr(row, key, None)
    return int(value) if value is not None else None

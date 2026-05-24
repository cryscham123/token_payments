"""PostgreSQL repositories for the authentication context."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
import uuid

from token_payments.contexts.auth.domain import (
    AuthNonce,
    AuthSession,
    ChallengePurpose,
    ChallengeStatus,
    Group,
    GroupId,
    GroupInvitation,
    GroupMembership,
    GroupType,
    InvitationId,
    InvitationStatus,
    LoginChallenge,
    LoginFailureReason,
    RefreshTokenHash,
    Role,
    RoleId,
    SessionId,
    SessionMembership,
    User,
    UserProfile,
    UserProfileStatus,
    UserRole,
)
from token_payments.contexts.auth.domain.wallet import (
    UserWallet,
    WalletId,
    WalletType,
    WalletVerificationStatus,
)
from token_payments.shared.adapter.postgres import PostgresConnection
from token_payments.shared.domain import StoreId, UserId, WalletAddress


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

SELECT_PROFILE_BY_USER_ID_SQL = """
SELECT
    user_id,
    display_name,
    status,
    created_at,
    updated_at
FROM auth_user_profiles
WHERE user_id = %(user_id)s
"""

SELECT_PROFILE_BY_DISPLAY_NAME_SQL = """
SELECT
    user_id,
    display_name,
    status,
    created_at,
    updated_at
FROM auth_user_profiles
WHERE status <> 'DELETED'
  AND lower(display_name) = lower(%(display_name)s)
LIMIT 1
"""

UPSERT_PROFILE_SQL = """
INSERT INTO auth_user_profiles (
    user_id,
    display_name,
    status,
    created_at,
    updated_at
) VALUES (
    %(user_id)s,
    %(display_name)s,
    %(status)s,
    %(created_at)s,
    %(updated_at)s
)
ON CONFLICT (user_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at
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
    rejected_reason,
    purpose,
    target_user_id
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
    rejected_reason,
    purpose,
    target_user_id
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
    rejected_reason,
    purpose,
    target_user_id
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
    %(rejected_reason)s,
    %(purpose)s,
    %(target_user_id)s
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
    purpose = EXCLUDED.purpose,
    target_user_id = EXCLUDED.target_user_id,
    updated_at = now()
"""

SELECT_WALLET_BY_ID_SQL = """
SELECT
    wallet_id,
    user_id,
    wallet_address,
    chain_id,
    wallet_type,
    verification_status,
    "primary",
    linked_at,
    revoked_at
FROM auth_user_wallets
WHERE wallet_id = %(wallet_id)s
"""

SELECT_ACTIVE_WALLET_BY_ADDRESS_SQL = """
SELECT
    wallet_id,
    user_id,
    wallet_address,
    chain_id,
    wallet_type,
    verification_status,
    "primary",
    linked_at,
    revoked_at
FROM auth_user_wallets
WHERE chain_id = %(chain_id)s
  AND wallet_address = %(wallet_address)s
  AND verification_status = 'VERIFIED'
  AND revoked_at IS NULL
LIMIT 1
"""

SELECT_WALLETS_BY_USER_SQL = """
SELECT
    wallet_id,
    user_id,
    wallet_address,
    chain_id,
    wallet_type,
    verification_status,
    "primary",
    linked_at,
    revoked_at
FROM auth_user_wallets
WHERE user_id = %(user_id)s
ORDER BY chain_id ASC, linked_at ASC, wallet_id ASC
"""

SELECT_PRIMARY_WALLET_BY_USER_CHAIN_SQL = """
SELECT
    wallet_id,
    user_id,
    wallet_address,
    chain_id,
    wallet_type,
    verification_status,
    "primary",
    linked_at,
    revoked_at
FROM auth_user_wallets
WHERE user_id = %(user_id)s
  AND chain_id = %(chain_id)s
  AND "primary" = true
  AND verification_status = 'VERIFIED'
  AND revoked_at IS NULL
ORDER BY linked_at DESC, wallet_id ASC
LIMIT 1
"""

UPSERT_WALLET_SQL = """
INSERT INTO auth_user_wallets (
    wallet_id,
    user_id,
    wallet_address,
    chain_id,
    wallet_type,
    verification_status,
    "primary",
    linked_at,
    revoked_at
) VALUES (
    %(wallet_id)s,
    %(user_id)s,
    %(wallet_address)s,
    %(chain_id)s,
    %(wallet_type)s,
    %(verification_status)s,
    %(primary)s,
    %(linked_at)s,
    %(revoked_at)s
)
ON CONFLICT (wallet_id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    wallet_address = EXCLUDED.wallet_address,
    chain_id = EXCLUDED.chain_id,
    wallet_type = EXCLUDED.wallet_type,
    verification_status = EXCLUDED.verification_status,
    "primary" = EXCLUDED."primary",
    linked_at = EXCLUDED.linked_at,
    revoked_at = EXCLUDED.revoked_at,
    updated_at = now()
"""

UNSET_PRIMARY_WALLETS_FOR_CHAIN_SQL = """
UPDATE auth_user_wallets
SET "primary" = false, updated_at = now()
WHERE user_id = %(user_id)s
  AND chain_id = %(chain_id)s
  AND wallet_id <> %(except_wallet_id)s
  AND verification_status = 'VERIFIED'
  AND revoked_at IS NULL
"""

SELECT_SESSION_BY_ID_SQL = """
SELECT
    s.session_id,
    s.user_id,
    s.login_wallet_id,
    s.refresh_token_hash,
    s.refresh_token_salt,
    s.refresh_token_rotation_version,
    s.device_id,
    s.expires_at,
    s.revoked_at,
    w.wallet_address
FROM auth_sessions s
JOIN auth_user_wallets w ON s.login_wallet_id = w.wallet_id
WHERE s.session_id = %(session_id)s
"""

SELECT_SESSION_BY_REFRESH_TOKEN_HASH_SQL = """
SELECT
    s.session_id,
    s.user_id,
    s.login_wallet_id,
    s.refresh_token_hash,
    s.refresh_token_salt,
    s.refresh_token_rotation_version,
    s.device_id,
    s.expires_at,
    s.revoked_at,
    w.wallet_address
FROM auth_sessions s
JOIN auth_user_wallets w ON s.login_wallet_id = w.wallet_id
WHERE s.refresh_token_hash = %(refresh_token_hash)s
  AND s.refresh_token_salt = %(refresh_token_salt)s
  AND s.refresh_token_rotation_version = %(refresh_token_rotation_version)s
"""

UPSERT_SESSION_SQL = """
INSERT INTO auth_sessions (
    session_id,
    user_id,
    login_wallet_id,
    refresh_token_hash,
    refresh_token_salt,
    refresh_token_rotation_version,
    device_id,
    expires_at,
    revoked_at
) VALUES (
    %(session_id)s,
    %(user_id)s,
    %(login_wallet_id)s,
    %(refresh_token_hash)s,
    %(refresh_token_salt)s,
    %(refresh_token_rotation_version)s,
    %(device_id)s,
    %(expires_at)s,
    %(revoked_at)s
)
ON CONFLICT (session_id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    login_wallet_id = EXCLUDED.login_wallet_id,
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

    def get_wallet_id_for_address(self, user_id: UserId, wallet: WalletAddress) -> WalletId:
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresUserRepository.get_wallet_id_for_address requires a UserId")
        if not isinstance(wallet, WalletAddress):
            raise ValueError("PostgresUserRepository.get_wallet_id_for_address requires a WalletAddress")

        row = _fetch_one(
            self._connection.execute(
                "SELECT wallet_id FROM auth_user_wallets WHERE user_id = %(user_id)s AND wallet_address = %(wallet_address)s",
                {"user_id": str(user_id), "wallet_address": str(wallet)},
            )
        )
        if row is not None:
            return WalletId(uuid.UUID(str(_row_value(row, "wallet_id"))))

        wallet_id = WalletId.new()
        self._connection.execute(
            'INSERT INTO auth_user_wallets (wallet_id, user_id, wallet_address, chain_id, wallet_type, verification_status, "primary", linked_at) '
            "VALUES (%(wallet_id)s, %(user_id)s, %(wallet_address)s, 1, 'EOA', 'VERIFIED', true, now())",
            {
                "wallet_id": str(wallet_id),
                "user_id": str(user_id),
                "wallet_address": str(wallet),
            }
        )
        return wallet_id


class PostgresUserWalletRepository:
    """Persist canonical verified wallets inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def save(self, wallet: UserWallet) -> None:
        if not isinstance(wallet, UserWallet):
            raise ValueError("PostgresUserWalletRepository.save requires a UserWallet")
        self._connection.execute(
            UPSERT_WALLET_SQL,
            {
                "wallet_id": str(wallet.wallet_id),
                "user_id": str(wallet.user_id),
                "wallet_address": str(wallet.address),
                "chain_id": wallet.chain_id,
                "wallet_type": wallet.wallet_type.value,
                "verification_status": wallet.verification_status.value,
                "primary": wallet.primary,
                "linked_at": wallet.linked_at,
                "revoked_at": wallet.revoked_at,
            },
        )

    def get_by_id(self, wallet_id: WalletId) -> UserWallet | None:
        if not isinstance(wallet_id, WalletId):
            raise ValueError("PostgresUserWalletRepository.get_by_id requires a WalletId")
        row = _fetch_one(self._connection.execute(SELECT_WALLET_BY_ID_SQL, {"wallet_id": str(wallet_id)}))
        return _row_to_wallet(row) if row is not None else None

    def get_active_by_address(self, chain_id: int, wallet: WalletAddress) -> UserWallet | None:
        if isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id <= 0:
            raise ValueError("PostgresUserWalletRepository.get_active_by_address requires positive chain_id")
        if not isinstance(wallet, WalletAddress):
            raise ValueError("PostgresUserWalletRepository.get_active_by_address requires a WalletAddress")
        row = _fetch_one(
            self._connection.execute(
                SELECT_ACTIVE_WALLET_BY_ADDRESS_SQL,
                {"chain_id": chain_id, "wallet_address": str(wallet)},
            )
        )
        return _row_to_wallet(row) if row is not None else None

    def list_for_user(self, user_id: UserId) -> tuple[UserWallet, ...]:
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresUserWalletRepository.list_for_user requires a UserId")
        result = self._connection.execute(SELECT_WALLETS_BY_USER_SQL, {"user_id": str(user_id)})
        return tuple(_row_to_wallet(row) for row in result)

    def get_primary_for_user_chain(self, user_id: UserId, chain_id: int) -> UserWallet | None:
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresUserWalletRepository.get_primary_for_user_chain requires a UserId")
        if isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id <= 0:
            raise ValueError("PostgresUserWalletRepository.get_primary_for_user_chain requires positive chain_id")
        row = _fetch_one(
            self._connection.execute(
                SELECT_PRIMARY_WALLET_BY_USER_CHAIN_SQL,
                {"user_id": str(user_id), "chain_id": chain_id},
            )
        )
        return _row_to_wallet(row) if row is not None else None

    def unset_primary_for_chain(self, user_id: UserId, chain_id: int, except_wallet_id: WalletId) -> None:
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresUserWalletRepository.unset_primary_for_chain requires a UserId")
        if isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id <= 0:
            raise ValueError("PostgresUserWalletRepository.unset_primary_for_chain requires positive chain_id")
        if not isinstance(except_wallet_id, WalletId):
            raise ValueError("PostgresUserWalletRepository.unset_primary_for_chain requires a WalletId")
        self._connection.execute(
            UNSET_PRIMARY_WALLETS_FOR_CHAIN_SQL,
            {
                "user_id": str(user_id),
                "chain_id": chain_id,
                "except_wallet_id": str(except_wallet_id),
            },
        )


class PostgresUserProfileRepository:
    """Persist auth user profiles inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def save(self, profile: UserProfile) -> None:
        if not isinstance(profile, UserProfile):
            raise ValueError("PostgresUserProfileRepository.save requires a UserProfile")
        self._connection.execute(
            UPSERT_PROFILE_SQL,
            {
                "user_id": str(profile.user_id),
                "display_name": profile.display_name,
                "status": profile.status.value,
                "created_at": profile.created_at,
                "updated_at": profile.updated_at,
            },
        )

    def get_by_user_id(self, user_id: UserId) -> UserProfile | None:
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresUserProfileRepository.get_by_user_id requires a UserId")
        row = _fetch_one(self._connection.execute(SELECT_PROFILE_BY_USER_ID_SQL, {"user_id": str(user_id)}))
        return _row_to_profile(row) if row is not None else None

    def get_by_display_name(self, display_name: str) -> UserProfile | None:
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("PostgresUserProfileRepository.get_by_display_name requires a display name")
        row = _fetch_one(
            self._connection.execute(
                SELECT_PROFILE_BY_DISPLAY_NAME_SQL,
                {"display_name": display_name.strip()},
            )
        )
        return _row_to_profile(row) if row is not None else None


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
                "purpose": challenge.purpose.value,
                "target_user_id": str(challenge.target_user_id) if challenge.target_user_id is not None else None,
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
                "login_wallet_id": str(session.login_wallet_id),
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


SELECT_PERSONAL_GROUP_SQL = """
SELECT group_id
FROM auth_groups
WHERE group_type = 'PERSONAL'
  AND resource_type = 'user'
  AND resource_id = %(user_id)s
  AND active = true
LIMIT 1
"""

INSERT_PERSONAL_GROUP_SQL = """
INSERT INTO auth_groups (
    group_id,
    group_type,
    name,
    resource_type,
    resource_id,
    active
) VALUES (
    %(group_id)s,
    'PERSONAL',
    %(name)s,
    'user',
    %(resource_id)s,
    true
)
ON CONFLICT (group_id) DO NOTHING
"""

INSERT_PERSONAL_MEMBERSHIP_SQL = """
INSERT INTO auth_group_memberships (
    group_id,
    user_id,
    role_id,
    active,
    joined_at
) VALUES (
    %(group_id)s,
    %(user_id)s,
    'PERSONAL_CUSTOMER',
    true,
    %(joined_at)s
)
ON CONFLICT (group_id, user_id) DO UPDATE SET
    active = true,
    updated_at = now()
"""

SELECT_MEMBERSHIPS_SQL = """
SELECT
    m.group_id,
    g.group_type,
    m.role_id,
    g.resource_type,
    g.resource_id
FROM auth_group_memberships m
JOIN auth_groups g ON m.group_id = g.group_id
JOIN auth_roles r ON m.role_id = r.role_id
WHERE m.user_id = %(user_id)s
  AND m.active = true
  AND g.active = true
  AND r.active = true
ORDER BY g.group_type DESC, m.group_id ASC
"""

SELECT_SCOPES_SQL = """
SELECT DISTINCT rp.permission_name
FROM auth_group_memberships m
JOIN auth_groups g ON m.group_id = g.group_id
JOIN auth_roles r ON m.role_id = r.role_id
JOIN auth_role_permissions rp ON r.role_id = rp.role_id
JOIN auth_permissions p ON rp.permission_name = p.permission_name
WHERE m.user_id = %(user_id)s
  AND m.active = true
  AND g.active = true
  AND r.active = true
  AND rp.active = true
  AND p.active = true
ORDER BY rp.permission_name ASC
"""

SELECT_PROCESSED_MEMBERSHIP_EVENT_SQL = """
SELECT 1 FROM processed_messages
WHERE consumer = 'auth-rbac-projector'
  AND message_id = %(message_id)s::uuid
"""

SELECT_MEMBERSHIP_VERSION_SQL = """
SELECT version FROM auth_group_memberships
WHERE group_id = %(group_id)s::uuid
  AND user_id = %(user_id)s::uuid
"""

UPSERT_PROJECTED_MEMBERSHIP_SQL = """
INSERT INTO auth_group_memberships (
    group_id,
    user_id,
    role_id,
    active,
    version,
    updated_at
) VALUES (
    %(group_id)s::uuid,
    %(user_id)s::uuid,
    %(role_id)s,
    %(active)s,
    %(version)s,
    now()
) ON CONFLICT (group_id, user_id) DO UPDATE SET
    role_id = EXCLUDED.role_id,
    active = EXCLUDED.active,
    version = EXCLUDED.version,
    updated_at = now()
"""

INSERT_PROCESSED_MEMBERSHIP_EVENT_SQL = """
INSERT INTO processed_messages (
    consumer,
    message_id
) VALUES (
    'auth-rbac-projector',
    %(message_id)s::uuid
) ON CONFLICT (consumer, message_id) DO NOTHING
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

SELECT_GROUP_MEMBERSHIPS_SQL = """
SELECT group_id, user_id, role_id, active, joined_at
FROM auth_group_memberships
WHERE group_id = %(group_id)s::uuid
ORDER BY joined_at ASC, user_id ASC
"""

SELECT_GROUP_MEMBERSHIP_SQL = """
SELECT group_id, user_id, role_id, active, joined_at
FROM auth_group_memberships
WHERE group_id = %(group_id)s::uuid
  AND user_id = %(user_id)s::uuid
LIMIT 1
"""

UPSERT_GROUP_MEMBERSHIP_SQL = """
INSERT INTO auth_group_memberships (
    group_id,
    user_id,
    role_id,
    active,
    joined_at
) VALUES (
    %(group_id)s::uuid,
    %(user_id)s::uuid,
    %(role_id)s,
    %(active)s,
    %(joined_at)s
)
ON CONFLICT (group_id, user_id) DO UPDATE SET
    role_id = EXCLUDED.role_id,
    active = EXCLUDED.active,
    joined_at = EXCLUDED.joined_at,
    updated_at = now()
"""

SELECT_GROUP_INVITATIONS_SQL = """
SELECT
    invitation_id,
    group_id,
    invited_role_id,
    invited_by_user_id,
    target_user_id,
    target_wallet_address,
    status,
    created_at,
    expires_at
FROM auth_group_invitations
WHERE group_id = %(group_id)s::uuid
ORDER BY created_at DESC, invitation_id ASC
"""

SELECT_GROUP_INVITATION_SQL = """
SELECT
    invitation_id,
    group_id,
    invited_role_id,
    invited_by_user_id,
    target_user_id,
    target_wallet_address,
    status,
    created_at,
    expires_at
FROM auth_group_invitations
WHERE invitation_id = %(invitation_id)s::uuid
LIMIT 1
"""

UPSERT_GROUP_INVITATION_SQL = """
INSERT INTO auth_group_invitations (
    invitation_id,
    group_id,
    invited_role_id,
    invited_by_user_id,
    target_user_id,
    target_wallet_address,
    status,
    created_at,
    expires_at
) VALUES (
    %(invitation_id)s::uuid,
    %(group_id)s::uuid,
    %(invited_role_id)s,
    %(invited_by_user_id)s::uuid,
    %(target_user_id)s::uuid,
    %(target_wallet_address)s,
    %(status)s,
    %(created_at)s,
    %(expires_at)s
)
ON CONFLICT (invitation_id) DO UPDATE SET
    invited_role_id = EXCLUDED.invited_role_id,
    target_user_id = EXCLUDED.target_user_id,
    target_wallet_address = EXCLUDED.target_wallet_address,
    status = EXCLUDED.status,
    expires_at = EXCLUDED.expires_at,
    updated_at = now()
"""

SELECT_ROLE_CATALOG_SQL = """
SELECT role_id, name, group_type, active, merchant_assignable, owner_role
FROM auth_roles
WHERE active = true
ORDER BY role_id ASC
"""

SELECT_ACTIVE_WALLET_OWNER_SQL = """
WITH active_wallet_owners AS (
    SELECT
        w.user_id,
        bool_or(w."primary") AS primary_wallet,
        min(w.linked_at) AS first_linked_at
    FROM auth_user_wallets w
    JOIN auth_users u ON u.user_id = w.user_id
    WHERE w.wallet_address = %(wallet_address)s
      AND w.verification_status = 'VERIFIED'
      AND w.revoked_at IS NULL
      AND u.active = true
    GROUP BY w.user_id
)
SELECT user_id
FROM active_wallet_owners
WHERE (SELECT count(*) FROM active_wallet_owners) = 1
ORDER BY primary_wallet DESC, first_linked_at ASC, user_id ASC
LIMIT 1
"""

SELECT_ACTIVE_DISPLAY_NAME_OWNER_SQL = """
SELECT user_id
FROM auth_user_profiles
WHERE status = 'ACTIVE'
  AND display_name IS NOT NULL
  AND lower(display_name) = lower(%(display_name)s)
LIMIT 1
"""


class PostgresAuthRbacRepository:
    """Persist group memberships and scopes inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def was_membership_event_processed(self, event_id: str) -> bool:
        from uuid import UUID
        try:
            UUID(str(event_id))
        except ValueError:
            return True
        row = _fetch_one(
            self._connection.execute(
                SELECT_PROCESSED_MEMBERSHIP_EVENT_SQL,
                {"message_id": str(event_id)},
            )
        )
        return row is not None

    def last_membership_projection_version(self, group_id: str, user_id: str) -> int:
        row = _fetch_one(
            self._connection.execute(
                SELECT_MEMBERSHIP_VERSION_SQL,
                {"group_id": str(group_id), "user_id": str(user_id)},
            )
        )
        if row is None:
            return 0
        return int(_row_value(row, "version"))

    def upsert_projected_membership(
        self,
        *,
        group_id: str,
        user_id: str,
        role_id: str,
        active: bool,
        version: int,
    ) -> None:
        self._connection.execute(
            UPSERT_PROJECTED_MEMBERSHIP_SQL,
            {
                "group_id": str(group_id),
                "user_id": str(user_id),
                "role_id": str(role_id),
                "active": bool(active),
                "version": int(version),
            },
        )

    def mark_membership_event_processed(self, event_id: str) -> None:
        from uuid import UUID
        try:
            UUID(str(event_id))
        except ValueError:
            return
        self._connection.execute(
            INSERT_PROCESSED_MEMBERSHIP_EVENT_SQL,
            {"message_id": str(event_id)},
        )

    def ensure_personal_membership(self, user: User, joined_at: datetime) -> tuple[SessionMembership, ...]:
        if not isinstance(user, User):
            raise ValueError("PostgresAuthRbacRepository.ensure_personal_membership requires a User")
        user_id_str = str(user.user_id)
        
        row = _fetch_one(
            self._connection.execute(
                SELECT_PERSONAL_GROUP_SQL,
                {"user_id": user_id_str}
            )
        )
        if row is not None:
            group_id = _row_value(row, "group_id")
        else:
            group_id = str(uuid.uuid4())
            self._connection.execute(
                INSERT_PERSONAL_GROUP_SQL,
                {
                    "group_id": group_id,
                    "name": f"personal:{user_id_str}",
                    "resource_id": user_id_str,
                }
            )
        
        self._connection.execute(
            INSERT_PERSONAL_MEMBERSHIP_SQL,
            {
                "group_id": group_id,
                "user_id": user_id_str,
                "joined_at": joined_at,
            }
        )
        
        return self.session_memberships_for_user(user.user_id)

    def session_memberships_for_user(self, user_id: UserId) -> tuple[SessionMembership, ...]:
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresAuthRbacRepository.session_memberships_for_user requires a UserId")
        
        result = self._connection.execute(
            SELECT_MEMBERSHIPS_SQL,
            {"user_id": str(user_id)}
        )
        
        memberships = []
        for row in result:
            memberships.append(
                SessionMembership(
                    group_id=GroupId(_row_value(row, "group_id")),
                    group_type=GroupType(str(_row_value(row, "group_type"))),
                    role_id=RoleId(str(_row_value(row, "role_id"))),
                    resource_type=_optional_row_value(row, "resource_type"),
                    resource_id=_optional_row_value(row, "resource_id"),
                )
            )
        return tuple(memberships)

    def scopes_for_user(self, user_id: UserId) -> tuple[str, ...]:
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresAuthRbacRepository.scopes_for_user requires a UserId")
        
        result = self._connection.execute(
            SELECT_SCOPES_SQL,
            {"user_id": str(user_id)}
        )
        
        scopes = []
        for row in result:
            scopes.append(str(_row_value(row, "permission_name")))
        return tuple(scopes)


class PostgresMerchantMembershipRepository:
    """Persist merchant group memberships and invitations inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def merchant_group_for_store(self, store_id: StoreId) -> Group | None:
        if not isinstance(store_id, StoreId):
            raise ValueError("PostgresMerchantMembershipRepository.merchant_group_for_store requires a StoreId")
        row = _fetch_one(
            self._connection.execute(
                SELECT_MERCHANT_GROUP_FOR_STORE_SQL,
                {"store_id": str(store_id)},
            )
        )
        return _row_to_group(row) if row is not None else None

    def members_for_group(self, group_id: GroupId) -> tuple[GroupMembership, ...]:
        if not isinstance(group_id, GroupId):
            raise ValueError("PostgresMerchantMembershipRepository.members_for_group requires a GroupId")
        result = self._connection.execute(SELECT_GROUP_MEMBERSHIPS_SQL, {"group_id": str(group_id)})
        return tuple(_row_to_group_membership(row) for row in _fetch_all(result))

    def get_membership(self, group_id: GroupId, user_id: UserId) -> GroupMembership | None:
        if not isinstance(group_id, GroupId):
            raise ValueError("PostgresMerchantMembershipRepository.get_membership requires a GroupId")
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresMerchantMembershipRepository.get_membership requires a UserId")
        row = _fetch_one(
            self._connection.execute(
                SELECT_GROUP_MEMBERSHIP_SQL,
                {"group_id": str(group_id), "user_id": str(user_id)},
            )
        )
        return _row_to_group_membership(row) if row is not None else None

    def save_membership(self, membership: GroupMembership) -> None:
        if not isinstance(membership, GroupMembership):
            raise ValueError("PostgresMerchantMembershipRepository.save_membership requires a GroupMembership")
        self._connection.execute(
            UPSERT_GROUP_MEMBERSHIP_SQL,
            {
                "group_id": str(membership.group_id),
                "user_id": str(membership.user_id),
                "role_id": str(membership.role_id),
                "active": membership.active,
                "joined_at": membership.joined_at,
            },
        )

    def invitations_for_group(self, group_id: GroupId) -> tuple[GroupInvitation, ...]:
        if not isinstance(group_id, GroupId):
            raise ValueError("PostgresMerchantMembershipRepository.invitations_for_group requires a GroupId")
        result = self._connection.execute(SELECT_GROUP_INVITATIONS_SQL, {"group_id": str(group_id)})
        return tuple(_row_to_group_invitation(row) for row in _fetch_all(result))

    def get_invitation(self, invitation_id: InvitationId) -> GroupInvitation | None:
        if not isinstance(invitation_id, InvitationId):
            raise ValueError("PostgresMerchantMembershipRepository.get_invitation requires an InvitationId")
        row = _fetch_one(
            self._connection.execute(
                SELECT_GROUP_INVITATION_SQL,
                {"invitation_id": str(invitation_id)},
            )
        )
        return _row_to_group_invitation(row) if row is not None else None

    def save_invitation(self, invitation: GroupInvitation) -> None:
        if not isinstance(invitation, GroupInvitation):
            raise ValueError("PostgresMerchantMembershipRepository.save_invitation requires a GroupInvitation")
        self._connection.execute(
            UPSERT_GROUP_INVITATION_SQL,
            {
                "invitation_id": str(invitation.invitation_id),
                "group_id": str(invitation.group_id),
                "invited_role_id": str(invitation.invited_role_id),
                "invited_by_user_id": str(invitation.invited_by_user_id),
                "target_user_id": str(invitation.target_user_id) if invitation.target_user_id is not None else None,
                "target_wallet_address": str(invitation.target_wallet) if invitation.target_wallet is not None else None,
                "status": invitation.status.value,
                "created_at": invitation.created_at,
                "expires_at": invitation.expires_at,
            },
        )

    def user_id_for_active_wallet(self, wallet: WalletAddress) -> UserId | None:
        if not isinstance(wallet, WalletAddress):
            raise ValueError("PostgresMerchantMembershipRepository.user_id_for_active_wallet requires a WalletAddress")
        row = _fetch_one(
            self._connection.execute(
                SELECT_ACTIVE_WALLET_OWNER_SQL,
                {"wallet_address": str(wallet)},
            )
        )
        return UserId(_row_value(row, "user_id")) if row is not None else None

    def user_id_for_active_display_name(self, display_name: str) -> UserId | None:
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("PostgresMerchantMembershipRepository.user_id_for_active_display_name requires display_name")
        row = _fetch_one(
            self._connection.execute(
                SELECT_ACTIVE_DISPLAY_NAME_OWNER_SQL,
                {"display_name": display_name.strip()},
            )
        )
        return UserId(_row_value(row, "user_id")) if row is not None else None

    def role_catalog(self) -> tuple[Role, ...]:
        result = self._connection.execute(SELECT_ROLE_CATALOG_SQL)
        return tuple(_row_to_role(row) for row in _fetch_all(result))


def _row_to_user(row: Mapping[str, Any] | object) -> User:
    return User(
        user_id=UserId(_row_value(row, "user_id")),
        primary_wallet=WalletAddress(str(_row_value(row, "wallet_address"))),
        role=UserRole(_row_value(row, "role")),
        active=bool(_row_value(row, "active")),
        last_login_at=_row_value(row, "last_login_at"),
    )


def _row_to_profile(row: Mapping[str, Any] | object) -> UserProfile:
    return UserProfile(
        user_id=UserId(_row_value(row, "user_id")),
        display_name=_row_value(row, "display_name"),
        status=UserProfileStatus(_row_value(row, "status")),
        created_at=_row_value(row, "created_at"),
        updated_at=_row_value(row, "updated_at"),
    )


def _row_to_wallet(row: Mapping[str, Any] | object) -> UserWallet:
    return UserWallet(
        wallet_id=WalletId(uuid.UUID(str(_row_value(row, "wallet_id")))),
        user_id=UserId(_row_value(row, "user_id")),
        address=WalletAddress(str(_row_value(row, "wallet_address"))),
        chain_id=int(_row_value(row, "chain_id")),
        wallet_type=WalletType(str(_row_value(row, "wallet_type"))),
        verification_status=WalletVerificationStatus(str(_row_value(row, "verification_status"))),
        primary=bool(_row_value(row, "primary")),
        linked_at=_row_value(row, "linked_at"),
        revoked_at=_row_value(row, "revoked_at"),
    )


def _row_to_challenge(row: Mapping[str, Any] | object) -> LoginChallenge:
    rejected_reason = _row_value(row, "rejected_reason")
    target_user_id = _optional_row_value(row, "target_user_id")
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
        purpose=ChallengePurpose(_optional_row_value(row, "purpose") or ChallengePurpose.LOGIN.value),
        target_user_id=UserId(target_user_id) if target_user_id is not None else None,
    )


def _row_to_session(row: Mapping[str, Any] | object) -> AuthSession:
    wallet_address = _optional_row_value(row, "wallet_address")
    return AuthSession(
        session_id=SessionId(_row_value(row, "session_id")),
        user_id=UserId(_row_value(row, "user_id")),
        login_wallet_id=WalletId(uuid.UUID(str(_row_value(row, "login_wallet_id")))),
        refresh_token_hash=RefreshTokenHash(
            hash=str(_row_value(row, "refresh_token_hash")),
            salt=str(_row_value(row, "refresh_token_salt")),
            rotation_version=int(_row_value(row, "refresh_token_rotation_version")),
        ),
        device_id=str(_row_value(row, "device_id")),
        expires_at=_row_value(row, "expires_at"),
        revoked_at=_row_value(row, "revoked_at"),
        wallet=WalletAddress(wallet_address) if wallet_address is not None else None,
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


def _row_to_group_membership(row: Mapping[str, Any] | object) -> GroupMembership:
    return GroupMembership(
        user_id=UserId(_row_value(row, "user_id")),
        group_id=GroupId(_row_value(row, "group_id")),
        role_id=RoleId(str(_row_value(row, "role_id"))),
        active=bool(_row_value(row, "active")),
        joined_at=_row_value(row, "joined_at"),
    )


def _row_to_group_invitation(row: Mapping[str, Any] | object) -> GroupInvitation:
    target_user_id = _optional_row_value(row, "target_user_id")
    target_wallet = _optional_row_value(row, "target_wallet_address")
    return GroupInvitation(
        invitation_id=InvitationId(_row_value(row, "invitation_id")),
        group_id=GroupId(_row_value(row, "group_id")),
        invited_role_id=RoleId(str(_row_value(row, "invited_role_id"))),
        invited_by_user_id=UserId(_row_value(row, "invited_by_user_id")),
        target_user_id=UserId(target_user_id) if target_user_id is not None else None,
        target_wallet=WalletAddress(target_wallet) if target_wallet is not None else None,
        status=InvitationStatus(_row_value(row, "status")),
        created_at=_row_value(row, "created_at"),
        expires_at=_row_value(row, "expires_at"),
    )


def _row_to_role(row: Mapping[str, Any] | object) -> Role:
    return Role(
        role_id=RoleId(str(_row_value(row, "role_id"))),
        name=str(_row_value(row, "name")),
        group_type=GroupType(_row_value(row, "group_type")),
        active=bool(_row_value(row, "active")),
        merchant_assignable=bool(_row_value(row, "merchant_assignable")),
        owner_role=bool(_row_value(row, "owner_role")),
    )


def _fetch_all(result: Any) -> tuple[Any, ...]:
    if result is None:
        return ()
    fetchall = getattr(result, "fetchall", None)
    if callable(fetchall):
        return tuple(fetchall())
    return tuple(result)


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

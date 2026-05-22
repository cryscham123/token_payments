"""Domain model for SIWE-backed MetaMask authentication."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self, TypeAlias
from uuid import UUID, uuid4

from token_payments.shared.domain import UserId, WalletAddress
from .wallet import WalletId


class UserRole(StrEnum):
    """Compatibility role enum for legacy fixtures.

    New authorization paths use group memberships and permissions instead of
    this account-wide value.
    """

    CUSTOMER = "CUSTOMER"
    STORE_OWNER = "STORE_OWNER"
    ADMIN = "ADMIN"


class GroupType(StrEnum):
    PERSONAL = "PERSONAL"
    MERCHANT = "MERCHANT"
    PLATFORM = "PLATFORM"


class InvitationStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class MerchantRoleTemplate(StrEnum):
    MERCHANT_MANAGER = "MERCHANT_MANAGER"
    MERCHANT_STAFF = "MERCHANT_STAFF"


@dataclass(frozen=True)
class GroupId:
    value: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _coerce_uuid(self.value, "GroupId.value"))

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class RoleId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _require_text(self.value, "RoleId.value"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PermissionName:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _require_text(self.value, "PermissionName.value"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class InvitationId:
    value: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _coerce_uuid(self.value, "InvitationId.value"))

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


class ChallengeStatus(StrEnum):
    ISSUED = "ISSUED"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class ChallengePurpose(StrEnum):
    LOGIN = "LOGIN"
    WALLET_LINK = "WALLET_LINK"


class LoginFailureReason(StrEnum):
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED_CHALLENGE = "EXPIRED_CHALLENGE"
    REUSED_NONCE = "REUSED_NONCE"
    WALLET_MISMATCH = "WALLET_MISMATCH"
    SIWE_MESSAGE_MISMATCH = "SIWE_MESSAGE_MISMATCH"


class LoginChallengeRejected(ValueError):
    def __init__(self, reason: LoginFailureReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


@dataclass(frozen=True)
class SessionId:
    value: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _coerce_uuid(self.value, "SessionId.value"))

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class AuthNonce:
    value: str
    expires_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _require_text(self.value, "AuthNonce.value"))
        object.__setattr__(
            self,
            "expires_at",
            _require_aware_datetime(self.expires_at, "AuthNonce.expires_at"),
        )

    def is_expired(self, now: datetime) -> bool:
        return _require_aware_datetime(now, "now") >= self.expires_at


@dataclass(frozen=True)
class RefreshTokenHash:
    hash: str
    salt: str
    rotation_version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "hash", _require_text(self.hash, "RefreshTokenHash.hash"))
        object.__setattr__(self, "salt", _require_text(self.salt, "RefreshTokenHash.salt"))
        if (
            isinstance(self.rotation_version, bool)
            or not isinstance(self.rotation_version, int)
            or self.rotation_version < 0
        ):
            raise ValueError("RefreshTokenHash.rotation_version must be a non-negative integer")

    def rotate(self, token_hash: str, salt: str) -> Self:
        return type(self)(
            hash=token_hash,
            salt=salt,
            rotation_version=self.rotation_version + 1,
        )


@dataclass(frozen=True)
class IssuedToken:
    access_token: str
    refresh_token: str
    expires_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "access_token", _require_text(self.access_token, "IssuedToken.access_token"))
        object.__setattr__(self, "refresh_token", _require_text(self.refresh_token, "IssuedToken.refresh_token"))
        object.__setattr__(
            self,
            "expires_at",
            _require_aware_datetime(self.expires_at, "IssuedToken.expires_at"),
        )


@dataclass(frozen=True)
class User:
    user_id: UserId
    primary_wallet: WalletAddress | str
    active: bool = True
    last_login_at: datetime | None = None
    role: InitVar[UserRole | str | None] = None

    def __post_init__(self, role: UserRole | str | None) -> None:
        if isinstance(role, property):
            role = None
        if not isinstance(self.user_id, UserId):
            raise ValueError("User.user_id must be a UserId")
        object.__setattr__(self, "primary_wallet", _coerce_wallet(self.primary_wallet))
        object.__setattr__(
            self,
            "_legacy_role",
            _coerce_user_role(role) if role is not None else UserRole.CUSTOMER,
        )
        if not isinstance(self.active, bool):
            raise ValueError("User.active must be a bool")
        if self.last_login_at is not None:
            object.__setattr__(
                self,
                "last_login_at",
                _require_aware_datetime(self.last_login_at, "User.last_login_at"),
            )

    @classmethod
    def register_by_wallet(
        cls,
        user_id: UserId,
        wallet: WalletAddress | str,
        role: UserRole | str | None = None,
    ) -> Self:
        return cls(user_id=user_id, primary_wallet=wallet, role=role, active=True)

    @property
    def role(self) -> UserRole:
        """Legacy account role view retained for old fixtures and migrations."""

        return getattr(self, "_legacy_role", UserRole.CUSTOMER)

    def link_wallet(self, wallet: WalletAddress | str) -> Self:
        self._ensure_active()
        return replace(self, primary_wallet=_coerce_wallet(wallet), role=self.role)

    def record_login(self, logged_in_at: datetime | None = None) -> Self:
        self._ensure_active()
        return replace(self, last_login_at=logged_in_at or datetime.now(UTC), role=self.role)

    def deactivate(self) -> Self:
        return replace(self, active=False, role=self.role)

    def _ensure_active(self) -> None:
        if not self.active:
            raise ValueError("inactive users cannot be changed")


@dataclass(frozen=True)
class Group:
    group_id: GroupId
    group_type: GroupType | str
    name: str
    active: bool = True
    resource_type: str | None = None
    resource_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.group_id, GroupId):
            raise ValueError("Group.group_id must be a GroupId")
        object.__setattr__(self, "group_type", _coerce_group_type(self.group_type))
        object.__setattr__(self, "name", _require_text(self.name, "Group.name"))
        if not isinstance(self.active, bool):
            raise ValueError("Group.active must be a bool")
        if self.resource_type is not None:
            object.__setattr__(self, "resource_type", _require_text(self.resource_type, "Group.resource_type"))
        if self.resource_id is not None:
            object.__setattr__(self, "resource_id", _require_text(self.resource_id, "Group.resource_id"))
        if self.group_type is GroupType.MERCHANT and (self.resource_type is None or self.resource_id is None):
            raise ValueError("MERCHANT groups require resource_type and resource_id")


@dataclass(frozen=True)
class Role:
    role_id: RoleId | str
    name: str
    group_type: GroupType | str
    active: bool = True
    merchant_assignable: bool = False
    owner_role: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.role_id, RoleId):
            object.__setattr__(self, "role_id", RoleId(str(self.role_id)))
        object.__setattr__(self, "name", _require_text(self.name, "Role.name"))
        object.__setattr__(self, "group_type", _coerce_group_type(self.group_type))
        if not isinstance(self.active, bool):
            raise ValueError("Role.active must be a bool")
        if not isinstance(self.merchant_assignable, bool):
            raise ValueError("Role.merchant_assignable must be a bool")
        if not isinstance(self.owner_role, bool):
            raise ValueError("Role.owner_role must be a bool")
        if self.owner_role and self.merchant_assignable:
            raise ValueError("owner roles are not merchant-facing assignable templates")


@dataclass(frozen=True)
class Permission:
    name: PermissionName | str
    description: str = ""
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, PermissionName):
            object.__setattr__(self, "name", PermissionName(str(self.name)))
        if self.description:
            object.__setattr__(self, "description", _require_text(self.description, "Permission.description"))
        if not isinstance(self.active, bool):
            raise ValueError("Permission.active must be a bool")


@dataclass(frozen=True)
class RolePermission:
    role_id: RoleId | str
    permission: PermissionName | str
    active: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.role_id, RoleId):
            object.__setattr__(self, "role_id", RoleId(str(self.role_id)))
        if not isinstance(self.permission, PermissionName):
            object.__setattr__(self, "permission", PermissionName(str(self.permission)))
        if not isinstance(self.active, bool):
            raise ValueError("RolePermission.active must be a bool")


@dataclass(frozen=True)
class GroupMembership:
    user_id: UserId
    group_id: GroupId
    role_id: RoleId | str
    active: bool = True
    joined_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("GroupMembership.user_id must be a UserId")
        if not isinstance(self.group_id, GroupId):
            raise ValueError("GroupMembership.group_id must be a GroupId")
        if not isinstance(self.role_id, RoleId):
            object.__setattr__(self, "role_id", RoleId(str(self.role_id)))
        if not isinstance(self.active, bool):
            raise ValueError("GroupMembership.active must be a bool")
        if self.joined_at is not None:
            object.__setattr__(
                self,
                "joined_at",
                _require_aware_datetime(self.joined_at, "GroupMembership.joined_at"),
            )


@dataclass(frozen=True)
class GroupInvitation:
    invitation_id: InvitationId
    group_id: GroupId
    invited_role_id: RoleId | str
    invited_by_user_id: UserId
    status: InvitationStatus | str
    created_at: datetime
    target_user_id: UserId | None = None
    target_wallet: WalletAddress | str | None = None
    target_email: str | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.invitation_id, InvitationId):
            raise ValueError("GroupInvitation.invitation_id must be an InvitationId")
        if not isinstance(self.group_id, GroupId):
            raise ValueError("GroupInvitation.group_id must be a GroupId")
        if not isinstance(self.invited_role_id, RoleId):
            object.__setattr__(self, "invited_role_id", RoleId(str(self.invited_role_id)))
        if not isinstance(self.invited_by_user_id, UserId):
            raise ValueError("GroupInvitation.invited_by_user_id must be a UserId")
        object.__setattr__(self, "status", _coerce_invitation_status(self.status))
        object.__setattr__(self, "created_at", _require_aware_datetime(self.created_at, "GroupInvitation.created_at"))
        if self.target_user_id is not None and not isinstance(self.target_user_id, UserId):
            raise ValueError("GroupInvitation.target_user_id must be a UserId")
        if self.target_wallet is not None:
            object.__setattr__(self, "target_wallet", _coerce_wallet(self.target_wallet))
        if self.target_email is not None:
            object.__setattr__(self, "target_email", _require_text(self.target_email, "GroupInvitation.target_email"))
        if self.expires_at is not None:
            object.__setattr__(self, "expires_at", _require_aware_datetime(self.expires_at, "GroupInvitation.expires_at"))
        if self.target_user_id is None and self.target_wallet is None and self.target_email is None:
            raise ValueError("GroupInvitation requires a user, wallet, or email target")

    def is_open_for(self, user_id: UserId, wallet: WalletAddress | str | None, now: datetime) -> bool:
        now = _require_aware_datetime(now, "now")
        if self.status is not InvitationStatus.PENDING:
            return False
        if self.expires_at is not None and now >= self.expires_at:
            return False
        if self.target_user_id is not None and self.target_user_id != user_id:
            return False
        if self.target_wallet is not None and wallet is not None and self.target_wallet != _coerce_wallet(wallet):
            return False
        return True


@dataclass(frozen=True)
class SessionMembership:
    group_id: GroupId
    group_type: GroupType | str
    role_id: RoleId | str
    resource_type: str | None = None
    resource_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.group_id, GroupId):
            raise ValueError("SessionMembership.group_id must be a GroupId")
        object.__setattr__(self, "group_type", _coerce_group_type(self.group_type))
        if not isinstance(self.role_id, RoleId):
            object.__setattr__(self, "role_id", RoleId(str(self.role_id)))
        if self.resource_type is not None:
            object.__setattr__(self, "resource_type", _require_text(self.resource_type, "SessionMembership.resource_type"))
        if self.resource_id is not None:
            object.__setattr__(self, "resource_id", _require_text(self.resource_id, "SessionMembership.resource_id"))

    def to_payload(self) -> dict[str, str | None]:
        return {
            "groupId": str(self.group_id),
            "groupType": self.group_type.value,
            "roleId": str(self.role_id),
            "resourceType": self.resource_type,
            "resourceId": self.resource_id,
        }


@dataclass(frozen=True)
class LoginChallenge:
    wallet: WalletAddress | str
    nonce: AuthNonce
    status: ChallengeStatus
    issued_at: datetime
    domain: str | None = None
    uri: str | None = None
    chain_id: int | None = None
    verified_at: datetime | None = None
    rejected_reason: LoginFailureReason | None = None
    purpose: ChallengePurpose | str = ChallengePurpose.LOGIN
    target_user_id: UserId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "wallet", _coerce_wallet(self.wallet))
        if not isinstance(self.nonce, AuthNonce):
            raise ValueError("LoginChallenge.nonce must be an AuthNonce")
        object.__setattr__(self, "status", _coerce_challenge_status(self.status))
        object.__setattr__(self, "purpose", _coerce_challenge_purpose(self.purpose))
        object.__setattr__(
            self,
            "issued_at",
            _require_aware_datetime(self.issued_at, "LoginChallenge.issued_at"),
        )
        if any(value is not None for value in (self.domain, self.uri, self.chain_id)):
            if self.domain is None or self.uri is None or self.chain_id is None:
                raise ValueError("LoginChallenge SIWE context requires domain, uri, and chain_id")
            object.__setattr__(self, "domain", _require_text(self.domain, "LoginChallenge.domain"))
            object.__setattr__(self, "uri", _require_text(self.uri, "LoginChallenge.uri"))
            if isinstance(self.chain_id, bool) or not isinstance(self.chain_id, int) or self.chain_id <= 0:
                raise ValueError("LoginChallenge.chain_id must be a positive integer")
        if self.verified_at is not None:
            object.__setattr__(
                self,
                "verified_at",
                _require_aware_datetime(self.verified_at, "LoginChallenge.verified_at"),
            )
        if self.rejected_reason is not None:
            object.__setattr__(self, "rejected_reason", _coerce_login_failure_reason(self.rejected_reason))
        if self.target_user_id is not None and not isinstance(self.target_user_id, UserId):
            raise ValueError("LoginChallenge.target_user_id must be a UserId")
        if self.purpose is ChallengePurpose.WALLET_LINK and self.target_user_id is None:
            raise ValueError("wallet link challenges require target_user_id")
        if self.status is ChallengeStatus.VERIFIED and self.verified_at is None:
            raise ValueError("verified challenges require verified_at")
        if self.status is ChallengeStatus.REJECTED and self.rejected_reason is None:
            raise ValueError("rejected challenges require rejected_reason")

    @classmethod
    def issue(
        cls,
        wallet: WalletAddress | str,
        nonce: AuthNonce,
        issued_at: datetime | None = None,
        *,
        domain: str | None = None,
        uri: str | None = None,
        chain_id: int | None = None,
        purpose: ChallengePurpose | str = ChallengePurpose.LOGIN,
        target_user_id: UserId | None = None,
    ) -> Self:
        issued_at = issued_at or datetime.now(UTC)
        issued_at = _require_aware_datetime(issued_at, "issued_at")
        if nonce.is_expired(issued_at):
            raise ValueError("LoginChallenge cannot be issued with an expired nonce")
        return cls(
            wallet=wallet,
            nonce=nonce,
            status=ChallengeStatus.ISSUED,
            issued_at=issued_at,
            domain=domain,
            uri=uri,
            chain_id=chain_id,
            purpose=purpose,
            target_user_id=target_user_id,
        )

    @property
    def expires_at(self) -> datetime:
        return self.nonce.expires_at

    def verify_signature(self, recovered_wallet: WalletAddress | str, now: datetime | None = None) -> Self:
        now = now or datetime.now(UTC)
        self._ensure_issued_for_attempt(now)
        if _coerce_wallet(recovered_wallet) != self.wallet:
            raise LoginChallengeRejected(LoginFailureReason.WALLET_MISMATCH)
        return replace(self, status=ChallengeStatus.VERIFIED, verified_at=now)

    def confirm_signature_verified(self, now: datetime | None = None) -> Self:
        now = now or datetime.now(UTC)
        self._ensure_issued_for_attempt(now)
        return replace(self, status=ChallengeStatus.VERIFIED, verified_at=now)

    def reject(self, reason: LoginFailureReason, now: datetime | None = None) -> Self:
        now = now or datetime.now(UTC)
        self._ensure_issued_for_attempt(now)
        reason = _coerce_login_failure_reason(reason)
        return replace(self, status=ChallengeStatus.REJECTED, rejected_reason=reason)

    def expire(self, now: datetime | None = None) -> Self:
        now = now or datetime.now(UTC)
        now = _require_aware_datetime(now, "now")
        if self.status is ChallengeStatus.EXPIRED:
            return self
        if self.status is not ChallengeStatus.ISSUED:
            raise LoginChallengeRejected(LoginFailureReason.REUSED_NONCE)
        if not self.nonce.is_expired(now):
            raise ValueError("LoginChallenge cannot expire before AuthNonce.expires_at")
        return replace(self, status=ChallengeStatus.EXPIRED)

    def _ensure_issued_for_attempt(self, now: datetime) -> None:
        now = _require_aware_datetime(now, "now")
        if self.status is ChallengeStatus.EXPIRED:
            raise LoginChallengeRejected(LoginFailureReason.EXPIRED_CHALLENGE)
        if self.status is not ChallengeStatus.ISSUED:
            raise LoginChallengeRejected(LoginFailureReason.REUSED_NONCE)
        if self.nonce.is_expired(now):
            raise LoginChallengeRejected(LoginFailureReason.EXPIRED_CHALLENGE)


@dataclass(frozen=True)
class AuthSession:
    session_id: SessionId
    user_id: UserId
    login_wallet_id: WalletId
    refresh_token_hash: RefreshTokenHash
    device_id: str
    expires_at: datetime
    revoked_at: datetime | None = None
    wallet: WalletAddress | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId):
            raise ValueError("AuthSession.session_id must be a SessionId")
        if not isinstance(self.user_id, UserId):
            raise ValueError("AuthSession.user_id must be a UserId")
        if not isinstance(self.login_wallet_id, WalletId):
            raise TypeError("AuthSession.login_wallet_id must be a WalletId")
        if not isinstance(self.refresh_token_hash, RefreshTokenHash):
            raise ValueError("AuthSession.refresh_token_hash must be a RefreshTokenHash")
        object.__setattr__(self, "device_id", _require_text(self.device_id, "AuthSession.device_id"))
        object.__setattr__(
            self,
            "expires_at",
            _require_aware_datetime(self.expires_at, "AuthSession.expires_at"),
        )
        if self.revoked_at is not None:
            object.__setattr__(
                self,
                "revoked_at",
                _require_aware_datetime(self.revoked_at, "AuthSession.revoked_at"),
            )
        if self.wallet is not None:
            object.__setattr__(self, "wallet", _coerce_wallet(self.wallet))

    @classmethod
    def create(
        cls,
        user_id: UserId,
        login_wallet_id: WalletId,
        refresh_token_hash: RefreshTokenHash,
        device_id: str,
        expires_at: datetime,
        session_id: SessionId | None = None,
        wallet: WalletAddress | str | None = None,
    ) -> Self:
        return cls(
            session_id=session_id or SessionId.new(),
            user_id=user_id,
            login_wallet_id=login_wallet_id,
            refresh_token_hash=refresh_token_hash,
            device_id=device_id,
            expires_at=expires_at,
            wallet=wallet,
        )

    def rotate_refresh_token(self, refresh_token_hash: RefreshTokenHash) -> Self:
        self._ensure_active(datetime.now(UTC))
        return replace(self, refresh_token_hash=refresh_token_hash)

    def revoke(self, revoked_at: datetime | None = None) -> Self:
        return replace(self, revoked_at=revoked_at or datetime.now(UTC))

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        now = _require_aware_datetime(now, "now")
        return self.revoked_at is None and now < self.expires_at

    def _ensure_active(self, now: datetime) -> None:
        if not self.is_active(now):
            raise ValueError("inactive sessions cannot be changed")


@dataclass(frozen=True)
class UserRegisteredEvent:
    user_id: UserId
    wallet: WalletAddress | str
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("UserRegisteredEvent.user_id must be a UserId")
        object.__setattr__(self, "wallet", _coerce_wallet(self.wallet))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "UserRegisteredEvent.created_at"),
        )


@dataclass(frozen=True)
class WalletVerifiedEvent:
    user_id: UserId
    wallet: WalletAddress | str
    verified_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("WalletVerifiedEvent.user_id must be a UserId")
        object.__setattr__(self, "wallet", _coerce_wallet(self.wallet))
        object.__setattr__(
            self,
            "verified_at",
            _require_aware_datetime(self.verified_at, "WalletVerifiedEvent.verified_at"),
        )


@dataclass(frozen=True)
class WalletLinkedEvent:
    user_id: UserId
    wallet_id: WalletId
    wallet: WalletAddress | str
    chain_id: int
    linked_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("WalletLinkedEvent.user_id must be a UserId")
        if not isinstance(self.wallet_id, WalletId):
            raise TypeError("WalletLinkedEvent.wallet_id must be a WalletId")
        object.__setattr__(self, "wallet", _coerce_wallet(self.wallet))
        if isinstance(self.chain_id, bool) or not isinstance(self.chain_id, int) or self.chain_id <= 0:
            raise ValueError("WalletLinkedEvent.chain_id must be a positive integer")
        object.__setattr__(
            self,
            "linked_at",
            _require_aware_datetime(self.linked_at, "WalletLinkedEvent.linked_at"),
        )


@dataclass(frozen=True)
class WalletPrimaryChangedEvent:
    user_id: UserId
    wallet_id: WalletId
    chain_id: int
    changed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("WalletPrimaryChangedEvent.user_id must be a UserId")
        if not isinstance(self.wallet_id, WalletId):
            raise TypeError("WalletPrimaryChangedEvent.wallet_id must be a WalletId")
        if isinstance(self.chain_id, bool) or not isinstance(self.chain_id, int) or self.chain_id <= 0:
            raise ValueError("WalletPrimaryChangedEvent.chain_id must be a positive integer")
        object.__setattr__(
            self,
            "changed_at",
            _require_aware_datetime(self.changed_at, "WalletPrimaryChangedEvent.changed_at"),
        )


@dataclass(frozen=True)
class WalletRevokedEvent:
    user_id: UserId
    wallet_id: WalletId
    wallet: WalletAddress | str
    chain_id: int
    revoked_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("WalletRevokedEvent.user_id must be a UserId")
        if not isinstance(self.wallet_id, WalletId):
            raise TypeError("WalletRevokedEvent.wallet_id must be a WalletId")
        object.__setattr__(self, "wallet", _coerce_wallet(self.wallet))
        if isinstance(self.chain_id, bool) or not isinstance(self.chain_id, int) or self.chain_id <= 0:
            raise ValueError("WalletRevokedEvent.chain_id must be a positive integer")
        object.__setattr__(
            self,
            "revoked_at",
            _require_aware_datetime(self.revoked_at, "WalletRevokedEvent.revoked_at"),
        )


@dataclass(frozen=True)
class UserLoggedInEvent:
    user_id: UserId
    session_id: SessionId
    logged_in_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("UserLoggedInEvent.user_id must be a UserId")
        if not isinstance(self.session_id, SessionId):
            raise ValueError("UserLoggedInEvent.session_id must be a SessionId")
        object.__setattr__(
            self,
            "logged_in_at",
            _require_aware_datetime(self.logged_in_at, "UserLoggedInEvent.logged_in_at"),
        )


@dataclass(frozen=True)
class LoginRejectedEvent:
    wallet: WalletAddress | str
    reason: LoginFailureReason
    rejected_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "wallet", _coerce_wallet(self.wallet))
        object.__setattr__(self, "reason", _coerce_login_failure_reason(self.reason))
        object.__setattr__(
            self,
            "rejected_at",
            _require_aware_datetime(self.rejected_at, "LoginRejectedEvent.rejected_at"),
        )


AuthEvent: TypeAlias = (
    UserRegisteredEvent
    | WalletVerifiedEvent
    | WalletLinkedEvent
    | WalletPrimaryChangedEvent
    | WalletRevokedEvent
    | UserLoggedInEvent
    | LoginRejectedEvent
)


def _coerce_wallet(value: WalletAddress | str) -> WalletAddress:
    return value if isinstance(value, WalletAddress) else WalletAddress(value)


def _coerce_user_role(value: UserRole | str) -> UserRole:
    if isinstance(value, UserRole):
        return value
    try:
        return UserRole(str(value))
    except ValueError as exc:
        raise ValueError("User.role must be a UserRole") from exc


def _coerce_group_type(value: GroupType | str) -> GroupType:
    if isinstance(value, GroupType):
        return value
    try:
        return GroupType(str(value))
    except ValueError as exc:
        raise ValueError("Group.group_type must be PERSONAL, MERCHANT, or PLATFORM") from exc


def _coerce_invitation_status(value: InvitationStatus | str) -> InvitationStatus:
    if isinstance(value, InvitationStatus):
        return value
    try:
        return InvitationStatus(str(value))
    except ValueError as exc:
        raise ValueError("GroupInvitation.status is invalid") from exc


def _coerce_challenge_status(value: ChallengeStatus | str) -> ChallengeStatus:
    if isinstance(value, ChallengeStatus):
        return value
    try:
        return ChallengeStatus(str(value))
    except ValueError as exc:
        raise ValueError("LoginChallenge.status must be a ChallengeStatus") from exc


def _coerce_challenge_purpose(value: ChallengePurpose | str) -> ChallengePurpose:
    if isinstance(value, ChallengePurpose):
        return value
    try:
        return ChallengePurpose(str(value))
    except ValueError as exc:
        raise ValueError("LoginChallenge.purpose must be a ChallengePurpose") from exc


def _coerce_login_failure_reason(value: LoginFailureReason | str) -> LoginFailureReason:
    if isinstance(value, LoginFailureReason):
        return value
    try:
        return LoginFailureReason(str(value))
    except ValueError as exc:
        raise ValueError("LoginFailureReason is invalid") from exc


def _coerce_uuid(value: UUID | str, field_name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return UUID(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a valid UUID") from exc
    raise ValueError(f"{field_name} must be a non-empty UUID")


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value

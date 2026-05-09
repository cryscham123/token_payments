"""Domain model for MetaMask nonce authentication."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self, TypeAlias
from uuid import UUID, uuid4

from token_payments.shared.domain import UserId, WalletAddress


class UserRole(StrEnum):
    CUSTOMER = "CUSTOMER"
    STORE_OWNER = "STORE_OWNER"
    ADMIN = "ADMIN"


class ChallengeStatus(StrEnum):
    ISSUED = "ISSUED"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class LoginFailureReason(StrEnum):
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED_CHALLENGE = "EXPIRED_CHALLENGE"
    REUSED_NONCE = "REUSED_NONCE"
    WALLET_MISMATCH = "WALLET_MISMATCH"


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
    role: UserRole = UserRole.CUSTOMER
    active: bool = True
    last_login_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UserId):
            raise ValueError("User.user_id must be a UserId")
        object.__setattr__(self, "primary_wallet", _coerce_wallet(self.primary_wallet))
        object.__setattr__(self, "role", _coerce_user_role(self.role))
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
        role: UserRole = UserRole.CUSTOMER,
    ) -> Self:
        return cls(user_id=user_id, primary_wallet=wallet, role=role, active=True)

    def link_wallet(self, wallet: WalletAddress | str) -> Self:
        self._ensure_active()
        return replace(self, primary_wallet=_coerce_wallet(wallet))

    def record_login(self, logged_in_at: datetime | None = None) -> Self:
        self._ensure_active()
        return replace(self, last_login_at=logged_in_at or datetime.now(UTC))

    def deactivate(self) -> Self:
        return replace(self, active=False)

    def _ensure_active(self) -> None:
        if not self.active:
            raise ValueError("inactive users cannot be changed")


@dataclass(frozen=True)
class LoginChallenge:
    wallet: WalletAddress | str
    nonce: AuthNonce
    status: ChallengeStatus
    issued_at: datetime
    verified_at: datetime | None = None
    rejected_reason: LoginFailureReason | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "wallet", _coerce_wallet(self.wallet))
        if not isinstance(self.nonce, AuthNonce):
            raise ValueError("LoginChallenge.nonce must be an AuthNonce")
        object.__setattr__(self, "status", _coerce_challenge_status(self.status))
        object.__setattr__(
            self,
            "issued_at",
            _require_aware_datetime(self.issued_at, "LoginChallenge.issued_at"),
        )
        if self.verified_at is not None:
            object.__setattr__(
                self,
                "verified_at",
                _require_aware_datetime(self.verified_at, "LoginChallenge.verified_at"),
            )
        if self.rejected_reason is not None:
            object.__setattr__(self, "rejected_reason", _coerce_login_failure_reason(self.rejected_reason))
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
    wallet: WalletAddress | str
    refresh_token_hash: RefreshTokenHash
    device_id: str
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, SessionId):
            raise ValueError("AuthSession.session_id must be a SessionId")
        if not isinstance(self.user_id, UserId):
            raise ValueError("AuthSession.user_id must be a UserId")
        object.__setattr__(self, "wallet", _coerce_wallet(self.wallet))
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

    @classmethod
    def create(
        cls,
        user_id: UserId,
        wallet: WalletAddress | str,
        refresh_token_hash: RefreshTokenHash,
        device_id: str,
        expires_at: datetime,
        session_id: SessionId | None = None,
    ) -> Self:
        return cls(
            session_id=session_id or SessionId.new(),
            user_id=user_id,
            wallet=wallet,
            refresh_token_hash=refresh_token_hash,
            device_id=device_id,
            expires_at=expires_at,
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


AuthEvent: TypeAlias = UserRegisteredEvent | WalletVerifiedEvent | UserLoggedInEvent | LoginRejectedEvent


def _coerce_wallet(value: WalletAddress | str) -> WalletAddress:
    return value if isinstance(value, WalletAddress) else WalletAddress(value)


def _coerce_user_role(value: UserRole | str) -> UserRole:
    if isinstance(value, UserRole):
        return value
    try:
        return UserRole(str(value))
    except ValueError as exc:
        raise ValueError("User.role must be a UserRole") from exc


def _coerce_challenge_status(value: ChallengeStatus | str) -> ChallengeStatus:
    if isinstance(value, ChallengeStatus):
        return value
    try:
        return ChallengeStatus(str(value))
    except ValueError as exc:
        raise ValueError("LoginChallenge.status must be a ChallengeStatus") from exc


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

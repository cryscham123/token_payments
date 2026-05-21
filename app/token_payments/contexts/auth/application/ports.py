"""Application port contracts for the authentication bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from token_payments.contexts.auth.domain import (
    AuthEvent,
    AuthSession,
    AuthNonce,
    IssuedToken,
    LoginChallenge,
    RefreshTokenHash,
    SessionMembership,
    SessionId,
    User,
    UserProfile,
)
from token_payments.shared.domain import UserId, WalletAddress


@dataclass(frozen=True)
class RequestLoginChallengeCommand:
    wallet_address: WalletAddress | str
    domain: str
    chain_id: int
    uri: str | None = None
    issued_at: datetime | None = None


@dataclass(frozen=True)
class LoginChallengeResult:
    challenge: LoginChallenge
    signing_message: str


@dataclass(frozen=True)
class LoginWithMetaMaskCommand:
    wallet_address: WalletAddress | str
    message: str
    signature: str
    device_id: str


@dataclass(frozen=True)
class LoginResult:
    user: User
    session: AuthSession
    issued_token: IssuedToken


class WalletSignatureVerificationFailure(StrEnum):
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    WALLET_MISMATCH = "WALLET_MISMATCH"
    UNSUPPORTED_CHAIN = "UNSUPPORTED_CHAIN"


@dataclass(frozen=True)
class WalletSignatureVerificationResult:
    verified: bool
    failure: WalletSignatureVerificationFailure | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.verified, bool):
            raise ValueError("WalletSignatureVerificationResult.verified must be a bool")
        if self.verified and self.failure is not None:
            raise ValueError("verified wallet signature results cannot include a failure")
        if not self.verified:
            if self.failure is None:
                raise ValueError("failed wallet signature results require a failure")
            object.__setattr__(self, "failure", WalletSignatureVerificationFailure(self.failure))

    @classmethod
    def verified(cls) -> "WalletSignatureVerificationResult":
        return cls(verified=True)

    @classmethod
    def failed(cls, failure: WalletSignatureVerificationFailure) -> "WalletSignatureVerificationResult":
        return cls(verified=False, failure=failure)


@dataclass(frozen=True)
class RefreshSessionCommand:
    session_id: SessionId
    refresh_token_hash: RefreshTokenHash


@dataclass(frozen=True)
class LogoutCommand:
    session_id: SessionId
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class CurrentUserQuery:
    user_id: UserId


@dataclass(frozen=True)
class GetCurrentUserProfileQuery:
    user_id: UserId


@dataclass(frozen=True)
class GetUserProfileQuery:
    user_id: UserId


@dataclass(frozen=True)
class UpdateUserProfileCommand:
    actor_user_id: UserId
    target_user_id: UserId
    display_name: str | None = None
    email: str | None = None
    locale: str | None = None
    timezone: str | None = None
    requested_at: datetime | None = None
    request_id: str | None = None
    actor_scopes: tuple[str, ...] = ()


class AuthUseCase(Protocol):
    def requestLoginChallenge(self, command: RequestLoginChallengeCommand) -> LoginChallengeResult:
        ...

    def loginWithMetaMask(self, command: LoginWithMetaMaskCommand) -> LoginResult:
        ...

    def refreshSession(self, command: RefreshSessionCommand) -> LoginResult:
        ...

    def logout(self, command: LogoutCommand) -> AuthSession:
        ...

    def getCurrentUser(self, query: CurrentUserQuery) -> User | None:
        ...

    def getCurrentUserProfile(self, query: GetCurrentUserProfileQuery) -> UserProfile | None:
        ...

    def getUserProfile(self, query: GetUserProfileQuery) -> UserProfile | None:
        ...

    def updateUserProfile(self, command: UpdateUserProfileCommand) -> UserProfile:
        ...


class UserRepository(Protocol):
    def save(self, user: User) -> None:
        ...

    def get_by_id(self, user_id: UserId) -> User | None:
        ...

    def get_by_wallet(self, wallet: WalletAddress) -> User | None:
        ...


class UserProfileRepository(Protocol):
    def save(self, profile: UserProfile) -> None:
        ...

    def get_by_user_id(self, user_id: UserId) -> UserProfile | None:
        ...


class LoginChallengeRepository(Protocol):
    def save(self, challenge: LoginChallenge) -> None:
        ...

    def get_by_nonce(self, nonce: AuthNonce) -> LoginChallenge | None:
        ...

    def get_issued_by_wallet(self, wallet: WalletAddress) -> LoginChallenge | None:
        ...


class AuthSessionRepository(Protocol):
    def save(self, session: AuthSession) -> None:
        ...

    def get_by_id(self, session_id: SessionId) -> AuthSession | None:
        ...

    def get_by_refresh_token_hash(self, refresh_token_hash: RefreshTokenHash) -> AuthSession | None:
        ...


class AuthRbacRepository(Protocol):
    def ensure_personal_membership(self, user: User, joined_at: datetime) -> tuple[SessionMembership, ...]:
        ...

    def session_memberships_for_user(self, user_id: UserId) -> tuple[SessionMembership, ...]:
        ...

    def scopes_for_user(self, user_id: UserId) -> tuple[str, ...]:
        ...


class WalletSignatureVerifier(Protocol):
    def verify_signature(
        self,
        wallet: WalletAddress,
        message: str,
        signature: str,
        chain_id: int,
    ) -> WalletSignatureVerificationResult:
        ...


class TokenIssuer(Protocol):
    def issue_tokens(self, user: User, session: AuthSession) -> IssuedToken:
        ...

    def refresh_tokens(self, session: AuthSession) -> IssuedToken:
        ...


class AuthEventPublisher(Protocol):
    def publish(self, event: AuthEvent) -> None:
        ...

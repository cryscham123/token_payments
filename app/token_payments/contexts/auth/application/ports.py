"""Application port contracts for the authentication bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from token_payments.contexts.auth.domain import (
    AuthEvent,
    AuthSession,
    AuthNonce,
    IssuedToken,
    LoginChallenge,
    RefreshTokenHash,
    SessionId,
    User,
)
from token_payments.shared.domain import UserId, WalletAddress


@dataclass(frozen=True)
class RequestLoginChallengeCommand:
    wallet_address: WalletAddress | str
    domain: str
    chain_id: int
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


class UserRepository(Protocol):
    def save(self, user: User) -> None:
        ...

    def get_by_id(self, user_id: UserId) -> User | None:
        ...

    def get_by_wallet(self, wallet: WalletAddress) -> User | None:
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


class WalletSignatureVerifier(Protocol):
    def recover_address(self, message: str, signature: str) -> WalletAddress:
        ...


class TokenIssuer(Protocol):
    def issue_tokens(self, user: User, session: AuthSession) -> IssuedToken:
        ...

    def refresh_tokens(self, session: AuthSession) -> IssuedToken:
        ...


class AuthEventPublisher(Protocol):
    def publish(self, event: AuthEvent) -> None:
        ...

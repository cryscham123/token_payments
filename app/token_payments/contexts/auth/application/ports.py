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
    OAuthIdentity,
    OAuthIdentityId,
    RefreshTokenHash,
    SessionMembership,
    SessionId,
    User,
    UserProfile,
)
from token_payments.shared.domain import UserId, WalletAddress
from token_payments.contexts.auth.domain.wallet import WalletId
from token_payments.contexts.auth.domain.wallet import UserWallet, WalletType



@dataclass(frozen=True)
class RequestLoginChallengeCommand:
    wallet_address: WalletAddress | str
    domain: str
    chain_id: int
    uri: str | None = None
    issued_at: datetime | None = None


@dataclass(frozen=True)
class RequestWalletLinkChallengeCommand:
    actor_user_id: UserId
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
class WalletLinkChallengeResult:
    challenge: LoginChallenge
    signing_message: str


@dataclass(frozen=True)
class LoginWithMetaMaskCommand:
    wallet_address: WalletAddress | str
    message: str
    signature: str
    device_id: str


class OAuthAuthorizationMode(StrEnum):
    LOGIN = "login"
    LINK = "link"


@dataclass(frozen=True)
class RequestOAuthAuthorizationCommand:
    provider: str
    redirect_uri: str
    mode: OAuthAuthorizationMode | str = OAuthAuthorizationMode.LOGIN
    actor_user_id: UserId | None = None
    requested_at: datetime | None = None


@dataclass(frozen=True)
class CompleteOAuthSessionCommand:
    provider: str
    code: str
    state: str
    redirect_uri: str
    device_id: str
    requested_at: datetime | None = None


@dataclass(frozen=True)
class LinkOAuthIdentityCommand:
    actor_user_id: UserId
    provider: str
    code: str
    state: str
    redirect_uri: str
    wallet_id: WalletId | None = None
    requested_at: datetime | None = None


@dataclass(frozen=True)
class ListOAuthIdentitiesQuery:
    actor_user_id: UserId


@dataclass(frozen=True)
class RevokeOAuthIdentityCommand:
    actor_user_id: UserId
    oauth_identity_id: OAuthIdentityId
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class OAuthAuthorizationResult:
    provider: str
    authorization_url: str
    state: str
    mode: OAuthAuthorizationMode | str
    expires_at: datetime
    pkce_required: bool = True


@dataclass(frozen=True)
class OAuthProviderIdentity:
    provider: str
    provider_subject: str


@dataclass(frozen=True)
class OAuthSessionResult:
    login: LoginResult
    oauth_identity: OAuthIdentity


@dataclass(frozen=True)
class OAuthIdentityResult:
    oauth_identity: OAuthIdentity


@dataclass(frozen=True)
class OAuthIdentitiesResult:
    oauth_identities: tuple[OAuthIdentity, ...]


@dataclass(frozen=True)
class LinkWalletCommand:
    actor_user_id: UserId
    wallet_address: WalletAddress | str
    message: str
    signature: str
    wallet_type: WalletType | str = WalletType.EOA


@dataclass(frozen=True)
class ListWalletsQuery:
    actor_user_id: UserId


@dataclass(frozen=True)
class SetPrimaryWalletCommand:
    actor_user_id: UserId
    wallet_id: WalletId


@dataclass(frozen=True)
class RevokeWalletCommand:
    actor_user_id: UserId
    wallet_id: WalletId
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class LoginResult:
    user: User
    session: AuthSession
    issued_token: IssuedToken


@dataclass(frozen=True)
class WalletResult:
    wallet: UserWallet


@dataclass(frozen=True)
class WalletsResult:
    wallets: tuple[UserWallet, ...]


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
    display_name_provided: bool = False
    requested_at: datetime | None = None
    request_id: str | None = None
    actor_scopes: tuple[str, ...] = ()


class AuthUseCase(Protocol):
    def requestLoginChallenge(self, command: RequestLoginChallengeCommand) -> LoginChallengeResult:
        ...

    def requestWalletLinkChallenge(self, command: RequestWalletLinkChallengeCommand) -> WalletLinkChallengeResult:
        ...

    def loginWithMetaMask(self, command: LoginWithMetaMaskCommand) -> LoginResult:
        ...

    def requestOAuthAuthorization(self, command: RequestOAuthAuthorizationCommand) -> OAuthAuthorizationResult:
        ...

    def completeOAuthSession(self, command: CompleteOAuthSessionCommand) -> OAuthSessionResult:
        ...

    def linkOAuthIdentity(self, command: LinkOAuthIdentityCommand) -> OAuthIdentityResult:
        ...

    def listOAuthIdentities(self, query: ListOAuthIdentitiesQuery) -> OAuthIdentitiesResult:
        ...

    def revokeOAuthIdentity(self, command: RevokeOAuthIdentityCommand) -> OAuthIdentityResult:
        ...

    def linkWallet(self, command: LinkWalletCommand) -> WalletResult:
        ...

    def listWallets(self, query: ListWalletsQuery) -> WalletsResult:
        ...

    def setPrimaryWallet(self, command: SetPrimaryWalletCommand) -> WalletResult:
        ...

    def revokeWallet(self, command: RevokeWalletCommand) -> WalletResult:
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

    def get_wallet_id_for_address(self, user_id: UserId, wallet: WalletAddress) -> WalletId:
        ...


class UserWalletRepository(Protocol):
    def save(self, wallet: UserWallet) -> None:
        ...

    def get_by_id(self, wallet_id: WalletId) -> UserWallet | None:
        ...

    def get_active_by_address(self, chain_id: int, wallet: WalletAddress) -> UserWallet | None:
        ...

    def list_for_user(self, user_id: UserId) -> tuple[UserWallet, ...]:
        ...

    def get_primary_for_user_chain(self, user_id: UserId, chain_id: int) -> UserWallet | None:
        ...

    def unset_primary_for_chain(self, user_id: UserId, chain_id: int, except_wallet_id: WalletId) -> None:
        ...


class UserProfileRepository(Protocol):
    def save(self, profile: UserProfile) -> None:
        ...

    def get_by_user_id(self, user_id: UserId) -> UserProfile | None:
        ...

    def get_by_display_name(self, display_name: str) -> UserProfile | None:
        ...


class OAuthIdentityRepository(Protocol):
    def save(self, identity: OAuthIdentity) -> None:
        ...

    def get_by_id(self, oauth_identity_id: OAuthIdentityId) -> OAuthIdentity | None:
        ...

    def get_active_by_provider_subject(self, provider: str, provider_subject: str) -> OAuthIdentity | None:
        ...

    def list_for_user(self, user_id: UserId) -> tuple[OAuthIdentity, ...]:
        ...


class OAuthProvider(Protocol):
    def build_authorization(
        self,
        *,
        provider: str,
        redirect_uri: str,
        state: str,
        mode: OAuthAuthorizationMode,
        expires_at: datetime,
    ) -> OAuthAuthorizationResult:
        ...

    def exchange_code(
        self,
        *,
        provider: str,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> OAuthProviderIdentity:
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

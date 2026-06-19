"""Pure authentication use case implementation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
from typing import Any

from token_payments.contexts.auth.domain import (
    AuthNonce,
    AuthSession,
    ChallengePurpose,
    IssuedToken,
    LoginChallenge,
    LoginChallengeRejected,
    LoginFailureReason,
    LoginRejectedEvent,
    OAuthIdentity,
    OAuthIdentityId,
    RefreshTokenHash,
    SessionId,
    User,
    UserLoggedInEvent,
    UserProfile,
    UserRegisteredEvent,
    WalletLinkedEvent,
    WalletPrimaryChangedEvent,
    WalletRevokedEvent,
    WalletVerifiedEvent,
)
from token_payments.shared.domain import UserId, WalletAddress
from token_payments.contexts.auth.domain.wallet import (
    UserWallet,
    WalletId,
    WalletType,
    WalletVerificationStatus,
)

from .ports import (
    AuthEventPublisher,
    AuthRbacRepository,
    AuthSessionRepository,
    CurrentUserQuery,
    CompleteOAuthSessionCommand,
    GetCurrentUserProfileQuery,
    GetUserProfileQuery,
    LinkOAuthIdentityCommand,
    LinkWalletCommand,
    ListOAuthIdentitiesQuery,
    ListWalletsQuery,
    LoginChallengeRepository,
    LoginChallengeResult,
    LoginResult,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    OAuthAuthorizationMode,
    OAuthAuthorizationResult,
    OAuthIdentitiesResult,
    OAuthIdentityRepository,
    OAuthIdentityResult,
    OAuthProvider,
    OAuthProviderIdentity,
    OAuthSessionResult,
    RefreshSessionCommand,
    RequestOAuthAuthorizationCommand,
    RequestLoginChallengeCommand,
    RequestWalletLinkChallengeCommand,
    RevokeOAuthIdentityCommand,
    RevokeWalletCommand,
    SetPrimaryWalletCommand,
    TokenIssuer,
    UpdateUserProfileCommand,
    UserProfileRepository,
    UserRepository,
    UserWalletRepository,
    WalletLinkChallengeResult,
    WalletResult,
    WalletSignatureVerificationFailure,
    WalletSignatureVerificationResult,
    WalletSignatureVerifier,
    WalletsResult,
)
from .siwe import (
    SIWE_VERSION,
    SiweMessage,
    build_siwe_message,
    default_siwe_uri,
    normalize_siwe_nonce,
    parse_siwe_message,
)


class AuthErrorCode(StrEnum):
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED_CHALLENGE = "EXPIRED_CHALLENGE"
    REUSED_NONCE = "REUSED_NONCE"
    WALLET_MISMATCH = "WALLET_MISMATCH"
    SIWE_MESSAGE_MISMATCH = "SIWE_MESSAGE_MISMATCH"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    USER_PROFILE_FORBIDDEN = "USER_PROFILE_FORBIDDEN"
    USER_PROFILE_NOT_FOUND = "USER_PROFILE_NOT_FOUND"
    USER_PROFILE_DISPLAY_NAME_CONFLICT = "USER_PROFILE_DISPLAY_NAME_CONFLICT"
    WALLET_ALREADY_LINKED = "WALLET_ALREADY_LINKED"
    WALLET_LINK_CHALLENGE_MISMATCH = "WALLET_LINK_CHALLENGE_MISMATCH"
    WALLET_NOT_FOUND = "WALLET_NOT_FOUND"
    WALLET_NOT_ACTIVE = "WALLET_NOT_ACTIVE"
    LAST_WALLET_REVOKE_DENIED = "LAST_WALLET_REVOKE_DENIED"
    OAUTH_PROVIDER_UNSUPPORTED = "OAUTH_PROVIDER_UNSUPPORTED"
    OAUTH_IDENTITY_NOT_LINKED = "OAUTH_IDENTITY_NOT_LINKED"
    OAUTH_IDENTITY_ALREADY_LINKED = "OAUTH_IDENTITY_ALREADY_LINKED"
    OAUTH_IDENTITY_NOT_FOUND = "OAUTH_IDENTITY_NOT_FOUND"
    LAST_LOGIN_METHOD_REVOKE_DENIED = "LAST_LOGIN_METHOD_REVOKE_DENIED"


class AuthApplicationError(Exception):
    def __init__(self, code: AuthErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class AuthApplicationService:
    """Application service for SIWE login and session lifecycle."""

    def __init__(
        self,
        *,
        clock: Any,
        nonce_generator: Any,
        user_id_generator: Any,
        session_id_generator: Any,
        users: UserRepository,
        login_challenges: LoginChallengeRepository,
        sessions: AuthSessionRepository,
        signature_verifier: WalletSignatureVerifier,
        token_issuer: TokenIssuer,
        event_publisher: AuthEventPublisher,
        wallets: UserWalletRepository | None = None,
        rbac: AuthRbacRepository | None = None,
        profiles: UserProfileRepository | None = None,
        oauth_identities: OAuthIdentityRepository | None = None,
        oauth_provider: OAuthProvider | None = None,
        challenge_ttl: timedelta = timedelta(minutes=5),
        session_ttl: timedelta = timedelta(days=30),
    ) -> None:
        self._clock = clock
        self._nonce_generator = nonce_generator
        self._user_id_generator = user_id_generator
        self._session_id_generator = session_id_generator
        self._users = users
        self._wallets = wallets
        self._login_challenges = login_challenges
        self._sessions = sessions
        self._rbac = rbac
        self._profiles = profiles
        self._oauth_identities = oauth_identities
        self._oauth_provider = oauth_provider
        self._signature_verifier = signature_verifier
        self._token_issuer = token_issuer
        self._event_publisher = event_publisher
        self._challenge_ttl = _require_positive_timedelta(challenge_ttl, "challenge_ttl")
        self._session_ttl = _require_positive_timedelta(session_ttl, "session_ttl")

    def requestLoginChallenge(self, command: RequestLoginChallengeCommand) -> LoginChallengeResult:
        wallet = _coerce_wallet(command.wallet_address)
        domain = _require_text(command.domain, "domain")
        chain_id = _require_positive_int(command.chain_id, "chain_id")
        uri = _optional_text(command.uri, "uri") or _default_siwe_uri(domain)
        issued_at = _coerce_datetime(command.issued_at or self._now(), "issued_at")
        nonce_value = _new_siwe_nonce(self._nonce_generator)
        nonce = AuthNonce(
            value=nonce_value,
            expires_at=issued_at + self._challenge_ttl,
        )
        challenge = LoginChallenge.issue(
            wallet=wallet,
            nonce=nonce,
            issued_at=issued_at,
            domain=domain,
            uri=uri,
            chain_id=chain_id,
        )
        signing_message = _build_siwe_message(
            SiweMessage(
                domain=domain,
                address=wallet,
                uri=uri,
                version=SIWE_VERSION,
                chain_id=chain_id,
                nonce=nonce.value,
                issued_at=issued_at,
                expiration_time=nonce.expires_at,
            )
        )

        self._login_challenges.save(challenge)
        return LoginChallengeResult(challenge=challenge, signing_message=signing_message)

    def requestWalletLinkChallenge(self, command: RequestWalletLinkChallengeCommand) -> WalletLinkChallengeResult:
        if not isinstance(command.actor_user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "actor_user_id must be a UserId")
        user = self._users.get_by_id(command.actor_user_id)
        if user is None or not user.active:
            raise AuthApplicationError(AuthErrorCode.AUTHENTICATION_REQUIRED, _message_for_code(AuthErrorCode.AUTHENTICATION_REQUIRED))

        wallet = _coerce_wallet(command.wallet_address)
        domain = _require_text(command.domain, "domain")
        chain_id = _require_positive_int(command.chain_id, "chain_id")
        existing = self._active_wallet_by_address(chain_id, wallet)
        if existing is not None and existing.user_id != command.actor_user_id:
            raise AuthApplicationError(AuthErrorCode.WALLET_ALREADY_LINKED, _message_for_code(AuthErrorCode.WALLET_ALREADY_LINKED))

        uri = _optional_text(command.uri, "uri") or _default_siwe_uri(domain)
        issued_at = _coerce_datetime(command.issued_at or self._now(), "issued_at")
        nonce_value = _new_siwe_nonce(self._nonce_generator)
        nonce = AuthNonce(value=nonce_value, expires_at=issued_at + self._challenge_ttl)
        challenge = LoginChallenge.issue(
            wallet=wallet,
            nonce=nonce,
            issued_at=issued_at,
            domain=domain,
            uri=uri,
            chain_id=chain_id,
            purpose=ChallengePurpose.WALLET_LINK,
            target_user_id=command.actor_user_id,
        )
        signing_message = _build_siwe_message(
            SiweMessage(
                domain=domain,
                address=wallet,
                uri=uri,
                version=SIWE_VERSION,
                chain_id=chain_id,
                nonce=nonce.value,
                issued_at=issued_at,
                expiration_time=nonce.expires_at,
            )
        )
        self._login_challenges.save(challenge)
        return WalletLinkChallengeResult(challenge=challenge, signing_message=signing_message)

    def loginWithMetaMask(self, command: LoginWithMetaMaskCommand) -> LoginResult:
        now = self._now()
        wallet = _coerce_wallet(command.wallet_address)
        message = _require_text(command.message, "message")
        signature = _require_text(command.signature, "signature")
        device_id = _require_text(command.device_id, "device_id")
        siwe_message = _parse_siwe_message(message)
        lookup_nonce = AuthNonce(siwe_message.nonce, now + self._challenge_ttl)
        challenge = self._login_challenges.get_by_nonce(lookup_nonce)
        if challenge is None:
            raise AuthApplicationError(AuthErrorCode.INVALID_SIGNATURE, _message_for_code(AuthErrorCode.INVALID_SIGNATURE))

        if challenge.wallet != wallet:
            self._reject_challenge(challenge, LoginFailureReason.WALLET_MISMATCH, now)
            raise AuthApplicationError(AuthErrorCode.WALLET_MISMATCH, _message_for_code(AuthErrorCode.WALLET_MISMATCH))
        try:
            _ensure_siwe_matches_challenge(siwe_message, challenge, wallet)
        except AuthApplicationError as exc:
            reason = (
                LoginFailureReason.WALLET_MISMATCH
                if exc.code is AuthErrorCode.WALLET_MISMATCH
                else LoginFailureReason.SIWE_MESSAGE_MISMATCH
            )
            self._reject_challenge(challenge, reason, now)
            raise

        verification_result = self._verify_wallet_signature(
            wallet=wallet,
            message=message,
            signature=signature,
            chain_id=siwe_message.chain_id,
        )
        if not verification_result.verified:
            reason, code = _failure_to_login_rejection(verification_result.failure)
            self._reject_challenge(challenge, reason, now)
            raise AuthApplicationError(code, _message_for_code(code))

        try:
            verified = challenge.confirm_signature_verified(now=now)
        except LoginChallengeRejected as exc:
            self._handle_challenge_rejection(challenge, exc.reason, now)
            raise AuthApplicationError(_code_for_reason(exc.reason), _message_for_code(_code_for_reason(exc.reason))) from exc

        self._login_challenges.save(verified)
        user, login_wallet, registered = self._resolve_login_user_and_wallet(verified, now)

        user = user.record_login(now)
        self._users.save(user)
        if login_wallet is not None:
            self._wallet_repository().save(login_wallet)
        if registered:
            self._ensure_personal_membership(user, now)
        session, issued_token = self._create_session_and_tokens(
            user,
            verified.wallet,
            device_id,
            now,
            login_wallet_id=login_wallet.wallet_id if login_wallet is not None else None,
        )

        self._sessions.save(session)
        if registered:
            self._event_publisher.publish(UserRegisteredEvent(user.user_id, verified.wallet, now))
        self._event_publisher.publish(WalletVerifiedEvent(user.user_id, verified.wallet, now))
        self._event_publisher.publish(UserLoggedInEvent(user.user_id, session.session_id, now))
        return LoginResult(user=user, session=session, issued_token=issued_token)

    def requestOAuthAuthorization(self, command: RequestOAuthAuthorizationCommand) -> OAuthAuthorizationResult:
        provider = _coerce_oauth_provider(command.provider)
        redirect_uri = _require_text(command.redirect_uri, "redirect_uri")
        mode = _coerce_oauth_mode(command.mode)
        if mode is OAuthAuthorizationMode.LINK:
            if command.actor_user_id is None:
                raise AuthApplicationError(AuthErrorCode.AUTHENTICATION_REQUIRED, _message_for_code(AuthErrorCode.AUTHENTICATION_REQUIRED))
            user = self._users.get_by_id(command.actor_user_id)
            if user is None or not user.active:
                raise AuthApplicationError(AuthErrorCode.AUTHENTICATION_REQUIRED, _message_for_code(AuthErrorCode.AUTHENTICATION_REQUIRED))
        requested_at = _coerce_datetime(command.requested_at or self._now(), "requested_at")
        return self._oauth_provider_port().build_authorization(
            provider=provider,
            redirect_uri=redirect_uri,
            state=_new_text_id(self._nonce_generator, "oauth_state_generator"),
            mode=mode,
            expires_at=requested_at + self._challenge_ttl,
        )

    def completeOAuthSession(self, command: CompleteOAuthSessionCommand) -> OAuthSessionResult:
        now = _coerce_datetime(command.requested_at or self._now(), "requested_at")
        provider_identity = self._exchange_oauth_code(
            provider=command.provider,
            code=command.code,
            state=command.state,
            redirect_uri=command.redirect_uri,
        )
        identity = self._oauth_identity_repository().get_active_by_provider_subject(
            provider_identity.provider,
            provider_identity.provider_subject,
        )
        
        registered = False
        if identity is None:
            wallet_addr = provider_identity.wallet_address
            user = self._users.get_by_wallet(wallet_addr)
            if user is None:
                user = User.register_by_wallet(
                    UserId(_new_text_id(self._user_id_generator, "user_id_generator")),
                    wallet_addr,
                )
                self._users.save(user)
                self._ensure_personal_membership(user, now)
                registered = True
                
                if self._wallets is not None:
                    # Only auto-bind the public testnet wallet on OAuth sign-up. The local
                    # testnet (1337) wallet is not auto-created; it can be linked manually.
                    for chain_id in [11155111]:
                        existing = self._wallets.get_active_by_address(chain_id, wallet_addr)
                        if existing is None:
                            active_same_chain = [
                                item
                                for item in self._wallets.list_for_user(user.user_id)
                                if item.chain_id == chain_id and item.is_active()
                            ]
                            wallet = UserWallet(
                                wallet_id=WalletId.new(),
                                user_id=user.user_id,
                                address=wallet_addr,
                                chain_id=chain_id,
                                wallet_type=WalletType.EOA,
                                verification_status=WalletVerificationStatus.VERIFIED,
                                primary=not active_same_chain,
                                linked_at=now,
                            )
                            self._wallets.save(wallet)
            
            identity = OAuthIdentity(
                oauth_identity_id=OAuthIdentityId.new(),
                provider=provider_identity.provider,
                provider_subject=provider_identity.provider_subject,
                user_id=user.user_id,
                wallet_id=None,
                linked_at=now,
            )
            self._oauth_identity_repository().save(identity)
        else:
            user = self._users.get_by_id(identity.user_id)
            if user is None or not user.active:
                raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "linked OAuth user is missing or inactive")

        device_id = _require_text(command.device_id, "device_id")
        user = user.record_login(now)
        self._users.save(user)
        session, issued_token = self._create_session_and_tokens(
            user,
            user.primary_wallet,
            device_id,
            now,
            login_wallet_id=identity.wallet_id,
        )
        self._sessions.save(session)
        
        if registered:
            self._event_publisher.publish(UserRegisteredEvent(user.user_id, user.primary_wallet, now))
            self._event_publisher.publish(WalletVerifiedEvent(user.user_id, user.primary_wallet, now))
            
        self._event_publisher.publish(UserLoggedInEvent(user.user_id, session.session_id, now))
        return OAuthSessionResult(login=LoginResult(user=user, session=session, issued_token=issued_token), oauth_identity=identity)

    def linkOAuthIdentity(self, command: LinkOAuthIdentityCommand) -> OAuthIdentityResult:
        now = _coerce_datetime(command.requested_at or self._now(), "requested_at")
        if not isinstance(command.actor_user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "actor_user_id must be a UserId")
        user = self._users.get_by_id(command.actor_user_id)
        if user is None or not user.active:
            raise AuthApplicationError(AuthErrorCode.AUTHENTICATION_REQUIRED, _message_for_code(AuthErrorCode.AUTHENTICATION_REQUIRED))
        wallet_id = command.wallet_id
        if wallet_id is not None:
            self._owned_wallet(command.actor_user_id, wallet_id)
        provider_identity = self._exchange_oauth_code(
            provider=command.provider,
            code=command.code,
            state=command.state,
            redirect_uri=command.redirect_uri,
        )
        repository = self._oauth_identity_repository()
        existing = repository.get_active_by_provider_subject(provider_identity.provider, provider_identity.provider_subject)
        if existing is not None:
            if existing.user_id == command.actor_user_id:
                return OAuthIdentityResult(existing)
            raise AuthApplicationError(
                AuthErrorCode.OAUTH_IDENTITY_ALREADY_LINKED,
                _message_for_code(AuthErrorCode.OAUTH_IDENTITY_ALREADY_LINKED),
            )
        identity = OAuthIdentity(
            oauth_identity_id=OAuthIdentityId.new(),
            provider=provider_identity.provider,
            provider_subject=provider_identity.provider_subject,
            user_id=command.actor_user_id,
            wallet_id=wallet_id,
            linked_at=now,
        )
        repository.save(identity)
        return OAuthIdentityResult(identity)

    def listOAuthIdentities(self, query: ListOAuthIdentitiesQuery) -> OAuthIdentitiesResult:
        if not isinstance(query.actor_user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "actor_user_id must be a UserId")
        user = self._users.get_by_id(query.actor_user_id)
        if user is None or not user.active:
            raise AuthApplicationError(AuthErrorCode.AUTHENTICATION_REQUIRED, _message_for_code(AuthErrorCode.AUTHENTICATION_REQUIRED))
        return OAuthIdentitiesResult(self._oauth_identity_repository().list_for_user(query.actor_user_id))

    def revokeOAuthIdentity(self, command: RevokeOAuthIdentityCommand) -> OAuthIdentityResult:
        revoked_at = _coerce_datetime(command.revoked_at or self._now(), "revoked_at")
        if not isinstance(command.actor_user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "actor_user_id must be a UserId")
        if not isinstance(command.oauth_identity_id, OAuthIdentityId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "oauth_identity_id must be an OAuthIdentityId")
        identity = self._oauth_identity_repository().get_by_id(command.oauth_identity_id)
        if identity is None or identity.user_id != command.actor_user_id:
            raise AuthApplicationError(
                AuthErrorCode.OAUTH_IDENTITY_NOT_FOUND,
                _message_for_code(AuthErrorCode.OAUTH_IDENTITY_NOT_FOUND),
            )
        if not identity.is_active():
            raise AuthApplicationError(
                AuthErrorCode.OAUTH_IDENTITY_NOT_FOUND,
                _message_for_code(AuthErrorCode.OAUTH_IDENTITY_NOT_FOUND),
            )
        if self._active_login_method_count(command.actor_user_id) <= 1:
            raise AuthApplicationError(
                AuthErrorCode.LAST_LOGIN_METHOD_REVOKE_DENIED,
                _message_for_code(AuthErrorCode.LAST_LOGIN_METHOD_REVOKE_DENIED),
            )
        revoked = identity.revoke(revoked_at)
        self._oauth_identity_repository().save(revoked)
        return OAuthIdentityResult(revoked)

    def linkWallet(self, command: LinkWalletCommand) -> WalletResult:
        now = self._now()
        if not isinstance(command.actor_user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "actor_user_id must be a UserId")
        user = self._users.get_by_id(command.actor_user_id)
        if user is None or not user.active:
            raise AuthApplicationError(AuthErrorCode.AUTHENTICATION_REQUIRED, _message_for_code(AuthErrorCode.AUTHENTICATION_REQUIRED))
        wallet = _coerce_wallet(command.wallet_address)
        message = _require_text(command.message, "message")
        signature = _require_text(command.signature, "signature")
        siwe_message = _parse_siwe_message(message)
        lookup_nonce = AuthNonce(siwe_message.nonce, now + self._challenge_ttl)
        challenge = self._login_challenges.get_by_nonce(lookup_nonce)
        if challenge is None:
            raise AuthApplicationError(AuthErrorCode.INVALID_SIGNATURE, _message_for_code(AuthErrorCode.INVALID_SIGNATURE))
        if (
            challenge.purpose is not ChallengePurpose.WALLET_LINK
            or challenge.target_user_id != command.actor_user_id
            or challenge.wallet != wallet
        ):
            raise AuthApplicationError(
                AuthErrorCode.WALLET_LINK_CHALLENGE_MISMATCH,
                _message_for_code(AuthErrorCode.WALLET_LINK_CHALLENGE_MISMATCH),
            )
        try:
            _ensure_siwe_matches_challenge(siwe_message, challenge, wallet)
        except AuthApplicationError as exc:
            reason = (
                LoginFailureReason.WALLET_MISMATCH
                if exc.code is AuthErrorCode.WALLET_MISMATCH
                else LoginFailureReason.SIWE_MESSAGE_MISMATCH
            )
            self._reject_challenge(challenge, reason, now)
            raise

        verification_result = self._verify_wallet_signature(
            wallet=wallet,
            message=message,
            signature=signature,
            chain_id=siwe_message.chain_id,
        )
        if not verification_result.verified:
            reason, code = _failure_to_login_rejection(verification_result.failure)
            self._reject_challenge(challenge, reason, now)
            raise AuthApplicationError(code, _message_for_code(code))
        try:
            verified = challenge.confirm_signature_verified(now=now)
        except LoginChallengeRejected as exc:
            self._handle_challenge_rejection(challenge, exc.reason, now)
            raise AuthApplicationError(_code_for_reason(exc.reason), _message_for_code(_code_for_reason(exc.reason))) from exc
        self._login_challenges.save(verified)

        wallet_repo = self._wallet_repository()
        existing = wallet_repo.get_active_by_address(siwe_message.chain_id, wallet)
        if existing is not None:
            if existing.user_id != command.actor_user_id:
                raise AuthApplicationError(AuthErrorCode.WALLET_ALREADY_LINKED, _message_for_code(AuthErrorCode.WALLET_ALREADY_LINKED))
            return WalletResult(existing)
        active_same_chain = [
            item
            for item in wallet_repo.list_for_user(command.actor_user_id)
            if item.chain_id == siwe_message.chain_id and item.is_active()
        ]
        linked = UserWallet(
            wallet_id=WalletId.new(),
            user_id=command.actor_user_id,
            address=wallet,
            chain_id=siwe_message.chain_id,
            wallet_type=_coerce_wallet_type(command.wallet_type),
            verification_status=WalletVerificationStatus.VERIFIED,
            primary=not active_same_chain,
            linked_at=now,
        )
        wallet_repo.save(linked)
        self._event_publisher.publish(WalletLinkedEvent(linked.user_id, linked.wallet_id, linked.address, linked.chain_id, now))
        return WalletResult(linked)

    def listWallets(self, query: ListWalletsQuery) -> WalletsResult:
        if not isinstance(query.actor_user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "actor_user_id must be a UserId")
        user = self._users.get_by_id(query.actor_user_id)
        if user is None or not user.active:
            raise AuthApplicationError(AuthErrorCode.AUTHENTICATION_REQUIRED, _message_for_code(AuthErrorCode.AUTHENTICATION_REQUIRED))
        return WalletsResult(self._wallet_repository().list_for_user(query.actor_user_id))

    def setPrimaryWallet(self, command: SetPrimaryWalletCommand) -> WalletResult:
        now = self._now()
        wallet = self._owned_wallet(command.actor_user_id, command.wallet_id)
        if not wallet.is_active():
            raise AuthApplicationError(AuthErrorCode.WALLET_NOT_ACTIVE, _message_for_code(AuthErrorCode.WALLET_NOT_ACTIVE))
        wallet_repo = self._wallet_repository()
        wallet_repo.unset_primary_for_chain(wallet.user_id, wallet.chain_id, wallet.wallet_id)
        primary = wallet.mark_primary()
        wallet_repo.save(primary)
        self._event_publisher.publish(WalletPrimaryChangedEvent(primary.user_id, primary.wallet_id, primary.chain_id, now))
        return WalletResult(primary)

    def revokeWallet(self, command: RevokeWalletCommand) -> WalletResult:
        revoked_at = _coerce_datetime(command.revoked_at or self._now(), "revoked_at")
        wallet = self._owned_wallet(command.actor_user_id, command.wallet_id)
        if not wallet.is_active():
            raise AuthApplicationError(AuthErrorCode.WALLET_NOT_ACTIVE, _message_for_code(AuthErrorCode.WALLET_NOT_ACTIVE))
        active_wallets = [item for item in self._wallet_repository().list_for_user(command.actor_user_id) if item.is_active()]
        if len(active_wallets) <= 1:
            raise AuthApplicationError(
                AuthErrorCode.LAST_WALLET_REVOKE_DENIED,
                _message_for_code(AuthErrorCode.LAST_WALLET_REVOKE_DENIED),
            )
        revoked = wallet.revoke(revoked_at)
        self._wallet_repository().save(revoked)
        self._event_publisher.publish(WalletRevokedEvent(revoked.user_id, revoked.wallet_id, revoked.address, revoked.chain_id, revoked_at))
        return WalletResult(revoked)

    def refreshSession(self, command: RefreshSessionCommand) -> LoginResult:
        now = self._now()
        if not isinstance(command.session_id, SessionId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "session_id must be a SessionId")
        if not isinstance(command.refresh_token_hash, RefreshTokenHash):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "refresh_token_hash must be a RefreshTokenHash")

        session = self._sessions.get_by_refresh_token_hash(command.refresh_token_hash)
        if session is None or session.session_id != command.session_id or not session.is_active(now):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "session is missing, expired, or revoked")
        user = self._users.get_by_id(session.user_id)
        if user is None or not user.active:
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "session user is missing or inactive")

        claims = self._claim_snapshot(user)
        refresh_with_claims = getattr(self._token_issuer, "refresh_tokens_with_claims", None)
        if callable(refresh_with_claims):
            issued_token = refresh_with_claims(user, session, claims)
        else:
            refresh_for_user = getattr(self._token_issuer, "refresh_tokens_for_user", None)
            if callable(refresh_for_user):
                issued_token = refresh_for_user(user, session)
            else:
                issued_token = self._token_issuer.refresh_tokens(session)
        rotated_hash = _refresh_token_hash(
            issued_token.refresh_token,
            salt=session.refresh_token_hash.salt,
            rotation_version=session.refresh_token_hash.rotation_version + 1,
        )
        refreshed_session = AuthSession(
            session_id=session.session_id,
            user_id=session.user_id,
            login_wallet_id=session.login_wallet_id,
            refresh_token_hash=rotated_hash,
            device_id=session.device_id,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
            wallet=session.wallet,
        )
        self._sessions.save(refreshed_session)
        return LoginResult(user=user, session=refreshed_session, issued_token=issued_token)

    def logout(self, command: LogoutCommand) -> AuthSession:
        now = _coerce_datetime(command.revoked_at or self._now(), "revoked_at")
        if not isinstance(command.session_id, SessionId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "session_id must be a SessionId")
        session = self._sessions.get_by_id(command.session_id)
        if session is None:
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "session was not found")
        revoked = session.revoke(now)
        self._sessions.save(revoked)
        return revoked

    def getCurrentUser(self, query: CurrentUserQuery) -> User | None:
        if not isinstance(query.user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "user_id must be a UserId")
        user = self._users.get_by_id(query.user_id)
        if user is None or not user.active:
            return None
        return user

    def getCurrentUserProfile(self, query: GetCurrentUserProfileQuery) -> UserProfile | None:
        if not isinstance(query.user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "user_id must be a UserId")
        return self._profile_repository().get_by_user_id(query.user_id)

    def getUserProfile(self, query: GetUserProfileQuery) -> UserProfile | None:
        if not isinstance(query.user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "user_id must be a UserId")
        return self._profile_repository().get_by_user_id(query.user_id)

    def updateUserProfile(self, command: UpdateUserProfileCommand) -> UserProfile:
        if not isinstance(command.actor_user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "actor_user_id must be a UserId")
        if not isinstance(command.target_user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "target_user_id must be a UserId")
        if command.actor_user_id != command.target_user_id and "user:manage" not in command.actor_scopes:
            raise AuthApplicationError(
                AuthErrorCode.USER_PROFILE_FORBIDDEN,
                "user:manage permission is required to update another user profile",
            )
        requested_at = _coerce_datetime(command.requested_at or self._now(), "requested_at")
        repository = self._profile_repository()
        existing = repository.get_by_user_id(command.target_user_id)
        display_name_provided = command.display_name_provided or command.display_name is not None
        if existing is None:
            existing = UserProfile(
                user_id=command.target_user_id,
                display_name=command.display_name if display_name_provided else None,
                created_at=requested_at,
                updated_at=requested_at,
            )
        else:
            existing = existing.update(
                display_name=command.display_name,
                display_name_provided=display_name_provided,
                updated_at=requested_at,
            )
        if existing.display_name is not None:
            display_name_conflict = repository.get_by_display_name(existing.display_name)
            if display_name_conflict is not None and display_name_conflict.user_id != existing.user_id:
                raise AuthApplicationError(
                    AuthErrorCode.USER_PROFILE_DISPLAY_NAME_CONFLICT,
                    "user profile displayName is already in use",
                )
        repository.save(existing)
        return existing

    def _profile_repository(self) -> UserProfileRepository:
        if self._profiles is None:
            raise AuthApplicationError(
                AuthErrorCode.USER_PROFILE_NOT_FOUND,
                "user profile repository is not configured",
            )
        return self._profiles

    def _oauth_identity_repository(self) -> OAuthIdentityRepository:
        if self._oauth_identities is None:
            raise AuthApplicationError(
                AuthErrorCode.OAUTH_PROVIDER_UNSUPPORTED,
                "OAuth identity repository is not configured",
            )
        return self._oauth_identities

    def _oauth_provider_port(self) -> OAuthProvider:
        if self._oauth_provider is None:
            raise AuthApplicationError(
                AuthErrorCode.OAUTH_PROVIDER_UNSUPPORTED,
                _message_for_code(AuthErrorCode.OAUTH_PROVIDER_UNSUPPORTED),
            )
        return self._oauth_provider

    def _exchange_oauth_code(self, *, provider: str, code: str, state: str, redirect_uri: str) -> OAuthProviderIdentity:
        result = self._oauth_provider_port().exchange_code(
            provider=_coerce_oauth_provider(provider),
            code=_require_text(code, "code"),
            state=_require_text(state, "state"),
            redirect_uri=_require_text(redirect_uri, "redirect_uri"),
        )
        return OAuthProviderIdentity(
            provider=_coerce_oauth_provider(result.provider),
            provider_subject=_require_text(result.provider_subject, "provider_subject"),
            wallet_address=_coerce_wallet(result.wallet_address),
        )

    def _active_login_method_count(self, user_id: UserId) -> int:
        active_oauth_count = sum(1 for identity in self._oauth_identity_repository().list_for_user(user_id) if identity.is_active())
        if self._wallets is None:
            return active_oauth_count + 1
        active_wallet_count = sum(1 for wallet in self._wallets.list_for_user(user_id) if wallet.is_active())
        return active_oauth_count + active_wallet_count

    def _wallet_repository(self) -> UserWalletRepository:
        if self._wallets is None:
            raise AuthApplicationError(
                AuthErrorCode.VALIDATION_ERROR,
                "user wallet repository is not configured",
            )
        return self._wallets

    def _active_wallet_by_address(self, chain_id: int, wallet: WalletAddress) -> UserWallet | None:
        if self._wallets is None:
            return None
        return self._wallets.get_active_by_address(chain_id, wallet)

    def _owned_wallet(self, actor_user_id: UserId, wallet_id: WalletId) -> UserWallet:
        if not isinstance(actor_user_id, UserId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "actor_user_id must be a UserId")
        if not isinstance(wallet_id, WalletId):
            raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "wallet_id must be a WalletId")
        wallet = self._wallet_repository().get_by_id(wallet_id)
        if wallet is None or wallet.user_id != actor_user_id:
            raise AuthApplicationError(AuthErrorCode.WALLET_NOT_FOUND, _message_for_code(AuthErrorCode.WALLET_NOT_FOUND))
        return wallet

    def _resolve_login_user_and_wallet(
        self,
        challenge: LoginChallenge,
        now: datetime,
    ) -> tuple[User, UserWallet | None, bool]:
        if self._wallets is None or challenge.chain_id is None:
            user = self._users.get_by_wallet(challenge.wallet)
            registered = user is None
            if user is None:
                user = User.register_by_wallet(
                    UserId(_new_text_id(self._user_id_generator, "user_id_generator")),
                    challenge.wallet,
                )
            return user, None, registered

        wallet = self._wallets.get_active_by_address(challenge.chain_id, challenge.wallet)
        if wallet is not None:
            user = self._users.get_by_id(wallet.user_id)
            if user is None or not user.active:
                raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "linked wallet user is missing or inactive")
            return user, wallet, False

        user = self._users.get_by_wallet(challenge.wallet)
        if user is not None:
            if not user.active:
                raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "linked wallet user is missing or inactive")
            active_same_chain = [
                item
                for item in self._wallets.list_for_user(user.user_id)
                if item.chain_id == challenge.chain_id and item.is_active()
            ]
            wallet = UserWallet(
                wallet_id=WalletId.new(),
                user_id=user.user_id,
                address=challenge.wallet,
                chain_id=challenge.chain_id,
                wallet_type=WalletType.EOA,
                verification_status=WalletVerificationStatus.VERIFIED,
                primary=not active_same_chain,
                linked_at=now,
            )
            return user, wallet, False

        user = User.register_by_wallet(
            UserId(_new_text_id(self._user_id_generator, "user_id_generator")),
            challenge.wallet,
        )
        wallet = UserWallet(
            wallet_id=WalletId.new(),
            user_id=user.user_id,
            address=challenge.wallet,
            chain_id=challenge.chain_id,
            wallet_type=WalletType.EOA,
            verification_status=WalletVerificationStatus.VERIFIED,
            primary=True,
            linked_at=now,
        )
        return user, wallet, True

    def _create_session_and_tokens(
        self,
        user: User,
        wallet_address: WalletAddress,
        device_id: str,
        now: datetime,
        *,
        login_wallet_id: WalletId | None = None,
    ) -> tuple[AuthSession, IssuedToken]:
        session_id = SessionId(_new_text_id(self._session_id_generator, "session_id_generator"))
        salt = str(session_id)
        login_wallet_id = login_wallet_id or self._users.get_wallet_id_for_address(user.user_id, wallet_address)
        provisional_session = AuthSession.create(
            session_id=session_id,
            user_id=user.user_id,
            login_wallet_id=login_wallet_id,
            refresh_token_hash=_refresh_token_hash(f"initial:{session_id}", salt=salt, rotation_version=0),
            device_id=device_id,
            expires_at=now + self._session_ttl,
            wallet=wallet_address,
        )
        claims = self._claim_snapshot(user)
        issue_with_claims = getattr(self._token_issuer, "issue_tokens_with_claims", None)
        if callable(issue_with_claims):
            issued_token = issue_with_claims(user, provisional_session, claims)
        else:
            issued_token = self._token_issuer.issue_tokens(user, provisional_session)
        session = AuthSession(
            session_id=provisional_session.session_id,
            user_id=provisional_session.user_id,
            login_wallet_id=provisional_session.login_wallet_id,
            refresh_token_hash=_refresh_token_hash(issued_token.refresh_token, salt=salt, rotation_version=0),
            device_id=provisional_session.device_id,
            expires_at=provisional_session.expires_at,
            wallet=wallet_address,
        )
        return session, issued_token

    def _ensure_personal_membership(self, user: User, joined_at: datetime) -> None:
        if self._rbac is None:
            return
        self._rbac.ensure_personal_membership(user, joined_at)

    def _claim_snapshot(self, user: User) -> dict[str, Any]:
        if self._rbac is None:
            return {"scopes": (), "groupMemberships": (), "activeGroupId": None}
        memberships = self._rbac.session_memberships_for_user(user.user_id)
        scopes = self._rbac.scopes_for_user(user.user_id)
        return {
            "scopes": scopes[:32],
            "groupMemberships": tuple(membership.to_payload() for membership in memberships[:16]),
            "activeGroupId": str(memberships[0].group_id) if memberships else None,
        }

    def _handle_challenge_rejection(
        self,
        challenge: LoginChallenge,
        reason: LoginFailureReason,
        now: datetime,
    ) -> None:
        if reason is LoginFailureReason.EXPIRED_CHALLENGE:
            expired = challenge.expire(now)
            self._login_challenges.save(expired)
            self._event_publisher.publish(LoginRejectedEvent(challenge.wallet, reason, now))
            return
        if reason is LoginFailureReason.REUSED_NONCE:
            self._event_publisher.publish(LoginRejectedEvent(challenge.wallet, reason, now))
            return
        self._reject_challenge(challenge, reason, now)

    def _reject_challenge(self, challenge: LoginChallenge, reason: LoginFailureReason, now: datetime) -> None:
        try:
            rejected = challenge.reject(reason, now)
        except LoginChallengeRejected:
            self._event_publisher.publish(LoginRejectedEvent(challenge.wallet, reason, now))
            return
        self._login_challenges.save(rejected)
        self._event_publisher.publish(LoginRejectedEvent(challenge.wallet, reason, now))

    def _now(self) -> datetime:
        now = self._clock.now()
        return _coerce_datetime(now, "clock.now()")

    def _verify_wallet_signature(
        self,
        *,
        wallet: WalletAddress,
        message: str,
        signature: str,
        chain_id: int,
    ) -> WalletSignatureVerificationResult:
        try:
            result = self._signature_verifier.verify_signature(
                wallet=wallet,
                message=message,
                signature=signature,
                chain_id=chain_id,
            )
        except Exception:
            return WalletSignatureVerificationResult.failed(WalletSignatureVerificationFailure.INVALID_SIGNATURE)
        return _coerce_wallet_signature_verification_result(result)


def _build_siwe_message(message: SiweMessage) -> str:
    try:
        return build_siwe_message(message)
    except ValueError as exc:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, str(exc)) from exc


def _parse_siwe_message(message: str) -> SiweMessage:
    try:
        return parse_siwe_message(message)
    except ValueError as exc:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, str(exc)) from exc


def _default_siwe_uri(domain: str) -> str:
    try:
        return default_siwe_uri(domain)
    except ValueError as exc:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, str(exc)) from exc


def _new_siwe_nonce(generator: Any) -> str:
    raw_value = _new_text_id(generator, "nonce_generator")
    try:
        return normalize_siwe_nonce(raw_value)
    except ValueError as exc:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, str(exc)) from exc


def _ensure_siwe_matches_challenge(
    message: SiweMessage,
    challenge: LoginChallenge,
    requested_wallet: WalletAddress,
) -> None:
    if message.address != requested_wallet or message.address != challenge.wallet:
        raise AuthApplicationError(AuthErrorCode.WALLET_MISMATCH, _message_for_code(AuthErrorCode.WALLET_MISMATCH))
    if (
        challenge.domain is None
        or challenge.uri is None
        or challenge.chain_id is None
        or message.domain != challenge.domain
        or message.uri != challenge.uri
        or message.chain_id != challenge.chain_id
        or message.nonce != challenge.nonce.value
        or message.issued_at != challenge.issued_at
        or message.expiration_time != challenge.expires_at
    ):
        raise AuthApplicationError(
            AuthErrorCode.SIWE_MESSAGE_MISMATCH,
            _message_for_code(AuthErrorCode.SIWE_MESSAGE_MISMATCH),
        )

def _code_for_reason(reason: LoginFailureReason) -> AuthErrorCode:
    return AuthErrorCode(reason.value)


def _failure_to_login_rejection(
    failure: WalletSignatureVerificationFailure | None,
) -> tuple[LoginFailureReason, AuthErrorCode]:
    if failure is WalletSignatureVerificationFailure.WALLET_MISMATCH:
        return LoginFailureReason.WALLET_MISMATCH, AuthErrorCode.WALLET_MISMATCH
    return LoginFailureReason.INVALID_SIGNATURE, AuthErrorCode.INVALID_SIGNATURE


def _message_for_code(code: AuthErrorCode) -> str:
    return {
        AuthErrorCode.INVALID_SIGNATURE: "login signature could not be verified",
        AuthErrorCode.EXPIRED_CHALLENGE: "login challenge has expired",
        AuthErrorCode.REUSED_NONCE: "login challenge nonce has already been used",
        AuthErrorCode.WALLET_MISMATCH: "wallet address does not match the login challenge",
        AuthErrorCode.SIWE_MESSAGE_MISMATCH: "SIWE login message does not match the issued challenge",
        AuthErrorCode.VALIDATION_ERROR: "invalid auth request",
        AuthErrorCode.AUTHENTICATION_REQUIRED: "authenticated session is required",
        AuthErrorCode.USER_PROFILE_FORBIDDEN: "user profile permission denied",
        AuthErrorCode.USER_PROFILE_NOT_FOUND: "user profile was not found",
        AuthErrorCode.USER_PROFILE_DISPLAY_NAME_CONFLICT: "user profile displayName is already in use",
        AuthErrorCode.WALLET_ALREADY_LINKED: "wallet is already linked to another active user",
        AuthErrorCode.WALLET_LINK_CHALLENGE_MISMATCH: "wallet link challenge does not match the authenticated user",
        AuthErrorCode.WALLET_NOT_FOUND: "wallet was not found for the authenticated user",
        AuthErrorCode.WALLET_NOT_ACTIVE: "wallet is not a verified active wallet",
        AuthErrorCode.LAST_WALLET_REVOKE_DENIED: "cannot revoke the last verified wallet",
        AuthErrorCode.OAUTH_PROVIDER_UNSUPPORTED: "OAuth provider is not configured",
        AuthErrorCode.OAUTH_IDENTITY_NOT_LINKED: "OAuth identity is not linked to an active user",
        AuthErrorCode.OAUTH_IDENTITY_ALREADY_LINKED: "OAuth identity is already linked to another active user",
        AuthErrorCode.OAUTH_IDENTITY_NOT_FOUND: "OAuth identity was not found for the authenticated user",
        AuthErrorCode.LAST_LOGIN_METHOD_REVOKE_DENIED: "cannot revoke the last active login method",
    }[code]


def _refresh_token_hash(refresh_token: str, *, salt: str, rotation_version: int) -> RefreshTokenHash:
    token = _require_text(refresh_token, "refresh_token")
    salt = _require_text(salt, "refresh_token_salt")
    digest = hashlib.sha256(f"{salt}:{token}".encode("utf-8")).hexdigest()
    return RefreshTokenHash(hash=digest, salt=salt, rotation_version=rotation_version)


def _new_text_id(generator: Any, field_name: str) -> str:
    new_id = getattr(generator, "new_id", None)
    if callable(new_id):
        value = new_id()
    elif callable(generator):
        value = generator()
    else:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{field_name} must generate ids")
    return _require_text(str(value), field_name)


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _coerce_wallet(value: WalletAddress | str) -> WalletAddress:
    try:
        return value if isinstance(value, WalletAddress) else WalletAddress(value)
    except ValueError as exc:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, str(exc)) from exc


def _coerce_wallet_type(value: WalletType | str) -> WalletType:
    if isinstance(value, WalletType):
        return value
    try:
        return WalletType(str(value))
    except ValueError as exc:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "wallet_type is invalid") from exc


def _coerce_oauth_provider(value: str) -> str:
    provider = _require_text(value, "provider").lower()
    if len(provider) > 32:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "provider must be at most 32 characters")
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in provider):
        raise AuthApplicationError(
            AuthErrorCode.VALIDATION_ERROR,
            "provider must contain only lowercase letters, digits, dot, underscore, or hyphen",
        )
    return provider


def _coerce_oauth_mode(value: OAuthAuthorizationMode | str) -> OAuthAuthorizationMode:
    if isinstance(value, OAuthAuthorizationMode):
        return value
    try:
        return OAuthAuthorizationMode(str(value))
    except ValueError as exc:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "OAuth authorization mode is invalid") from exc


def _coerce_wallet_signature_verification_result(value: object) -> WalletSignatureVerificationResult:
    if isinstance(value, WalletSignatureVerificationResult):
        return value
    if isinstance(value, bool):
        if value:
            return WalletSignatureVerificationResult.verified()
        return WalletSignatureVerificationResult.failed(WalletSignatureVerificationFailure.INVALID_SIGNATURE)
    return WalletSignatureVerificationResult.failed(WalletSignatureVerificationFailure.INVALID_SIGNATURE)


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{field_name} must be a non-empty string")
    return value.strip()


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{field_name} must be a positive integer")
    return value


def _require_positive_timedelta(value: timedelta, field_name: str) -> timedelta:
    if not isinstance(value, timedelta) or value.total_seconds() <= 0:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{field_name} must be positive")
    return value


def _coerce_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)

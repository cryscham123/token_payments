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
    GetCurrentUserProfileQuery,
    GetUserProfileQuery,
    LinkWalletCommand,
    ListWalletsQuery,
    LoginChallengeRepository,
    LoginChallengeResult,
    LoginResult,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    RefreshSessionCommand,
    RequestLoginChallengeCommand,
    RequestWalletLinkChallengeCommand,
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
    WALLET_ALREADY_LINKED = "WALLET_ALREADY_LINKED"
    WALLET_LINK_CHALLENGE_MISMATCH = "WALLET_LINK_CHALLENGE_MISMATCH"
    WALLET_NOT_FOUND = "WALLET_NOT_FOUND"
    WALLET_NOT_ACTIVE = "WALLET_NOT_ACTIVE"
    LAST_WALLET_REVOKE_DENIED = "LAST_WALLET_REVOKE_DENIED"


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
        if existing is None:
            if command.display_name is None:
                raise AuthApplicationError(
                    AuthErrorCode.VALIDATION_ERROR,
                    "display_name is required when creating a profile",
                )
            existing = UserProfile(
                user_id=command.target_user_id,
                display_name=command.display_name,
                email=command.email,
                locale=command.locale,
                timezone=command.timezone,
                created_at=requested_at,
                updated_at=requested_at,
            )
        else:
            existing = existing.update(
                display_name=command.display_name,
                email=command.email,
                locale=command.locale,
                timezone=command.timezone,
                updated_at=requested_at,
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
        AuthErrorCode.WALLET_ALREADY_LINKED: "wallet is already linked to another active user",
        AuthErrorCode.WALLET_LINK_CHALLENGE_MISMATCH: "wallet link challenge does not match the authenticated user",
        AuthErrorCode.WALLET_NOT_FOUND: "wallet was not found for the authenticated user",
        AuthErrorCode.WALLET_NOT_ACTIVE: "wallet is not a verified active wallet",
        AuthErrorCode.LAST_WALLET_REVOKE_DENIED: "cannot revoke the last verified wallet",
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

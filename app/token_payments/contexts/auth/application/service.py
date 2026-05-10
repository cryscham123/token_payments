"""Pure authentication use case implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import hashlib
from typing import Any

from token_payments.contexts.auth.domain import (
    AuthNonce,
    AuthSession,
    IssuedToken,
    LoginChallenge,
    LoginChallengeRejected,
    LoginFailureReason,
    LoginRejectedEvent,
    RefreshTokenHash,
    SessionId,
    User,
    UserLoggedInEvent,
    UserRegisteredEvent,
    WalletVerifiedEvent,
)
from token_payments.shared.domain import UserId, WalletAddress

from .ports import (
    AuthEventPublisher,
    AuthSessionRepository,
    CurrentUserQuery,
    LoginChallengeRepository,
    LoginChallengeResult,
    LoginResult,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    RefreshSessionCommand,
    RequestLoginChallengeCommand,
    TokenIssuer,
    UserRepository,
    WalletSignatureVerifier,
)


class AuthErrorCode(StrEnum):
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED_CHALLENGE = "EXPIRED_CHALLENGE"
    REUSED_NONCE = "REUSED_NONCE"
    WALLET_MISMATCH = "WALLET_MISMATCH"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class AuthApplicationError(Exception):
    def __init__(self, code: AuthErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class _SigningMessageParts:
    wallet: WalletAddress
    domain: str
    chain_id: int
    nonce: str
    issued_at: datetime
    expires_at: datetime


class AuthApplicationService:
    """Application service for MetaMask nonce login and session lifecycle."""

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
        challenge_ttl: timedelta = timedelta(minutes=5),
        session_ttl: timedelta = timedelta(days=30),
    ) -> None:
        self._clock = clock
        self._nonce_generator = nonce_generator
        self._user_id_generator = user_id_generator
        self._session_id_generator = session_id_generator
        self._users = users
        self._login_challenges = login_challenges
        self._sessions = sessions
        self._signature_verifier = signature_verifier
        self._token_issuer = token_issuer
        self._event_publisher = event_publisher
        self._challenge_ttl = _require_positive_timedelta(challenge_ttl, "challenge_ttl")
        self._session_ttl = _require_positive_timedelta(session_ttl, "session_ttl")

    def requestLoginChallenge(self, command: RequestLoginChallengeCommand) -> LoginChallengeResult:
        wallet = _coerce_wallet(command.wallet_address)
        domain = _require_text(command.domain, "domain")
        chain_id = _require_positive_int(command.chain_id, "chain_id")
        issued_at = _coerce_datetime(command.issued_at or self._now(), "issued_at")
        nonce = AuthNonce(
            value=_new_text_id(self._nonce_generator, "nonce_generator"),
            expires_at=issued_at + self._challenge_ttl,
        )
        challenge = LoginChallenge.issue(wallet=wallet, nonce=nonce, issued_at=issued_at)
        signing_message = _build_signing_message(
            _SigningMessageParts(
                wallet=wallet,
                domain=domain,
                chain_id=chain_id,
                nonce=nonce.value,
                issued_at=issued_at,
                expires_at=nonce.expires_at,
            )
        )

        self._login_challenges.save(challenge)
        return LoginChallengeResult(challenge=challenge, signing_message=signing_message)

    def loginWithMetaMask(self, command: LoginWithMetaMaskCommand) -> LoginResult:
        now = self._now()
        wallet = _coerce_wallet(command.wallet_address)
        message = _require_text(command.message, "message")
        signature = _require_text(command.signature, "signature")
        device_id = _require_text(command.device_id, "device_id")
        nonce_value = _extract_message_value(message, "Nonce")
        lookup_nonce = AuthNonce(nonce_value, now + self._challenge_ttl)
        challenge = self._login_challenges.get_by_nonce(lookup_nonce)
        if challenge is None:
            raise AuthApplicationError(AuthErrorCode.INVALID_SIGNATURE, _message_for_code(AuthErrorCode.INVALID_SIGNATURE))

        if challenge.wallet != wallet:
            self._reject_challenge(challenge, LoginFailureReason.WALLET_MISMATCH, now)
            raise AuthApplicationError(AuthErrorCode.WALLET_MISMATCH, _message_for_code(AuthErrorCode.WALLET_MISMATCH))

        try:
            recovered_wallet = self._signature_verifier.recover_address(message, signature)
        except Exception as exc:
            self._reject_challenge(challenge, LoginFailureReason.INVALID_SIGNATURE, now)
            raise AuthApplicationError(
                AuthErrorCode.INVALID_SIGNATURE,
                _message_for_code(AuthErrorCode.INVALID_SIGNATURE),
            ) from exc

        try:
            verified = challenge.verify_signature(recovered_wallet, now=now)
        except LoginChallengeRejected as exc:
            self._handle_challenge_rejection(challenge, exc.reason, now)
            raise AuthApplicationError(_code_for_reason(exc.reason), _message_for_code(_code_for_reason(exc.reason))) from exc

        self._login_challenges.save(verified)
        user = self._users.get_by_wallet(verified.wallet)
        registered = user is None
        if user is None:
            user = User.register_by_wallet(UserId(_new_text_id(self._user_id_generator, "user_id_generator")), verified.wallet)

        user = user.record_login(now)
        session, issued_token = self._create_session_and_tokens(user, device_id, now)

        self._users.save(user)
        self._sessions.save(session)
        if registered:
            self._event_publisher.publish(UserRegisteredEvent(user.user_id, user.primary_wallet, now))
        self._event_publisher.publish(WalletVerifiedEvent(user.user_id, user.primary_wallet, now))
        self._event_publisher.publish(UserLoggedInEvent(user.user_id, session.session_id, now))
        return LoginResult(user=user, session=session, issued_token=issued_token)

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

        issued_token = self._token_issuer.refresh_tokens(session)
        rotated_hash = _refresh_token_hash(
            issued_token.refresh_token,
            salt=session.refresh_token_hash.salt,
            rotation_version=session.refresh_token_hash.rotation_version + 1,
        )
        refreshed_session = AuthSession(
            session_id=session.session_id,
            user_id=session.user_id,
            wallet=session.wallet,
            refresh_token_hash=rotated_hash,
            device_id=session.device_id,
            expires_at=session.expires_at,
            revoked_at=session.revoked_at,
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

    def _create_session_and_tokens(self, user: User, device_id: str, now: datetime) -> tuple[AuthSession, IssuedToken]:
        session_id = SessionId(_new_text_id(self._session_id_generator, "session_id_generator"))
        salt = str(session_id)
        provisional_session = AuthSession.create(
            session_id=session_id,
            user_id=user.user_id,
            wallet=user.primary_wallet,
            refresh_token_hash=_refresh_token_hash(f"initial:{session_id}", salt=salt, rotation_version=0),
            device_id=device_id,
            expires_at=now + self._session_ttl,
        )
        issued_token = self._token_issuer.issue_tokens(user, provisional_session)
        session = AuthSession(
            session_id=provisional_session.session_id,
            user_id=provisional_session.user_id,
            wallet=provisional_session.wallet,
            refresh_token_hash=_refresh_token_hash(issued_token.refresh_token, salt=salt, rotation_version=0),
            device_id=provisional_session.device_id,
            expires_at=provisional_session.expires_at,
        )
        return session, issued_token

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


def _build_signing_message(parts: _SigningMessageParts) -> str:
    return "\n".join(
        (
            "Token Payments wants you to sign in with your Ethereum account:",
            str(parts.wallet),
            "",
            f"Domain: {parts.domain}",
            f"Chain ID: {parts.chain_id}",
            f"Nonce: {parts.nonce}",
            f"Issued At: {parts.issued_at.isoformat()}",
            f"Expiration Time: {parts.expires_at.isoformat()}",
        )
    )


def _extract_message_value(message: str, label: str) -> str:
    prefix = f"{label}:"
    for line in message.splitlines():
        if line.startswith(prefix):
            return _require_text(line[len(prefix) :], label)
    raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"signing message is missing {label}")


def _code_for_reason(reason: LoginFailureReason) -> AuthErrorCode:
    return AuthErrorCode(reason.value)


def _message_for_code(code: AuthErrorCode) -> str:
    return {
        AuthErrorCode.INVALID_SIGNATURE: "login signature could not be verified",
        AuthErrorCode.EXPIRED_CHALLENGE: "login challenge has expired",
        AuthErrorCode.REUSED_NONCE: "login challenge nonce has already been used",
        AuthErrorCode.WALLET_MISMATCH: "wallet address does not match the login challenge",
        AuthErrorCode.VALIDATION_ERROR: "invalid auth request",
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


def _coerce_wallet(value: WalletAddress | str) -> WalletAddress:
    try:
        return value if isinstance(value, WalletAddress) else WalletAddress(value)
    except ValueError as exc:
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, str(exc)) from exc


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

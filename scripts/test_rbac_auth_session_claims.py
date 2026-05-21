from __future__ import annotations

import base64
import json
import sys
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api.contracts import ApiAuthContext  # noqa: E402
from token_payments.contexts.auth.application import (  # noqa: E402
    AuthApplicationService,
    CurrentUserQuery,
    LoginWithMetaMaskCommand,
    RefreshSessionCommand,
    RequestLoginChallengeCommand,
    WalletSignatureVerificationResult,
)
from token_payments.contexts.auth.domain import (  # noqa: E402
    AuthNonce,
    AuthSession,
    GroupId,
    GroupType,
    IssuedToken,
    LoginChallenge,
    RefreshTokenHash,
    SessionId,
    SessionMembership,
    User,
)
from token_payments.runtime.session_transport import (  # noqa: E402
    CookieSessionTransport,
    CookieSettings,
    SessionClaims,
    SessionKeyRing,
    SessionTokenSigner,
)
from token_payments.shared.domain import UserId, WalletAddress  # noqa: E402


NOW = datetime(2026, 5, 20, 3, 0, tzinfo=UTC)
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdccb101")
SESSION_ID = SessionId("018f33aa-9e6d-73d8-9dc3-47d6cdccb102")
PERSONAL_GROUP_ID = GroupId("018f33aa-9e6d-73d8-9dc3-47d6cdccb103")
WALLET = WalletAddress("0x1111111111111111111111111111111111111111")


def test_auth_service_creates_personal_group_membership_and_issues_claim_snapshot_without_role() -> None:
    service, repositories, tokens, rbac = _service()
    challenge = service.requestLoginChallenge(
        RequestLoginChallengeCommand(wallet_address=WALLET, domain="token-payments.local", chain_id=11155111)
    )

    result = service.loginWithMetaMask(
        LoginWithMetaMaskCommand(
            wallet_address=WALLET,
            message=challenge.signing_message,
            signature="signature-valid",
            device_id="browser-1",
        )
    )

    assert "role" not in {field.name for field in fields(User)}
    assert result.user.user_id == USER_ID
    assert rbac.personal_memberships == [(USER_ID, WALLET)]
    assert tokens.issue_claims == {
        "activeGroupId": str(PERSONAL_GROUP_ID),
        "groupMemberships": (
            {
                "groupId": str(PERSONAL_GROUP_ID),
                "groupType": "PERSONAL",
                "roleId": "PERSONAL_CUSTOMER",
                "resourceType": "user",
                "resourceId": str(USER_ID),
            },
        ),
        "scopes": ("user:self",),
    }
    assert service.getCurrentUser(CurrentUserQuery(user_id=USER_ID)) == result.user
    assert repositories.users.get_by_wallet(WALLET) == result.user


def test_refresh_session_rebuilds_claim_snapshot_from_current_memberships() -> None:
    service, _repositories, tokens, rbac = _service()
    challenge = service.requestLoginChallenge(
        RequestLoginChallengeCommand(wallet_address=WALLET, domain="token-payments.local", chain_id=11155111)
    )
    login = service.loginWithMetaMask(
        LoginWithMetaMaskCommand(
            wallet_address=WALLET,
            message=challenge.signing_message,
            signature="signature-valid",
            device_id="browser-1",
        )
    )
    rbac.extra_scopes = ("user:self", "inventory:read")

    refreshed = service.refreshSession(
        RefreshSessionCommand(
            session_id=login.session.session_id,
            refresh_token_hash=login.session.refresh_token_hash,
        )
    )

    assert refreshed.session.refresh_token_hash.rotation_version == 1
    assert tokens.refresh_claims["scopes"] == ("user:self", "inventory:read")


def test_session_claim_payload_uses_group_snapshot_and_no_role_claim() -> None:
    signer = SessionTokenSigner(
        SessionKeyRing(active_key_id="active", keys={"active": "active-live-session-signing-secret-at-least-32-bytes"}),
        jti_factory=lambda: "jti-rbac",
    )
    claims = SessionClaims(
        user_id=str(USER_ID),
        session_id=str(SESSION_ID),
        wallet_address=str(WALLET),
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        token_type="access",
        jti="pending",
        active_group_id=str(PERSONAL_GROUP_ID),
        group_memberships=(
            {
                "groupId": str(PERSONAL_GROUP_ID),
                "groupType": "PERSONAL",
                "roleId": "PERSONAL_CUSTOMER",
                "resourceType": "user",
                "resourceId": str(USER_ID),
            },
        ),
        scopes=("user:self",),
    )

    token = signer.sign(claims)
    payload = _token_payload(token)
    verified = signer.verify(token, expected_type="access", now=NOW)

    assert "role" not in payload
    assert payload["activeGroupId"] == str(PERSONAL_GROUP_ID)
    assert payload["scopes"] == ["user:self"]
    assert verified.role is None
    assert verified.group_memberships[0]["roleId"] == "PERSONAL_CUSTOMER"


def test_cookie_transport_auth_context_ignores_legacy_role_and_preserves_bounded_claims() -> None:
    signer = SessionTokenSigner(
        SessionKeyRing(active_key_id="active", keys={"active": "active-live-session-signing-secret-at-least-32-bytes"}),
        jti_factory=lambda: "jti-cookie",
    )
    transport = CookieSessionTransport(
        signer=signer,
        settings=CookieSettings(access_max_age_seconds=900, refresh_max_age_seconds=2_592_000),
        clock=FakeClock(NOW),
    )
    access = signer.sign(
        SessionClaims(
            user_id=str(USER_ID),
            session_id=str(SESSION_ID),
            wallet_address=str(WALLET),
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=15),
            token_type="access",
            jti="pending",
            active_group_id=str(PERSONAL_GROUP_ID),
            scopes=("user:self",),
        )
    )
    cookies = transport.issue_cookies(access_token=access, refresh_token="unused", now=NOW)

    context = transport.extract_auth_context({"Cookie": cookies.access_cookie.split(";", 1)[0]})

    assert context is not None
    assert "role" not in {field.name for field in fields(ApiAuthContext)}
    assert context.role is None
    assert context.active_group_id == str(PERSONAL_GROUP_ID)
    assert context.scopes == ("user:self",)


def _service() -> tuple[AuthApplicationService, "Repositories", "ClaimTokenIssuer", "FakeRbacRepository"]:
    repositories = Repositories()
    tokens = ClaimTokenIssuer()
    rbac = FakeRbacRepository()
    service = AuthApplicationService(
        clock=FakeClock(NOW),
        nonce_generator=FixedIds("nonce-1234"),
        user_id_generator=FixedIds(str(USER_ID)),
        session_id_generator=FixedIds(str(SESSION_ID)),
        users=repositories.users,
        login_challenges=repositories.challenges,
        sessions=repositories.sessions,
        signature_verifier=AcceptingVerifier(),
        token_issuer=tokens,
        event_publisher=repositories.events,
        rbac=rbac,
    )
    return service, repositories, tokens, rbac


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


class FixedIds:
    def __init__(self, value: str) -> None:
        self.value = value

    def new_id(self) -> str:
        return self.value


class AcceptingVerifier:
    def verify_signature(self, **_kwargs: Any) -> WalletSignatureVerificationResult:
        return WalletSignatureVerificationResult.verified()


class ClaimTokenIssuer:
    def __init__(self) -> None:
        self.issue_claims: dict[str, Any] | None = None
        self.refresh_claims: dict[str, Any] | None = None

    def issue_tokens_with_claims(self, _user: User, session: AuthSession, claims: dict[str, Any]) -> IssuedToken:
        self.issue_claims = claims
        return IssuedToken(
            access_token=f"access:{session.user_id}:{session.session_id}",
            refresh_token=f"refresh:{session.session_id}:0",
            expires_at=NOW + timedelta(minutes=15),
        )

    def refresh_tokens_with_claims(self, _user: User, session: AuthSession, claims: dict[str, Any]) -> IssuedToken:
        self.refresh_claims = claims
        return IssuedToken(
            access_token=f"access:{session.user_id}:{session.session_id}:1",
            refresh_token=f"refresh:{session.session_id}:1",
            expires_at=NOW + timedelta(minutes=15),
        )

    def issue_tokens(self, user: User, session: AuthSession) -> IssuedToken:
        return self.issue_tokens_with_claims(user, session, {})

    def refresh_tokens(self, session: AuthSession) -> IssuedToken:
        return IssuedToken("access", "refresh", NOW + timedelta(minutes=15))


class FakeRbacRepository:
    def __init__(self) -> None:
        self.personal_memberships: list[tuple[UserId, WalletAddress]] = []
        self.extra_scopes: tuple[str, ...] = ("user:self",)

    def ensure_personal_membership(self, user: User, _joined_at: datetime) -> tuple[SessionMembership, ...]:
        self.personal_memberships.append((user.user_id, user.primary_wallet))
        return self.session_memberships_for_user(user.user_id)

    def session_memberships_for_user(self, user_id: UserId) -> tuple[SessionMembership, ...]:
        return (
            SessionMembership(
                group_id=PERSONAL_GROUP_ID,
                group_type=GroupType.PERSONAL,
                role_id="PERSONAL_CUSTOMER",
                resource_type="user",
                resource_id=str(user_id),
            ),
        )

    def scopes_for_user(self, _user_id: UserId) -> tuple[str, ...]:
        return self.extra_scopes


class Repositories:
    def __init__(self) -> None:
        self.users = UserRepository()
        self.challenges = ChallengeRepository()
        self.sessions = SessionRepository()
        self.events = EventPublisher()


class UserRepository:
    def __init__(self) -> None:
        self.by_id: dict[UserId, User] = {}
        self.by_wallet: dict[WalletAddress, User] = {}

    def save(self, user: User) -> None:
        self.by_id[user.user_id] = user
        self.by_wallet[user.primary_wallet] = user

    def get_by_id(self, user_id: UserId) -> User | None:
        return self.by_id.get(user_id)

    def get_by_wallet(self, wallet: WalletAddress) -> User | None:
        return self.by_wallet.get(wallet)


class ChallengeRepository:
    def __init__(self) -> None:
        self.by_nonce: dict[str, LoginChallenge] = {}

    def save(self, challenge: LoginChallenge) -> None:
        self.by_nonce[challenge.nonce.value] = challenge

    def get_by_nonce(self, nonce: AuthNonce) -> LoginChallenge | None:
        return self.by_nonce.get(nonce.value)

    def get_issued_by_wallet(self, _wallet: WalletAddress) -> LoginChallenge | None:
        return None


class SessionRepository:
    def __init__(self) -> None:
        self.by_id: dict[SessionId, AuthSession] = {}
        self.by_hash: dict[tuple[str, str, int], AuthSession] = {}

    def save(self, session: AuthSession) -> None:
        stale = [key for key, value in self.by_hash.items() if value.session_id == session.session_id]
        for key in stale:
            del self.by_hash[key]
        self.by_id[session.session_id] = session
        key = (
            session.refresh_token_hash.hash,
            session.refresh_token_hash.salt,
            session.refresh_token_hash.rotation_version,
        )
        self.by_hash[key] = session

    def get_by_id(self, session_id: SessionId) -> AuthSession | None:
        return self.by_id.get(session_id)

    def get_by_refresh_token_hash(self, refresh_token_hash: RefreshTokenHash) -> AuthSession | None:
        return self.by_hash.get((refresh_token_hash.hash, refresh_token_hash.salt, refresh_token_hash.rotation_version))


class EventPublisher:
    def publish(self, _event: Any) -> None:
        return None


def _token_payload(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    decoded = json.loads(base64.urlsafe_b64decode((payload + "=" * (-len(payload) % 4)).encode("ascii")))
    assert isinstance(decoded, dict)
    return decoded

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import AUTH_HTTP_ROUTES, ApiAuthContext, AuthApi, HttpRouter, register_auth_routes  # noqa: E402
from token_payments.contexts.auth.application import (  # noqa: E402
    AuthApplicationError,
    AuthApplicationService,
    AuthErrorCode,
    CompleteOAuthSessionCommand,
    LinkOAuthIdentityCommand,
    ListOAuthIdentitiesQuery,
    LoginResult,
    OAuthAuthorizationResult,
    OAuthIdentitiesResult,
    OAuthIdentityResult,
    OAuthProviderIdentity,
    OAuthSessionResult,
    RequestOAuthAuthorizationCommand,
    RevokeOAuthIdentityCommand,
)
from token_payments.contexts.auth.domain import AuthSession, IssuedToken, OAuthIdentity, OAuthIdentityId, RefreshTokenHash, SessionId, User  # noqa: E402
from token_payments.contexts.auth.domain.wallet import WalletId  # noqa: E402
from token_payments.shared.domain import UserId  # noqa: E402


NOW = datetime(2026, 5, 24, 3, 0, tzinfo=UTC)
USER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc2701"
SESSION_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc2702"
OAUTH_IDENTITY_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc2703"
WALLET = "0x1111111111111111111111111111111111111111"


def test_oauth_auth_routes_are_part_of_public_manifest_and_register_to_auth_facade() -> None:
    assert AUTH_HTTP_ROUTES["request_oauth_authorization"].method == "POST"
    assert AUTH_HTTP_ROUTES["request_oauth_authorization"].path == "/auth/oauth/{provider}/authorize"
    assert AUTH_HTTP_ROUTES["request_oauth_authorization"].operation_id == "requestOAuthAuthorization"
    assert AUTH_HTTP_ROUTES["complete_oauth_session"].path == "/auth/oauth/{provider}/sessions"
    assert AUTH_HTTP_ROUTES["link_oauth_identity"].path == "/auth/oauth/{provider}/links"
    assert AUTH_HTTP_ROUTES["list_oauth_identities"].path == "/auth/oauth/identities"
    assert AUTH_HTTP_ROUTES["revoke_oauth_identity"].path == "/auth/oauth/identities/{oauthIdentityId}"

    use_case = FakeOAuthAuthUseCase()
    router = HttpRouter(auth_context_factory=lambda _request: ApiAuthContext(user_id=USER_ID, session_id=SESSION_ID, scopes=("user:self",)))
    routes = register_auth_routes(router, AuthApi(use_case))

    assert len(routes) == 17
    assert {
        "requestOAuthAuthorization",
        "completeOAuthSession",
        "linkOAuthIdentity",
        "listOAuthIdentities",
        "revokeOAuthIdentity",
    } <= {route.operation_id for route in routes}

    authorize = router.handle(
        "POST",
        "/auth/oauth/google/authorize",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-oauth-authorize"},
        body=b'{"redirectUri":"https://token-payments.local/oauth/callback","mode":"login"}',
        received_at=NOW,
    )

    assert authorize.status_code == 201
    authorize_body = _json(authorize.body)
    assert authorize_body["oauthAuthorization"] == {
        "provider": "google",
        "authorizationUrl": "https://oauth.example/authorize?state=state-route",
        "state": "state-route",
        "mode": "login",
        "expiresAt": (NOW + timedelta(minutes=5)).isoformat(),
        "pkceRequired": True,
    }
    assert isinstance(use_case.calls[-1], RequestOAuthAuthorizationCommand)
    assert use_case.calls[-1].provider == "google"

    session = router.handle(
        "POST",
        "/auth/oauth/google/sessions",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-oauth-session"},
        body=b'{"code":"oauth-code","state":"state-route","redirectUri":"https://token-payments.local/oauth/callback","deviceId":"browser-1"}',
        received_at=NOW,
    )

    assert session.status_code == 200
    session_body = _json(session.body)
    assert session_body["token"]["accessToken"] == "access-oauth"
    assert session_body["oauthIdentity"]["provider"] == "google"
    assert "signatureVerification" not in session_body
    assert isinstance(use_case.calls[-1], CompleteOAuthSessionCommand)

    link = router.handle(
        "POST",
        "/auth/oauth/google/links",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-oauth-link"},
        body=b'{"code":"oauth-code","state":"state-route","redirectUri":"https://token-payments.local/oauth/callback"}',
        received_at=NOW,
    )

    assert link.status_code == 201
    assert _json(link.body)["oauthIdentity"]["oauthIdentityId"] == OAUTH_IDENTITY_ID
    assert isinstance(use_case.calls[-1], LinkOAuthIdentityCommand)

    identities = router.handle(
        "GET",
        "/auth/oauth/identities",
        headers={"X-Request-Id": "req-oauth-identities"},
        received_at=NOW,
    )

    assert identities.status_code == 200
    assert _json(identities.body)["oauthIdentities"][0]["provider"] == "google"
    assert isinstance(use_case.calls[-1], ListOAuthIdentitiesQuery)

    revoked = router.handle(
        "DELETE",
        f"/auth/oauth/identities/{OAUTH_IDENTITY_ID}",
        headers={"X-Request-Id": "req-oauth-revoke"},
        received_at=NOW,
    )

    assert revoked.status_code == 200
    assert _json(revoked.body)["oauthIdentity"]["revokedAt"] == NOW.isoformat()
    assert isinstance(use_case.calls[-1], RevokeOAuthIdentityCommand)

    combined_payload = json.dumps(
        [
            authorize_body,
            session_body,
            _json(link.body),
            _json(identities.body),
            _json(revoked.body),
        ],
        sort_keys=True,
    )
    assert "providerSubject" not in combined_payload
    assert "email" not in combined_payload.lower()


def test_oauth_routes_are_documented_in_api_spec_postman_and_expected_fixtures() -> None:
    from token_payments.api import http_route_manifest

    api_spec = (ROOT / "docs/API_SPEC.md").read_text(encoding="utf-8")
    collection = _read_json(ROOT / "postman/token-payments.local.postman_collection.json")
    expected = _read_json(ROOT / "postman/expected/token-payments.api.expected.json")
    collection_items = _operation_items(collection)
    expected_routes = {route["operationId"]: route for route in expected["routes"]}

    oauth_routes = {
        route["operationId"]: route
        for route in http_route_manifest()
        if route["operationId"] in {
            "requestOAuthAuthorization",
            "completeOAuthSession",
            "linkOAuthIdentity",
            "listOAuthIdentities",
            "revokeOAuthIdentity",
        }
    }

    assert len(oauth_routes) == 5
    for operation_id, route in oauth_routes.items():
        assert f"| `{operation_id}` | `{route['method']}` | `{route['path']}` |" in api_spec
        assert operation_id in collection_items
        assert operation_id in expected_routes
        assert expected_routes[operation_id]["path"] == route["path"]

    assert "OAuth/social identity is keyed by `provider` plus `providerSubject`, not by email" in api_spec
    assert "Google email claims are not persisted" in api_spec


def test_auth_application_service_links_logs_in_and_soft_revokes_oauth_identity() -> None:
    users = FakeUserRepository()
    oauth_identities = FakeOAuthIdentityRepository()
    sessions = FakeSessionRepository()
    service = AuthApplicationService(
        clock=StaticClock(),
        nonce_generator=SequenceIds("state-route"),
        user_id_generator=SequenceIds(USER_ID),
        session_id_generator=SequenceIds(SESSION_ID),
        users=users,
        login_challenges=UnusedRepository(),
        sessions=sessions,
        signature_verifier=UnusedVerifier(),
        token_issuer=FakeTokenIssuer(),
        event_publisher=UnusedPublisher(),
        oauth_identities=oauth_identities,
        oauth_provider=FakeOAuthProvider(),
    )

    linked = service.linkOAuthIdentity(
        LinkOAuthIdentityCommand(
            actor_user_id=UserId(USER_ID),
            provider="Google",
            code="oauth-code",
            state="state-route",
            redirect_uri="https://token-payments.local/oauth/callback",
            requested_at=NOW,
        )
    )

    assert linked.oauth_identity.provider == "google"
    assert linked.oauth_identity.provider_subject == "google-subject-123"
    assert oauth_identities.get_active_by_provider_subject("google", "google-subject-123") == linked.oauth_identity

    session = service.completeOAuthSession(
        CompleteOAuthSessionCommand(
            provider="google",
            code="oauth-code",
            state="state-route",
            redirect_uri="https://token-payments.local/oauth/callback",
            device_id="browser-1",
            requested_at=NOW,
        )
    )

    assert session.login.user.user_id == UserId(USER_ID)
    assert session.login.session.device_id == "browser-1"
    assert sessions.saved[-1] == session.login.session

    revoked = service.revokeOAuthIdentity(
        RevokeOAuthIdentityCommand(
            actor_user_id=UserId(USER_ID),
            oauth_identity_id=linked.oauth_identity.oauth_identity_id,
            revoked_at=NOW,
        )
    )

    assert revoked.oauth_identity.revoked_at == NOW
    assert oauth_identities.get_active_by_provider_subject("google", "google-subject-123") is None

    session2 = service.completeOAuthSession(
        CompleteOAuthSessionCommand(
            provider="google",
            code="oauth-code",
            state="state-route",
            redirect_uri="https://token-payments.local/oauth/callback",
            device_id="browser-1",
            requested_at=NOW,
        )
    )
    assert session2.login.user.user_id == UserId(USER_ID)



def _json(body: bytes) -> dict[str, object]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _operation_items(collection: dict[str, object]) -> dict[str, dict[str, object]]:
    items: dict[str, dict[str, object]] = {}

    def walk(nodes: object) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if "request" in node and isinstance(node.get("id"), str):
                items[str(node["id"])] = node
            walk(node.get("item"))

    walk(collection.get("item"))
    return items


class FakeOAuthAuthUseCase:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def requestOAuthAuthorization(self, command: RequestOAuthAuthorizationCommand) -> OAuthAuthorizationResult:
        self.calls.append(command)
        return OAuthAuthorizationResult(
            provider=command.provider,
            authorization_url="https://oauth.example/authorize?state=state-route",
            state="state-route",
            mode=command.mode,
            expires_at=NOW + timedelta(minutes=5),
            pkce_required=True,
        )

    def completeOAuthSession(self, command: CompleteOAuthSessionCommand) -> OAuthSessionResult:
        self.calls.append(command)
        return OAuthSessionResult(
            login=_login_result(),
            oauth_identity=_oauth_identity(),
        )

    def linkOAuthIdentity(self, command: LinkOAuthIdentityCommand) -> OAuthIdentityResult:
        self.calls.append(command)
        return OAuthIdentityResult(oauth_identity=_oauth_identity())

    def listOAuthIdentities(self, query: ListOAuthIdentitiesQuery) -> OAuthIdentitiesResult:
        self.calls.append(query)
        return OAuthIdentitiesResult(oauth_identities=(_oauth_identity(),))

    def revokeOAuthIdentity(self, command: RevokeOAuthIdentityCommand) -> OAuthIdentityResult:
        self.calls.append(command)
        return OAuthIdentityResult(oauth_identity=_oauth_identity(revoked_at=NOW))

    def __getattr__(self, name: str) -> object:
        def unused(*_args: object, **_kwargs: object) -> object:
            raise AssertionError(f"{name} was not expected in this test")

        return unused


class FakeUserRepository:
    def __init__(self) -> None:
        self.user = User(user_id=UserId(USER_ID), primary_wallet=WALLET, active=True, last_login_at=None)

    def save(self, user: User) -> None:
        self.user = user

    def get_by_id(self, user_id: UserId) -> User | None:
        return self.user if user_id == self.user.user_id else None

    def get_by_wallet(self, _wallet: object) -> User | None:
        return self.user

    def get_wallet_id_for_address(self, _user_id: UserId, _wallet: object) -> WalletId:
        return WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc2704")


class FakeOAuthIdentityRepository:
    def __init__(self) -> None:
        self.identities: dict[str, OAuthIdentity] = {}

    def save(self, identity: OAuthIdentity) -> None:
        self.identities[str(identity.oauth_identity_id)] = identity

    def get_by_id(self, oauth_identity_id: OAuthIdentityId) -> OAuthIdentity | None:
        return self.identities.get(str(oauth_identity_id))

    def get_active_by_provider_subject(self, provider: str, provider_subject: str) -> OAuthIdentity | None:
        for identity in self.identities.values():
            if identity.provider == provider and identity.provider_subject == provider_subject and identity.is_active():
                return identity
        return None

    def list_for_user(self, user_id: UserId) -> tuple[OAuthIdentity, ...]:
        return tuple(identity for identity in self.identities.values() if identity.user_id == user_id)


class FakeSessionRepository:
    def __init__(self) -> None:
        self.saved: list[AuthSession] = []

    def save(self, session: AuthSession) -> None:
        self.saved.append(session)

    def get_by_id(self, _session_id: SessionId) -> AuthSession | None:
        return None

    def get_by_refresh_token_hash(self, _refresh_token_hash: RefreshTokenHash) -> AuthSession | None:
        return None


class FakeOAuthProvider:
    def build_authorization(self, **kwargs: object) -> OAuthAuthorizationResult:
        return OAuthAuthorizationResult(
            provider=str(kwargs["provider"]),
            authorization_url="https://oauth.example/authorize?state=state-route",
            state=str(kwargs["state"]),
            mode=kwargs["mode"],
            expires_at=kwargs["expires_at"],
            pkce_required=True,
        )

    def exchange_code(self, **kwargs: object) -> OAuthProviderIdentity:
        assert kwargs["code"] == "oauth-code"
        assert kwargs["state"] == "state-route"
        return OAuthProviderIdentity(
            provider=str(kwargs["provider"]),
            provider_subject="google-subject-123",
            wallet_address="0x2222222222222222222222222222222222222222",
        )


class FakeTokenIssuer:
    def issue_tokens(self, _user: User, session: AuthSession) -> IssuedToken:
        return IssuedToken(
            access_token=f"access:{session.session_id}",
            refresh_token=f"refresh:{session.session_id}",
            expires_at=NOW + timedelta(minutes=15),
        )

    def refresh_tokens(self, session: AuthSession) -> IssuedToken:
        return self.issue_tokens(User(user_id=session.user_id, primary_wallet=WALLET), session)


class StaticClock:
    def now(self) -> datetime:
        return NOW


class SequenceIds:
    def __init__(self, *values: str) -> None:
        self.values = list(values)

    def new_id(self) -> str:
        if not self.values:
            return "018f33aa-9e6d-73d8-9dc3-47d6cdcc2799"
        return self.values.pop(0)


class UnusedRepository:
    def __getattr__(self, name: str) -> object:
        def unused(*_args: object, **_kwargs: object) -> object:
            raise AssertionError(f"{name} was not expected in this test")

        return unused


class UnusedVerifier:
    def verify_signature(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("verify_signature was not expected in this test")


class UnusedPublisher:
    def publish(self, _event: object) -> None:
        pass


def _login_result() -> LoginResult:
    return LoginResult(
        user=User(user_id=UserId(USER_ID), primary_wallet=WALLET, active=True, last_login_at=NOW),
        session=AuthSession(
            session_id=SessionId(SESSION_ID),
            user_id=UserId(USER_ID),
            login_wallet_id=WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc2704"),
            refresh_token_hash=RefreshTokenHash("hash-oauth", "salt-oauth", 0),
            device_id="browser-1",
            expires_at=NOW + timedelta(days=30),
            wallet=WALLET,
        ),
        issued_token=IssuedToken(
            access_token="access-oauth",
            refresh_token="refresh-oauth",
            expires_at=NOW + timedelta(minutes=15),
        ),
    )


def _oauth_identity(*, revoked_at: datetime | None = None) -> OAuthIdentity:
    return OAuthIdentity(
        oauth_identity_id=OAuthIdentityId(OAUTH_IDENTITY_ID),
        provider="google",
        provider_subject="google-subject-123",
        user_id=UserId(USER_ID),
        wallet_id=None,
        linked_at=NOW,
        revoked_at=revoked_at,
    )

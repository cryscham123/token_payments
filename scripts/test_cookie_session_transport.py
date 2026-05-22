from __future__ import annotations

import ast
import base64
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import AuthApi, HttpRouter, OrdersApi, register_auth_routes, register_order_routes  # noqa: E402
from token_payments.contexts.auth.application import (  # noqa: E402
    CurrentUserQuery,
    LoginChallengeResult,
    LoginResult,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    RefreshSessionCommand,
    RequestLoginChallengeCommand,
)
from token_payments.contexts.auth.domain import (  # noqa: E402
    AuthNonce,
    AuthSession,
    IssuedToken,
    LoginChallenge,
    RefreshTokenHash,
    SessionId,
    User,
    UserRole,
)
from token_payments.contexts.auth.domain.wallet import WalletId
from token_payments.contexts.order.application import CreateOrderCommand, OrderCreationResult  # noqa: E402
from token_payments.contexts.order.domain import Address, Customer, Order, Product, Store, TrackingId  # noqa: E402
from token_payments.runtime import LiveRuntimeConfig, describe_live_runtime_dependencies  # noqa: E402
from token_payments.runtime.session_transport import (  # noqa: E402
    CookieSessionTransport,
    CookieSettings,
    SessionClaims,
    SessionKeyRing,
    SessionTokenSigner,
)
from token_payments.shared.domain import (  # noqa: E402
    CheckoutEventName,
    Crypto,
    CustomerId,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)
USER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"
SESSION_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
TRACKING_ID = TrackingId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c27")
OWNER_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c28")
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c29")
WALLET = "0x1111111111111111111111111111111111111111"
STORE_WALLET = "0x2222222222222222222222222222222222222222"
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
ACTIVE_SECRET = "active-live-session-signing-secret-at-least-32-bytes"
PREVIOUS_SECRET = "previous-live-session-signing-secret-at-least-32-bytes"


def test_hmac_session_signer_uses_kid_claims_expiry_and_previous_key_verification() -> None:
    old_signer = SessionTokenSigner(
        SessionKeyRing(active_key_id="previous", keys={"previous": PREVIOUS_SECRET}),
        jti_factory=lambda: "jti-old",
    )
    new_signer = SessionTokenSigner(
        SessionKeyRing(active_key_id="active", keys={"active": ACTIVE_SECRET, "previous": PREVIOUS_SECRET}),
        jti_factory=lambda: "jti-new",
    )
    claims = _claims(token_type="access", expires_at=NOW + timedelta(minutes=15), rotation_version=0)

    old_token = old_signer.sign(claims)
    new_token = new_signer.sign(claims)

    assert new_token.count(".") == 2
    assert not new_token.startswith(("access:", "refresh:"))
    assert _token_header(new_token)["kid"] == "active"
    payload = _token_payload(new_token)
    assert {
        "sub",
        "sessionId",
        "walletAddress",
        "activeGroupId",
        "groupMemberships",
        "iat",
        "exp",
        "typ",
        "jti",
    } <= set(payload)
    assert "role" not in payload
    assert payload["typ"] == "access"
    assert payload["jti"] == "jti-new"
    assert new_signer.verify(old_token, expected_type="access", now=NOW).jti == "jti-old"

    with pytest.raises(ValueError, match="expired"):
        new_signer.verify(new_token, expected_type="access", now=NOW + timedelta(hours=1))


def test_cookie_transport_serializes_secure_http_only_cookies_and_extracts_auth_context() -> None:
    transport = _transport()
    access_token = transport.signer.sign(_claims(token_type="access", expires_at=NOW + timedelta(minutes=15)))
    refresh_token = transport.signer.sign(
        _claims(token_type="refresh", expires_at=NOW + timedelta(days=30), rotation_version=3)
    )

    cookies = transport.issue_cookies(access_token=access_token, refresh_token=refresh_token, now=NOW)

    for header in (cookies.access_cookie, cookies.refresh_cookie):
        assert "HttpOnly" in header
        assert "Secure" in header
        assert "SameSite=Lax" in header
        assert "Path=/" in header
        assert "Max-Age=" in header
        assert "Expires=" in header
        assert ACTIVE_SECRET not in header

    request_context = transport.extract_auth_context({"Cookie": _cookie_header(cookies.set_cookie_headers)})

    assert request_context is not None
    assert request_context.user_id == USER_ID
    assert request_context.session_id == SESSION_ID
    assert request_context.wallet_address == WALLET
    assert request_context.role is None
    assert request_context.active_group_id == str(USER_ID)
    assert request_context.scopes == ("user:self",)
    assert request_context.refresh_token_hash == {
        "hash": _refresh_hash(refresh_token, rotation_version=3).hash,
        "salt": SESSION_ID,
        "rotationVersion": 3,
    }


def test_auth_routes_set_rotate_and_expire_cookies_without_exposing_internal_refresh_hash() -> None:
    transport = _transport()
    use_case = CookieAuthUseCase(transport)
    router = HttpRouter(auth_context_factory=transport.auth_context_from_http_request)
    register_auth_routes(router, AuthApi(use_case), session_transport=transport)

    login = router.handle(
        "POST",
        "/auth/sessions",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-login"},
        body=_json_body(
            {
                "walletAddress": WALLET,
                "message": "sign nonce",
                "signature": "signature-valid",
                "deviceId": "browser-1",
            }
        ),
        received_at=NOW,
    )

    login_body = _json(login.body)
    login_cookies = _header_values(login, "Set-Cookie")
    assert login.status_code == 200
    assert len(login_cookies) == 2
    assert "refreshTokenHash" not in login_body["session"]
    assert login_body["token"]["transport"] == "cookie"
    assert login_body["token"]["accessToken"] == "<set-cookie>"
    assert login_body["token"]["refreshToken"] == "<set-cookie>"

    refresh = router.handle(
        "POST",
        "/auth/sessions/refresh",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-refresh",
            "Cookie": _cookie_header(login_cookies),
        },
        body=_json_body({}),
        received_at=NOW + timedelta(minutes=10),
    )

    refresh_body = _json(refresh.body)
    refresh_cookies = _header_values(refresh, "Set-Cookie")
    assert refresh.status_code == 200
    assert len(refresh_cookies) == 2
    assert refresh_cookies != login_cookies
    assert "refreshTokenHash" not in refresh_body["session"]
    assert use_case.refresh_commands[0].session_id == SessionId(SESSION_ID)
    assert use_case.refresh_commands[0].refresh_token_hash == _refresh_hash(
        use_case.login_refresh_token,
        rotation_version=0,
    )

    logout = router.handle(
        "DELETE",
        "/auth/sessions",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-logout",
            "Cookie": _cookie_header(refresh_cookies),
        },
        body=_json_body({}),
        received_at=NOW + timedelta(minutes=11),
    )

    logout_cookies = _header_values(logout, "Set-Cookie")
    assert logout.status_code == 200
    assert len(logout_cookies) == 2
    assert all("Max-Age=0" in header for header in logout_cookies)
    assert all("Expires=Thu, 01 Jan 1970 00:00:00 GMT" in header for header in logout_cookies)
    assert use_case.logout_commands[0].session_id == SessionId(SESSION_ID)


def test_live_runtime_session_config_parses_redacts_and_rejects_live_placeholder_keys() -> None:
    env = {
        "RUNTIME_ENVIRONMENT": "live",
        "SESSION_ACTIVE_KEY_ID": "active",
        "SESSION_SIGNING_KEYS": json.dumps({"active": ACTIVE_SECRET, "previous": PREVIOUS_SECRET}),
        "SESSION_ACCESS_TTL_SECONDS": "900",
        "SESSION_REFRESH_TTL_SECONDS": "2592000",
    }

    config = LiveRuntimeConfig.from_env(env)
    preview = describe_live_runtime_dependencies(config=config)

    assert config.session_key_ring.active_key_id == "active"
    assert sorted(config.session_key_ring.keys) == ["active", "previous"]
    assert preview["config"]["session"]["signingKeysConfigured"] is True
    assert preview["config"]["session"]["activeKeyId"] == "active"
    assert ACTIVE_SECRET not in json.dumps(preview, sort_keys=True)
    assert PREVIOUS_SECRET not in json.dumps(preview, sort_keys=True)

    with pytest.raises(ValueError, match="SESSION_SIGNING_KEYS"):
        LiveRuntimeConfig.from_env({"RUNTIME_ENVIRONMENT": "live", "SESSION_ACTIVE_KEY_ID": "active"})

    with pytest.raises(ValueError, match="placeholder"):
        LiveRuntimeConfig.from_env(
            {
                "RUNTIME_ENVIRONMENT": "production",
                "SESSION_ACTIVE_KEY_ID": "placeholder",
                "SESSION_SIGNING_KEYS": "placeholder=replace_with_local_dev_only_session_signing_key",
            }
        )


def test_production_router_ignores_dev_claim_headers_and_accepts_cookie_auth_context() -> None:
    transport = _transport()
    order_use_case = CapturingOrderUseCase()
    router = HttpRouter(
        auth_context_factory=transport.auth_context_from_http_request,
        allow_dev_auth_headers=False,
    )
    register_order_routes(router, OrdersApi(order_use_case))

    rejected = router.handle(
        "POST",
        "/orders",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-header-only",
            "X-User-Id": "attacker-user",
        },
        body=_create_order_body(),
        received_at=NOW,
    )

    assert rejected.status_code == 400
    assert order_use_case.commands == []

    access_token = transport.signer.sign(_claims(token_type="access", expires_at=NOW + timedelta(minutes=15)))
    cookies = transport.issue_cookies(access_token=access_token, refresh_token="unused.refresh.token", now=NOW)
    accepted = router.handle(
        "POST",
        "/orders",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-cookie",
            "X-User-Id": "attacker-user",
            "Cookie": _cookie_header((cookies.access_cookie,)),
        },
        body=_create_order_body(),
        received_at=NOW,
    )

    assert accepted.status_code == 201
    assert order_use_case.commands[0].authenticated_user_id == UserId(USER_ID)


def test_session_transport_import_boundary_avoids_http_frameworks_and_live_drivers() -> None:
    imported_roots = _imported_roots(ROOT / "app/token_payments/runtime/session_transport.py")

    assert imported_roots.isdisjoint(
        {
            "asyncpg",
            "confluent_kafka",
            "docker",
            "fastapi",
            "kafka",
            "psycopg",
            "psycopg2",
            "requests",
            "socket",
            "starlette",
            "uvicorn",
            "web3",
        }
    )


def _transport() -> CookieSessionTransport:
    return CookieSessionTransport(
        signer=SessionTokenSigner(
            SessionKeyRing(active_key_id="active", keys={"active": ACTIVE_SECRET, "previous": PREVIOUS_SECRET}),
            jti_factory=lambda: "jti-test",
        ),
        settings=CookieSettings(
            access_max_age_seconds=900,
            refresh_max_age_seconds=2_592_000,
        ),
        clock=FakeClock(NOW),
    )


def _claims(*, token_type: str, expires_at: datetime, rotation_version: int = 0) -> SessionClaims:
    return SessionClaims(
        user_id=USER_ID,
        session_id=SESSION_ID,
        wallet_address=WALLET,
        active_group_id=USER_ID,
        group_memberships=(
            {
                "groupId": USER_ID,
                "groupType": "PERSONAL",
                "roleId": "PERSONAL_CUSTOMER",
                "resourceType": "user",
                "resourceId": USER_ID,
            },
        ),
        scopes=("user:self",),
        issued_at=NOW,
        expires_at=expires_at,
        token_type=token_type,
        jti="jti-input",
        rotation_version=rotation_version,
    )


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json(body: bytes) -> dict[str, Any]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


def _create_order_body() -> bytes:
    return _json_body(
        {
            "storeId": str(STORE_ID),
            "deliveryAddress": {"id": "ship-to", "street": "2 River Rd"},
            "items": [{"productId": str(PRODUCT_ID), "quantity": 2}],
        }
    )


def _header_values(response: Any, name: str) -> tuple[str, ...]:
    values = tuple(value for key, value in response.header_items() if key.lower() == name.lower())
    assert values
    return values


def _cookie_header(set_cookie_headers: tuple[str, ...]) -> str:
    return "; ".join(header.split(";", 1)[0] for header in set_cookie_headers)


def _refresh_hash(token: str, *, rotation_version: int) -> RefreshTokenHash:
    return RefreshTokenHash(
        hash=hashlib.sha256(f"{SESSION_ID}:{token}".encode("utf-8")).hexdigest(),
        salt=SESSION_ID,
        rotation_version=rotation_version,
    )


def _token_header(token: str) -> dict[str, Any]:
    return _decode_token_part(token.split(".", 2)[0])


def _token_payload(token: str) -> dict[str, Any]:
    return _decode_token_part(token.split(".", 2)[1])


def _decode_token_part(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    assert isinstance(decoded, dict)
    return decoded


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".", 1)[0])
    return modules


@dataclass
class FakeClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


class CookieAuthUseCase:
    def __init__(self, transport: CookieSessionTransport) -> None:
        self._transport = transport
        self.login_access_token = transport.signer.sign(_claims(token_type="access", expires_at=NOW + timedelta(minutes=15)))
        self.login_refresh_token = transport.signer.sign(
            _claims(token_type="refresh", expires_at=NOW + timedelta(days=30), rotation_version=0)
        )
        self.refreshed_access_token = transport.signer.sign(
            _claims(token_type="access", expires_at=NOW + timedelta(minutes=25), rotation_version=1)
        )
        self.refreshed_refresh_token = transport.signer.sign(
            _claims(token_type="refresh", expires_at=NOW + timedelta(days=30, minutes=10), rotation_version=1)
        )
        self.refresh_commands: list[RefreshSessionCommand] = []
        self.logout_commands: list[LogoutCommand] = []

    def requestLoginChallenge(self, command: RequestLoginChallengeCommand) -> LoginChallengeResult:
        return LoginChallengeResult(
            challenge=LoginChallenge.issue(WALLET, AuthNonce("nonce", NOW + timedelta(minutes=5)), issued_at=NOW),
            signing_message="sign nonce",
        )

    def loginWithMetaMask(self, command: LoginWithMetaMaskCommand) -> LoginResult:
        return _login_result(
            access_token=self.login_access_token,
            refresh_token=self.login_refresh_token,
            refresh_token_hash=_refresh_hash(self.login_refresh_token, rotation_version=0),
        )

    def refreshSession(self, command: RefreshSessionCommand) -> LoginResult:
        self.refresh_commands.append(command)
        return _login_result(
            access_token=self.refreshed_access_token,
            refresh_token=self.refreshed_refresh_token,
            refresh_token_hash=_refresh_hash(self.refreshed_refresh_token, rotation_version=1),
        )

    def logout(self, command: LogoutCommand) -> AuthSession:
        self.logout_commands.append(command)
        return _session(refresh_token_hash=_refresh_hash(self.refreshed_refresh_token, rotation_version=1), revoked_at=NOW)

    def getCurrentUser(self, query: CurrentUserQuery) -> User:
        return _user()


class CapturingOrderUseCase:
    def __init__(self) -> None:
        self.commands: list[CreateOrderCommand] = []

    def createOrder(self, command: CreateOrderCommand) -> OrderCreationResult:
        self.commands.append(command)
        amount = Crypto(
            amount="12.50",
            symbol="USDC",
            chain_id=11155111,
            token_address=TOKEN_ADDRESS,
            decimals=6,
        )
        customer = Customer(customer_id=CUSTOMER_ID, user_id=command.authenticated_user_id)
        product = Product(product_id=PRODUCT_ID, name="Ledger Mug", price=amount)
        store = Store(
            store_id=STORE_ID,
            owner_user_id=OWNER_USER_ID,
            products=(product,),
            store_wallet=STORE_WALLET,
            supported_chain_ids=(11155111,),
        )
        order = Order.initialize_order(
            order_id=ORDER_ID,
            customer=customer,
            store=store,
            delivery_address=Address(id="ship-to", street="2 River Rd"),
            product_quantities={PRODUCT_ID: 2},
            tracking_id=TRACKING_ID,
            created_at=NOW,
        )
        return OrderCreationResult(
            order=order,
            total_amount=order.items[0].sub_total,
            outbox_message=OutboxMessage(
                kind=OutboxMessageKind.EVENT,
                identity=str(MESSAGE_ID),
                name=CheckoutEventName.ORDER_CREATED.value,
                topic="order.events",
                key=str(ORDER_ID),
                payload={"orderId": str(ORDER_ID)},
                created_at=NOW,
            ),
        )


def _login_result(
    *,
    access_token: str,
    refresh_token: str,
    refresh_token_hash: RefreshTokenHash,
) -> LoginResult:
    return LoginResult(
        user=_user(),
        session=_session(refresh_token_hash=refresh_token_hash),
        issued_token=IssuedToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=NOW + timedelta(minutes=15),
        ),
    )


def _user() -> User:
    return User(
        user_id=UserId(USER_ID),
        primary_wallet=WALLET,
        role=UserRole.CUSTOMER,
        active=True,
        last_login_at=NOW,
    )


def _session(*, refresh_token_hash: RefreshTokenHash, revoked_at: datetime | None = None) -> AuthSession:
    return AuthSession(
        session_id=SessionId(SESSION_ID),
        user_id=UserId(USER_ID),
        login_wallet_id=WalletId.new(),
        refresh_token_hash=refresh_token_hash,
        device_id="browser-1",
        expires_at=NOW + timedelta(days=30),
        revoked_at=revoked_at,
    )

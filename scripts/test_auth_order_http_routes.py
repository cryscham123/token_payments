from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import (  # noqa: E402
    AUTH_HTTP_ROUTES,
    ORDER_HTTP_ROUTES,
    AuthApi,
    HttpRouter,
    OrdersApi,
    register_auth_routes,
    register_order_routes,
)
from token_payments.contexts.auth.application import (  # noqa: E402
    AuthApplicationError,
    AuthErrorCode,
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
    ChallengeStatus,
    IssuedToken,
    LoginChallenge,
    RefreshTokenHash,
    SessionId,
    User,
)
from token_payments.contexts.auth.domain.wallet import WalletId
from token_payments.contexts.order.application import CreateOrderCommand, OrderCreationResult  # noqa: E402
from token_payments.contexts.order.domain import Address, Customer, Order, Product, Store, TrackingId  # noqa: E402
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


NOW = datetime(2026, 5, 10, 7, 0, tzinfo=UTC)
WALLET = "0xABCDabcdABCDabcdABCDabcdABCDabcdABCDabcd"
NORMALIZED_WALLET = "0xabcdabcdabcdabcdabcdabcdabcdabcdabcdabcd"
USER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"
SESSION_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
TRACKING_ID = TrackingId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c27")
OWNER_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c28")
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c29")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")


def test_auth_route_manifest_exposes_stable_methods_paths_and_operations() -> None:
    assert AUTH_HTTP_ROUTES["request_login_challenge"].method == "POST"
    assert AUTH_HTTP_ROUTES["request_login_challenge"].path == "/auth/challenges"
    assert AUTH_HTTP_ROUTES["request_login_challenge"].operation_id == "requestLoginChallenge"
    assert AUTH_HTTP_ROUTES["login_with_metamask"].method == "POST"
    assert AUTH_HTTP_ROUTES["login_with_metamask"].path == "/auth/sessions"
    assert AUTH_HTTP_ROUTES["refresh_session"].method == "POST"
    assert AUTH_HTTP_ROUTES["refresh_session"].path == "/auth/sessions/refresh"
    assert AUTH_HTTP_ROUTES["logout"].method == "DELETE"
    assert AUTH_HTTP_ROUTES["logout"].path == "/auth/sessions"
    assert AUTH_HTTP_ROUTES["current_user"].method == "GET"
    assert AUTH_HTTP_ROUTES["current_user"].path == "/auth/me"

    assert ORDER_HTTP_ROUTES["create_order"].method == "POST"
    assert ORDER_HTTP_ROUTES["create_order"].path == "/orders"
    assert ORDER_HTTP_ROUTES["create_order"].operation_id == "createOrder"


def test_auth_http_routes_call_existing_auth_facade_methods() -> None:
    use_case = FakeAuthUseCase()
    router = HttpRouter()

    routes = register_auth_routes(router, AuthApi(use_case))

    assert len(routes) == 5
    assert {route.operation_id for route in routes} == {
        "requestLoginChallenge",
        "loginWithMetaMask",
        "refreshSession",
        "logout",
        "getCurrentUser",
    }

    challenge = router.handle(
        "POST",
        "/auth/challenges",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-auth-challenge"},
        body=b'{"walletAddress":"0xABCDabcdABCDabcdABCDabcdABCDabcdABCDabcd","domain":"token-payments.local","chainId":11155111}',
        received_at=NOW,
    )

    assert challenge.status_code == 201
    challenge_payload = _json(challenge.body)
    assert challenge_payload == {
        "expiresAt": (NOW + timedelta(minutes=5)).isoformat(),
        "nonce": "nonce-route",
        "signingMessage": "sign nonce-route",
        "signatureVerification": {
            "erc1271MagicValue": "0x1626ba7e",
            "erc6492": "future_scope",
            "messageFormat": "SIWE_V1",
            "requiresDeployedCode": True,
            "signatureVerificationMethod": "SIWE_PERSONAL_SIGN_EOA_OR_ERC1271",
            "smartWalletStandard": "ERC-1271",
            "supportedWalletTypes": ["EOA", "DEPLOYED_SMART_WALLET"],
        },
        "walletAddress": NORMALIZED_WALLET,
    }
    assert isinstance(use_case.calls[-1], RequestLoginChallengeCommand)
    assert use_case.calls[-1].wallet_address == WALLET

    login = router.handle(
        "POST",
        "/auth/sessions",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-auth-login"},
        body=b'{"walletAddress":"0xABCDabcdABCDabcdABCDabcdABCDabcdABCDabcd","message":"sign nonce-route","signature":"sig-valid","deviceId":"browser-1"}',
        received_at=NOW,
    )

    assert login.status_code == 200
    assert _json(login.body)["session"]["deviceId"] == "browser-1"
    assert _json(login.body)["token"]["accessToken"] == "access-route"
    assert isinstance(use_case.calls[-1], LoginWithMetaMaskCommand)
    assert use_case.calls[-1].device_id == "browser-1"

    refresh = router.handle(
        "POST",
        "/auth/sessions/refresh",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-auth-refresh"},
        body=b'{"sessionId":"018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22","refreshTokenHash":{"hash":"hash-route","salt":"salt-route","rotationVersion":0}}',
        received_at=NOW,
    )

    assert refresh.status_code == 200
    assert _json(refresh.body)["session"]["refreshTokenHash"]["rotationVersion"] == 1
    assert isinstance(use_case.calls[-1], RefreshSessionCommand)
    assert use_case.calls[-1].refresh_token_hash.hash == "hash-route"

    logout = router.handle(
        "DELETE",
        "/auth/sessions",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-auth-logout"},
        body=b'{"sessionId":"018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"}',
        received_at=NOW,
    )

    assert logout.status_code == 200
    assert _json(logout.body)["session"]["revokedAt"] == NOW.isoformat()
    assert isinstance(use_case.calls[-1], LogoutCommand)

    current_user = router.handle(
        "GET",
        "/auth/me",
        query={"userId": USER_ID},
        headers={"X-Request-Id": "req-auth-me"},
        received_at=NOW,
    )

    assert current_user.status_code == 200
    assert _json(current_user.body)["user"]["userId"] == USER_ID
    assert isinstance(use_case.calls[-1], CurrentUserQuery)


def test_auth_http_routes_preserve_facade_error_status_and_body() -> None:
    router = HttpRouter()
    register_auth_routes(router, AuthApi(RejectingAuthUseCase()))

    response = router.handle(
        "POST",
        "/auth/sessions",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-auth-error"},
        body=b'{"walletAddress":"0xABCDabcdABCDabcdABCDabcdABCDabcdABCDabcd","message":"sign nonce-route","signature":"sig-valid","deviceId":"browser-1"}',
    )

    assert response.status_code == 409
    assert _json(response.body) == {
        "error": {
            "code": "REUSED_NONCE",
            "message": "route rejected nonce",
        }
    }


def test_order_http_route_calls_orders_facade_and_preserves_user_header() -> None:
    use_case = FakeOrderUseCase()
    api = CapturingOrdersApi(use_case)
    router = HttpRouter()

    routes = register_order_routes(router, api)
    assert len(routes) == 1
    assert routes[0].operation_id == "createOrder"

    response = router.handle(
        "POST",
        "/orders",
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": "req-order-create",
            "X-User-Id": USER_ID,
        },
        body=b'{"storeId":"018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26","deliveryAddress":{"id":"ship-to","street":"2 River Rd"},"items":[{"productId":"018f33aa-9e6d-73d8-9dc3-47d6cdcc6c27","quantity":2}]}',
        received_at=NOW,
    )

    assert response.status_code == 201
    assert _json(response.body)["order"]["status"] == "PENDING"
    assert _json(response.body)["order"]["totalAmount"] == {
        "amount": "25.00",
        "chainId": 11155111,
        "decimals": 6,
        "symbol": "USDC",
        "tokenAddress": str(TOKEN_ADDRESS),
    }
    assert api.requests[0].headers["X-User-Id"] == USER_ID
    assert use_case.commands[0].authenticated_user_id == UserId(USER_ID)
    assert use_case.commands[0].causation_id == "req-order-create"
    assert use_case.commands[0].requested_at == NOW


def _json(body: bytes) -> dict[str, object]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


class FakeAuthUseCase:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def requestLoginChallenge(self, command: RequestLoginChallengeCommand) -> LoginChallengeResult:
        self.calls.append(command)
        return LoginChallengeResult(
            challenge=LoginChallenge.issue(
                wallet=command.wallet_address,
                nonce=AuthNonce("nonce-route", NOW + timedelta(minutes=5)),
                issued_at=NOW,
            ),
            signing_message="sign nonce-route",
        )

    def loginWithMetaMask(self, command: LoginWithMetaMaskCommand) -> LoginResult:
        self.calls.append(command)
        return _login_result(device_id=command.device_id)

    def refreshSession(self, command: RefreshSessionCommand) -> LoginResult:
        self.calls.append(command)
        return _login_result(refresh_token_hash=command.refresh_token_hash.rotate("hash-refreshed", "salt-refreshed"))

    def logout(self, command: LogoutCommand) -> AuthSession:
        self.calls.append(command)
        return _session(session_id=command.session_id, revoked_at=NOW)

    def getCurrentUser(self, query: CurrentUserQuery) -> User:
        self.calls.append(query)
        return _user()


class RejectingAuthUseCase:
    def requestLoginChallenge(self, command: object) -> object:
        raise AssertionError("not used")

    def loginWithMetaMask(self, command: object) -> object:
        raise AuthApplicationError(AuthErrorCode.REUSED_NONCE, "route rejected nonce")

    def refreshSession(self, command: object) -> object:
        raise AssertionError("not used")

    def logout(self, command: object) -> object:
        raise AssertionError("not used")

    def getCurrentUser(self, query: object) -> object:
        raise AssertionError("not used")


class CapturingOrdersApi(OrdersApi):
    def __init__(self, use_case: FakeOrderUseCase) -> None:
        super().__init__(use_case)
        self.requests = []

    def create_order(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        return super().create_order(request)


class FakeOrderUseCase:
    def __init__(self) -> None:
        self.commands: list[CreateOrderCommand] = []

    def createOrder(self, command: CreateOrderCommand) -> OrderCreationResult:
        self.commands.append(command)
        amount = Crypto(
            amount=Decimal("12.50"),
            symbol="USDC",
            chain_id=11155111,
            token_address=TOKEN_ADDRESS,
            decimals=6,
        )
        customer = Customer(
            customer_id=CUSTOMER_ID,
            user_id=command.authenticated_user_id,
        )
        store = Store(
            store_id=STORE_ID,
            owner_user_id=OWNER_USER_ID,
            products=(Product(product_id=PRODUCT_ID, name="Ledger Mug", price=amount),),
            store_wallet="0x2222222222222222222222222222222222222222",
            supported_chain_ids=(11155111,),
        )
        order = Order.initialize_order(
            order_id=ORDER_ID,
            customer=customer,
            store=store,
            delivery_address=Address(id="ship-to", street="2 River Rd"),
            product_quantities={PRODUCT_ID: 2},
            created_at=NOW,
            tracking_id=TRACKING_ID,
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
    device_id: str = "browser-1",
    refresh_token_hash: RefreshTokenHash | None = None,
) -> LoginResult:
    return LoginResult(
        user=_user(),
        session=_session(refresh_token_hash=refresh_token_hash, device_id=device_id),
        issued_token=IssuedToken(
            access_token="access-route",
            refresh_token="refresh-route",
            expires_at=NOW + timedelta(minutes=15),
        ),
    )


def _user() -> User:
    return User(
        user_id=UserId(USER_ID),
        primary_wallet=WALLET,
        active=True,
        last_login_at=NOW,
    )


def _session(
    *,
    session_id: SessionId | None = None,
    refresh_token_hash: RefreshTokenHash | None = None,
    device_id: str = "browser-1",
    revoked_at: datetime | None = None,
) -> AuthSession:
    return AuthSession(
        session_id=session_id or SessionId(SESSION_ID),
        user_id=UserId(USER_ID),
        login_wallet_id=WalletId.new(),
        refresh_token_hash=refresh_token_hash or RefreshTokenHash("hash-route", "salt-route", 0),
        device_id=device_id,
        expires_at=NOW + timedelta(days=30),
        revoked_at=revoked_at,
    )

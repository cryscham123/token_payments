from __future__ import annotations

import ast
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import AuthApi, HttpRouter, build_asgi_app, json_response, register_auth_routes  # noqa: E402
from token_payments.contexts.auth.application import (  # noqa: E402
    CurrentUserQuery,
    LoginChallengeResult,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    RefreshSessionCommand,
    RequestLoginChallengeCommand,
)
from token_payments.contexts.auth.domain import AuthNonce, LoginChallenge  # noqa: E402
from token_payments.runtime.security import (  # noqa: E402
    CorsPolicy,
    CsrfCookieSettings,
    CsrfTokenService,
    HmacCsrfTokenSigner,
    RequestBodyLimit,
    RequestGuard,
)


NOW = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)
WALLET = "0x1111111111111111111111111111111111111111"
ACTIVE_CSRF_SECRET = "active-live-csrf-signing-secret-at-least-32-bytes"
LOCAL_ORIGIN = "http://localhost:5173"
ADMIN_ORIGIN = "http://127.0.0.1:8765"


def test_login_challenge_issues_signed_csrf_token_cookie_without_expanding_route_manifest() -> None:
    csrf = _csrf_service()
    router = HttpRouter(request_guard=_guard(csrf_service=csrf))
    register_auth_routes(router, AuthApi(ChallengeOnlyUseCase()), csrf_token_service=csrf)

    response = router.handle(
        "POST",
        "/auth/challenges",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-challenge"},
        body=_json_body({"walletAddress": WALLET, "domain": "token-payments.local", "chainId": 1337}),
        received_at=NOW,
    )

    body = _json(response.body)
    csrf_cookie = _header_values(response, "Set-Cookie")[0]

    assert response.status_code == 201
    assert body["csrfToken"].startswith("csrf-active.")
    assert body["csrf"] == {
        "cookieName": "csrf_token",
        "headerName": "X-CSRF-Token",
    }
    assert f"csrf_token={body['csrfToken']}" in csrf_cookie
    assert "Secure" in csrf_cookie
    assert "SameSite=Lax" in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "auth/csrf" not in {route["path"] for route in __import__("token_payments.api").api.http_route_manifest()}
    assert len(__import__("token_payments.api").api.http_route_manifest()) == 47


def test_cookie_authenticated_mutating_requests_require_valid_double_submit_csrf() -> None:
    csrf = _csrf_service()
    guard = _guard(csrf_service=csrf)
    router = HttpRouter(request_guard=guard)
    calls: list[Mapping[str, Any]] = []

    def handler(request: Any):
        calls.append(request.body)
        return json_response({"ok": True}, status_code=201, request_id=request.request_id)

    router.add_route("POST", "/orders", handler, operation_id="createOrder")
    token = csrf.issue_token(now=NOW).token

    missing = router.handle(
        "POST",
        "/orders",
        headers={
            "Content-Type": "application/json",
            "Cookie": "access_token=session-token; csrf_token=%s" % token,
            "X-Request-Id": "req-missing",
        },
        body=_json_body({"storeId": "store-001"}),
        received_at=NOW,
    )
    invalid = router.handle(
        "POST",
        "/orders",
        headers={
            "Content-Type": "application/json",
            "Cookie": "access_token=session-token; csrf_token=%s" % token,
            "X-CSRF-Token": token + "-tampered",
            "X-Request-Id": "req-invalid",
        },
        body=_json_body({"storeId": "store-001"}),
        received_at=NOW,
    )
    accepted = router.handle(
        "POST",
        "/orders",
        headers={
            "Content-Type": "application/json",
            "Cookie": "access_token=session-token; csrf_token=%s" % token,
            "X-CSRF-Token": token,
            "X-Request-Id": "req-ok",
        },
        body=_json_body({"storeId": "store-001"}),
        received_at=NOW,
    )

    assert missing.status_code == 403
    assert _json(missing.body)["error"]["code"] == "CSRF_TOKEN_MISSING"
    assert invalid.status_code == 403
    assert _json(invalid.body)["error"]["code"] == "CSRF_TOKEN_INVALID"
    assert accepted.status_code == 201
    assert calls == [{"storeId": "store-001"}]


def test_safe_methods_do_not_require_csrf_even_when_auth_cookies_are_present() -> None:
    router = HttpRouter(request_guard=_guard())
    calls: list[str] = []

    def handler(request: Any):
        calls.append(request.method)
        return json_response({"ok": True}, request_id=request.request_id)

    router.add_route("GET", "/auth/me", handler, operation_id="getCurrentUser")

    response = router.handle(
        "GET",
        "/auth/me",
        headers={"Cookie": "access_token=session-token", "X-Request-Id": "req-safe"},
    )

    assert response.status_code == 200
    assert calls == ["GET"]


def test_credentialed_cors_uses_allowlist_and_preflight_bypasses_business_logic() -> None:
    router = HttpRouter(request_guard=_guard())
    calls: list[str] = []
    router.add_route(
        "POST",
        "/orders",
        lambda request: calls.append(request.path) or json_response({"ok": True}, request_id=request.request_id),
        operation_id="createOrder",
    )

    preflight = router.handle(
        "OPTIONS",
        "/orders",
        headers={
            "Origin": LOCAL_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
            "X-Request-Id": "req-preflight",
        },
    )
    rejected = router.handle(
        "OPTIONS",
        "/orders",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "X-Request-Id": "req-preflight-rejected",
        },
    )

    assert preflight.status_code == 204
    assert _headers(preflight)["Access-Control-Allow-Origin"] == LOCAL_ORIGIN
    assert _headers(preflight)["Access-Control-Allow-Credentials"] == "true"
    assert _headers(preflight)["Access-Control-Allow-Methods"] == "DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT"
    assert _headers(preflight)["Access-Control-Allow-Headers"] == "content-type, x-csrf-token"
    assert _headers(preflight)["Access-Control-Allow-Origin"] != "*"
    assert rejected.status_code == 403
    assert _json(rejected.body)["error"]["code"] == "CORS_ORIGIN_FORBIDDEN"
    assert calls == []

    with pytest.raises(ValueError, match="wildcard"):
        CorsPolicy(allowed_origins=("*",), allow_credentials=True)


def test_actual_cors_request_gets_allowlist_headers_without_wildcard_credentials() -> None:
    router = HttpRouter(request_guard=_guard())
    router.add_route(
        "GET",
        "/operator/dashboard",
        lambda request: json_response({"ok": True}, request_id=request.request_id),
        operation_id="getOperatorDashboard",
    )

    response = router.handle(
        "GET",
        "/operator/dashboard",
        headers={"Origin": ADMIN_ORIGIN, "X-Request-Id": "req-cors"},
    )

    assert response.status_code == 200
    assert _headers(response)["Access-Control-Allow-Origin"] == ADMIN_ORIGIN
    assert _headers(response)["Access-Control-Allow-Credentials"] == "true"
    assert _headers(response)["Vary"] == "Origin"


def test_request_body_limit_blocks_before_handler_and_malformed_json_contract_stays_400() -> None:
    router = HttpRouter(request_guard=_guard(body_limit=RequestBodyLimit(max_bytes=8)))
    calls: list[str] = []
    router.add_route(
        "POST",
        "/payments/transaction-hashes",
        lambda request: calls.append("called") or json_response({"ok": True}, request_id=request.request_id),
        operation_id="submitTransactionHash",
    )

    too_large = router.handle(
        "POST",
        "/payments/transaction-hashes",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-too-large"},
        body=b'{"too":9}',
    )
    malformed = router.handle(
        "POST",
        "/payments/transaction-hashes",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-bad-json"},
        body=b'{"bad":',
    )

    assert too_large.status_code == 413
    assert _json(too_large.body)["error"]["code"] == "REQUEST_BODY_TOO_LARGE"
    assert malformed.status_code == 400
    assert _json(malformed.body)["error"]["code"] == "MALFORMED_JSON"
    assert calls == []


def test_asgi_body_limit_uses_request_body_limit_contract_before_dispatch() -> None:
    router = HttpRouter()
    calls: list[str] = []
    router.add_route(
        "POST",
        "/orders",
        lambda request: calls.append("called") or json_response({"ok": True}, request_id=request.request_id),
        operation_id="createOrder",
    )

    sent = _run_asgi_http(
        build_asgi_app(router, request_body_limit=RequestBodyLimit(max_bytes=4)),
        {
            "type": "http",
            "method": "POST",
            "path": "/orders",
            "query_string": b"",
            "headers": [(b"x-request-id", b"req-asgi-too-large")],
        },
        receive_events=[{"type": "http.request", "body": b"12345", "more_body": False}],
    )

    assert _start(sent)["status"] == 413
    assert json.loads(_body(sent))["error"]["code"] == "REQUEST_BODY_TOO_LARGE"
    assert calls == []


def test_asgi_preflight_204_sends_no_body_for_h11_compatibility() -> None:
    router = HttpRouter(request_guard=_guard())
    router.add_route(
        "POST",
        "/orders",
        lambda request: json_response({"ok": True}, request_id=request.request_id),
        operation_id="createOrder",
    )

    sent = _run_asgi_http(
        build_asgi_app(router),
        {
            "type": "http",
            "method": "OPTIONS",
            "path": "/orders",
            "query_string": b"",
            "headers": [
                (b"origin", LOCAL_ORIGIN.encode("ascii")),
                (b"access-control-request-method", b"POST"),
                (b"x-request-id", b"req-asgi-preflight"),
            ],
        },
    )

    assert _start(sent)["status"] == 204
    assert _body(sent) == b""


def test_security_guard_source_avoids_frameworks_drivers_and_live_clients() -> None:
    imports = _imported_roots(ROOT / "app/token_payments/runtime/security.py")

    assert imports.isdisjoint(
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


def _guard(
    *,
    csrf_service: CsrfTokenService | None = None,
    body_limit: RequestBodyLimit | None = None,
) -> RequestGuard:
    return RequestGuard(
        csrf_token_service=csrf_service or _csrf_service(),
        cors_policy=CorsPolicy(allowed_origins=(LOCAL_ORIGIN, ADMIN_ORIGIN), allow_credentials=True),
        body_limit=body_limit or RequestBodyLimit(max_bytes=1024),
        auth_cookie_names=("access_token", "refresh_token"),
    )


def _csrf_service() -> CsrfTokenService:
    return CsrfTokenService(
        signer=HmacCsrfTokenSigner(
            key_id="csrf-active",
            secret_provider=lambda: ACTIVE_CSRF_SECRET,
            nonce_factory=lambda: "csrf-nonce-001",
        ),
        cookie_settings=CsrfCookieSettings(max_age_seconds=3600),
    )


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json(body: bytes) -> dict[str, Any]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


def _headers(response: Any) -> dict[str, str]:
    return {key: value for key, value in response.header_items()}


def _header_values(response: Any, name: str) -> tuple[str, ...]:
    values = tuple(value for key, value in response.header_items() if key.lower() == name.lower())
    assert values
    return values


def _run_asgi_http(
    app: Any,
    scope: dict[str, Any],
    *,
    receive_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    pending = list(receive_events or [{"type": "http.request", "body": b"", "more_body": False}])

    async def receive() -> dict[str, Any]:
        if pending:
            return pending.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return sent


def _start(sent: list[dict[str, Any]]) -> dict[str, Any]:
    return sent[0]


def _body(sent: list[dict[str, Any]]) -> bytes:
    return sent[1]["body"]


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


class ChallengeOnlyUseCase:
    def requestLoginChallenge(self, command: RequestLoginChallengeCommand) -> LoginChallengeResult:
        return LoginChallengeResult(
            challenge=LoginChallenge.issue(WALLET, AuthNonce("nonce-001", NOW + timedelta(minutes=5)), issued_at=NOW),
            signing_message="Sign in to token-payments.local with nonce nonce-001",
        )

    def loginWithMetaMask(self, command: LoginWithMetaMaskCommand) -> Any:
        raise AssertionError("not used")

    def refreshSession(self, command: RefreshSessionCommand) -> Any:
        raise AssertionError("not used")

    def logout(self, command: LogoutCommand) -> Any:
        raise AssertionError("not used")

    def getCurrentUser(self, query: CurrentUserQuery) -> Any:
        raise AssertionError("not used")

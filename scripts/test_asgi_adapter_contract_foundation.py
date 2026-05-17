from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_asgi_adapter_public_exports_cover_standard_boundary_surface() -> None:
    import token_payments.api as api

    expected = {"AsgiApplication", "AsgiReceive", "AsgiScope", "AsgiSend", "build_asgi_app"}

    assert expected <= set(api.__all__)
    assert all(hasattr(api, name) for name in expected)


def test_asgi_app_converts_get_scope_to_http_request_and_serializes_response_events() -> None:
    from token_payments.api import ApiRequest, HttpRouter, build_asgi_app, json_response

    captured: list[ApiRequest] = []

    def handler(request: ApiRequest):
        captured.append(request)
        return json_response(
            {
                "body": request.body,
                "filter": request.query["filter"],
                "orderId": request.query["orderId"],
                "requestId": request.request_id,
            },
            status_code=202,
            request_id=request.request_id,
            headers={"Cache-Control": "no-store"},
        )

    router = HttpRouter()
    router.add_route("GET", "/orders/{orderId}", handler, operation_id="getOrder")

    sent = _run_asgi_http(
        build_asgi_app(router),
        {
            "type": "http",
            "method": "get",
            "path": "/orders/order-asgi-1",
            "query_string": b"filter=awaiting_signature",
            "headers": [
                (b"x-request-id", b"req-asgi-get"),
                (b"x-user-role", b"ADMIN"),
            ],
        },
    )

    assert len(captured) == 1
    request = captured[0]
    assert request.method == "GET"
    assert request.path == "/orders/order-asgi-1"
    assert request.request_id == "req-asgi-get"
    assert request.headers["X-Request-Id"] == "req-asgi-get"
    assert request.headers["X-User-Role"] == "ADMIN"
    assert request.query == {"orderId": "order-asgi-1", "filter": "awaiting_signature"}
    assert request.body is None

    assert sent == [
        {
            "type": "http.response.start",
            "status": 202,
            "headers": [
                (b"Content-Type", b"application/json"),
                (b"Cache-Control", b"no-store"),
                (b"Content-Length", str(len(_body(sent))).encode("ascii")),
                (b"X-Request-Id", b"req-asgi-get"),
            ],
        },
        {
            "type": "http.response.body",
            "body": _body(sent),
            "more_body": False,
        },
    ]
    assert json.loads(_body(sent)) == {
        "body": None,
        "filter": "awaiting_signature",
        "orderId": "order-asgi-1",
        "requestId": "req-asgi-get",
    }


def test_asgi_app_collects_json_post_body_and_preserves_response_header_contract() -> None:
    from token_payments.api import ApiRequest, HttpRouter, build_asgi_app, json_response

    captured: list[ApiRequest] = []

    def handler(request: ApiRequest):
        captured.append(request)
        return json_response(
            {
                "received": request.body,
                "contentType": request.headers["Content-Type"],
                "paymentId": request.query["paymentId"],
            },
            status_code=201,
            request_id=request.request_id,
            headers={"X-Correlation-Id": "corr-asgi-1"},
        )

    router = HttpRouter()
    router.add_route("POST", "/payments/{paymentId}/transaction-hashes", handler, operation_id="submitTxHash")
    body = b'{"confirmations":1,"txHash":"0xabc"}'

    sent = _run_asgi_http(
        build_asgi_app(router),
        {
            "type": "http",
            "method": "POST",
            "path": "/payments/pay-asgi-1/transaction-hashes",
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"x-request-id", b"req-asgi-post"),
            ],
        },
        receive_events=[
            {"type": "http.request", "body": body[:18], "more_body": True},
            {"type": "http.request", "body": body[18:], "more_body": False},
        ],
    )

    assert captured[0].body == {"confirmations": 1, "txHash": "0xabc"}
    assert captured[0].headers["Content-Type"] == "application/json; charset=utf-8"
    assert _headers(sent)["X-Correlation-Id"] == "corr-asgi-1"
    assert _headers(sent)["X-Request-Id"] == "req-asgi-post"
    assert _headers(sent)["Content-Length"] == str(len(_body(sent)))
    assert _body(sent) == (
        b'{"contentType":"application/json; charset=utf-8",'
        b'"paymentId":"pay-asgi-1","received":{"confirmations":1,"txHash":"0xabc"}}'
    )


def test_asgi_app_serializes_router_errors_for_missing_route_method_mismatch_and_bad_json() -> None:
    from token_payments.api import HttpRouter, build_asgi_app, json_response

    router = HttpRouter()
    router.add_route("GET", "/orders/{orderId}", lambda request: json_response({"ok": True}, request_id=request.request_id))
    app = build_asgi_app(router)

    missing = _run_asgi_http(
        app,
        {
            "type": "http",
            "method": "GET",
            "path": "/missing",
            "query_string": b"",
            "headers": [(b"x-request-id", b"req-missing")],
        },
    )
    mismatch = _run_asgi_http(
        app,
        {
            "type": "http",
            "method": "POST",
            "path": "/orders/order-asgi-1",
            "query_string": b"",
            "headers": [(b"x-request-id", b"req-mismatch")],
        },
    )
    bad_json = _run_asgi_http(
        app,
        {
            "type": "http",
            "method": "GET",
            "path": "/orders/order-asgi-1",
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-request-id", b"req-bad-json"),
            ],
        },
        receive_events=[{"type": "http.request", "body": b'{"bad":', "more_body": False}],
    )

    assert _start(missing)["status"] == 404
    assert json.loads(_body(missing))["error"]["code"] == "ROUTE_NOT_FOUND"
    assert _headers(missing)["X-Request-Id"] == "req-missing"

    assert _start(mismatch)["status"] == 405
    assert _headers(mismatch)["Allow"] == "GET"
    assert json.loads(_body(mismatch))["error"]["code"] == "METHOD_NOT_ALLOWED"

    assert _start(bad_json)["status"] == 400
    assert json.loads(_body(bad_json)) == {
        "error": {
            "code": "MALFORMED_JSON",
            "message": "Request body must be valid JSON.",
        }
    }


def test_asgi_app_handles_lifespan_and_websocket_scopes_without_long_running_loop() -> None:
    from token_payments.api import HttpRouter, build_asgi_app

    app = build_asgi_app(HttpRouter())

    lifespan_sent = _run_asgi(
        app,
        {"type": "lifespan"},
        [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}],
    )
    websocket_sent = _run_asgi(
        app,
        {"type": "websocket", "path": "/ws", "headers": []},
        [{"type": "websocket.connect"}],
    )

    assert lifespan_sent == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]
    assert websocket_sent == [
        {
            "type": "websocket.close",
            "code": 1003,
            "reason": "Unsupported ASGI scope type: websocket",
        }
    ]


def test_asgi_adapter_foundation_imports_only_framework_neutral_dependencies() -> None:
    imports = _imported_modules(ROOT / "app/token_payments/api/asgi.py")
    forbidden = {
        "fastapi",
        "starlette",
        "uvicorn",
        "requests",
        "httpx",
        "psycopg",
        "psycopg2",
        "kafka",
        "confluent_kafka",
        "web3",
        "docker",
    }

    assert imports.isdisjoint(forbidden)
    assert all(not module.startswith("token_payments.contexts") for module in imports)


def _run_asgi_http(
    app: Any,
    scope: dict[str, Any],
    *,
    receive_events: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return _run_asgi(app, scope, receive_events or [{"type": "http.request", "body": b"", "more_body": False}])


def _run_asgi(
    app: Any,
    scope: dict[str, Any],
    receive_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    pending = list(receive_events)

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


def _headers(sent: list[dict[str, Any]]) -> dict[str, str]:
    return {key.decode("ascii"): value.decode("ascii") for key, value in _start(sent)["headers"]}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules

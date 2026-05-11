from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_http_router_converts_http_request_to_api_request_and_merges_path_params() -> None:
    from token_payments.api import ApiRequest, HttpRouter, json_response

    captured: list[ApiRequest] = []

    def handler(request: ApiRequest):
        captured.append(request)
        return json_response(
            {"paymentId": request.query["paymentId"], "filter": request.query["filter"], "body": request.body},
            status_code=202,
            request_id=request.request_id,
            headers={"Cache-Control": "no-store"},
        )

    router = HttpRouter()
    router.add_route("POST", "/payments/{paymentId}/transaction-hashes", handler, operation_id="submitTxHash")

    response = router.handle(
        "post",
        "/payments/pay-path/transaction-hashes",
        query="paymentId=pay-query&filter=active",
        headers={"Content-Type": "application/json; charset=utf-8", "X-Request-Id": "req-http-1"},
        body=b'{"txHash":"0xabc","confirmations":1}',
    )

    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.path == "/payments/pay-path/transaction-hashes"
    assert request.request_id == "req-http-1"
    assert request.headers["Content-Type"] == "application/json; charset=utf-8"
    assert request.query == {"paymentId": "pay-query", "filter": "active"}
    assert request.body == {"txHash": "0xabc", "confirmations": 1}

    assert response.status_code == 202
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-Id"] == "req-http-1"
    assert response.headers["Content-Length"] == str(len(response.body))
    assert json.loads(response.body) == {
        "body": {"confirmations": 1, "txHash": "0xabc"},
        "filter": "active",
        "paymentId": "pay-query",
    }


def test_http_router_decodes_json_only_for_application_json_and_preserves_empty_body() -> None:
    from token_payments.api import ApiRequest, HttpRouter, json_response

    captured: list[ApiRequest] = []

    def handler(request: ApiRequest):
        captured.append(request)
        return json_response({"body": request.body}, request_id=request.request_id)

    router = HttpRouter()
    router.add_route("POST", "/echo", handler)

    object_response = router.handle(
        "POST",
        "/echo",
        headers={"Content-Type": "application/json"},
        body=b'{"enabled":true}',
    )
    array_response = router.handle("POST", "/echo", headers={"Content-Type": "application/json"}, body=b"[1,2]")
    scalar_response = router.handle("POST", "/echo", headers={"Content-Type": "application/json"}, body=b"42")
    text_response = router.handle("POST", "/echo", headers={"Content-Type": "text/plain"}, body=b'{"not":"json"}')
    empty_response = router.handle("POST", "/echo", headers={"Content-Type": "application/json"}, body=b"")

    assert [request.body for request in captured] == [
        {"enabled": True},
        [1, 2],
        42,
        '{"not":"json"}',
        None,
    ]
    assert json.loads(object_response.body)["body"] == {"enabled": True}
    assert json.loads(array_response.body)["body"] == [1, 2]
    assert json.loads(scalar_response.body)["body"] == 42
    assert json.loads(text_response.body)["body"] == '{"not":"json"}'
    assert json.loads(empty_response.body)["body"] is None


def test_malformed_json_returns_400_without_calling_facade_handler() -> None:
    from token_payments.api import HttpRouter, json_response

    calls: list[str] = []

    def handler(request):
        calls.append(request.request_id)
        return json_response({"ok": True}, request_id=request.request_id)

    router = HttpRouter()
    router.add_route("POST", "/payments", handler)

    response = router.handle(
        "POST",
        "/payments",
        headers={"Content-Type": "application/json", "X-Request-Id": "req-bad-json"},
        body=b'{"amount":',
    )

    assert calls == []
    assert response.status_code == 400
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["X-Request-Id"] == "req-bad-json"
    assert response.headers["Content-Length"] == str(len(response.body))
    assert json.loads(response.body) == {
        "error": {
            "code": "MALFORMED_JSON",
            "message": "Request body must be valid JSON.",
        }
    }


def test_route_miss_method_mismatch_and_generated_request_id_are_stable() -> None:
    from token_payments.api import HttpRouter, json_response

    router = HttpRouter()
    router.add_route("GET", "/orders/{orderId}", lambda request: json_response({"ok": True}, request_id=request.request_id))

    miss = router.handle("GET", "/missing", query="a=1", body=b"")
    repeat_miss = router.handle("GET", "/missing", query="a=1", body=b"")
    mismatch = router.handle("POST", "/orders/order-1", headers={})

    assert miss.status_code == 404
    assert json.loads(miss.body)["error"]["code"] == "ROUTE_NOT_FOUND"
    assert miss.headers["X-Request-Id"].startswith("req-")
    assert repeat_miss.headers["X-Request-Id"] == miss.headers["X-Request-Id"]

    assert mismatch.status_code == 405
    assert mismatch.headers["Allow"] == "GET"
    assert json.loads(mismatch.body)["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_http_response_serializes_api_response_with_stable_headers_and_body_bytes() -> None:
    from token_payments.api import HttpResponse, json_response

    api_response = json_response(
        {"status": "AWAITING_SIGNATURE", "amount": "1.25"},
        status_code=201,
        request_id="req-serialize",
        headers={"content-type": "application/json", "X-Correlation-Id": "corr-1"},
    )

    response = HttpResponse.from_api_response(api_response)

    assert response.status_code == 201
    assert response.headers == {
        "Content-Type": "application/json",
        "X-Correlation-Id": "corr-1",
        "Content-Length": str(len(response.body)),
        "X-Request-Id": "req-serialize",
    }
    assert isinstance(response.body, bytes)
    assert response.body == b'{"amount":"1.25","status":"AWAITING_SIGNATURE"}'


def test_http_adapter_foundation_is_public_and_framework_neutral() -> None:
    import token_payments.api as api

    expected = {"HttpRequest", "HttpResponse", "HttpRoute", "HttpRouter"}
    assert expected <= set(api.__all__)
    assert all(hasattr(api, name) for name in expected)

    imports = _imported_modules(ROOT / "app/token_payments/api/http.py")
    assert "fastapi" not in imports
    assert "flask" not in imports
    assert "django" not in imports
    assert "token_payments.contexts" not in imports
    assert all(not module.startswith("token_payments.contexts") for module in imports)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules

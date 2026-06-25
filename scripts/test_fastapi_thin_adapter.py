from __future__ import annotations

import ast
import asyncio
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

FASTAPI_ADAPTER_EXPORTS = {
    "FastApiAdapterUnavailable",
    "build_fastapi_app",
    "is_fastapi_available",
}

FORBIDDEN_FRAMEWORK_ROOTS = {"fastapi", "starlette", "uvicorn"}


def test_fastapi_thin_adapter_public_exports_are_available_from_api_package() -> None:
    import token_payments.api as api

    assert FASTAPI_ADAPTER_EXPORTS <= set(api.__all__)
    assert all(hasattr(api, name) for name in FASTAPI_ADAPTER_EXPORTS)


def test_fastapi_adapter_modules_import_without_requiring_fastapi_dependency() -> None:
    assert importlib.import_module("token_payments.api.fastapi") is not None
    assert importlib.import_module("token_payments.api") is not None


def test_fastapi_unavailable_contract_is_domain_specific_and_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    from token_payments.api import FastApiAdapterUnavailable, HttpRouter, build_fastapi_app
    import token_payments.api.fastapi as fastapi_adapter

    real_import_module = fastapi_adapter.importlib.import_module
    real_find_spec = fastapi_adapter.importlib.util.find_spec

    def fake_import_module(name: str, package: str | None = None) -> Any:
        if name == "fastapi":
            raise ModuleNotFoundError("No module named 'fastapi'")
        return real_import_module(name, package)

    def fake_find_spec(name: str, package: str | None = None) -> Any:
        if name == "fastapi":
            return None
        return real_find_spec(name, package)

    monkeypatch.setattr(fastapi_adapter.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(fastapi_adapter.importlib.util, "find_spec", fake_find_spec)

    assert fastapi_adapter.is_fastapi_available() is False
    with pytest.raises(FastApiAdapterUnavailable) as exc_info:
        build_fastapi_app(HttpRouter())

    message = str(exc_info.value)
    assert "FastAPI adapter is unavailable" in message
    assert "optional" in message
    assert "pip install fastapi" in message


def test_fastapi_route_metadata_matches_existing_http_route_manifest_when_dependency_is_available() -> None:
    import token_payments.api.fastapi as fastapi_adapter
    from token_payments.api import ApiRequest, HttpRouter, http_route_manifest, json_response

    if not fastapi_adapter.is_fastapi_available():
        pytest.skip("FastAPI is optional and is not installed in this environment")

    router = HttpRouter()

    def handler(request: ApiRequest):
        return json_response({"operationId": request.query.get("operationId")}, request_id=request.request_id)

    manifest = list(http_route_manifest())
    for entry in manifest:
        router.add_route(
            entry["method"],
            entry["path"],
            handler,
            operation_id=entry["operationId"],
        )

    app = fastapi_adapter.build_fastapi_app(router, title="Token Payments", version="test")
    expected = {entry["operationId"]: entry for entry in manifest}
    actual: dict[str, dict[str, str]] = {}
    for route in app.routes:
        operation_id = getattr(route, "operation_id", None)
        if operation_id not in expected:
            continue
        actual[operation_id] = {
            "method": expected[operation_id]["method"],
            "path": getattr(route, "path"),
            "operationId": operation_id,
        }
        assert expected[operation_id]["method"] in getattr(route, "methods")

    assert len(actual) == 59
    assert actual == expected

    openapi = app.openapi()
    for entry in manifest:
        operation = openapi["paths"][entry["path"]][entry["method"].lower()]
        assert operation["operationId"] == entry["operationId"]


def test_fastapi_app_delegates_http_request_and_response_through_http_router() -> None:
    import token_payments.api.fastapi as fastapi_adapter
    from token_payments.api import ApiRequest, HttpRouter, json_response

    if not fastapi_adapter.is_fastapi_available():
        pytest.skip("FastAPI is optional and is not installed in this environment")

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
            headers={"X-Correlation-Id": "corr-fastapi-1"},
        )

    router = HttpRouter()
    router.add_route("POST", "/orders/{orderId}", handler, operation_id="createOrder")
    app = fastapi_adapter.build_fastapi_app(router)

    sent = _run_fastapi_asgi_http(
        app,
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/orders/order-fastapi-1",
            "raw_path": b"/orders/order-fastapi-1",
            "query_string": b"filter=awaiting_signature",
            "headers": [
                (b"content-type", b"application/json"),
                (b"x-request-id", b"req-fastapi-post"),
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        },
        [{"type": "http.request", "body": b'{"quantity":2}', "more_body": False}],
    )

    assert captured[0].method == "POST"
    assert captured[0].path == "/orders/order-fastapi-1"
    assert captured[0].query == {"orderId": "order-fastapi-1", "filter": "awaiting_signature"}
    assert captured[0].body == {"quantity": 2}
    assert _headers(sent)["X-Correlation-Id"] == "corr-fastapi-1"
    assert _headers(sent)["X-Request-Id"] == "req-fastapi-post"
    assert json.loads(_body(sent)) == {
        "body": {"quantity": 2},
        "filter": "awaiting_signature",
        "orderId": "order-fastapi-1",
        "requestId": "req-fastapi-post",
    }


def test_fastapi_adapter_source_uses_existing_router_boundary_without_facade_duplication() -> None:
    path = ROOT / "app/token_payments/api/fastapi.py"
    source = path.read_text(encoding="utf-8")
    imports = _imported_modules(path)

    assert "token_payments.api.auth" not in imports
    assert "token_payments.api.orders" not in imports
    assert "token_payments.api.checkout" not in imports
    assert "token_payments.api.payments" not in imports
    assert "token_payments.api.operator" not in imports
    assert "token_payments.api.operator_actions" not in imports
    assert "HttpRouter" in source
    assert "AuthApi" not in source
    assert "OrdersApi" not in source
    assert "CheckoutApi" not in source
    assert "PaymentsApi" not in source
    assert "OperatorApi" not in source


def test_fastapi_starlette_uvicorn_imports_are_confined_to_optional_adapter_module() -> None:
    violations: dict[str, list[str]] = {}
    allowed_path = ROOT / "app/token_payments/api/fastapi.py"
    scanned_roots = (
        ROOT / "app/token_payments/api",
        ROOT / "app/token_payments/contexts",
        ROOT / "app/token_payments/runtime",
    )

    for root in scanned_roots:
        for path in sorted(root.rglob("*.py")):
            if path == allowed_path:
                continue
            illegal = sorted(
                module
                for module in _external_imported_modules(path)
                if module.split(".", 1)[0] in FORBIDDEN_FRAMEWORK_ROOTS
            )
            if illegal:
                violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _external_imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _run_fastapi_asgi_http(
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


def _body(sent: list[dict[str, Any]]) -> bytes:
    return sent[1]["body"]


def _headers(sent: list[dict[str, Any]]) -> dict[str, str]:
    return {key.decode("ascii").title(): value.decode("ascii") for key, value in sent[0]["headers"]}

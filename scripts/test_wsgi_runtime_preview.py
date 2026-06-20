from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_wsgi_app_adapts_environ_to_http_router_and_returns_wsgi_response() -> None:
    from token_payments.api import ApiRequest, HttpRouter, build_wsgi_app, json_response

    captured: list[ApiRequest] = []

    def handler(request: ApiRequest):
        captured.append(request)
        return json_response(
            {
                "body": request.body,
                "orderId": request.query["orderId"],
                "include": request.query["include"],
                "requestId": request.request_id,
            },
            status_code=201,
            request_id=request.request_id,
            headers={"Cache-Control": "no-store"},
        )

    router = HttpRouter()
    router.add_route("POST", "/orders/{orderId}", handler, operation_id="createOrder")
    app = build_wsgi_app(router)
    body = b'{"storeId":"store-1","items":[{"sku":"sku-1","quantity":2}]}'
    captured_start: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None) -> None:
        captured_start["status"] = status
        captured_start["headers"] = dict(headers)
        captured_start["exc_info"] = exc_info

    response_chunks = list(
        app(
            {
                "REQUEST_METHOD": "post",
                "PATH_INFO": "/orders/order-wsgi-1",
                "QUERY_STRING": "include=items",
                "CONTENT_TYPE": "application/json; charset=utf-8",
                "CONTENT_LENGTH": str(len(body)),
                "HTTP_X_REQUEST_ID": "req-wsgi-1",
                "HTTP_X_USER_ROLE": "ADMIN",
                "wsgi.input": io.BytesIO(body),
            },
            start_response,
        )
    )

    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.path == "/orders/order-wsgi-1"
    assert request.request_id == "req-wsgi-1"
    assert request.headers["Content-Type"] == "application/json; charset=utf-8"
    assert request.headers["X-Request-Id"] == "req-wsgi-1"
    assert request.headers["X-User-Role"] == "ADMIN"
    assert request.query == {"orderId": "order-wsgi-1", "include": "items"}
    assert request.body == {"storeId": "store-1", "items": [{"sku": "sku-1", "quantity": 2}]}

    assert captured_start["status"] == "201 Created"
    assert captured_start["headers"]["Content-Type"] == "application/json"
    assert captured_start["headers"]["Cache-Control"] == "no-store"
    assert captured_start["headers"]["X-Request-Id"] == "req-wsgi-1"
    assert captured_start["headers"]["Content-Length"] == str(len(b"".join(response_chunks)))
    assert json.loads(b"".join(response_chunks)) == {
        "body": {"items": [{"quantity": 2, "sku": "sku-1"}], "storeId": "store-1"},
        "include": "items",
        "orderId": "order-wsgi-1",
        "requestId": "req-wsgi-1",
    }


def test_wsgi_app_handles_missing_wsgi_input_and_route_errors_without_server_framework() -> None:
    from token_payments.api import HttpRouter, build_wsgi_app

    router = HttpRouter()
    app = build_wsgi_app(router)
    started: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None) -> None:
        started["status"] = status
        started["headers"] = dict(headers)

    body = b"".join(
        app(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/missing",
                "QUERY_STRING": "",
            },
            start_response,
        )
    )

    assert started["status"] == "404 Not Found"
    assert started["headers"]["Content-Type"] == "application/json"
    assert json.loads(body)["error"]["code"] == "ROUTE_NOT_FOUND"


def test_http_route_manifest_is_complete_and_deterministically_ordered() -> None:
    from token_payments.api import http_route_manifest, list_http_route_specs

    manifest = list(http_route_manifest())
    specs = list(list_http_route_specs())

    assert [entry["operationId"] for entry in manifest] == [
        "requestLoginChallenge",
        "loginWithMetaMask",
        "requestOAuthAuthorization",
        "completeOAuthSession",
        "linkOAuthIdentity",
        "listOAuthIdentities",
        "revokeOAuthIdentity",
        "requestWalletLinkChallenge",
        "linkWallet",
        "listWallets",
        "setPrimaryWallet",
        "revokeWallet",
        "refreshSession",
        "logout",
        "getCurrentUser",
        "getCurrentUserProfile",
        "updateCurrentUserProfile",
        "createOrder",
        "getCheckoutTrackingByTrackingId",
        "getCheckoutTrackingByOrderId",
        "listUserPayments",
        "submitTransactionHash",
        "cancelPayment",
        "listPublicStores",
        "listAllPublicProducts",
        "getStoreProfile",
        "listPublicProducts",
        "getPublicProduct",
        "listMerchantStores",
        "updateStoreProfile",
        "createOrReuseStoreUser",
        "createStore",
        "grantStoreMembership",
        "listMerchantProducts",
        "getMerchantProduct",
        "registerStoreProduct",
        "updateStoreProduct",
        "listStoreOwnerInventory",
        "increaseStoreOwnerInventoryStock",
        "correctStoreOwnerInventoryStock",
        "pauseStoreOwnerInventorySales",
        "resumeStoreOwnerInventorySales",
        "listMerchantStoreMembers",
        "listMerchantStoreInvitations",
        "createMerchantStoreInvitation",
        "acceptMerchantInvitation",
        "revokeMerchantInvitation",
        "updateMerchantStoreMemberRole",
        "removeMerchantStoreMember",
        "getMerchantRoleCatalog",
        "getOperatorDashboard",
        "getOperatorOrderDetail",
        "getOperatorPaymentDetail",
        "getOperatorOutboxDetail",
        "cancelOperatorOrder",
        "retryOperatorOutboxMessage",
        "replayOperatorMessage",
    ]
    assert [(entry["method"], entry["path"]) for entry in manifest] == [
        (spec.method, spec.path) for spec in specs
    ]


def test_api_and_serve_api_cli_return_bounded_route_manifest_without_starting_server() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")

    for command in ("api", "serve-api"):
        result = subprocess.run(
            [sys.executable, "-m", "token_payments", command],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )

        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["command"] == command
        assert payload["status"] == "SUCCEEDED"
        assert "server was not started" in payload["summary"]
        assert payload["details"]["http"]["longRunning"] is False
        assert payload["details"]["http"]["wsgiFactory"] == "token_payments.api.build_wsgi_app"
        assert payload["details"]["http"]["routeCount"] == 57
        assert payload["details"]["http"]["routes"][0] == {
            "method": "POST",
            "path": "/auth/challenges",
            "operationId": "requestLoginChallenge",
        }

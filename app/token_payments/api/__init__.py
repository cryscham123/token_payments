"""Framework-neutral API DTOs and response helpers."""

from importlib import import_module as _import_module

from .auth import AuthApi
from .asgi import AsgiApplication, AsgiReceive, AsgiScope, AsgiSend, build_asgi_app
from .checkout import CheckoutApi
from .contracts import ApiRequest, ApiResponse, JsonValue, json_response
from .http import (
    AUTH_HTTP_ROUTES,
    CHECKOUT_HTTP_ROUTES,
    ORDER_HTTP_ROUTES,
    OPERATOR_ACTION_HTTP_ROUTES,
    OPERATOR_HTTP_ROUTES,
    PAYMENT_HTTP_ROUTES,
    HttpHandler,
    HttpRequest,
    HttpResponse,
    HttpRoute,
    HttpRouteSpec,
    HttpRouter,
    WsgiApplication,
    WsgiStartResponse,
    build_wsgi_app,
    describe_http_routes,
    http_route_manifest,
    list_http_route_specs,
    register_auth_routes,
    register_checkout_routes,
    register_order_routes,
    register_operator_action_routes,
    register_operator_routes,
    register_payment_routes,
)
from .operator import AdminRoleOperatorPolicy, OperatorAccessPolicy, OperatorApi, OperatorClaims
from .operator_actions import (
    AdminRoleOperatorActionPolicy,
    CancelOrderCommandHandler,
    OperatorActionApi,
    OperatorActionAuditRepository,
    OperatorActionAuditRecord,
    OperatorActionCommand,
    OperatorActionName,
    OperatorActionPolicy,
    OperatorActionResult,
    OperatorActionResultStatus,
    OperatorActionTarget,
    OperatorActionTargetKind,
    OperatorCancelOrderActionExecutor,
    OperatorMessageReplayPort,
    OperatorMessageReplayRequest,
    OperatorOutboxActionExecutor,
    OperatorOutboxActionPortResult,
    OperatorOutboxActionStatus,
    OperatorOutboxRetryPort,
    OperatorOutboxRetryRequest,
)
from .orders import OrdersApi
from .payments import PaymentsApi

_FASTAPI_ADAPTER_EXPORTS = frozenset(
    {
        "FastApiAdapterUnavailable",
        "build_fastapi_app",
        "is_fastapi_available",
    }
)

__all__ = [
    "AdminRoleOperatorActionPolicy",
    "AdminRoleOperatorPolicy",
    "AUTH_HTTP_ROUTES",
    "AuthApi",
    "ApiRequest",
    "ApiResponse",
    "AsgiApplication",
    "AsgiReceive",
    "AsgiScope",
    "AsgiSend",
    "CHECKOUT_HTTP_ROUTES",
    "CheckoutApi",
    "CancelOrderCommandHandler",
    "FastApiAdapterUnavailable",
    "HttpHandler",
    "HttpRequest",
    "HttpResponse",
    "HttpRoute",
    "HttpRouteSpec",
    "HttpRouter",
    "JsonValue",
    "ORDER_HTTP_ROUTES",
    "OPERATOR_ACTION_HTTP_ROUTES",
    "OPERATOR_HTTP_ROUTES",
    "OperatorAccessPolicy",
    "OperatorActionApi",
    "OperatorActionAuditRepository",
    "OperatorActionAuditRecord",
    "OperatorActionCommand",
    "OperatorActionName",
    "OperatorActionPolicy",
    "OperatorActionResult",
    "OperatorActionResultStatus",
    "OperatorActionTarget",
    "OperatorActionTargetKind",
    "OperatorApi",
    "OperatorClaims",
    "OperatorCancelOrderActionExecutor",
    "OperatorMessageReplayPort",
    "OperatorMessageReplayRequest",
    "OperatorOutboxActionExecutor",
    "OperatorOutboxActionPortResult",
    "OperatorOutboxActionStatus",
    "OperatorOutboxRetryPort",
    "OperatorOutboxRetryRequest",
    "OrdersApi",
    "PAYMENT_HTTP_ROUTES",
    "PaymentsApi",
    "WsgiApplication",
    "WsgiStartResponse",
    "build_asgi_app",
    "build_fastapi_app",
    "build_wsgi_app",
    "describe_http_routes",
    "http_route_manifest",
    "is_fastapi_available",
    "json_response",
    "list_http_route_specs",
    "register_auth_routes",
    "register_checkout_routes",
    "register_order_routes",
    "register_operator_action_routes",
    "register_operator_routes",
    "register_payment_routes",
]


def __getattr__(name: str):
    if name in _FASTAPI_ADAPTER_EXPORTS:
        value = getattr(_import_module("token_payments.api.fastapi"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

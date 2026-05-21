"""Framework-neutral HTTP adapter contracts for API facades."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from http import HTTPStatus
import json
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote

from .contracts import ApiAuthContext, ApiRequest, ApiResponse, json_response


HttpHandler = Callable[[ApiRequest], ApiResponse]
WsgiStartResponse = Callable[[str, list[tuple[str, str]], object | None], object]
WsgiApplication = Callable[[Mapping[str, Any], WsgiStartResponse], Iterable[bytes]]


@dataclass(frozen=True)
class HttpRequest:
    """Raw HTTP boundary input independent of a server framework."""

    method: str
    path: str
    query: str | bytes | Mapping[str, Any] | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    received_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", _require_text(self.method, "HttpRequest.method").upper())
        path = _require_text(self.path, "HttpRequest.path")
        if not path.startswith("/"):
            raise ValueError("HttpRequest.path must start with /")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "headers", MappingProxyType(_string_mapping(self.headers, "HttpRequest.headers")))
        if self.body is None:
            object.__setattr__(self, "body", b"")
        elif isinstance(self.body, bytearray):
            object.__setattr__(self, "body", bytes(self.body))
        elif not isinstance(self.body, bytes):
            raise ValueError("HttpRequest.body must be bytes")


AuthContextFactory = Callable[[HttpRequest], ApiAuthContext | None]


@dataclass(frozen=True)
class HttpResponse:
    """Serialized HTTP response that can be returned by any framework adapter."""

    status_code: int
    headers: Mapping[str, str]
    body: bytes
    multi_headers: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.status_code, bool) or not isinstance(self.status_code, int):
            raise ValueError("HttpResponse.status_code must be an integer")
        if self.status_code < 100 or self.status_code > 599:
            raise ValueError("HttpResponse.status_code must be between 100 and 599")
        object.__setattr__(self, "headers", MappingProxyType(_string_mapping(self.headers, "HttpResponse.headers")))
        object.__setattr__(self, "multi_headers", _header_pairs(self.multi_headers, "HttpResponse.multi_headers"))
        if isinstance(self.body, bytearray):
            object.__setattr__(self, "body", bytes(self.body))
        elif not isinstance(self.body, bytes):
            raise ValueError("HttpResponse.body must be bytes")

    @classmethod
    def from_api_response(cls, response: ApiResponse) -> "HttpResponse":
        body = json.dumps(response.body, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        headers = _response_headers(response.headers, request_id=response.request_id, content_length=len(body))
        return cls(status_code=response.status_code, headers=headers, body=body, multi_headers=response.multi_headers)

    def header_items(self) -> tuple[tuple[str, str], ...]:
        return (*self.headers.items(), *self.multi_headers)


@dataclass(frozen=True)
class HttpRoute:
    """Route template and facade handler pair."""

    method: str
    path_template: str
    handler: HttpHandler
    operation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", _require_text(self.method, "HttpRoute.method").upper())
        template = _require_text(self.path_template, "HttpRoute.path_template")
        if not template.startswith("/"):
            raise ValueError("HttpRoute.path_template must start with /")
        _validate_template_segments(template)
        if not callable(self.handler):
            raise ValueError("HttpRoute.handler must be callable")
        if self.operation_id is not None:
            object.__setattr__(self, "operation_id", _require_text(self.operation_id, "HttpRoute.operation_id"))
        object.__setattr__(self, "path_template", template)

    def match_path(self, path: str) -> dict[str, str] | None:
        if not isinstance(path, str) or not path.startswith("/"):
            return None

        template_segments = _path_segments(self.path_template)
        path_segments = _path_segments(path)
        if len(template_segments) != len(path_segments):
            return None

        params: dict[str, str] = {}
        for template_segment, path_segment in zip(template_segments, path_segments, strict=True):
            if _is_param_segment(template_segment):
                params[template_segment[1:-1]] = unquote(path_segment)
            elif template_segment != path_segment:
                return None
        return params


@dataclass(frozen=True)
class HttpRouteSpec:
    """Stable public route contract used by framework adapters and docs."""

    method: str
    path: str
    operation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", _require_text(self.method, "HttpRouteSpec.method").upper())
        path = _require_text(self.path, "HttpRouteSpec.path")
        if not path.startswith("/"):
            raise ValueError("HttpRouteSpec.path must start with /")
        _validate_template_segments(path)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "operation_id", _require_text(self.operation_id, "HttpRouteSpec.operation_id"))


class HttpRouter:
    """Small route dispatcher for framework-neutral API facades."""

    def __init__(
        self,
        routes: Iterable[HttpRoute] = (),
        *,
        request_id_factory: Callable[[HttpRequest], str] | None = None,
        auth_context_factory: AuthContextFactory | None = None,
        allow_dev_auth_headers: bool = True,
        request_guard: Any | None = None,
    ) -> None:
        self._routes: list[HttpRoute] = list(routes)
        self._request_id_factory = request_id_factory or _default_request_id
        self._auth_context_factory = auth_context_factory
        self._allow_dev_auth_headers = _require_bool(allow_dev_auth_headers, "HttpRouter.allow_dev_auth_headers")
        self._request_guard = request_guard

    @property
    def routes(self) -> tuple[HttpRoute, ...]:
        return tuple(self._routes)

    def add_route(
        self,
        method: str,
        path_template: str,
        handler: HttpHandler,
        *,
        operation_id: str | None = None,
    ) -> HttpRoute:
        route = HttpRoute(method=method, path_template=path_template, handler=handler, operation_id=operation_id)
        self._routes.append(route)
        return route

    def route(
        self,
        method: str,
        path_template: str,
        *,
        operation_id: str | None = None,
    ) -> Callable[[HttpHandler], HttpHandler]:
        def decorator(handler: HttpHandler) -> HttpHandler:
            self.add_route(method, path_template, handler, operation_id=operation_id)
            return handler

        return decorator

    def handle(
        self,
        method_or_request: str | HttpRequest,
        path: str | None = None,
        *,
        query: str | bytes | Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
        received_at: datetime | None = None,
    ) -> HttpResponse:
        request = (
            method_or_request
            if isinstance(method_or_request, HttpRequest)
            else HttpRequest(
                method=method_or_request,
                path=_require_text(path, "HttpRouter.handle.path"),
                query=query,
                headers=headers or {},
                body=body,
                received_at=received_at,
            )
        )
        request_id = _request_id(request, self._request_id_factory)
        guard_response = self._guard_response(request, request_id)
        if guard_response is not None:
            return self._with_guard_headers(request, guard_response)

        path_matches: list[tuple[HttpRoute, dict[str, str]]] = []
        for route in self._routes:
            params = route.match_path(request.path)
            if params is not None:
                path_matches.append((route, params))
                if route.method == request.method:
                    return self._with_guard_headers(request, self._handle_route(route, params, request, request_id))

        if path_matches:
            allowed = ", ".join(sorted({route.method for route, _params in path_matches}))
            return self._with_guard_headers(
                request,
                _error_response(
                    status_code=405,
                    code="METHOD_NOT_ALLOWED",
                    message=f"Method {request.method} is not allowed for {request.path}.",
                    request_id=request_id,
                    headers={"Allow": allowed},
                ),
            )

        return self._with_guard_headers(
            request,
            _error_response(
                status_code=404,
                code="ROUTE_NOT_FOUND",
                message=f"No route matches {request.path}.",
                request_id=request_id,
            ),
        )

    def _guard_response(self, request: HttpRequest, request_id: str) -> HttpResponse | None:
        if self._request_guard is None:
            return None
        guard = getattr(self._request_guard, "guard", None)
        if not callable(guard):
            raise ValueError("HttpRouter.request_guard must expose guard(request, request_id=...)")
        response = guard(request, request_id=request_id)
        if response is None:
            return None
        if isinstance(response, HttpResponse):
            return response
        if isinstance(response, ApiResponse):
            return HttpResponse.from_api_response(response)
        if all(hasattr(response, attr) for attr in ("status_code", "body", "headers", "request_id")):
            return HttpResponse.from_api_response(
                ApiResponse(
                    status_code=response.status_code,
                    body=response.body,
                    headers=response.headers,
                    multi_headers=getattr(response, "multi_headers", ()),
                    request_id=response.request_id,
                )
            )
        raise ValueError("request guard must return ApiResponse, HttpResponse, or None")

    def _with_guard_headers(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        if self._request_guard is None:
            return response
        response_headers = getattr(self._request_guard, "response_headers", None)
        if not callable(response_headers):
            return response
        extra = _string_mapping(response_headers(request), "request guard response headers")
        if not extra:
            return response
        headers = dict(response.headers)
        headers.update(extra)
        return HttpResponse(
            status_code=response.status_code,
            headers=headers,
            body=response.body,
            multi_headers=response.multi_headers,
        )

    def _handle_route(
        self,
        route: HttpRoute,
        path_params: Mapping[str, str],
        request: HttpRequest,
        request_id: str,
    ) -> HttpResponse:
        decoded_body = _decode_body(request)
        if isinstance(decoded_body, _MalformedJson):
            return _error_response(
                status_code=400,
                code="MALFORMED_JSON",
                message="Request body must be valid JSON.",
                request_id=request_id,
            )

        query = dict(path_params)
        query.update(_query_mapping(request.query))
        try:
            auth_context = self._auth_context(request, request_id)
        except _AuthenticationRejected as exc:
            return _error_response(
                status_code=401,
                code="INVALID_AUTH_TOKEN",
                message=str(exc),
                request_id=exc.request_id,
            )

        api_kwargs: dict[str, Any] = {
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "headers": request.headers,
            "query": query,
            "body": decoded_body,
            "auth_context": auth_context,
            "local_auth_fallback_enabled": self._allow_dev_auth_headers,
        }
        if request.received_at is not None:
            api_kwargs["received_at"] = request.received_at

        return HttpResponse.from_api_response(route.handler(ApiRequest(**api_kwargs)))

    def _auth_context(self, request: HttpRequest, request_id: str) -> ApiAuthContext | None:
        if self._auth_context_factory is None:
            return None
        try:
            context = self._auth_context_factory(request)
        except ValueError as exc:
            raise _AuthenticationRejected(request_id=request_id, message=str(exc)) from exc
        if context is not None and not isinstance(context, ApiAuthContext):
            raise _AuthenticationRejected(
                request_id=request_id,
                message="auth context factory must return ApiAuthContext or None",
            )
        return context


def build_wsgi_app(router: HttpRouter) -> WsgiApplication:
    """Return a bounded WSGI callable backed by a framework-neutral router."""

    if not isinstance(router, HttpRouter):
        raise ValueError("build_wsgi_app.router must be an HttpRouter")

    def app(environ: Mapping[str, Any], start_response: WsgiStartResponse) -> Iterable[bytes]:
        request = HttpRequest(
            method=str(environ.get("REQUEST_METHOD") or "GET"),
            path=str(environ.get("PATH_INFO") or "/"),
            query=str(environ.get("QUERY_STRING") or ""),
            headers=_headers_from_wsgi_environ(environ),
            body=_body_from_wsgi_environ(environ),
        )
        response = router.handle(request)
        start_response(_status_line(response.status_code), list(response.header_items()), None)
        return [response.body]

    return app


def list_http_route_specs() -> tuple[HttpRouteSpec, ...]:
    """Return every public HTTP route spec in stable product-family order."""

    return (
        *AUTH_HTTP_ROUTES.values(),
        *ORDER_HTTP_ROUTES.values(),
        *CHECKOUT_HTTP_ROUTES.values(),
        *PAYMENT_HTTP_ROUTES.values(),
        *ADMIN_STORE_CATALOG_HTTP_ROUTES.values(),
        *STORE_OWNER_CATALOG_HTTP_ROUTES.values(),
        *STORE_OWNER_INVENTORY_HTTP_ROUTES.values(),
        *MERCHANT_MEMBERSHIP_HTTP_ROUTES.values(),
        *OPERATOR_HTTP_ROUTES.values(),
        *OPERATOR_ACTION_HTTP_ROUTES.values(),
    )


def http_route_manifest() -> tuple[dict[str, str], ...]:
    """Return a JSON-safe HTTP route manifest for docs, CLI previews, and adapters."""

    return tuple(
        {
            "method": spec.method,
            "path": spec.path,
            "operationId": spec.operation_id,
        }
        for spec in list_http_route_specs()
    )


def describe_http_routes() -> tuple[dict[str, str], ...]:
    """Alias used by runtime previews to avoid exposing mutable route state."""

    return http_route_manifest()


def register_auth_routes(
    router: HttpRouter,
    auth_api: Any,
    *,
    session_transport: Any | None = None,
    csrf_token_service: Any | None = None,
) -> tuple[HttpRoute, ...]:
    """Register AuthApi facade routes on an existing router."""

    return (
        _add_manifest_route(
            router,
            AUTH_HTTP_ROUTES["request_login_challenge"],
            _csrf_issue_handler(auth_api.request_login_challenge, csrf_token_service),
        ),
        _add_manifest_route(
            router,
            AUTH_HTTP_ROUTES["login_with_metamask"],
            _csrf_issue_handler(
                _cookie_login_handler(auth_api.login_with_metamask, session_transport),
                csrf_token_service,
            ),
        ),
        _add_manifest_route(
            router,
            AUTH_HTTP_ROUTES["refresh_session"],
            _csrf_issue_handler(
                _cookie_login_handler(auth_api.refresh_session, session_transport),
                csrf_token_service,
            ),
        ),
        _add_manifest_route(
            router,
            AUTH_HTTP_ROUTES["logout"],
            _cookie_logout_handler(auth_api.logout, session_transport),
        ),
        _add_manifest_route(router, AUTH_HTTP_ROUTES["current_user"], auth_api.current_user),
    )


def register_order_routes(router: HttpRouter, orders_api: Any) -> tuple[HttpRoute, ...]:
    """Register OrdersApi facade routes on an existing router."""

    return (
        _add_manifest_route(router, ORDER_HTTP_ROUTES["create_order"], orders_api.create_order),
    )


def register_checkout_routes(router: HttpRouter, checkout_api: Any) -> tuple[HttpRoute, ...]:
    """Register CheckoutApi facade routes on an existing router."""

    return (
        _add_manifest_route(
            router,
            CHECKOUT_HTTP_ROUTES["get_tracking_by_tracking_id"],
            checkout_api.get_tracking,
        ),
        _add_manifest_route(
            router,
            CHECKOUT_HTTP_ROUTES["get_tracking_by_order_id"],
            checkout_api.get_tracking,
        ),
    )


def register_payment_routes(router: HttpRouter, payments_api: Any) -> tuple[HttpRoute, ...]:
    """Register PaymentsApi facade routes on an existing router."""

    return (
        _add_manifest_route(
            router,
            PAYMENT_HTTP_ROUTES["submit_transaction_hash"],
            payments_api.submit_transaction_hash,
        ),
    )


def register_store_catalog_routes(router: HttpRouter, catalog_api: Any) -> tuple[HttpRoute, ...]:
    """Register admin store provisioning and store-owner catalog routes."""

    return (
        _add_manifest_route(
            router,
            ADMIN_STORE_CATALOG_HTTP_ROUTES["create_or_reuse_store_user"],
            catalog_api.create_or_reuse_store_user,
        ),
        _add_manifest_route(
            router,
            ADMIN_STORE_CATALOG_HTTP_ROUTES["create_store"],
            catalog_api.create_store,
        ),
        _add_manifest_route(
            router,
            ADMIN_STORE_CATALOG_HTTP_ROUTES["grant_store_membership"],
            catalog_api.grant_store_membership,
        ),
        _add_manifest_route(
            router,
            STORE_OWNER_CATALOG_HTTP_ROUTES["register_product"],
            catalog_api.register_store_product,
        ),
    )


def register_store_owner_inventory_routes(router: HttpRouter, inventory_api: Any) -> tuple[HttpRoute, ...]:
    """Register store-owner inventory facade routes on an existing router."""

    return (
        _add_manifest_route(
            router,
            STORE_OWNER_INVENTORY_HTTP_ROUTES["list_inventory"],
            inventory_api.list_inventory,
        ),
        _add_manifest_route(
            router,
            STORE_OWNER_INVENTORY_HTTP_ROUTES["increase_stock"],
            inventory_api.increase_stock,
        ),
        _add_manifest_route(
            router,
            STORE_OWNER_INVENTORY_HTTP_ROUTES["correct_stock"],
            inventory_api.correct_stock,
        ),
        _add_manifest_route(
            router,
            STORE_OWNER_INVENTORY_HTTP_ROUTES["pause_sales"],
            inventory_api.pause_sales,
        ),
        _add_manifest_route(
            router,
            STORE_OWNER_INVENTORY_HTTP_ROUTES["resume_sales"],
            inventory_api.resume_sales,
        ),
    )


def register_merchant_membership_routes(router: HttpRouter, merchant_api: Any) -> tuple[HttpRoute, ...]:
    """Register MerchantMembershipApi facade routes on an existing router."""

    return (
        _add_manifest_route(router, MERCHANT_MEMBERSHIP_HTTP_ROUTES["list_members"], merchant_api.list_members),
        _add_manifest_route(router, MERCHANT_MEMBERSHIP_HTTP_ROUTES["list_invitations"], merchant_api.list_invitations),
        _add_manifest_route(router, MERCHANT_MEMBERSHIP_HTTP_ROUTES["create_invitation"], merchant_api.create_invitation),
        _add_manifest_route(router, MERCHANT_MEMBERSHIP_HTTP_ROUTES["accept_invitation"], merchant_api.accept_invitation),
        _add_manifest_route(router, MERCHANT_MEMBERSHIP_HTTP_ROUTES["revoke_invitation"], merchant_api.revoke_invitation),
        _add_manifest_route(router, MERCHANT_MEMBERSHIP_HTTP_ROUTES["update_member_role"], merchant_api.update_member_role),
        _add_manifest_route(router, MERCHANT_MEMBERSHIP_HTTP_ROUTES["remove_member"], merchant_api.remove_member),
        _add_manifest_route(router, MERCHANT_MEMBERSHIP_HTTP_ROUTES["role_catalog"], merchant_api.role_catalog),
    )


def register_operator_routes(router: HttpRouter, operator_api: Any) -> tuple[HttpRoute, ...]:
    """Register OperatorApi facade routes on an existing router."""

    return (
        _add_manifest_route(
            router,
            OPERATOR_HTTP_ROUTES["get_dashboard"],
            operator_api.get_dashboard,
        ),
        _add_manifest_route(
            router,
            OPERATOR_HTTP_ROUTES["get_order_detail"],
            operator_api.get_order,
        ),
        _add_manifest_route(
            router,
            OPERATOR_HTTP_ROUTES["get_payment_detail"],
            operator_api.get_payment,
        ),
        _add_manifest_route(
            router,
            OPERATOR_HTTP_ROUTES["get_outbox_detail"],
            operator_api.get_outbox_message,
        ),
    )


def register_operator_action_routes(router: HttpRouter, operator_action_api: Any) -> tuple[HttpRoute, ...]:
    """Register operator lifecycle action facade routes on an existing router."""

    return (
        _add_manifest_route(
            router,
            OPERATOR_ACTION_HTTP_ROUTES["cancel_order"],
            operator_action_api.cancel_order,
        ),
        _add_manifest_route(
            router,
            OPERATOR_ACTION_HTTP_ROUTES["retry_outbox_message"],
            operator_action_api.retry_outbox_message,
        ),
        _add_manifest_route(
            router,
            OPERATOR_ACTION_HTTP_ROUTES["replay_message"],
            operator_action_api.replay_message,
        ),
    )


def _add_manifest_route(router: HttpRouter, spec: HttpRouteSpec, handler: HttpHandler) -> HttpRoute:
    return router.add_route(spec.method, spec.path, handler, operation_id=spec.operation_id)


def _csrf_issue_handler(handler: HttpHandler, csrf_token_service: Any | None) -> HttpHandler:
    if csrf_token_service is None:
        return handler

    def wrapped(request: ApiRequest) -> ApiResponse:
        response = handler(request)
        if response.status_code < 200 or response.status_code >= 300:
            return response
        issue_token = getattr(csrf_token_service, "issue_token", None)
        if not callable(issue_token):
            raise ValueError("csrf token service must expose issue_token(now=...)")
        issued = issue_token(now=request.received_at)
        body = dict(response.body) if isinstance(response.body, Mapping) else response.body
        body_fields = getattr(issued, "body_fields", None)
        if isinstance(body, dict) and callable(body_fields):
            body.update(body_fields())
        set_cookie_header_pair = getattr(issued, "set_cookie_header_pair", None)
        if (
            not isinstance(set_cookie_header_pair, tuple)
            or len(set_cookie_header_pair) != 2
            or set_cookie_header_pair[0] != "Set-Cookie"
        ):
            raise ValueError("csrf token issue must expose a Set-Cookie header pair")
        return json_response(
            body,
            status_code=response.status_code,
            request_id=response.request_id,
            headers=_extra_headers(response.headers),
            multi_headers=(*response.multi_headers, set_cookie_header_pair),
        )

    return wrapped


@dataclass(frozen=True)
class _MalformedJson:
    reason: str


class _AuthenticationRejected(ValueError):
    def __init__(self, *, request_id: str, message: str) -> None:
        self.request_id = request_id
        super().__init__(message)


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    headers: Mapping[str, str] | None = None,
) -> HttpResponse:
    return HttpResponse.from_api_response(
        json_response(
            {"error": {"code": code, "message": message}},
            status_code=status_code,
            request_id=request_id,
            headers=headers,
        )
    )


def _cookie_login_handler(handler: HttpHandler, session_transport: Any | None) -> HttpHandler:
    if session_transport is None:
        return handler

    def wrapped(request: ApiRequest) -> ApiResponse:
        response = handler(request)
        if response.status_code < 200 or response.status_code >= 300:
            return response
        token_payload = response.body.get("token") if isinstance(response.body, Mapping) else None
        if not isinstance(token_payload, Mapping):
            return response
        access_token = token_payload.get("accessToken")
        refresh_token = token_payload.get("refreshToken")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            return response
        cookie_pair = session_transport.issue_cookies(
            access_token=access_token,
            refresh_token=refresh_token,
            now=request.received_at,
        )
        return json_response(
            _sanitize_auth_payload(response.body),
            status_code=response.status_code,
            request_id=response.request_id,
            headers=_extra_headers(response.headers),
            multi_headers=(*response.multi_headers, *cookie_pair.set_cookie_header_pairs),
        )

    return wrapped


def _cookie_logout_handler(handler: HttpHandler, session_transport: Any | None) -> HttpHandler:
    if session_transport is None:
        return handler

    def wrapped(request: ApiRequest) -> ApiResponse:
        response = handler(request)
        if response.status_code < 200 or response.status_code >= 300:
            return response
        return json_response(
            _sanitize_auth_payload(response.body),
            status_code=response.status_code,
            request_id=response.request_id,
            headers=_extra_headers(response.headers),
            multi_headers=(*response.multi_headers, *session_transport.expire_cookie_header_pairs(now=request.received_at)),
        )

    return wrapped


def _sanitize_auth_payload(body: Any) -> Any:
    if not isinstance(body, Mapping):
        return body
    payload = dict(body)
    session = payload.get("session")
    if isinstance(session, Mapping):
        safe_session = dict(session)
        safe_session.pop("refreshTokenHash", None)
        payload["session"] = safe_session
    token = payload.get("token")
    if isinstance(token, Mapping):
        safe_token = dict(token)
        if "accessToken" in safe_token:
            safe_token["accessToken"] = "<set-cookie>"
        if "refreshToken" in safe_token:
            safe_token["refreshToken"] = "<set-cookie>"
        safe_token["transport"] = "cookie"
        payload["token"] = safe_token
    return payload


def _extra_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if _canonical_header_name(key) not in {"Content-Type", "Content-Length", "X-Request-Id"}
    }


def _decode_body(request: HttpRequest) -> Any:
    if not request.body:
        return None

    if _media_type(_header_value(request.headers, "Content-Type")) == "application/json":
        try:
            return json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _MalformedJson(reason=str(exc))

    return request.body.decode("utf-8", errors="replace")


def _request_id(request: HttpRequest, request_id_factory: Callable[[HttpRequest], str]) -> str:
    header_request_id = _header_value(request.headers, "X-Request-Id")
    if header_request_id and header_request_id.strip():
        return header_request_id.strip()
    return _require_text(request_id_factory(request), "generated request id")


def _default_request_id(request: HttpRequest) -> str:
    normalized_query = json.dumps(_query_mapping(request.query), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256()
    digest.update(request.method.encode("utf-8"))
    digest.update(b"\n")
    digest.update(request.path.encode("utf-8"))
    digest.update(b"\n")
    digest.update(normalized_query.encode("utf-8"))
    digest.update(b"\n")
    digest.update(request.body)
    return f"req-{digest.hexdigest()[:16]}"


def _query_mapping(query: str | bytes | Mapping[str, Any] | None) -> dict[str, Any]:
    if query is None:
        return {}

    if isinstance(query, bytes):
        query = query.decode("utf-8")

    if isinstance(query, str):
        parsed = parse_qs(query, keep_blank_values=True)
        return {key: values[0] if len(values) == 1 else values for key, values in parsed.items()}

    if not isinstance(query, Mapping):
        raise ValueError("HTTP query must be a mapping, string, bytes, or None")

    output: dict[str, Any] = {}
    for key, value in query.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("HTTP query keys must be non-empty strings")
        if isinstance(value, tuple | list):
            output[key] = [str(item) for item in value]
        elif value is None:
            output[key] = None
        else:
            output[key] = str(value)
    return output


def _response_headers(headers: Mapping[str, str], *, request_id: str | None, content_length: int) -> dict[str, str]:
    content_type = _header_value(headers, "Content-Type") or "application/json"
    existing_request_id = _header_value(headers, "X-Request-Id")
    output: dict[str, str] = {"Content-Type": content_type}

    for key, value in headers.items():
        canonical = _canonical_header_name(key)
        if canonical in {"Content-Type", "Content-Length", "X-Request-Id"}:
            continue
        output[key.strip()] = str(value)

    output["Content-Length"] = str(content_length)
    if request_id is not None:
        output["X-Request-Id"] = request_id
    elif existing_request_id:
        output["X-Request-Id"] = existing_request_id
    return output


def _canonical_header_name(name: str) -> str:
    lower = name.lower()
    if lower == "content-type":
        return "Content-Type"
    if lower == "content-length":
        return "Content-Length"
    if lower == "x-request-id":
        return "X-Request-Id"
    return name


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return str(value)
    return None


def _media_type(content_type: str | None) -> str | None:
    if content_type is None:
        return None
    return content_type.split(";", 1)[0].strip().lower()


def _validate_template_segments(path_template: str) -> None:
    seen_params: set[str] = set()
    for segment in _path_segments(path_template):
        if _is_param_segment(segment):
            param = segment[1:-1]
            if not param.strip():
                raise ValueError("HttpRoute path param names must be non-empty")
            if param in seen_params:
                raise ValueError(f"duplicate HttpRoute path param `{param}`")
            seen_params.add(param)
        elif "{" in segment or "}" in segment:
            raise ValueError("HttpRoute path params must occupy a full segment")


def _path_segments(path: str) -> tuple[str, ...]:
    if path == "/":
        return ()
    return tuple(path.strip("/").split("/"))


def _is_param_segment(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}") and len(segment) > 2


def _headers_from_wsgi_environ(environ: Mapping[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in environ.items():
        if not key.startswith("HTTP_") or value is None:
            continue
        headers[_header_name_from_wsgi_key(key[5:])] = str(value)

    content_type = environ.get("CONTENT_TYPE")
    if content_type:
        headers["Content-Type"] = str(content_type)

    content_length = environ.get("CONTENT_LENGTH")
    if content_length:
        headers["Content-Length"] = str(content_length)

    return headers


def _body_from_wsgi_environ(environ: Mapping[str, Any]) -> bytes:
    input_stream = environ.get("wsgi.input")
    content_length = _wsgi_content_length(environ.get("CONTENT_LENGTH"))
    if input_stream is None or content_length <= 0:
        return b""

    raw_body = input_stream.read(content_length)
    if isinstance(raw_body, bytes):
        return raw_body
    if isinstance(raw_body, bytearray):
        return bytes(raw_body)
    if isinstance(raw_body, str):
        return raw_body.encode("utf-8")
    return bytes(raw_body)


def _wsgi_content_length(value: Any) -> int:
    try:
        content_length = int(str(value or "0"))
    except ValueError:
        return 0
    return max(content_length, 0)


def _header_name_from_wsgi_key(key: str) -> str:
    return "-".join(part.capitalize() for part in key.split("_") if part)


def _status_line(status_code: int) -> str:
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = "Unknown"
    return f"{status_code} {phrase}"


def _string_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    output: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        output[key.strip()] = str(item)
    return output


def _header_pairs(value: tuple[tuple[str, str], ...], field_name: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    output: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError(f"{field_name} items must be header name/value tuples")
        key, item_value = item
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        output.append((key.strip(), str(item_value)))
    return tuple(output)


def _require_bool(value: bool, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a bool")
    return value


def _require_text(value: str | None, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


AUTH_HTTP_ROUTES: Mapping[str, HttpRouteSpec] = MappingProxyType(
    {
        "request_login_challenge": HttpRouteSpec("POST", "/auth/challenges", "requestLoginChallenge"),
        "login_with_metamask": HttpRouteSpec("POST", "/auth/sessions", "loginWithMetaMask"),
        "refresh_session": HttpRouteSpec("POST", "/auth/sessions/refresh", "refreshSession"),
        "logout": HttpRouteSpec("DELETE", "/auth/sessions", "logout"),
        "current_user": HttpRouteSpec("GET", "/auth/me", "getCurrentUser"),
    }
)

ORDER_HTTP_ROUTES: Mapping[str, HttpRouteSpec] = MappingProxyType(
    {
        "create_order": HttpRouteSpec("POST", "/orders", "createOrder"),
    }
)

CHECKOUT_HTTP_ROUTES: Mapping[str, HttpRouteSpec] = MappingProxyType(
    {
        "get_tracking_by_tracking_id": HttpRouteSpec(
            "GET",
            "/checkouts/tracking/{trackingId}",
            "getCheckoutTrackingByTrackingId",
        ),
        "get_tracking_by_order_id": HttpRouteSpec(
            "GET",
            "/checkouts/orders/{orderId}",
            "getCheckoutTrackingByOrderId",
        ),
    }
)

PAYMENT_HTTP_ROUTES: Mapping[str, HttpRouteSpec] = MappingProxyType(
    {
        "submit_transaction_hash": HttpRouteSpec(
            "POST",
            "/payments/transaction-hashes",
            "submitTransactionHash",
        ),
    }
)


ADMIN_STORE_CATALOG_HTTP_ROUTES: Mapping[str, HttpRouteSpec] = MappingProxyType(
    {
        "create_or_reuse_store_user": HttpRouteSpec("POST", "/admin/store-users", "createOrReuseStoreUser"),
        "create_store": HttpRouteSpec("POST", "/admin/stores", "createStore"),
        "grant_store_membership": HttpRouteSpec(
            "POST",
            "/admin/stores/{storeId}/memberships",
            "grantStoreMembership",
        ),
    }
)


STORE_OWNER_CATALOG_HTTP_ROUTES: Mapping[str, HttpRouteSpec] = MappingProxyType(
    {
        "register_product": HttpRouteSpec(
            "POST",
            "/store-owner/stores/{storeId}/products",
            "registerStoreProduct",
        ),
    }
)


STORE_OWNER_INVENTORY_HTTP_ROUTES: Mapping[str, HttpRouteSpec] = MappingProxyType(
    {
        "list_inventory": HttpRouteSpec("GET", "/store-owner/inventory", "listStoreOwnerInventory"),
        "increase_stock": HttpRouteSpec(
            "POST",
            "/store-owner/stores/{storeId}/inventory/{productId}/intake",
            "increaseStoreOwnerInventoryStock",
        ),
        "correct_stock": HttpRouteSpec(
            "POST",
            "/store-owner/stores/{storeId}/inventory/{productId}/corrections",
            "correctStoreOwnerInventoryStock",
        ),
        "pause_sales": HttpRouteSpec(
            "POST",
            "/store-owner/stores/{storeId}/inventory/{productId}/pause",
            "pauseStoreOwnerInventorySales",
        ),
        "resume_sales": HttpRouteSpec(
            "POST",
            "/store-owner/stores/{storeId}/inventory/{productId}/resume",
            "resumeStoreOwnerInventorySales",
        ),
    }
)


MERCHANT_MEMBERSHIP_HTTP_ROUTES: Mapping[str, HttpRouteSpec] = MappingProxyType(
    {
        "list_members": HttpRouteSpec("GET", "/merchant/stores/{storeId}/members", "listMerchantStoreMembers"),
        "list_invitations": HttpRouteSpec("GET", "/merchant/stores/{storeId}/invitations", "listMerchantStoreInvitations"),
        "create_invitation": HttpRouteSpec("POST", "/merchant/stores/{storeId}/invitations", "createMerchantStoreInvitation"),
        "accept_invitation": HttpRouteSpec("POST", "/merchant/invitations/{invitationId}/accept", "acceptMerchantInvitation"),
        "revoke_invitation": HttpRouteSpec("POST", "/merchant/invitations/{invitationId}/revoke", "revokeMerchantInvitation"),
        "update_member_role": HttpRouteSpec("PATCH", "/merchant/stores/{storeId}/members/{userId}", "updateMerchantStoreMemberRole"),
        "remove_member": HttpRouteSpec("DELETE", "/merchant/stores/{storeId}/members/{userId}", "removeMerchantStoreMember"),
        "role_catalog": HttpRouteSpec("GET", "/merchant/role-catalog", "getMerchantRoleCatalog"),
    }
)


OPERATOR_HTTP_ROUTES: Mapping[str, HttpRouteSpec] = MappingProxyType(
    {
        "get_dashboard": HttpRouteSpec("GET", "/operator/dashboard", "getOperatorDashboard"),
        "get_order_detail": HttpRouteSpec("GET", "/operator/orders/{orderId}", "getOperatorOrderDetail"),
        "get_payment_detail": HttpRouteSpec("GET", "/operator/payments/{paymentId}", "getOperatorPaymentDetail"),
        "get_outbox_detail": HttpRouteSpec("GET", "/operator/outbox/{messageId}", "getOperatorOutboxDetail"),
    }
)


OPERATOR_ACTION_HTTP_ROUTES: Mapping[str, HttpRouteSpec] = MappingProxyType(
    {
        "cancel_order": HttpRouteSpec("POST", "/operator/orders/{orderId}/cancel", "cancelOperatorOrder"),
        "retry_outbox_message": HttpRouteSpec(
            "POST",
            "/operator/outbox/{messageId}/retry",
            "retryOperatorOutboxMessage",
        ),
        "replay_message": HttpRouteSpec(
            "POST",
            "/operator/messages/{messageId}/replay",
            "replayOperatorMessage",
        ),
    }
)


__all__ = [
    "ADMIN_STORE_CATALOG_HTTP_ROUTES",
    "AUTH_HTTP_ROUTES",
    "CHECKOUT_HTTP_ROUTES",
    "HttpHandler",
    "HttpRequest",
    "HttpResponse",
    "HttpRoute",
    "HttpRouteSpec",
    "HttpRouter",
    "MERCHANT_MEMBERSHIP_HTTP_ROUTES",
    "ORDER_HTTP_ROUTES",
    "OPERATOR_ACTION_HTTP_ROUTES",
    "OPERATOR_HTTP_ROUTES",
    "PAYMENT_HTTP_ROUTES",
    "STORE_OWNER_INVENTORY_HTTP_ROUTES",
    "STORE_OWNER_CATALOG_HTTP_ROUTES",
    "WsgiApplication",
    "WsgiStartResponse",
    "build_wsgi_app",
    "describe_http_routes",
    "http_route_manifest",
    "list_http_route_specs",
    "register_auth_routes",
    "register_checkout_routes",
    "register_merchant_membership_routes",
    "register_order_routes",
    "register_operator_action_routes",
    "register_operator_routes",
    "register_payment_routes",
    "register_store_catalog_routes",
    "register_store_owner_inventory_routes",
]

"""Framework-neutral HTTP adapter contracts for API facades."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote

from .contracts import ApiRequest, ApiResponse, json_response


HttpHandler = Callable[[ApiRequest], ApiResponse]


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


@dataclass(frozen=True)
class HttpResponse:
    """Serialized HTTP response that can be returned by any framework adapter."""

    status_code: int
    headers: Mapping[str, str]
    body: bytes

    def __post_init__(self) -> None:
        if isinstance(self.status_code, bool) or not isinstance(self.status_code, int):
            raise ValueError("HttpResponse.status_code must be an integer")
        if self.status_code < 100 or self.status_code > 599:
            raise ValueError("HttpResponse.status_code must be between 100 and 599")
        object.__setattr__(self, "headers", MappingProxyType(_string_mapping(self.headers, "HttpResponse.headers")))
        if isinstance(self.body, bytearray):
            object.__setattr__(self, "body", bytes(self.body))
        elif not isinstance(self.body, bytes):
            raise ValueError("HttpResponse.body must be bytes")

    @classmethod
    def from_api_response(cls, response: ApiResponse) -> "HttpResponse":
        body = json.dumps(response.body, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        headers = _response_headers(response.headers, request_id=response.request_id, content_length=len(body))
        return cls(status_code=response.status_code, headers=headers, body=body)


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
    ) -> None:
        self._routes: list[HttpRoute] = list(routes)
        self._request_id_factory = request_id_factory or _default_request_id

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

        path_matches: list[tuple[HttpRoute, dict[str, str]]] = []
        for route in self._routes:
            params = route.match_path(request.path)
            if params is not None:
                path_matches.append((route, params))
                if route.method == request.method:
                    return self._handle_route(route, params, request, request_id)

        if path_matches:
            allowed = ", ".join(sorted({route.method for route, _params in path_matches}))
            return _error_response(
                status_code=405,
                code="METHOD_NOT_ALLOWED",
                message=f"Method {request.method} is not allowed for {request.path}.",
                request_id=request_id,
                headers={"Allow": allowed},
            )

        return _error_response(
            status_code=404,
            code="ROUTE_NOT_FOUND",
            message=f"No route matches {request.path}.",
            request_id=request_id,
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
        api_kwargs: dict[str, Any] = {
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "headers": request.headers,
            "query": query,
            "body": decoded_body,
        }
        if request.received_at is not None:
            api_kwargs["received_at"] = request.received_at

        return HttpResponse.from_api_response(route.handler(ApiRequest(**api_kwargs)))


def register_auth_routes(router: HttpRouter, auth_api: Any) -> tuple[HttpRoute, ...]:
    """Register AuthApi facade routes on an existing router."""

    return (
        _add_manifest_route(router, AUTH_HTTP_ROUTES["request_login_challenge"], auth_api.request_login_challenge),
        _add_manifest_route(router, AUTH_HTTP_ROUTES["login_with_metamask"], auth_api.login_with_metamask),
        _add_manifest_route(router, AUTH_HTTP_ROUTES["refresh_session"], auth_api.refresh_session),
        _add_manifest_route(router, AUTH_HTTP_ROUTES["logout"], auth_api.logout),
        _add_manifest_route(router, AUTH_HTTP_ROUTES["current_user"], auth_api.current_user),
    )


def register_order_routes(router: HttpRouter, orders_api: Any) -> tuple[HttpRoute, ...]:
    """Register OrdersApi facade routes on an existing router."""

    return (
        _add_manifest_route(router, ORDER_HTTP_ROUTES["create_order"], orders_api.create_order),
    )


def _add_manifest_route(router: HttpRouter, spec: HttpRouteSpec, handler: HttpHandler) -> HttpRoute:
    return router.add_route(spec.method, spec.path, handler, operation_id=spec.operation_id)


@dataclass(frozen=True)
class _MalformedJson:
    reason: str


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


def _string_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    output: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        output[key.strip()] = str(item)
    return output


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


__all__ = [
    "AUTH_HTTP_ROUTES",
    "HttpHandler",
    "HttpRequest",
    "HttpResponse",
    "HttpRoute",
    "HttpRouteSpec",
    "HttpRouter",
    "ORDER_HTTP_ROUTES",
    "register_auth_routes",
    "register_order_routes",
]

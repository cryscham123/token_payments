"""Optional FastAPI adapter backed by the framework-neutral HTTP router."""

from __future__ import annotations

import importlib
import importlib.util
from typing import Any

from .http import HttpRequest, HttpResponse, HttpRoute, HttpRouter


DEFAULT_FASTAPI_TITLE = "Token Payments API"
DEFAULT_FASTAPI_VERSION = "0.1.0"
FASTAPI_INSTALL_HINT = (
    "Install the optional FastAPI adapter dependency in the runtime environment with "
    "`pip install fastapi` before building the FastAPI app."
)


class FastApiAdapterUnavailable(RuntimeError):
    """Raised when the optional FastAPI runtime dependency is not installed."""


def is_fastapi_available() -> bool:
    """Return whether the optional FastAPI dependency can be imported."""

    try:
        return importlib.util.find_spec("fastapi") is not None
    except (ImportError, ValueError):
        return False


def build_fastapi_app(
    router: HttpRouter,
    *,
    title: str = DEFAULT_FASTAPI_TITLE,
    version: str = DEFAULT_FASTAPI_VERSION,
) -> Any:
    """Return a FastAPI application that delegates all requests to an HttpRouter."""

    if not isinstance(router, HttpRouter):
        raise ValueError("build_fastapi_app.router must be an HttpRouter")

    FastAPI, Request, Response = _load_fastapi_contracts()
    app = FastAPI(
        title=_require_text(title, "build_fastapi_app.title"),
        version=_require_text(version, "build_fastapi_app.version"),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    for route in router.routes:
        _register_route(app, router, route, Request, Response)

    return app


def _load_fastapi_contracts() -> tuple[Any, Any, Any]:
    try:
        fastapi_module = importlib.import_module("fastapi")
    except ImportError as exc:
        raise FastApiAdapterUnavailable(
            f"FastAPI adapter is unavailable because optional dependency `fastapi` is not installed. "
            f"{FASTAPI_INSTALL_HINT}"
        ) from exc

    try:
        return fastapi_module.FastAPI, fastapi_module.Request, fastapi_module.Response
    except AttributeError as exc:
        raise FastApiAdapterUnavailable(
            f"FastAPI adapter is unavailable because the installed `fastapi` package is incomplete. "
            f"{FASTAPI_INSTALL_HINT}"
        ) from exc


def _register_route(app: Any, router: HttpRouter, route: HttpRoute, Request: Any, Response: Any) -> None:
    endpoint = _make_endpoint(router, Request, Response)
    app.api_route(
        route.path_template,
        methods=[route.method],
        operation_id=route.operation_id,
        name=route.operation_id or f"{route.method} {route.path_template}",
    )(endpoint)


def _make_endpoint(router: HttpRouter, Request: Any, Response: Any) -> Any:
    async def endpoint(request: Any) -> Any:
        response = router.handle(
            HttpRequest(
                method=str(request.method),
                path=_request_path(request),
                query=_request_query_string(request),
                headers=_request_headers(request),
                body=await request.body(),
            )
        )
        return _fastapi_response(response, Response)

    endpoint.__annotations__ = {"request": Request}
    return endpoint


def _fastapi_response(response: HttpResponse, Response: Any) -> Any:
    return Response(
        content=response.body,
        status_code=response.status_code,
        headers=dict(response.headers),
    )


def _request_path(request: Any) -> str:
    scope_path = request.scope.get("path")
    if isinstance(scope_path, str) and scope_path.startswith("/"):
        return scope_path
    return str(request.url.path or "/")


def _request_query_string(request: Any) -> bytes | str:
    value = request.scope.get("query_string", b"")
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return str(value or "")


def _request_headers(request: Any) -> dict[str, str]:
    return {str(name): str(value) for name, value in request.headers.items()}


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


__all__ = [
    "FastApiAdapterUnavailable",
    "build_fastapi_app",
    "is_fastapi_available",
]

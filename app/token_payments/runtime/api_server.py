"""Explicit live API server entrypoint contracts.

The module can describe or prepare the long-running API server path without
binding sockets or importing optional server frameworks at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import importlib.util
import json
import os
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

from token_payments.api import HttpRequest, HttpResponse, HttpRoute, HttpRouter, build_asgi_app, http_route_manifest, json_response

from .composition import (
    LiveRuntimeConfig,
    LiveRuntimeDependencies,
    build_live_readiness_probes,
    build_live_api_router,
    build_live_runtime_dependencies_from_env,
)
from .contracts import JsonValue
from .observability import AccessLogEvent, ReadinessProbe, evaluate_readiness
from .security import RequestBodyLimit


LIVE_API_SERVER_PLAN_CONTRACT = "token-payments.live-api-server.plan.v1"
LIVE_API_CONFIRMATION_REQUIRED = "LIVE_API_CONFIRMATION_REQUIRED"
LIVE_API_CONFIGURATION_INVALID = "LIVE_API_CONFIGURATION_INVALID"
LIVE_API_SERVER_RUNNER_UNAVAILABLE = "LIVE_API_SERVER_RUNNER_UNAVAILABLE"
LIVE_API_SERVER_UNEXPECTED_ERROR = "LIVE_API_SERVER_UNEXPECTED_ERROR"
LIVE_API_APP_FACTORY = "token_payments.runtime.api_server.build_live_asgi_application"


@dataclass(frozen=True)
class LiveApiServerPlan:
    """JSON-safe description of the explicit live API server path."""

    host: str
    port: int
    route_count: int
    required_dependency_groups: tuple[Mapping[str, JsonValue], ...]
    optional_dependencies: Mapping[str, JsonValue]
    session: Mapping[str, JsonValue]
    guards: Mapping[str, JsonValue]
    redaction: Mapping[str, JsonValue]
    readiness: Mapping[str, JsonValue]
    app_factory: str = LIVE_API_APP_FACTORY
    contract: str = LIVE_API_SERVER_PLAN_CONTRACT
    requires_confirmation: bool = True
    server_started: bool = False
    long_running: bool = True

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "contract": self.contract,
            "host": self.host,
            "port": self.port,
            "appFactory": self.app_factory,
            "routeCount": self.route_count,
            "requiredDependencyGroups": [dict(group) for group in self.required_dependency_groups],
            "optionalDependencies": dict(self.optional_dependencies),
            "session": dict(self.session),
            "guards": dict(self.guards),
            "redaction": dict(self.redaction),
            "readiness": dict(self.readiness),
            "requiresConfirmation": self.requires_confirmation,
            "serverStarted": self.server_started,
            "longRunning": self.long_running,
        }


@dataclass(frozen=True)
class LiveApiServerResult:
    """Bounded result returned by an explicit live server start attempt."""

    status: str
    host: str
    port: int
    server_started: bool
    long_running: bool = True
    contract: str = LIVE_API_SERVER_PLAN_CONTRACT
    app_factory: str = LIVE_API_APP_FACTORY
    error: Mapping[str, JsonValue] | None = None
    runner_result: Mapping[str, JsonValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JsonValue]:
        payload: dict[str, JsonValue] = {
            "contract": self.contract,
            "status": self.status,
            "host": self.host,
            "port": self.port,
            "appFactory": self.app_factory,
            "serverStarted": self.server_started,
            "longRunning": self.long_running,
        }
        if self.error is not None:
            payload["error"] = dict(self.error)
        if self.runner_result:
            payload["runner"] = dict(self.runner_result)
        return payload


def describe_live_api_server_plan(
    *,
    config: LiveRuntimeConfig | None = None,
    env: Mapping[str, str] | None = None,
) -> LiveApiServerPlan:
    """Return a dry-run plan without building an app or opening live dependencies."""

    source = os.environ if env is None else env
    host, port = _host_port(config=config, env=source)
    return LiveApiServerPlan(
        host=host,
        port=port,
        route_count=len(http_route_manifest()),
        required_dependency_groups=_required_dependency_groups(),
        optional_dependencies=_optional_dependency_metadata(),
        session=_session_validation_metadata(config=config, env=source),
        guards={
            "cookieSession": True,
            "csrf": True,
            "cors": True,
            "requestBodyLimit": True,
        },
        redaction={
            "secretsRedacted": True,
            "tokenAddressesRedacted": True,
        },
        readiness={
            "healthRoute": "/healthz",
            "readinessRoute": "/readyz",
            "systemRoutesPublicManifest": False,
            "injectedProbes": ["postgres", "kafka", "blockchain"],
            "accessLogRedaction": True,
            "idempotencyHeader": "Idempotency-Key",
        },
    )


def build_live_system_router(
    *,
    readiness_probes: Sequence[ReadinessProbe] = (),
    access_log_sink: Callable[[Mapping[str, JsonValue]], Any] | None = None,
) -> HttpRouter:
    """Build live-only system routes without requiring live application dependencies."""

    router = HttpRouter()
    _register_live_system_routes(router, readiness_probes=readiness_probes)
    if access_log_sink is None:
        return router
    return _ObservedHttpRouter(router, access_log_sink=access_log_sink)


def build_live_http_router(
    *,
    config: LiveRuntimeConfig | None = None,
    dependencies: LiveRuntimeDependencies | None = None,
    readiness_probes: Sequence[ReadinessProbe] | None = None,
    access_log_sink: Callable[[Mapping[str, JsonValue]], Any] | None = None,
) -> HttpRouter:
    """Build public live API routes plus live-only health/readiness routes."""

    live_config = config or LiveRuntimeConfig.from_env(_live_env(os.environ))
    live_dependencies = dependencies or build_live_runtime_dependencies_from_env(config=live_config)
    live_readiness_probes = (
        tuple(readiness_probes)
        if readiness_probes is not None
        else build_live_readiness_probes(config=live_config, dependencies=live_dependencies)
    )
    router = build_live_api_router(config=live_config, dependencies=live_dependencies)
    _register_live_system_routes(router, readiness_probes=live_readiness_probes)
    if access_log_sink is None:
        return router
    return _ObservedHttpRouter(router, access_log_sink=access_log_sink)


def build_live_asgi_application(
    *,
    config: LiveRuntimeConfig | None = None,
    dependencies: LiveRuntimeDependencies | None = None,
    readiness_probes: Sequence[ReadinessProbe] | None = None,
    access_log_sink: Callable[[Mapping[str, JsonValue]], Any] | None = None,
) -> Any:
    """Build the live ASGI application from the framework-neutral live router."""

    live_config = config or LiveRuntimeConfig.from_env(_live_env(os.environ))
    live_dependencies = dependencies or build_live_runtime_dependencies_from_env(config=live_config)
    router = build_live_http_router(
        config=live_config,
        dependencies=live_dependencies,
        readiness_probes=readiness_probes,
        access_log_sink=access_log_sink,
    )
    return build_asgi_app(
        router,
        request_body_limit=RequestBodyLimit(max_bytes=live_config.request_body_max_bytes),
    )


def run_live_api_server(
    *,
    config: LiveRuntimeConfig | None = None,
    dependencies: LiveRuntimeDependencies | None = None,
    confirmed: bool = False,
    runner: Callable[..., Mapping[str, Any] | None] | None = None,
) -> LiveApiServerResult:
    """Run the live API server only after explicit confirmation."""

    plan = describe_live_api_server_plan(config=config)
    if not confirmed:
        return LiveApiServerResult(
            status="refused",
            host=plan.host,
            port=plan.port,
            server_started=False,
            error={
                "code": LIVE_API_CONFIRMATION_REQUIRED,
                "message": "Explicit --confirm-live-api is required before starting the live API server.",
            },
        )

    try:
        live_config = config or LiveRuntimeConfig.from_env(_live_env(os.environ))
        live_dependencies = dependencies or build_live_runtime_dependencies_from_env(config=live_config)
        app = build_live_asgi_application(config=live_config, dependencies=live_dependencies)
        runner_result = _runner_result(
            (runner or _run_with_uvicorn)(app, host=live_config.api_host, port=live_config.api_port)
        )
        server_started = _server_started(runner_result)
        return LiveApiServerResult(
            status="started" if server_started else "stopped",
            host=live_config.api_host,
            port=live_config.api_port,
            server_started=server_started,
            runner_result=runner_result,
        )
    except ImportError as exc:
        return _error_result(
            config=config,
            code=LIVE_API_SERVER_RUNNER_UNAVAILABLE,
            message=str(exc),
        )
    except ValueError as exc:
        return _error_result(
            config=config,
            code=LIVE_API_CONFIGURATION_INVALID,
            message=str(exc),
        )
    except Exception as exc:
        return _error_result(
            config=config,
            code=LIVE_API_SERVER_UNEXPECTED_ERROR,
            message=f"{type(exc).__name__}: {exc}",
        )


def _run_with_uvicorn(app: Any, *, host: str, port: int) -> Mapping[str, JsonValue]:
    uvicorn = importlib.import_module("uvicorn")
    uvicorn.run(app, host=host, port=port)
    return {"serverStarted": True, "runner": "uvicorn"}


def _register_live_system_routes(
    router: HttpRouter,
    *,
    readiness_probes: Sequence[ReadinessProbe],
) -> None:
    router.add_route(
        "GET",
        "/healthz",
        _healthz_handler,
        operation_id="getRuntimeHealth",
    )

    def readyz_handler(request: Any) -> Any:
        return _readyz_handler(request, readiness_probes=readiness_probes)

    router.add_route(
        "GET",
        "/readyz",
        readyz_handler,
        operation_id="getRuntimeReadiness",
    )


def _healthz_handler(request: Any) -> Any:
    return json_response(
        {
            "component": "runtime",
            "state": "OK",
            "checkedAt": request.received_at.isoformat(),
            "details": {
                "serverStarted": False,
                "externalConnectionsOpened": False,
                "scope": "process",
            },
        },
        request_id=request.request_id,
    )


def _readyz_handler(request: Any, *, readiness_probes: Sequence[ReadinessProbe]) -> Any:
    readiness = evaluate_readiness(readiness_probes, checked_at=request.received_at)
    return json_response(
        readiness.to_dict(),
        status_code=readiness.status_code,
        request_id=request.request_id,
    )


class _ObservedHttpRouter(HttpRouter):
    def __init__(
        self,
        delegate: HttpRouter,
        *,
        access_log_sink: Callable[[Mapping[str, JsonValue]], Any],
    ) -> None:
        self._delegate = delegate
        self._access_log_sink = access_log_sink

    @property
    def routes(self) -> tuple[HttpRoute, ...]:
        return self._delegate.routes

    def add_route(self, method: str, path_template: str, handler: Any, *, operation_id: str | None = None) -> HttpRoute:
        return self._delegate.add_route(method, path_template, handler, operation_id=operation_id)

    def handle(
        self,
        method_or_request: str | HttpRequest,
        path: str | None = None,
        *,
        query: str | bytes | Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
        received_at: Any | None = None,
    ) -> HttpResponse:
        request = (
            method_or_request
            if isinstance(method_or_request, HttpRequest)
            else HttpRequest(
                method=method_or_request,
                path=_require_text(path or "", "path"),
                query=query,
                headers=headers or {},
                body=body,
                received_at=received_at,
            )
        )
        started_at = perf_counter()
        response = self._delegate.handle(request)
        duration_ms = round((perf_counter() - started_at) * 1000, 3)
        route = _matched_route(self._delegate.routes, request)
        self._access_log_sink(
            AccessLogEvent(
                method=request.method,
                path_template=route.path_template if route is not None else request.path,
                route_id=route.operation_id if route is not None and route.operation_id else "unmatched",
                status=response.status_code,
                request_id=_response_request_id(response) or _request_header(request, "X-Request-Id") or "<unknown>",
                duration_ms=duration_ms,
                actor=_actor_summary_from_request(request),
                error_code=_response_error_code(response),
            ).to_dict()
        )
        return response


def _error_result(
    *,
    config: LiveRuntimeConfig | None,
    code: str,
    message: str,
) -> LiveApiServerResult:
    plan = describe_live_api_server_plan(config=config)
    return LiveApiServerResult(
        status="error",
        host=plan.host,
        port=plan.port,
        server_started=False,
        error={
            "code": code,
            "message": message,
        },
    )


def _host_port(*, config: LiveRuntimeConfig | None, env: Mapping[str, str]) -> tuple[str, int]:
    if config is not None:
        return config.api_host, config.api_port
    host = _text_env(env, "RUNTIME_API_HOST", "0.0.0.0")
    port = _int_env(env, "RUNTIME_API_PORT", 8000)
    return host, port


def _matched_route(routes: tuple[HttpRoute, ...], request: HttpRequest) -> HttpRoute | None:
    for route in routes:
        if route.method == request.method and route.match_path(request.path) is not None:
            return route
    return None


def _response_request_id(response: HttpResponse) -> str | None:
    for name, value in response.header_items():
        if name.lower() == "x-request-id" and value.strip():
            return value.strip()
    return None


def _request_header(request: HttpRequest, header_name: str) -> str | None:
    for name, value in request.headers.items():
        if name.lower() == header_name.lower() and value.strip():
            return value.strip()
    return None


def _actor_summary_from_request(request: HttpRequest) -> dict[str, JsonValue]:
    user_id = _request_header(request, "X-User-Id")
    role = _request_header(request, "X-User-Role")
    scopes = _request_header(request, "X-User-Scopes")
    if not user_id:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "userId": user_id,
        "role": role,
        "scopes": [scope.strip() for scope in (scopes or "").split(",") if scope.strip()],
    }


def _response_error_code(response: HttpResponse) -> str | None:
    if response.status_code < 400:
        return None
    try:
        decoded = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "HTTP_ERROR"
    error = decoded.get("error") if isinstance(decoded, Mapping) else None
    code = error.get("code") if isinstance(error, Mapping) else None
    return str(code) if code else "HTTP_ERROR"


def _session_validation_metadata(
    *,
    config: LiveRuntimeConfig | None,
    env: Mapping[str, str],
) -> dict[str, JsonValue]:
    if config is not None:
        return {
            "envBackedValidationStatus": "valid",
            "activeKeyId": "<redacted>",
            "signingKeysConfigured": bool(config.session_key_ring.keys),
            "signingKeyCount": len(config.session_key_ring.keys),
        }

    try:
        live_config = LiveRuntimeConfig.from_env(_live_env(env))
    except ValueError as exc:
        return {
            "envBackedValidationStatus": "invalid",
            "activeKeyId": "<redacted>",
            "signingKeysConfigured": bool(env.get("SESSION_SIGNING_KEYS")),
            "signingKeyCount": _signing_key_count(env.get("SESSION_SIGNING_KEYS")),
            "error": {
                "code": LIVE_API_CONFIGURATION_INVALID,
                "message": str(exc),
            },
        }

    return {
        "envBackedValidationStatus": "valid",
        "activeKeyId": "<redacted>",
        "signingKeysConfigured": bool(live_config.session_key_ring.keys),
        "signingKeyCount": len(live_config.session_key_ring.keys),
    }


def _required_dependency_groups() -> tuple[Mapping[str, JsonValue], ...]:
    return (
        {
            "name": "postgres",
            "required": ["postgres_session_factory"],
            "injectedExternally": True,
        },
        {
            "name": "kafka",
            "required": ["kafka_producer"],
            "injectedExternally": True,
        },
        {
            "name": "walletSignature",
            "required": ["wallet_signature_client"],
            "injectedExternally": True,
        },
        {
            "name": "blockchain",
            "required": ["blockchain_client"],
            "injectedExternally": True,
        },
        {
            "name": "runtimePorts",
            "required": ["clock", "id_generator"],
            "injectedExternally": True,
        },
    )


def _optional_dependency_metadata() -> dict[str, JsonValue]:
    fastapi_available = importlib.util.find_spec("fastapi") is not None
    uvicorn_available = importlib.util.find_spec("uvicorn") is not None
    return {
        "fastapiAvailable": fastapi_available,
        "fastapiUnavailableReason": None
        if fastapi_available
        else "Optional dependency `fastapi` is not installed; dry-run and refusal paths do not require it.",
        "uvicornAvailable": uvicorn_available,
        "uvicornUnavailableReason": None
        if uvicorn_available
        else "Optional dependency `uvicorn` is not installed; dry-run and refusal paths do not require it.",
    }


def _live_env(env: Mapping[str, str]) -> dict[str, str]:
    output = dict(env)
    output.setdefault("RUNTIME_ENVIRONMENT", "local")
    return output


def _text_env(env: Mapping[str, str], key: str, default: str) -> str:
    value = str(env.get(key, default)).strip()
    if not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _int_env(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    if value <= 0 or value > 65535:
        raise ValueError(f"{key} must be between 1 and 65535")
    return value


def _signing_key_count(raw_keys: str | None) -> int:
    if not raw_keys:
        return 0
    stripped = raw_keys.strip()
    if stripped.startswith("{"):
        return stripped.count(":")
    return sum(1 for part in stripped.split(",") if part.strip())


def _runner_result(value: Mapping[str, Any] | None) -> dict[str, JsonValue]:
    if value is None:
        return {"serverStarted": True}
    return {str(key): _json_safe(item) for key, item in value.items()}


def _server_started(runner_result: Mapping[str, JsonValue]) -> bool:
    value = runner_result.get("serverStarted", True)
    return bool(value)


def _json_safe(value: Any) -> JsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    return type(value).__name__


__all__ = [
    "LIVE_API_CONFIRMATION_REQUIRED",
    "LIVE_API_SERVER_PLAN_CONTRACT",
    "LiveApiServerPlan",
    "LiveApiServerResult",
    "build_live_asgi_application",
    "build_live_http_router",
    "build_live_system_router",
    "describe_live_api_server_plan",
    "run_live_api_server",
]

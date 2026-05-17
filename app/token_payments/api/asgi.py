"""Standard-library ASGI adapter backed by the framework-neutral HTTP router."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, TypeAlias

from .contracts import json_response
from .http import HttpRequest, HttpResponse, HttpRouter


AsgiMessage: TypeAlias = dict[str, Any]
AsgiScope: TypeAlias = Mapping[str, Any]
AsgiReceive: TypeAlias = Callable[[], Awaitable[AsgiMessage]]
AsgiSend: TypeAlias = Callable[[AsgiMessage], Awaitable[None]]
AsgiApplication: TypeAlias = Callable[[AsgiScope, AsgiReceive, AsgiSend], Awaitable[None]]

_MAX_BODY_BYTES = 1024 * 1024
_MAX_BODY_EVENTS = 128


def build_asgi_app(router: HttpRouter) -> AsgiApplication:
    """Return a bounded ASGI callable backed by a framework-neutral router."""

    if not isinstance(router, HttpRouter):
        raise ValueError("build_asgi_app.router must be an HttpRouter")

    async def app(scope: AsgiScope, receive: AsgiReceive, send: AsgiSend) -> None:
        scope_type = str(scope.get("type") or "")
        if scope_type == "http":
            response = await _handle_http_scope(router, scope, receive)
            await _send_http_response(send, response)
            return
        if scope_type == "websocket":
            await send(
                {
                    "type": "websocket.close",
                    "code": 1003,
                    "reason": "Unsupported ASGI scope type: websocket",
                }
            )
            return
        if scope_type == "lifespan":
            message = await receive()
            event_type = str(message.get("type") or "lifespan.startup")
            failed_type = "lifespan.shutdown.failed" if event_type == "lifespan.shutdown" else "lifespan.startup.failed"
            await send({"type": failed_type, "message": "Unsupported ASGI scope type: lifespan"})
            return
        raise ValueError(f"Unsupported ASGI scope type: {scope_type or '<missing>'}")

    return app


async def _handle_http_scope(router: HttpRouter, scope: AsgiScope, receive: AsgiReceive) -> HttpResponse:
    body_result = await _body_from_asgi_receive(receive)
    if isinstance(body_result, HttpResponse):
        return body_result

    request = HttpRequest(
        method=str(scope.get("method") or "GET"),
        path=str(scope.get("path") or "/"),
        query=_query_string(scope.get("query_string")),
        headers=_headers_from_asgi_scope(scope),
        body=body_result,
    )
    return router.handle(request)


async def _body_from_asgi_receive(receive: AsgiReceive) -> bytes | HttpResponse:
    chunks: list[bytes] = []
    total_size = 0

    for _event_count in range(_MAX_BODY_EVENTS):
        message = await receive()
        message_type = str(message.get("type") or "")
        if message_type == "http.disconnect":
            break
        if message_type != "http.request":
            return _error_response(
                status_code=400,
                code="UNSUPPORTED_ASGI_MESSAGE",
                message=f"Unsupported ASGI receive message type: {message_type or '<missing>'}.",
            )

        body = _message_body(message.get("body", b""))
        total_size += len(body)
        if total_size > _MAX_BODY_BYTES:
            return _error_response(
                status_code=413,
                code="REQUEST_BODY_TOO_LARGE",
                message=f"Request body exceeds {_MAX_BODY_BYTES} bytes.",
            )
        chunks.append(body)
        if not bool(message.get("more_body", False)):
            return b"".join(chunks)

    return _error_response(
        status_code=400,
        code="ASGI_BODY_STREAM_LIMIT_EXCEEDED",
        message=f"Request body stream did not finish within {_MAX_BODY_EVENTS} receive events.",
    )


async def _send_http_response(send: AsgiSend, response: HttpResponse) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": response.status_code,
            "headers": _headers_to_asgi(response.header_items()),
        }
    )
    await send({"type": "http.response.body", "body": response.body, "more_body": False})


def _error_response(*, status_code: int, code: str, message: str) -> HttpResponse:
    return HttpResponse.from_api_response(
        json_response(
            {"error": {"code": code, "message": message}},
            status_code=status_code,
        )
    )


def _query_string(value: Any) -> bytes | str:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return str(value)


def _headers_from_asgi_scope(scope: AsgiScope) -> dict[str, str]:
    headers: dict[str, str] = {}
    raw_headers = scope.get("headers") or ()
    if not isinstance(raw_headers, Sequence):
        return headers

    for raw_name, raw_value in raw_headers:
        name = _header_text(raw_name)
        value = _header_text(raw_value)
        if not name.strip():
            continue
        headers[_header_name(name)] = value
    return headers


def _headers_to_asgi(headers: Mapping[str, str] | tuple[tuple[str, str], ...]) -> list[tuple[bytes, bytes]]:
    items = headers.items() if isinstance(headers, Mapping) else headers
    return [(_header_bytes(name), _header_bytes(value)) for name, value in items]


def _message_body(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


def _header_name(name: str) -> str:
    return "-".join(part.capitalize() for part in name.split("-") if part)


def _header_text(value: Any) -> str:
    if isinstance(value, bytes | bytearray):
        return bytes(value).decode("latin-1")
    return str(value)


def _header_bytes(value: str) -> bytes:
    return str(value).encode("latin-1")


__all__ = [
    "AsgiApplication",
    "AsgiReceive",
    "AsgiScope",
    "AsgiSend",
    "build_asgi_app",
]

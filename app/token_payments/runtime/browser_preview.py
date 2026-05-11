"""Local browser preview server for the customer and operator UI fixtures."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any
from urllib.parse import urlsplit

from token_payments.api import http_route_manifest
from token_payments.ui.preview import render_ui_preview


DEFAULT_BROWSER_PREVIEW_HOST = "127.0.0.1"
DEFAULT_BROWSER_PREVIEW_PORT = 8765
HTML_CONTENT_TYPE = "text/html; charset=utf-8"
JSON_CONTENT_TYPE = "application/json; charset=utf-8"


class BrowserPreviewHttpServer(ThreadingHTTPServer):
    """Threaded localhost server for bounded UI preview routes."""

    daemon_threads = True


class BrowserPreviewRequestHandler(BaseHTTPRequestHandler):
    """Serve deterministic preview HTML and metadata without app side effects."""

    server_version = "TokenPaymentsBrowserPreview/1.0"
    sys_version = ""

    def do_GET(self) -> None:
        self._handle(send_body=True)

    def do_HEAD(self) -> None:
        self._handle(send_body=False)

    def log_message(self, format: str, *args: Any) -> None:
        return None

    def _handle(self, *, send_body: bool) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/customer"}:
            self._send_html(render_ui_preview("customer")["html"], send_body=send_body)
            return
        if path == "/operator":
            self._send_html(render_ui_preview("operator")["html"], send_body=send_body)
            return
        if path == "/healthz":
            self._send_json(_health_payload(), send_body=send_body)
            return
        if path == "/api/routes":
            self._send_json(list(http_route_manifest()), send_body=send_body)
            return
        self._send_not_found(path, send_body=send_body)

    def _send_html(self, html: object, *, send_body: bool, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = str(html).encode("utf-8")
        self._send_response(status, HTML_CONTENT_TYPE, body, send_body=send_body)

    def _send_json(self, payload: object, *, send_body: bool, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self._send_response(status, JSON_CONTENT_TYPE, body, send_body=send_body)

    def _send_not_found(self, path: str, *, send_body: bool) -> None:
        escaped_path = _escape_html(path[:160] or "/")
        html = (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head><meta charset=\"utf-8\"><title>404 Not Found</title></head>\n"
            f"<body><main><h1>404 Not Found</h1><p>No preview route matches {escaped_path}.</p></main></body>\n"
            "</html>"
        )
        self._send_html(html, send_body=send_body, status=HTTPStatus.NOT_FOUND)

    def _send_response(self, status: HTTPStatus, content_type: str, body: bytes, *, send_body: bool) -> None:
        self.send_response(status.value, status.phrase)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)


def build_browser_preview_server(
    host: str = DEFAULT_BROWSER_PREVIEW_HOST,
    port: int = DEFAULT_BROWSER_PREVIEW_PORT,
) -> BrowserPreviewHttpServer:
    """Bind and return a preview server for explicit CLI/test callers."""

    return BrowserPreviewHttpServer((_require_loopback_host(host), port), BrowserPreviewRequestHandler)


def serve_browser_preview(
    host: str = DEFAULT_BROWSER_PREVIEW_HOST,
    port: int = DEFAULT_BROWSER_PREVIEW_PORT,
) -> None:
    """Run the browser preview server until interrupted."""

    server = build_browser_preview_server(host=host, port=port)
    bound_host, bound_port = server.server_address[:2]
    print(f"Browser preview listening at http://{bound_host}:{bound_port}/customer", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _health_payload() -> dict[str, object]:
    return {
        "component": "browser-preview",
        "status": "ok",
        "views": ["customer", "operator"],
    }


def _require_loopback_host(host: str) -> str:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("browser preview host must be a loopback address")
    return host


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


__all__ = [
    "DEFAULT_BROWSER_PREVIEW_HOST",
    "DEFAULT_BROWSER_PREVIEW_PORT",
    "BrowserPreviewHttpServer",
    "BrowserPreviewRequestHandler",
    "build_browser_preview_server",
    "serve_browser_preview",
]

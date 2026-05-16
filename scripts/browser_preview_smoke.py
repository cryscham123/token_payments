#!/usr/bin/env python3
"""Smoke-check the local browser preview routes and print a manual checklist."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http import HTTPStatus
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from token_payments.api import http_route_manifest
from token_payments.runtime.browser_preview import (
    DEFAULT_BROWSER_PREVIEW_HOST,
    DEFAULT_BROWSER_PREVIEW_PORT,
    build_browser_preview_server,
    render_browser_preview_document,
)


CONTRACT = "token-payments.browser-preview-smoke.v1"
REQUEST_TIMEOUT_SECONDS = 5
MAX_BODY_BYTES = 262_144
MAX_ERROR_CHARS = 240


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-check Token Payments browser preview routes.")
    parser.add_argument(
        "--base-url",
        help="Existing loopback preview server base URL. When omitted, an ephemeral preview server is started.",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the customer and operator preview URLs after smoke checks complete.",
    )
    args = parser.parse_args(argv)

    exit_code, payload = run_smoke(base_url=args.base_url, open_browser=args.open_browser)
    _print_json(payload)
    return exit_code


def run_smoke(
    *,
    base_url: str | None = None,
    open_browser: bool = False,
    browser_open: Callable[[str], object] = webbrowser.open,
) -> tuple[int, dict[str, Any]]:
    server_started = False
    server = None
    thread: threading.Thread | None = None
    resolved_base_url = ""
    checks: list[dict[str, Any]] = []
    browser_open_errors = 0

    fetch = _fetch
    try:
        if base_url is None:
            try:
                server = build_browser_preview_server(host=DEFAULT_BROWSER_PREVIEW_HOST, port=0)
            except PermissionError:
                resolved_base_url = f"http://{DEFAULT_BROWSER_PREVIEW_HOST}:{DEFAULT_BROWSER_PREVIEW_PORT}"
                fetch = _direct_fetch
            else:
                host, port = server.server_address[:2]
                resolved_base_url = _normalize_base_url(f"http://{host}:{port}")
                thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
                thread.start()
                server_started = True
        else:
            resolved_base_url = _normalize_base_url(base_url)

        manual_urls = _manual_browser_urls(resolved_base_url)
        checks = _run_checks(resolved_base_url, fetch=fetch)
        browser_ready = all(bool(check["passed"]) for check in checks)

        if open_browser:
            browser_open_errors = _open_manual_preview_urls(manual_urls, browser_open)

        payload = _payload(
            status="PASSED" if browser_ready else "FAILED",
            server_started=server_started,
            browser_ready=browser_ready,
            base_url=resolved_base_url,
            manual_urls=manual_urls,
            checks=checks,
            open_browser_requested=open_browser,
            browser_open_errors=browser_open_errors,
        )
        return (0 if browser_ready else 1), payload
    except Exception as exc:
        if not resolved_base_url:
            resolved_base_url = _fallback_base_url(base_url)
        manual_urls = _manual_browser_urls(resolved_base_url) if resolved_base_url else {}
        payload = _payload(
            status="FAILED",
            server_started=server_started,
            browser_ready=False,
            base_url=resolved_base_url,
            manual_urls=manual_urls,
            checks=checks,
            open_browser_requested=open_browser,
            browser_open_errors=browser_open_errors,
        )
        payload["error"] = {
            "code": "BROWSER_PREVIEW_SMOKE_ERROR",
            "message": _safe_text(str(exc)),
        }
        return 1, payload
    finally:
        if server is not None:
            server.shutdown()
            if thread is not None:
                thread.join(timeout=5)
            server.server_close()


def _run_checks(
    base_url: str,
    *,
    fetch: Callable[[str], dict[str, object]] | None = None,
) -> list[dict[str, Any]]:
    fetch_route = fetch or _fetch
    return [
        _check_html(
            name="root-html",
            url=f"{base_url}/",
            required_text=("data-view=\"checkout\"", "Checkout", "Sign Payment"),
            fetch=fetch_route,
        ),
        _check_html(
            name="customer-html",
            url=f"{base_url}/customer",
            required_text=(
                "data-view=\"checkout\"",
                "Checkout",
                "Sign Payment",
                "PaymentConfirmedEvent",
                "PaymentFailedEvent",
                "PaymentExpiredEvent",
            ),
            fetch=fetch_route,
        ),
        _check_html(
            name="operator-html",
            url=f"{base_url}/operator",
            required_text=(
                "data-view=\"operator\"",
                "Operator Dashboard",
                "Retry candidate",
                "cancelOperatorOrder",
                "retryOperatorOutboxMessage",
                "replayOperatorMessage",
                "outbox-relay",
            ),
            fetch=fetch_route,
        ),
        _check_health_json(f"{base_url}/healthz", fetch=fetch_route),
        _check_routes_json(f"{base_url}/api/routes", fetch=fetch_route),
    ]


def _check_html(
    *,
    name: str,
    url: str,
    required_text: tuple[str, ...],
    fetch: Callable[[str], dict[str, object]],
) -> dict[str, Any]:
    response = fetch(url)
    status_code = int(response["statusCode"])
    body = str(response.get("body", ""))
    content_type = _header(response, "Content-Type")
    missing = [text for text in required_text if text not in body]
    passed = (
        status_code == HTTPStatus.OK.value
        and content_type == "text/html; charset=utf-8"
        and body.startswith("<!doctype html>")
        and not missing
    )
    if passed:
        summary = f"200 text/html includes {', '.join(required_text)}"
    else:
        summary = _failure_summary(
            expected=f"200 text/html with {', '.join(required_text)}",
            status_code=status_code,
            content_type=content_type,
            missing=missing,
            response=response,
        )
    return _check_result(name=name, url=url, status_code=status_code, passed=passed, summary=summary)


def _check_health_json(url: str, *, fetch: Callable[[str], dict[str, object]]) -> dict[str, Any]:
    response = fetch(url)
    status_code = int(response["statusCode"])
    content_type = _header(response, "Content-Type")
    payload = _json_body(response)
    passed = (
        status_code == HTTPStatus.OK.value
        and content_type == "application/json; charset=utf-8"
        and payload
        == {
            "component": "browser-preview",
            "status": "ok",
            "views": ["customer", "operator"],
        }
    )
    summary = (
        "200 health JSON reports browser-preview ok for customer/operator"
        if passed
        else _failure_summary(
            expected="200 health JSON with component browser-preview and status ok",
            status_code=status_code,
            content_type=content_type,
            response=response,
        )
    )
    return _check_result(name="health-json", url=url, status_code=status_code, passed=passed, summary=summary)


def _check_routes_json(url: str, *, fetch: Callable[[str], dict[str, object]]) -> dict[str, Any]:
    response = fetch(url)
    status_code = int(response["statusCode"])
    content_type = _header(response, "Content-Type")
    payload = _json_body(response)
    route_text = json.dumps(payload, sort_keys=True) if payload is not None else ""
    route_count = len(payload) if isinstance(payload, list) else 0
    missing = [route for route in ("/orders", "/operator/dashboard") if route not in route_text]
    passed = (
        status_code == HTTPStatus.OK.value
        and content_type == "application/json; charset=utf-8"
        and isinstance(payload, list)
        and route_count > 0
        and not missing
    )
    summary = (
        f"200 route manifest JSON lists {route_count} route(s), including /orders and /operator/dashboard"
        if passed
        else _failure_summary(
            expected="200 route manifest JSON including /orders and /operator/dashboard",
            status_code=status_code,
            content_type=content_type,
            missing=missing,
            response=response,
        )
    )
    return _check_result(name="routes-json", url=url, status_code=status_code, passed=passed, summary=summary)


def _fetch(url: str) -> dict[str, object]:
    try:
        with urlopen(Request(url, method="GET"), timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_BODY_BYTES).decode("utf-8", errors="replace")
            return {
                "statusCode": int(response.status),
                "headers": dict(response.headers.items()),
                "body": body,
            }
    except HTTPError as exc:
        body = exc.read(MAX_BODY_BYTES).decode("utf-8", errors="replace")
        return {
            "statusCode": int(exc.code),
            "headers": dict(exc.headers.items()),
            "body": body,
        }
    except URLError as exc:
        return {
            "statusCode": 0,
            "headers": {},
            "body": "",
            "error": _safe_text(str(exc.reason)),
        }


def _direct_fetch(url: str) -> dict[str, object]:
    path = urlsplit(url).path or "/"
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if path in {"/", "/customer"}:
        return {
            "statusCode": HTTPStatus.OK.value,
            "headers": {**headers, "Content-Type": "text/html; charset=utf-8"},
            "body": render_browser_preview_document("customer"),
        }
    if path == "/operator":
        return {
            "statusCode": HTTPStatus.OK.value,
            "headers": {**headers, "Content-Type": "text/html; charset=utf-8"},
            "body": render_browser_preview_document("operator"),
        }
    if path == "/healthz":
        return {
            "statusCode": HTTPStatus.OK.value,
            "headers": {**headers, "Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps(
                {"component": "browser-preview", "status": "ok", "views": ["customer", "operator"]},
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
        }
    if path == "/api/routes":
        return {
            "statusCode": HTTPStatus.OK.value,
            "headers": {**headers, "Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps(list(http_route_manifest()), ensure_ascii=True, separators=(",", ":"), sort_keys=True),
        }
    return {
        "statusCode": HTTPStatus.NOT_FOUND.value,
        "headers": {**headers, "Content-Type": "text/html; charset=utf-8"},
        "body": "<!doctype html><html><body><main><h1>404 Not Found</h1></main></body></html>",
    }


def _json_body(response: dict[str, object]) -> object | None:
    try:
        return json.loads(str(response.get("body", "")))
    except json.JSONDecodeError:
        return None


def _payload(
    *,
    status: str,
    server_started: bool,
    browser_ready: bool,
    base_url: str,
    manual_urls: dict[str, str],
    checks: list[dict[str, Any]],
    open_browser_requested: bool,
    browser_open_errors: int,
) -> dict[str, Any]:
    return {
        "contract": CONTRACT,
        "status": status,
        "serverStarted": server_started,
        "browserReady": browser_ready,
        "baseUrl": base_url,
        "manualBrowserUrls": manual_urls,
        "checks": checks,
        "openBrowserRequested": open_browser_requested,
        "browserOpenErrors": browser_open_errors,
    }


def _check_result(*, name: str, url: str, status_code: int, passed: bool, summary: str) -> dict[str, Any]:
    return {
        "name": name,
        "url": url,
        "statusCode": status_code,
        "passed": passed,
        "summary": _safe_text(summary),
    }


def _failure_summary(
    *,
    expected: str,
    status_code: int,
    content_type: str,
    response: dict[str, object],
    missing: list[str] | None = None,
) -> str:
    parts = [f"expected {expected}", f"got status {status_code}", f"content-type {content_type or 'missing'}"]
    if missing:
        parts.append(f"missing {', '.join(missing)}")
    if response.get("error"):
        parts.append(f"error {response['error']}")
    return "; ".join(parts)


def _manual_browser_urls(base_url: str) -> dict[str, str]:
    return {
        "customer": f"{base_url}/customer",
        "operator": f"{base_url}/operator",
        "health": f"{base_url}/healthz",
        "routes": f"{base_url}/api/routes",
    }


def _open_manual_preview_urls(manual_urls: dict[str, str], browser_open: Callable[[str], object]) -> int:
    errors = 0
    for key in ("customer", "operator"):
        try:
            result = browser_open(manual_urls[key])
        except Exception:
            errors += 1
            continue
        if result is False:
            errors += 1
    return errors


def _normalize_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url.strip())
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port is None:
        raise ValueError("base-url must be an absolute HTTP loopback URL with an explicit port")
    return f"http://{parsed.netloc}".rstrip("/")


def _fallback_base_url(base_url: str | None) -> str:
    if not base_url:
        return ""
    try:
        return _normalize_base_url(base_url)
    except ValueError:
        return ""


def _header(response: dict[str, object], name: str) -> str:
    headers = response.get("headers")
    if not isinstance(headers, dict):
        return ""
    for key, value in headers.items():
        if str(key).lower() == name.lower():
            return str(value)
    return ""


def _safe_text(value: str) -> str:
    compact = " ".join(value.split())
    if len(compact) > MAX_ERROR_CHARS:
        return compact[: MAX_ERROR_CHARS - 3] + "..."
    return compact


def _print_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())

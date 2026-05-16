from __future__ import annotations

import json
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_browser_preview_server_defaults_are_localhost_only() -> None:
    from token_payments.runtime.browser_preview import (
        DEFAULT_BROWSER_PREVIEW_HOST,
        DEFAULT_BROWSER_PREVIEW_PORT,
        build_browser_preview_server,
    )

    assert DEFAULT_BROWSER_PREVIEW_HOST == "127.0.0.1"
    assert DEFAULT_BROWSER_PREVIEW_PORT == 8765
    with pytest.raises(ValueError, match="loopback"):
        build_browser_preview_server(host="0.0.0.0", port=0)


def test_browser_preview_server_http_routes_are_browser_openable() -> None:
    from token_payments.runtime.browser_preview import build_browser_preview_server

    with _running_server(_build_server_or_skip(build_browser_preview_server)) as base_url:
        root = _fetch(base_url + "/")
        customer = _fetch(base_url + "/customer")
        operator = _fetch(base_url + "/operator")

    for response in (root, customer, operator):
        assert response["status"] == 200
        assert response["headers"]["Content-Type"] == "text/html; charset=utf-8"
        assert response["headers"]["Cache-Control"] == "no-store"
        assert response["headers"]["X-Content-Type-Options"] == "nosniff"
        assert response["body"].startswith("<!doctype html>")

    assert 'data-view="checkout"' in root["body"]
    assert 'data-view="checkout"' in customer["body"]
    assert "OrderApprovedEvent" in customer["body"]
    assert "PaymentFailedEvent" in customer["body"]
    assert "PaymentExpiredEvent" in customer["body"]
    assert "Ledger Mug &lt;sample&gt;" in customer["body"]

    assert 'data-view="operator"' in operator["body"]
    assert "Operator Dashboard" in operator["body"]
    assert "Retry candidate" in operator["body"]
    assert "cancelOperatorOrder" in operator["body"]
    assert "retryOperatorOutboxMessage" in operator["body"]
    assert "replayOperatorMessage" in operator["body"]
    assert "outbox-relay" in operator["body"]


def test_browser_preview_server_json_routes_health_and_404_are_bounded() -> None:
    from token_payments.api import http_route_manifest
    from token_payments.runtime.browser_preview import build_browser_preview_server

    with _running_server(_build_server_or_skip(build_browser_preview_server)) as base_url:
        health = _fetch_json(base_url + "/healthz")
        routes = _fetch_json(base_url + "/api/routes")
        missing = _fetch_error(base_url + "/missing")
        still_healthy = _fetch_json(base_url + "/healthz")

    assert health == {
        "component": "browser-preview",
        "status": "ok",
        "views": ["customer", "operator"],
    }
    assert routes == list(http_route_manifest())
    assert still_healthy["status"] == "ok"

    assert missing["status"] == 404
    assert missing["headers"]["Content-Type"] == "text/html; charset=utf-8"
    assert missing["headers"]["Cache-Control"] == "no-store"
    assert missing["headers"]["X-Content-Type-Options"] == "nosniff"
    assert "404" in missing["body"]
    assert len(missing["body"].encode("utf-8")) < 2048


def test_browser_preview_server_source_and_responses_avoid_sensitive_or_tool_specific_values() -> None:
    from token_payments.runtime.browser_preview import build_browser_preview_server

    source_paths = (
        ROOT / "app/token_payments/runtime/browser_preview.py",
        ROOT / "scripts/browser_preview_server.py",
    )
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)

    with _running_server(_build_server_or_skip(build_browser_preview_server)) as base_url:
        response_text = "\n".join(
            (
                _fetch(base_url + "/")["body"],
                _fetch(base_url + "/customer")["body"],
                _fetch(base_url + "/operator")["body"],
                json.dumps(_fetch_json(base_url + "/healthz"), sort_keys=True),
                json.dumps(_fetch_json(base_url + "/api/routes"), sort_keys=True),
                _fetch_error(base_url + "/unknown")["body"],
            )
        )

    combined = f"{source_text}\n{response_text}".lower()
    for blocked in _blocked_terms():
        assert blocked not in combined


@contextmanager
def _running_server(server) -> Iterator[str]:
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _build_server_or_skip(build_browser_preview_server):
    try:
        return build_browser_preview_server(host="127.0.0.1", port=0)
    except PermissionError as exc:
        pytest.skip(f"loopback socket binding is not available in this environment: {exc}")


def _fetch(url: str) -> dict[str, object]:
    with urlopen(Request(url), timeout=5) as response:
        return {
            "status": response.status,
            "headers": dict(response.headers.items()),
            "body": response.read().decode("utf-8"),
        }


def _fetch_json(url: str) -> object:
    response = _fetch(url)
    assert response["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert response["headers"]["Cache-Control"] == "no-store"
    assert response["headers"]["X-Content-Type-Options"] == "nosniff"
    return json.loads(str(response["body"]))


def _fetch_error(url: str) -> dict[str, object]:
    try:
        return _fetch(url)
    except HTTPError as exc:
        return {
            "status": exc.code,
            "headers": dict(exc.headers.items()),
            "body": exc.read().decode("utf-8"),
        }


def _blocked_terms() -> tuple[str, ...]:
    return (
        "cla" + "ude",
        ".cla" + "ude",
        "anth" + "ropic",
        "private" + "_key",
        "private" + " key",
        "seed" + " phrase",
        "mnemon" + "ic",
        "sec" + "ret placeholder",
    )

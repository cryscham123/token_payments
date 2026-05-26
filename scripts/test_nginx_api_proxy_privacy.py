from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_compose_routes_public_api_through_nginx_without_publishing_token_api_port() -> None:
    services = _compose_services()
    api = services["token_payments_api"]
    nginx = services["nginx"]

    assert _list_for_key(api, "ports") == []
    assert _list_for_key(api, "expose") == ["8000"]
    assert _list_for_key(nginx, "ports") == ["443:443", "80:80"]
    assert _list_for_key(nginx, "profiles") == ["api"]
    assert _depends_on_conditions(nginx) == {"token_payments_api": "service_healthy"}


def test_nginx_proxy_config_disables_ip_logs_and_does_not_forward_client_ip_headers() -> None:
    config = (ROOT / "app" / "nginx" / "default.conf").read_text(encoding="utf-8")

    assert "server token_payments_api:8000;" in config
    assert "proxy_pass http://token_payments_api;" in config
    assert "access_log off;" in config
    assert "error_log /dev/null crit;" in config
    assert "proxy_set_header Host $host;" in config
    assert "proxy_set_header X-Forwarded-Host $host;" in config
    assert "proxy_set_header X-Forwarded-Proto https;" in config

    forbidden = (
        "$remote_addr",
        "$binary_remote_addr",
        "$http_x_forwarded_for",
        "$proxy_add_x_forwarded_for",
        "X-Forwarded-For",
        "X-Real-IP",
        "real_ip_header",
        "set_real_ip_from",
    )
    for term in forbidden:
        assert term not in config


def test_token_api_uvicorn_runner_disables_access_log_while_accepting_non_ip_proxy_metadata(
    monkeypatch: Any,
) -> None:
    import token_payments.runtime.api_server as api_server

    captured: dict[str, Any] = {}

    class FakeUvicorn:
        @staticmethod
        def run(app: Any, **kwargs: Any) -> None:
            captured["app"] = app
            captured.update(kwargs)

    def fake_import_module(name: str) -> Any:
        if name == "uvicorn":
            return FakeUvicorn
        raise AssertionError(f"unexpected import {name}")

    monkeypatch.setattr(api_server.importlib, "import_module", fake_import_module)

    app = object()
    result = api_server._run_with_uvicorn(app, host="0.0.0.0", port=8000)

    assert result == {"serverStarted": True, "runner": "uvicorn", "accessLog": False}
    assert captured["app"] is app
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 8000
    assert captured["access_log"] is False
    assert captured["proxy_headers"] is True
    assert captured["forwarded_allow_ips"] == "*"


def test_runtime_dry_run_documents_no_client_ip_logging() -> None:
    from token_payments.runtime import describe_live_api_server_plan

    plan = describe_live_api_server_plan(env={"RUNTIME_API_HOST": "0.0.0.0", "RUNTIME_API_PORT": "8000"}).to_dict()

    assert plan["redaction"]["clientIpLogged"] is False
    assert plan["redaction"]["forwardedClientIpHeaders"] is False
    assert plan["redaction"]["nonIpProxyMetadataAccepted"] is True
    assert plan["readiness"]["accessLogRedaction"] is True


def _compose_services() -> dict[str, tuple[str, ...]]:
    services: dict[str, list[str]] = {}
    current_service: str | None = None
    in_services = False
    for raw_line in (ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = _indent_width(raw_line)
        if indent == 0 and stripped == "services:":
            in_services = True
            continue
        if not in_services:
            continue
        if indent == 0:
            break
        if indent == 2 and stripped.endswith(":") and not stripped.startswith("- "):
            current_service = stripped[:-1]
            services[current_service] = []
            continue
        if current_service is not None:
            services[current_service].append(raw_line)
    return {name: tuple(block) for name, block in services.items()}


def _list_for_key(block: tuple[str, ...], key: str) -> list[str]:
    values: list[str] = []
    in_key = False
    key_indent = -1
    for raw_line in block:
        stripped = raw_line.strip()
        indent = _indent_width(raw_line)
        if stripped == f"{key}:":
            in_key = True
            key_indent = indent
            continue
        if in_key and indent <= key_indent and not stripped.startswith("- "):
            break
        if in_key and stripped.startswith("- "):
            values.append(stripped[2:].strip().strip('"'))
    return values


def _depends_on_conditions(block: tuple[str, ...]) -> dict[str, str]:
    dependencies: dict[str, str] = {}
    in_depends = False
    current_dependency: str | None = None
    depends_indent = -1
    current_indent = -1
    for raw_line in block:
        stripped = raw_line.strip()
        indent = _indent_width(raw_line)
        if stripped == "depends_on:":
            in_depends = True
            depends_indent = indent
            continue
        if not in_depends:
            continue
        if indent <= depends_indent and not stripped.startswith("- "):
            break
        if stripped.endswith(":") and indent == depends_indent + 2:
            current_dependency = stripped[:-1]
            current_indent = indent
            continue
        if current_dependency and indent == current_indent + 2 and stripped.startswith("condition:"):
            dependencies[current_dependency] = stripped.split(":", 1)[1].strip()
    return dependencies


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))

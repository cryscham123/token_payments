from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from uuid import UUID

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


NOW = datetime(2026, 5, 10, 4, 45, tzinfo=UTC)


def test_runtime_config_parses_env_and_worker_loop_options() -> None:
    from token_payments.runtime import RuntimeConfig, WorkerLoopOptions

    config = RuntimeConfig.from_env(
        {
            "RUNTIME_API_HOST": "127.0.0.1",
            "RUNTIME_API_PORT": "8123",
            "RUNTIME_REQUEST_TIMEOUT_SECONDS": "12.5",
            "RUNTIME_WORKER_BATCH_SIZE": "25",
            "RUNTIME_WORKER_POLL_INTERVAL_SECONDS": "0.25",
            "RUNTIME_RECEIPT_POLL_INTERVAL_SECONDS": "4",
        }
    )

    assert config.api_host == "127.0.0.1"
    assert config.api_port == 8123
    assert config.request_timeout_seconds == 12.5
    assert config.worker_batch_size == 25
    assert config.worker_poll_interval_seconds == 0.25
    assert config.receipt_poll_interval_seconds == 4.0
    assert config.worker_loop_options() == WorkerLoopOptions(
        batch_size=25,
        poll_interval_seconds=0.25,
        receipt_poll_interval_seconds=4.0,
    )

    defaults = RuntimeConfig.from_env({})
    assert defaults.api_host == "0.0.0.0"
    assert defaults.api_port == 8000
    assert defaults.worker_batch_size == 100

    with pytest.raises(ValueError, match="RUNTIME_API_PORT"):
        RuntimeConfig.from_env({"RUNTIME_API_PORT": "70000"})
    with pytest.raises(ValueError, match="RUNTIME_WORKER_BATCH_SIZE"):
        RuntimeConfig.from_env({"RUNTIME_WORKER_BATCH_SIZE": "0"})


def test_api_request_response_envelopes_are_framework_free_and_json_safe() -> None:
    from token_payments.api import ApiRequest, ApiResponse, json_response

    class DemoStatus(StrEnum):
        ACCEPTED = "ACCEPTED"

    @dataclass(frozen=True)
    class DemoBody:
        payment_id: UUID
        amount: Decimal
        created_at: datetime
        status: DemoStatus

    request = ApiRequest(
        request_id="req-123",
        method="post",
        path="/checkout/orders",
        headers={"X-Request-Id": "req-123"},
        query={"trackingId": "track-1"},
        body={"quantity": 2},
        received_at=NOW,
    )
    response = json_response(
        DemoBody(
            payment_id=UUID("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25"),
            amount=Decimal("1.25"),
            created_at=NOW,
            status=DemoStatus.ACCEPTED,
        ),
        status_code=202,
        request_id=request.request_id,
        headers={"Cache-Control": "no-store"},
    )

    assert request.method == "POST"
    assert request.path == "/checkout/orders"
    assert request.headers["X-Request-Id"] == "req-123"
    assert request.query["trackingId"] == "track-1"
    assert isinstance(response, ApiResponse)
    assert response.status_code == 202
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.request_id == "req-123"
    assert response.body == {
        "payment_id": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25",
        "amount": "1.25",
        "created_at": NOW.isoformat(),
        "status": "ACCEPTED",
    }
    assert json.loads(response.to_json()) == {
        "requestId": "req-123",
        "statusCode": 202,
        "body": response.body,
        "headers": dict(response.headers),
    }

    with pytest.raises(ValueError, match="status_code"):
        json_response({"ok": True}, status_code=99)


def test_command_dispatch_result_and_health_status_are_json_safe_values() -> None:
    from token_payments.runtime import CommandDispatchResult, CommandDispatchStatus, HealthState, HealthStatus

    health = HealthStatus(
        component="runtime",
        state=HealthState.OK,
        checked_at=NOW,
        details={"apiHost": "0.0.0.0", "apiPort": 8000},
    )
    result = CommandDispatchResult.succeeded(
        command="health",
        summary="runtime config loaded",
        details={"health": health},
    )
    failed = CommandDispatchResult.failed(command="worker", summary="worker command is not wired", exit_code=78)

    assert health.to_dict() == {
        "component": "runtime",
        "state": "OK",
        "checkedAt": NOW.isoformat(),
        "details": {"apiHost": "0.0.0.0", "apiPort": 8000},
    }
    assert result.status is CommandDispatchStatus.SUCCEEDED
    assert result.exit_code == 0
    assert result.success is True
    assert result.to_dict()["details"]["health"]["state"] == "OK"
    assert failed.status is CommandDispatchStatus.FAILED
    assert failed.success is False
    assert failed.exit_code == 78

    with pytest.raises(ValueError, match="HealthStatus.component"):
        HealthStatus(component="", state=HealthState.OK, checked_at=NOW)


def test_runtime_container_protocol_and_main_entrypoint_delegate_without_starting_server(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from token_payments.runtime import (
        CommandDispatchResult,
        HealthState,
        HealthStatus,
        RuntimeConfig,
        RuntimeContainer,
        dispatch_runtime_command,
    )

    class FakeContainer:
        def __init__(self) -> None:
            self.config = RuntimeConfig.from_env({})
            self.commands: list[str] = []

        def health(self) -> HealthStatus:
            return HealthStatus(component="runtime", state=HealthState.OK, checked_at=NOW)

        def dispatch_command(self, command: str) -> CommandDispatchResult:
            self.commands.append(command)
            return CommandDispatchResult.succeeded(command=command, summary=f"{command} delegated")

    container = FakeContainer()
    result = dispatch_runtime_command(["health"], container=container)

    assert getattr(RuntimeContainer, "_is_protocol", False)
    assert isinstance(container, RuntimeContainer)
    assert container.commands == ["health"]
    assert result.command == "health"
    assert result.summary == "health delegated"

    import token_payments.__main__ as entrypoint

    delegated_argv: list[list[str]] = []

    def fake_dispatch(argv: list[str]) -> CommandDispatchResult:
        delegated_argv.append(argv)
        return CommandDispatchResult.succeeded(command="health", summary="main delegated")

    monkeypatch.setattr(entrypoint, "dispatch_runtime_command", fake_dispatch)

    assert entrypoint.main(["health"]) == 0
    assert delegated_argv == [["health"]]
    assert "main delegated" in capsys.readouterr().out


def test_runtime_and_api_public_contracts_are_exported() -> None:
    import token_payments.api as api_contracts
    import token_payments.runtime as runtime_contracts

    assert {
        "ApiRequest",
        "ApiResponse",
        "JsonValue",
        "json_response",
    } <= set(api_contracts.__all__)
    assert {
        "Clock",
        "CommandDispatchResult",
        "CommandDispatchStatus",
        "HealthState",
        "HealthStatus",
        "IdGenerator",
        "RuntimeConfig",
        "RuntimeContainer",
        "WorkerLoopOptions",
        "dispatch_runtime_command",
    } <= set(runtime_contracts.__all__)


def test_runtime_env_and_readmes_document_contract_without_secrets() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    app_readme = (ROOT / "app/README.md").read_text(encoding="utf-8")

    for key in (
        "RUNTIME_API_HOST=0.0.0.0",
        "RUNTIME_API_PORT=8000",
        "RUNTIME_REQUEST_TIMEOUT_SECONDS=30",
        "RUNTIME_WORKER_BATCH_SIZE=100",
        "RUNTIME_WORKER_POLL_INTERVAL_SECONDS=1",
        "RUNTIME_RECEIPT_POLL_INTERVAL_SECONDS=5",
    ):
        assert key in env_example

    for text in (
        "PYTHONPATH=app .venv/bin/python -m token_payments health",
        "scripts/test_runtime_contract_foundation.py",
    ):
        assert text in readme
        assert text in app_readme

    for forbidden in ("PRIVATE_KEY", "SEED_PHRASE", "API_KEY"):
        assert f"RUNTIME_{forbidden}" not in env_example


def test_domain_and_application_layers_do_not_import_runtime_api_or_adapter_implementations() -> None:
    violations: dict[str, list[str]] = {}

    for path in sorted((ROOT / "app/token_payments").rglob("*.py")):
        if not _is_domain_or_application_path(path):
            continue

        illegal = sorted(module for module in _imported_modules(path) if _is_forbidden_internal_boundary(module))
        if illegal:
            violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


def _is_domain_or_application_path(path: Path) -> bool:
    return any(parent.name in {"domain", "application"} for parent in path.parents)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _is_forbidden_internal_boundary(module_name: str) -> bool:
    return (
        module_name.startswith("token_payments.api")
        or module_name.startswith("token_payments.runtime")
        or module_name.startswith("token_payments.shared.adapter")
        or ".adapter" in module_name
    )

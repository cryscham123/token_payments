from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


API_EXPORTS = {
    "token_payments.api": {
        "AdminRoleOperatorPolicy",
        "ApiRequest",
        "ApiResponse",
        "AuthApi",
        "CheckoutApi",
        "JsonValue",
        "OperatorAccessPolicy",
        "OperatorApi",
        "OperatorClaims",
        "OrdersApi",
        "PaymentsApi",
        "json_response",
    },
    "token_payments.api.auth": {"AuthApi"},
    "token_payments.api.checkout": {"CheckoutApi"},
    "token_payments.api.orders": {"OrdersApi"},
    "token_payments.api.payments": {"PaymentsApi"},
    "token_payments.api.operator": {
        "AdminRoleOperatorPolicy",
        "OperatorAccessPolicy",
        "OperatorApi",
        "OperatorClaims",
    },
}

RUNTIME_EXPORTS = {
    "Clock",
    "CommandDispatchResult",
    "CommandDispatchStatus",
    "ContractRuntimeContainer",
    "HealthState",
    "HealthStatus",
    "IdGenerator",
    "JsonValue",
    "KafkaConsumerWorker",
    "OperatorDashboardQuery",
    "OperatorErrorSnapshot",
    "OperatorObservabilityQueryPort",
    "OperatorObservabilitySnapshot",
    "OperatorOrderSnapshot",
    "OperatorOutboxSnapshot",
    "OperatorPage",
    "OperatorPaymentSnapshot",
    "OperatorSortDirection",
    "OperatorWorkerSnapshot",
    "OutboxRelayWorker",
    "PaymentReceiptPollingWorker",
    "PaymentTimeoutCandidate",
    "PaymentTimeoutWorker",
    "PostgresOperatorObservabilityQuery",
    "RuntimeConfig",
    "RuntimeContainer",
    "WorkerBatchResult",
    "WorkerLoopOptions",
    "WorkerRunSummary",
    "WorkerRuntime",
    "dispatch_runtime_command",
}

FORBIDDEN_DOMAIN_APPLICATION_IMPORTS = (
    "token_payments.api",
    "token_payments.runtime",
    "token_payments.shared.adapter",
)


def test_api_public_exports_cover_customer_checkout_payment_and_operator_facades() -> None:
    for module_name, expected_names in API_EXPORTS.items():
        module = importlib.import_module(module_name)
        exported = set(getattr(module, "__all__", ()))

        assert expected_names <= exported, f"{module_name} missing __all__ exports: {sorted(expected_names - exported)}"
        assert all(hasattr(module, name) for name in expected_names), module_name


def test_worker_runtime_public_exports_cover_entrypoint_workers_and_observability_contracts() -> None:
    runtime = importlib.import_module("token_payments.runtime")
    exported = set(getattr(runtime, "__all__", ()))

    assert RUNTIME_EXPORTS <= exported
    assert all(hasattr(runtime, name) for name in RUNTIME_EXPORTS)
    assert getattr(runtime.RuntimeContainer, "_is_protocol", False)
    assert getattr(runtime.OperatorObservabilityQueryPort, "_is_protocol", False)


def test_cli_entrypoint_outputs_json_contract_without_starting_live_infrastructure() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "app")
    result = subprocess.run(
        [sys.executable, "-m", "token_payments", "health"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "health"
    assert payload["status"] == "SUCCEEDED"
    assert payload["exitCode"] == 0
    assert payload["details"]["health"]["state"] == "OK"


def test_cli_entrypoint_stays_a_thin_runtime_dispatcher() -> None:
    imported_modules = _imported_modules(ROOT / "app/token_payments/__main__.py")

    assert "token_payments.runtime" not in imported_modules
    assert "runtime" in imported_modules
    assert "uvicorn" not in imported_modules
    assert "click" not in imported_modules
    assert "argparse" not in imported_modules


def test_domain_and_application_layers_do_not_depend_on_api_runtime_or_adapters() -> None:
    violations: dict[str, list[str]] = {}
    for path in sorted((ROOT / "app/token_payments").rglob("*.py")):
        if not _is_domain_or_application_path(path):
            continue
        illegal = sorted(
            module
            for module in _imported_modules(path)
            if module.startswith(FORBIDDEN_DOMAIN_APPLICATION_IMPORTS) or ".adapter" in module
        )
        if illegal:
            violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


def test_env_compose_schema_and_runtime_config_are_consistent_for_local_runtime() -> None:
    env_values = _parse_env_example()
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    schema = (ROOT / "app/postgres/init.d/001-token-payments-schema.sql").read_text(encoding="utf-8")

    assert env_values["RUNTIME_API_HOST"] == "0.0.0.0"
    assert env_values["RUNTIME_API_PORT"] == "8000"
    assert env_values["RUNTIME_WORKER_BATCH_SIZE"] == env_values["ADAPTER_OUTBOX_BATCH_SIZE"] == "100"
    assert env_values["RUNTIME_WORKER_POLL_INTERVAL_SECONDS"] == env_values["ADAPTER_OUTBOX_POLL_INTERVAL_SECONDS"] == "1"
    assert env_values["TEST_NETWORK_NETWORK_ID"] == env_values["ADAPTER_BLOCKCHAIN_CHAIN_ID"] == "1337"
    assert env_values["ADAPTER_BLOCKCHAIN_RPC_URL"] == ""
    assert env_values["ADAPTER_BLOCKCHAIN_RPC_HOST"] == "test_network"
    assert env_values["ADAPTER_BLOCKCHAIN_RPC_PORT"] == "8545"

    for service_name in ("postgres", "kafka", "kafka-ui", "pgweb", "test_network"):
        assert f"{service_name}:" in compose

    for table_name in (
        "auth_users",
        "auth_login_challenges",
        "auth_sessions",
        "orders",
        "payments",
        "payment_authorizations",
        "outbox_messages",
        "processed_messages",
        "processed_commands",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in schema


def test_readmes_document_api_worker_runtime_commands_and_next_phase_candidates() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    app_readme = (ROOT / "app/README.md").read_text(encoding="utf-8")

    assert "app/README.md" in readme
    assert "애플리케이션 런타임" in readme

    for text in (
        "scripts/test_api_worker_runtime_public_contracts.py",
        "PYTHONPATH=app .venv/bin/python -m token_payments health",
        "PYTHONPATH=app .venv/bin/python -m token_payments worker",
        "AuthApi",
        "OrdersApi",
        "CheckoutApi",
        "PaymentsApi",
        "OperatorApi",
        "WorkerRuntime",
        "Frontend client implementation is outside the active backend runtime contract",
        "HTTP APIs, route manifests, and Postman/local smoke contracts",
        "docker compose integration smoke",
        "happy-path e2e checkout",
    ):
        assert text in app_readme


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


def _parse_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values

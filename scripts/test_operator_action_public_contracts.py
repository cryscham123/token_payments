from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


OPERATOR_ACTION_EXPORTS = {
    "AdminRoleOperatorActionPolicy",
    "OPERATOR_ACTION_HTTP_ROUTES",
    "OperatorActionApi",
    "OperatorActionAuditRecord",
    "OperatorActionAuditRepository",
    "OperatorActionCommand",
    "OperatorActionName",
    "OperatorActionPolicy",
    "OperatorActionResult",
    "OperatorActionResultStatus",
    "OperatorActionTarget",
    "OperatorActionTargetKind",
    "OperatorCancelOrderActionExecutor",
    "OperatorMessageReplayPort",
    "OperatorMessageReplayRequest",
    "OperatorOutboxActionExecutor",
    "OperatorOutboxActionPortResult",
    "OperatorOutboxActionStatus",
    "OperatorOutboxRetryPort",
    "OperatorOutboxRetryRequest",
    "register_operator_action_routes",
}

PHASE_7_OPERATION_IDS = {
    "requestLoginChallenge",
    "loginWithMetaMask",
    "refreshSession",
    "logout",
    "getCurrentUser",
    "createOrder",
    "getCheckoutTrackingByTrackingId",
    "getCheckoutTrackingByOrderId",
    "submitTransactionHash",
    "getOperatorDashboard",
    "getOperatorOrderDetail",
    "getOperatorPaymentDetail",
    "getOperatorOutboxDetail",
}

PHASE_8_OPERATION_IDS = {
    "cancelOperatorOrder",
    "retryOperatorOutboxMessage",
    "replayOperatorMessage",
}

FRAMEWORK_AND_INFRA_CLIENT_ROOTS = {
    "aiohttp",
    "asyncpg",
    "confluent_kafka",
    "django",
    "fastapi",
    "flask",
    "httpx",
    "kafka",
    "psycopg",
    "psycopg2",
    "requests",
    "sqlalchemy",
    "starlette",
    "uvicorn",
}


def test_operator_action_api_contracts_policy_routes_and_register_helper_are_public_exports() -> None:
    import token_payments.api as api

    exported = set(api.__all__)

    assert OPERATOR_ACTION_EXPORTS <= exported
    assert all(hasattr(api, name) for name in OPERATOR_ACTION_EXPORTS)
    assert api.OPERATOR_ACTION_HTTP_ROUTES["cancel_order"].operation_id == "cancelOperatorOrder"
    assert callable(api.register_operator_action_routes)
    assert getattr(api.OperatorActionPolicy, "_is_protocol", False)
    assert getattr(api.OperatorActionAuditRepository, "_is_protocol", False)
    assert getattr(api.OperatorOutboxRetryPort, "_is_protocol", False)
    assert getattr(api.OperatorMessageReplayPort, "_is_protocol", False)


def test_http_route_manifest_keeps_existing_routes_and_adds_store_owner_inventory_routes() -> None:
    from token_payments.api import http_route_manifest, list_http_route_specs

    manifest = list(http_route_manifest())
    specs = list(list_http_route_specs())
    operation_ids = [entry["operationId"] for entry in manifest]

    assert len(manifest) == 21
    assert len(operation_ids) == len(set(operation_ids))
    assert PHASE_7_OPERATION_IDS <= set(operation_ids)
    assert PHASE_8_OPERATION_IDS <= set(operation_ids)
    assert {
        "listStoreOwnerInventory",
        "increaseStoreOwnerInventoryStock",
        "correctStoreOwnerInventoryStock",
        "pauseStoreOwnerInventorySales",
        "resumeStoreOwnerInventorySales",
    } <= set(operation_ids)
    assert operation_ids[-3:] == [
        "cancelOperatorOrder",
        "retryOperatorOutboxMessage",
        "replayOperatorMessage",
    ]
    assert [(entry["method"], entry["path"]) for entry in manifest] == [
        (spec.method, spec.path) for spec in specs
    ]


def test_operator_action_modules_avoid_web_framework_kafka_and_postgres_clients() -> None:
    action_boundary_files = (
        ROOT / "app/token_payments/api/operator_actions.py",
        ROOT / "app/token_payments/api/http.py",
    )
    violations: dict[str, list[str]] = {}

    for path in action_boundary_files:
        illegal = sorted(
            module
            for module in _imported_modules(path)
            if module.split(".", 1)[0] in FRAMEWORK_AND_INFRA_CLIENT_ROOTS
        )
        if illegal:
            violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


def test_existing_api_runtime_ui_and_e2e_public_contract_imports_still_resolve() -> None:
    modules = (
        "token_payments",
        "token_payments.api",
        "token_payments.api.auth",
        "token_payments.api.checkout",
        "token_payments.api.http",
        "token_payments.api.operator",
        "token_payments.api.operator_actions",
        "token_payments.api.orders",
        "token_payments.api.payments",
        "token_payments.runtime",
        "token_payments.runtime.smoke",
        "token_payments.ui",
        "token_payments.ui.preview",
        "token_payments.contexts.order.application",
        "token_payments.contexts.order.adapter",
    )

    for module_name in modules:
        module = importlib.import_module(module_name)
        assert module is not None


def test_readmes_document_operator_action_endpoint_verification_and_phase_boundaries() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    app_readme = (ROOT / "app/README.md").read_text(encoding="utf-8")

    for text in (
        "scripts/test_operator_action_public_contracts.py",
        "scripts/test_operator_action_http_routes.py",
        "cancel/retry/replay operator actions",
        "bounded framework-neutral endpoint contract",
        "live Docker/Kafka publish is not started automatically",
        "ASGI/FastAPI thin adapter",
        "live Docker compose integration",
        "operator action UI wiring",
    ):
        assert text in readme
        assert text in app_readme


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules

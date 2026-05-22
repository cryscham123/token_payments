from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_inventory_application_uses_actor_role_dto_not_auth_domain_enum() -> None:
    for relative_path in (
        "app/token_payments/contexts/inventory/application/commands.py",
        "app/token_payments/contexts/inventory/application/ports.py",
    ):
        imports = _imported_names(ROOT / relative_path)

        assert "token_payments.contexts.auth.domain.UserRole" not in imports
        assert "token_payments.contexts.auth.domain" not in imports


def test_store_catalog_application_service_depends_on_ports_not_auth_or_payment_domain_objects() -> None:
    imports = _imported_names(ROOT / "app/token_payments/contexts/store_catalog/application/service.py")

    forbidden = {
        "token_payments.contexts.auth.domain",
        "token_payments.contexts.auth.domain.User",
        "token_payments.contexts.auth.domain.UserRole",
        "token_payments.contexts.auth.domain.GroupId",
        "token_payments.contexts.payment.domain",
        "token_payments.contexts.payment.domain.PaymentAsset",
        "token_payments.contexts.payment.domain.PaymentAssetRegistry",
    }

    assert imports.isdisjoint(forbidden)


def test_order_postgres_tracking_mapper_uses_order_owned_snapshots_for_payment_request_and_gas() -> None:
    imports = _imported_names(ROOT / "app/token_payments/contexts/order/adapter/postgres.py")

    assert "token_payments.contexts.payment.domain.GasEstimate" not in imports
    assert "token_payments.contexts.payment.domain.TransactionSignatureRequest" not in imports


def test_order_application_tracking_contract_exports_snapshot_dtos() -> None:
    from token_payments.contexts.order.application.queries import GasEstimateSnapshot, PaymentRequestSnapshot

    assert GasEstimateSnapshot.__module__ == "token_payments.contexts.order.application.queries"
    assert PaymentRequestSnapshot.__module__ == "token_payments.contexts.order.application.queries"


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module = "." * node.level + node.module if node.level else node.module
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names

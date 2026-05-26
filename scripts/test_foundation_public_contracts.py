from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_foundation_runtime_and_context_packages_are_importable() -> None:
    modules = [
        "token_payments",
        "token_payments.__main__",
        "token_payments.shared.domain",
        "token_payments.contexts.auth.domain",
        "token_payments.contexts.auth.application",
        "token_payments.contexts.order.domain",
        "token_payments.contexts.checkout.application",
        "token_payments.contexts.inventory.domain",
        "token_payments.contexts.inventory.application",
        "token_payments.contexts.inventory.adapter",
        "token_payments.contexts.payment.domain",
        "token_payments.contexts.payment.application",
        "token_payments.contexts.payment.adapter",
        "token_payments.contexts.store_approval.domain",
        "token_payments.contexts.store_approval.application",
        "token_payments.contexts.store_approval.adapter",
    ]

    for module_name in modules:
        assert importlib.import_module(module_name), f"{module_name} must be importable"


def test_foundation_public_contracts_are_exported_from_package_boundaries() -> None:
    contract_names = {
        "token_payments.shared.domain": {
            "OrderId",
            "PaymentId",
            "WalletAddress",
            "Crypto",
            "CheckoutEventName",
            "CheckoutCommandName",
            "OutboxMessage",
            "ProcessedMessage",
            "ProcessedCommand",
        },
        "token_payments.contexts.auth.domain": {
            "User",
            "LoginChallenge",
            "AuthSession",
            "AuthNonce",
            "LoginFailureReason",
        },
        "token_payments.contexts.auth.application": {
            "AuthUseCase",
            "UserRepository",
            "LoginChallengeRepository",
            "AuthSessionRepository",
            "WalletSignatureVerifier",
            "TokenIssuer",
        },
        "token_payments.contexts.order.domain": {
            "Order",
            "OrderItem",
            "Customer",
            "Store",
            "Product",
            "OrderCreatedEvent",
            "OrderPaidEvent",
            "OrderCancelledEvent",
        },
        "token_payments.contexts.checkout.application": {
            "CheckoutProcessManager",
            "CheckoutProcessEvent",
            "CheckoutCommandDecision",
        },
    }

    for module_name, names in contract_names.items():
        module = importlib.import_module(module_name)
        exported = set(getattr(module, "__all__", ()))
        assert names <= exported, f"{module_name} is missing exports: {sorted(names - exported)}"


def test_root_readme_lists_executable_workspace_entrypoint_commands_and_doc_owners() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for command in [
        "python3 -m venv .venv",
        ".venv/bin/python -m pip install -r requirements-dev.txt",
        ".venv/bin/python scripts/validate_phases.py",
        ".venv/bin/python -m pytest scripts/test_*.py",
        "python3 .githooks/pre_commit_check.py",
        "python3 scripts/execute.py <phase-dir>",
        "PYTHONPATH=app .venv/bin/python -m token_payments",
    ]:
        assert command in readme

    for owner_doc in [
        "docs/PRD.md",
        "docs/ARCHITECTURE.md",
        "docs/DOMAIN_MODEL.md",
        "docs/API_SPEC.md",
        "app/README.md",
        "docs/HARNESS.md",
    ]:
        assert owner_doc in readme
    assert "root README에는 phase별 완료 로그" in readme

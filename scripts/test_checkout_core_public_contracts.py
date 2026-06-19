from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


CHECKOUT_CORE_EXPORTS = {
    "token_payments.contexts.inventory.domain": {
        "InventoryConfirmedEvent",
        "InventoryEvent",
        "InventoryReleasedEvent",
        "InventoryReservation",
        "InventoryReservedEvent",
        "ProductInventory",
        "Quantity",
        "ReservationExpiredEvent",
        "ReservationId",
        "ReservationStatus",
        "StockDecreasedEvent",
        "StockIncreasedEvent",
    },
    "token_payments.contexts.inventory.application": {
        "ConfirmInventoryCommand",
        "InventoryCommandHandler",
        "InventoryCommandRejected",
        "InventoryCommandRejectionReason",
        "InventoryCommandResult",
        "InventoryCommandStatus",
        "InventoryRepository",
        "OutboxMessageRepository",
        "ProcessedCommandRepository",
        "ReleaseInventoryCommand",
        "ReserveInventoryCommand",
    },
    "token_payments.contexts.payment.domain": {
        "AuthorizationStatus",
        "GasEstimate",
        "Payment",
        "PaymentAuthorization",
        "PaymentConfirmedEvent",
        "PaymentEvent",
        "PaymentExpiredEvent",
        "PaymentFailedEvent",
        "PaymentProcessingStartedEvent",
        "PaymentRefundedEvent",
        "PaymentStatus",
        "TransactionReceipt",
        "TransactionSignatureRequest",
    },
    "token_payments.contexts.payment.application": {
        "BlockchainAdapter",
        "ConfirmPaymentReceiptCommand",
        "ExpireAwaitingSignatureCommand",
        "InitiatePaymentCommand",
        "OutboxMessageRepository",
        "PaymentAuthorizationRepository",
        "PaymentCommandHandler",
        "PaymentCommandRejected",
        "PaymentCommandRejectionReason",
        "PaymentCommandResult",
        "PaymentCommandStatus",
        "PaymentRepository",
        "PaymentTimeoutScheduler",
        "ProcessedCommandRepository",
        "RefundPaymentCommand",
        "SubmitTransactionHashCommand",
        "TransactionService",
    },
    "token_payments.contexts.store_approval.domain": {
        "ApprovalStatus",
        "OrderApprovedEvent",
        "OrderDetail",
        "OrderRejectedEvent",
        "Product",
        "Store",
        "StoreApprovalEvent",
    },
    "token_payments.contexts.store_approval.application": {
        "OrderDetailRepository",
        "OutboxMessageRepository",
        "ProcessedCommandRepository",
        "RequestStoreApprovalCommand",
        "StoreApprovalRejected",
        "StoreApprovalRejectionReason",
        "StoreApprovalResult",
        "StoreApprovalResultStatus",
        "StoreApprovalService",
        "StoreRepository",
    },
}

CHECKOUT_CORE_LAYER_PATHS = (
    ROOT / "app/token_payments/contexts/inventory/domain",
    ROOT / "app/token_payments/contexts/inventory/application",
    ROOT / "app/token_payments/contexts/payment/domain",
    ROOT / "app/token_payments/contexts/payment/application",
    ROOT / "app/token_payments/contexts/store_approval/domain",
    ROOT / "app/token_payments/contexts/store_approval/application",
)

FORBIDDEN_ADAPTER_IMPORT_ROOTS = {
    "blockchain",
    "kafka",
    "metamask",
    "psycopg",
    "requests",
    "sqlalchemy",
    "web3",
}


def test_checkout_core_public_exports_cover_domain_and_application_contracts() -> None:
    for module_name, expected_names in CHECKOUT_CORE_EXPORTS.items():
        module = importlib.import_module(module_name)
        exported = set(getattr(module, "__all__", ()))

        missing_exports = expected_names - exported
        missing_attributes = {name for name in expected_names if not hasattr(module, name)}

        assert missing_exports == set(), f"{module_name} is missing __all__ exports: {sorted(missing_exports)}"
        assert missing_attributes == set(), f"{module_name} is missing public attributes: {sorted(missing_attributes)}"


def test_checkout_core_application_ports_are_protocol_boundaries() -> None:
    inventory_application = importlib.import_module("token_payments.contexts.inventory.application")
    payment_application = importlib.import_module("token_payments.contexts.payment.application")
    store_approval_application = importlib.import_module("token_payments.contexts.store_approval.application")

    ports = (
        inventory_application.InventoryRepository,
        inventory_application.ProcessedCommandRepository,
        inventory_application.OutboxMessageRepository,
        payment_application.PaymentRepository,
        payment_application.PaymentAuthorizationRepository,
        payment_application.ProcessedCommandRepository,
        payment_application.OutboxMessageRepository,
        payment_application.BlockchainAdapter,
        payment_application.PaymentTimeoutScheduler,
        payment_application.TransactionService,
        store_approval_application.StoreRepository,
        store_approval_application.OrderDetailRepository,
        store_approval_application.ProcessedCommandRepository,
        store_approval_application.OutboxMessageRepository,
    )

    for port in ports:
        assert getattr(port, "_is_protocol", False), f"{port.__module__}.{port.__name__} must be a Protocol"


def test_checkout_core_layers_do_not_import_adapters_or_external_clients() -> None:
    violations: dict[str, list[str]] = {}
    for layer_path in CHECKOUT_CORE_LAYER_PATHS:
        for path in sorted(layer_path.glob("**/*.py")):
            imported_modules = _imported_modules(path)
            illegal = sorted(module for module in imported_modules if _is_forbidden_dependency(module))
            if illegal:
                violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


def test_checkout_core_message_names_are_ready_for_process_manager_and_adapters() -> None:
    from token_payments.shared.domain import CheckoutCommandName, CheckoutEventName, CommandId, OrderId

    order_id = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")

    assert {event.value for event in CheckoutEventName} >= {
        "OrderCancelledEvent",
        "InventoryReservedEvent",
        "PaymentConfirmedEvent",
        "PaymentFailedEvent",
        "PaymentExpiredEvent",
        "OrderApprovedEvent",
        "OrderRejectedEvent",
    }
    assert {command.value for command in CheckoutCommandName} >= {
        "ReserveInventoryCommand",
        "InitiatePaymentCommand",
        "RequestStoreApprovalCommand",
        "ReleaseInventoryCommand",
        "RefundPaymentCommand",
        "CancelOrderCommand",
    }
    assert str(CommandId.for_order_action(order_id, CheckoutCommandName.RELEASE_INVENTORY)) == (
        f"{order_id}:ReleaseInventoryCommand"
    )
    assert str(CommandId.for_order_action(order_id, CheckoutCommandName.REFUND_PAYMENT)) == (
        f"{order_id}:RefundPaymentCommand"
    )


def test_checkout_adapter_preserves_variant_inventory_targets_from_order_items() -> None:
    from token_payments.contexts.checkout.adapter.kafka import _inventory_command_targets
    from token_payments.shared.domain import CheckoutCommandName

    payload = {
        "storeId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24",
        "items": [
            {
                "productId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25",
                "publicVariantId": "hoodie-l",
                "orderLineKey": "line-hoodie-l-premium",
                "quantity": 2,
            }
        ],
    }
    reservation_targets = _inventory_command_targets(
        CheckoutCommandName.RESERVE_INVENTORY,
        payload,
    )
    confirmation_targets = _inventory_command_targets(CheckoutCommandName.CONFIRM_INVENTORY, payload)

    expected_target = (
        {
            "productId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25",
            "storeId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24",
            "publicVariantId": "hoodie-l",
            "orderLineKey": "line-hoodie-l-premium",
            "quantity": 2,
        },
    )
    assert reservation_targets == expected_target
    assert confirmation_targets == expected_target


def test_checkout_adapter_combines_quantities_for_duplicate_inventory_targets() -> None:
    from token_payments.contexts.checkout.adapter.kafka import _inventory_command_targets
    from token_payments.shared.domain import CheckoutCommandName

    targets = _inventory_command_targets(
        CheckoutCommandName.RESERVE_INVENTORY,
        {
            "storeId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24",
            "items": [
                {
                    "productId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25",
                    "publicVariantId": "hoodie-l",
                    "orderLineKey": "line-1",
                    "quantity": 2,
                },
                {
                    "productId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25",
                    "publicVariantId": "hoodie-l",
                    "orderLineKey": "line-2",
                    "quantity": 1,
                },
            ],
        },
    )

    assert targets == (
        {
            "productId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25",
            "storeId": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24",
            "publicVariantId": "hoodie-l",
            "quantity": 3,
        },
    )


def test_public_docs_document_checkout_core_contracts_and_adapter_boundaries() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "docs" / "DOMAIN_MODEL.md",
            ROOT / "docs" / "ARCHITECTURE.md",
            ROOT / "app" / "README.md",
        )
    )

    for phrase in (
        "ProductInventory",
        "PaymentAuthorization",
        "StoreApprovalRequestListener",
        "OutboxMessageRepository",
        "PostgreSQL repositories",
        "outbox relay",
        "Kafka consumer",
        "Blockchain RPC",
        "MetaMask client",
    ):
        assert phrase in docs


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _is_forbidden_dependency(module_name: str) -> bool:
    parts = module_name.split(".")
    return parts[0] in FORBIDDEN_ADAPTER_IMPORT_ROOTS or "adapter" in parts

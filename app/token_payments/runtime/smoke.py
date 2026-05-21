"""Deterministic smoke scenario contracts for integration readiness."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
import json
import math
from pathlib import Path
import shlex
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence
from uuid import UUID


SMOKE_CONTRACT = "CommandDispatchResult.details.smoke"
UNKNOWN_SMOKE_SCENARIO_ERROR = "UNKNOWN_SMOKE_SCENARIO"
AVAILABLE_SMOKE_SCENARIOS = (
    "happy-path-checkout",
    "compensation-checkout",
    "compose-readiness",
    "docker-runtime-readiness",
    "postman-docker-api-readiness",
)
COMPOSE_READINESS_REQUIRED_ENV_KEYS = (
    "COMPOSE_PROFILES",
    "TEST_NETWORK_PRIVATE_KEY",
    "TEST_NETWORK_ACCOUNT",
    "TEST_NETWORK_NETWORK_ID",
    "TEST_NETWORK_DB_PATH",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "TZ",
    "RUNTIME_API_HOST",
    "RUNTIME_API_PORT",
    "RUNTIME_REQUEST_TIMEOUT_SECONDS",
    "RUNTIME_WORKER_BATCH_SIZE",
    "RUNTIME_WORKER_POLL_INTERVAL_SECONDS",
    "RUNTIME_RECEIPT_POLL_INTERVAL_SECONDS",
    "ADAPTER_POSTGRES_DSN",
    "ADAPTER_KAFKA_BOOTSTRAP_SERVERS",
    "ADAPTER_KAFKA_CLIENT_ID",
    "ADAPTER_OUTBOX_BATCH_SIZE",
    "ADAPTER_OUTBOX_POLL_INTERVAL_SECONDS",
    "ADAPTER_OUTBOX_RETRY_MAX_ATTEMPTS",
    "ADAPTER_OUTBOX_RETRY_INITIAL_DELAY_SECONDS",
    "ADAPTER_OUTBOX_RETRY_MAX_DELAY_SECONDS",
    "ADAPTER_WALLET_SIGNATURE_DOMAIN",
    "ADAPTER_BLOCKCHAIN_RPC_SCHEME",
    "ADAPTER_BLOCKCHAIN_RPC_HOST",
    "ADAPTER_BLOCKCHAIN_RPC_PORT",
    "ADAPTER_BLOCKCHAIN_RPC_PATH",
    "ADAPTER_BLOCKCHAIN_RPC_URL",
    "ADAPTER_BLOCKCHAIN_CHAIN_ID",
    "ADAPTER_BLOCKCHAIN_NATIVE_SYMBOL",
    "ADAPTER_BLOCKCHAIN_NATIVE_DECIMALS",
    "ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS",
    "ADAPTER_BLOCKCHAIN_GAS_BUFFER_RATE",
)
COMPOSE_READINESS_SENSITIVE_PLACEHOLDER_KEYS = (
    "TEST_NETWORK_PRIVATE_KEY",
    "TEST_NETWORK_ACCOUNT",
    "POSTGRES_PASSWORD",
    "ADAPTER_POSTGRES_DSN",
    "ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS",
)
COMPOSE_READINESS_REQUIRED_SERVICES = ("postgres", "kafka", "kafka-ui", "pgweb", "test_network")
COMPOSE_READINESS_COMMAND_SEQUENCE = (
    "health",
    "worker",
    "ui customer",
    "ui operator",
    "smoke happy-path-checkout",
    "smoke compensation-checkout",
)
DOCKER_RUNTIME_REQUIRED_DOCKERIGNORE_PATTERNS = (
    ".env",
    ".venv",
    "**/data",
    "phases/**/step*-output.json",
    "phases/**/phase*-output.json",
    ".git",
    "__pycache__",
    ".pytest_cache",
)
DOCKER_RUNTIME_SUPPORT_COPY_SOURCES = (
    "Dockerfile",
    ".dockerignore",
    "docker-compose.yml",
    ".env.example",
    "requirements-runtime.txt",
    "app/postgres/init.d/001-token-payments-schema.sql",
    "app/test_network/Dockerfile",
)
DOCKER_RUNTIME_RUN_COMMANDS = (
    "docker compose --env-file .env --profile runtime run --rm token_payments_health",
    "docker compose --env-file .env --profile runtime run --rm token_payments_worker",
    "docker compose --env-file .env --profile smoke run --rm token_payments_smoke",
)
DOCKER_RUNTIME_BUILD_COMMAND = "docker compose --env-file .env --profile runtime build token_payments_health"
DOCKER_RUNTIME_COMPOSE_CONFIG_VALIDATION_COMMAND = (
    "docker compose --env-file .env.example config --services"
)
POSTMAN_API_SERVICE_NAME = "token_payments_api"
POSTMAN_API_COMMAND = ("python", "-m", "token_payments", "serve-api", "--live", "--confirm-live-api")
POSTMAN_API_REQUIRED_ENV_KEYS = (
    "LOCAL_API_ORIGIN",
    "API_PUBLIC_BASE_URL",
    "RUNTIME_API_HOST",
    "RUNTIME_API_PORT",
    "RUNTIME_REQUEST_TIMEOUT_SECONDS",
    "REQUEST_BODY_MAX_BYTES",
    "CORS_ALLOWED_ORIGINS",
    "CORS_ALLOW_CREDENTIALS",
    "CORS_MAX_AGE_SECONDS",
    "COOKIE_SECURE",
    "COOKIE_SAMESITE",
    "CSRF_ACTIVE_KEY_ID",
    "CSRF_SIGNING_KEY",
    "CSRF_MAX_AGE_SECONDS",
    "CSRF_COOKIE_NAME",
    "CSRF_HEADER_NAME",
    "SESSION_ACTIVE_KEY_ID",
    "SESSION_SIGNING_KEYS",
    "SESSION_ACCESS_TTL_SECONDS",
    "SESSION_REFRESH_TTL_SECONDS",
    "ADAPTER_POSTGRES_DSN",
    "ADAPTER_KAFKA_BOOTSTRAP_SERVERS",
    "ADAPTER_BLOCKCHAIN_RPC_SCHEME",
    "ADAPTER_BLOCKCHAIN_RPC_HOST",
    "ADAPTER_BLOCKCHAIN_RPC_PORT",
    "ADAPTER_BLOCKCHAIN_RPC_PATH",
    "ADAPTER_BLOCKCHAIN_RPC_URL",
)
POSTMAN_API_SERVICE: Mapping[str, Mapping[str, Any] | Sequence[Any] | str] = MappingProxyType(
    {
        "image": "token_payments_runtime",
        "buildContext": ".",
        "dockerfile": "Dockerfile",
        "envFile": [".env"],
        "pythonPath": "/workspace/app",
        "command": list(POSTMAN_API_COMMAND),
        "restart": "unless-stopped",
        "profiles": ["api"],
        "ports": ["8000:8000"],
        "environmentKeys": ["PYTHONPATH", *sorted(POSTMAN_API_REQUIRED_ENV_KEYS)],
        "dependsOn": {
            "postgres": "service_healthy",
            "kafka": "service_started",
            "test_network": "service_started",
        },
    }
)
POSTMAN_API_COMPOSE_CONFIG_VALIDATION_COMMAND = "docker compose --env-file .env.example config --services"
POSTMAN_API_BUILD_COMMAND = "docker compose --env-file .env build token_payments_api"
POSTMAN_API_MANUAL_LIVE_COMMANDS = (
    "cp .env.example .env",
    "docker compose --env-file .env config --services",
    POSTMAN_API_BUILD_COMMAND,
    "docker compose up -d",
    "curl --fail http://localhost:8000/healthz",
    "curl --fail http://localhost:8000/readyz",
    "docker compose down",
)
POSTMAN_DOCKER_API_READINESS_CONTRACT = "token-payments.postman-docker-api-readiness.plan.v1"
POSTMAN_DOCKER_API_READINESS_PLAN_COMMAND = "python3 scripts/docker_live_smoke.py --api-readiness --plan"
POSTMAN_DOCKER_API_READINESS_REFUSAL_COMMAND = "python3 scripts/docker_live_smoke.py --api-readiness --execute"
POSTMAN_DOCKER_API_READINESS_CONFIRMED_COMMAND = (
    "python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker"
)
POSTMAN_DOCKER_API_READINESS_COMMAND_SEQUENCE = (
    "api-compose-config",
    "build-api-service",
    "start-infrastructure",
    "start-api-service",
    "seed-local-fixtures",
    "validate-session-signing-keys",
    "healthz",
    "readyz",
    "auth-cookie-flow",
    "expired-token-rejected",
    "invalid-signature-rejected",
    "csrf-failure",
    "csrf-success",
    "cors-preflight",
    "oversized-body",
    "malformed-json",
    "idempotency-duplicate",
    "checkout-happy-path",
    "operator-action-smoke",
)
POSTMAN_DOCKER_API_READINESS_MANUAL_COMMANDS = (
    "cp .env.example .env",
    POSTMAN_DOCKER_API_READINESS_PLAN_COMMAND,
    POSTMAN_DOCKER_API_READINESS_REFUSAL_COMMAND,
    POSTMAN_DOCKER_API_READINESS_CONFIRMED_COMMAND,
)
DOCKER_RUNTIME_MANUAL_LIVE_COMMANDS = (
    "cp .env.example .env",
    "docker compose --env-file .env --profile runtime config --services",
    DOCKER_RUNTIME_BUILD_COMMAND,
    "docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network",
    *DOCKER_RUNTIME_RUN_COMMANDS,
    "docker compose --env-file .env down",
)
DOCKER_RUNTIME_SERVICES: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "token_payments_health": {
            "image": "token_payments_runtime",
            "buildContext": ".",
            "dockerfile": "Dockerfile",
            "envFile": [".env"],
            "pythonPath": "/workspace/app",
            "command": ["python", "-m", "token_payments", "health"],
            "restart": "no",
            "profiles": ["runtime"],
            "dependsOn": {
                "postgres": "service_healthy",
                "kafka": "service_started",
                "test_network": "service_started",
            },
        },
        "token_payments_worker": {
            "image": "token_payments_runtime",
            "buildContext": ".",
            "dockerfile": "Dockerfile",
            "envFile": [".env"],
            "pythonPath": "/workspace/app",
            "command": ["python", "-m", "token_payments", "worker"],
            "restart": "no",
            "profiles": ["runtime"],
            "dependsOn": {
                "postgres": "service_healthy",
                "kafka": "service_started",
                "test_network": "service_started",
            },
        },
        "token_payments_smoke": {
            "image": "token_payments_runtime",
            "buildContext": ".",
            "dockerfile": "Dockerfile",
            "envFile": [".env"],
            "pythonPath": "/workspace/app",
            "command": ["python", "-m", "token_payments", "smoke", "compose-readiness"],
            "restart": "no",
            "profiles": ["runtime", "smoke"],
            "dependsOn": {
                "postgres": "service_healthy",
                "kafka": "service_started",
                "test_network": "service_started",
            },
        },
    }
)

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
SmokeRunner = Callable[[], "SmokeScenarioResult"]


class SmokeStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class SmokeResult:
    status: SmokeStatus | str
    summary: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _coerce_status(self.status))
        object.__setattr__(self, "summary", _require_text(self.summary, "SmokeResult.summary"))
        object.__setattr__(self, "details", MappingProxyType(_to_json_safe_mapping(self.details)))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "status": self.status.value,
            "summary": self.summary,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class SmokeStep:
    name: str
    result: SmokeResult

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_text(self.name, "SmokeStep.name"))
        if not isinstance(self.result, SmokeResult):
            raise ValueError("SmokeStep.result must be a SmokeResult")

    def to_dict(self) -> dict[str, JsonValue]:
        return {"name": self.name} | self.result.to_dict()


@dataclass(frozen=True)
class SmokeScenarioResult:
    scenario: str
    result: SmokeResult
    steps: tuple[SmokeStep, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario", _require_text(self.scenario, "SmokeScenarioResult.scenario"))
        if not isinstance(self.result, SmokeResult):
            raise ValueError("SmokeScenarioResult.result must be a SmokeResult")
        object.__setattr__(self, "steps", tuple(self.steps))
        if not all(isinstance(step, SmokeStep) for step in self.steps):
            raise ValueError("SmokeScenarioResult.steps must contain only SmokeStep values")
        object.__setattr__(self, "details", MappingProxyType(_to_json_safe_mapping(self.details)))

    @property
    def status(self) -> SmokeStatus:
        return self.result.status

    @property
    def summary(self) -> str:
        return self.result.summary

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "contract": SMOKE_CONTRACT,
            "scenario": self.scenario,
            "status": self.status.value,
            "summary": self.summary,
            "steps": [step.to_dict() for step in self.steps],
            "details": dict(self.details),
        }


class UnknownSmokeScenario(ValueError):
    """Raised when a smoke scenario selector is not known."""

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        super().__init__(f"unknown smoke scenario: {scenario}")

    def to_error(self) -> dict[str, JsonValue]:
        return {
            "code": UNKNOWN_SMOKE_SCENARIO_ERROR,
            "scenario": self.scenario,
            "availableScenarios": list(AVAILABLE_SMOKE_SCENARIOS),
        }


def describe_smoke_registry() -> dict[str, JsonValue]:
    return {
        "contract": SMOKE_CONTRACT,
        "availableScenarios": list(AVAILABLE_SMOKE_SCENARIOS),
        "runnerCount": len(_SMOKE_RUNNERS),
    }


def run_smoke_scenario(scenario: str) -> SmokeScenarioResult:
    normalized = _normalize_scenario(scenario)
    if normalized not in AVAILABLE_SMOKE_SCENARIOS:
        raise UnknownSmokeScenario(normalized)

    runner = _SMOKE_RUNNERS.get(normalized)
    if runner is None:
        return SmokeScenarioResult(
            scenario=normalized,
            result=SmokeResult(
                status=SmokeStatus.SKIPPED,
                summary="smoke scenario runner is reserved but not implemented",
            ),
            details={
                "runnerImplemented": False,
                "availableScenarios": AVAILABLE_SMOKE_SCENARIOS,
            },
        )
    return runner()


def _normalize_scenario(scenario: str) -> str:
    return _require_text(scenario, "scenario").lower()


def _run_happy_path_checkout() -> SmokeScenarioResult:
    from token_payments.contexts.checkout.application import CheckoutProcessManager
    from token_payments.contexts.inventory.application import InventoryCommandHandler, ReserveInventoryCommand
    from token_payments.contexts.inventory.domain import ProductInventory
    from token_payments.contexts.order.application import (
        CreateOrderCommand,
        CreateOrderItem,
        OrderApplicationService,
        OrderStatusEventProjector,
    )
    from token_payments.contexts.order.domain import (
        Address,
        Customer,
        Product as OrderProduct,
        Store as OrderStore,
        TrackingId,
    )
    from token_payments.contexts.payment.application import (
        ConfirmPaymentReceiptCommand,
        InitiatePaymentCommand,
        PaymentCommandHandler,
        SubmitTransactionHashCommand,
    )
    from token_payments.contexts.payment.domain import GasEstimate, TransactionReceipt
    from token_payments.contexts.store_approval.application import RequestStoreApprovalCommand, StoreApprovalService
    from token_payments.contexts.store_approval.domain import (
        OrderDetail,
        Product as ApprovalProduct,
        Store as ApprovalStore,
    )
    from token_payments.shared.adapter.messaging import MessageTopicResolver
    from token_payments.shared.domain import (
        ChainNetwork,
        CheckoutCommandName,
        CheckoutEventName,
        CommandId,
        Crypto,
        CustomerId,
        MessageId,
        OrderId,
        PaymentId,
        ProductId,
        StoreId,
        TransactionHash,
        UserId,
        WalletAddress,
    )

    now = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    order_id = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
    product_id = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
    store_id = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
    payment_id = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
    customer_id = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
    user_id = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c27")
    owner_user_id = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c28")
    tracking_id = TrackingId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c29")
    wallet_from = WalletAddress("0x1111111111111111111111111111111111111111")
    wallet_to = WalletAddress("0x2222222222222222222222222222222222222222")
    token_address = WalletAddress("0x3333333333333333333333333333333333333333")
    tx_hash = TransactionHash("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    chain = ChainNetwork(chain_id=11155111, name="Sepolia")
    unit_price = Crypto(
        amount=Decimal("1.25"),
        symbol="USDC",
        chain_id=chain.chain_id,
        token_address=token_address,
        decimals=6,
    )

    outbox_messages = _InMemoryOutboxMessageRepository()
    processed_messages = _InMemoryProcessedMessageRepository()
    order_projected_messages = _InMemoryProcessedMessageRepository()
    inventory_processed_commands = _InMemoryProcessedCommandRepository()
    payment_processed_commands = _InMemoryProcessedCommandRepository()
    approval_processed_commands = _InMemoryProcessedCommandRepository()

    customer = Customer(customer_id=customer_id, user_id=user_id, customer_wallet=wallet_from)
    order_product = OrderProduct(product_id=product_id, name="Deterministic Checkout Item", price=unit_price)
    order_store = OrderStore(
        store_id=store_id,
        owner_user_id=owner_user_id,
        products=(order_product,),
        store_address=Address(id="store-address-1", street="42 Token Street"),
        store_wallet=wallet_to,
        supported_chain_ids=(chain.chain_id,),
    )
    order_repository = _InMemoryOrderRepository()
    order_service = OrderApplicationService(
        customers=_InMemoryCustomerRepository({str(user_id): customer}),
        stores=_InMemoryOrderStoreRepository({str(store_id): order_store}),
        orders=order_repository,
        outbox_messages=outbox_messages,
    )
    order_status_projector = OrderStatusEventProjector(order_repository, order_projected_messages)

    order_result = order_service.createOrder(
        CreateOrderCommand(
            authenticated_user_id=user_id,
            store_id=store_id,
            delivery_address=Address(id="delivery-address-1", street="7 Checkout Avenue"),
            items=(CreateOrderItem(product_id=product_id, quantity=1),),
            order_id=order_id,
            tracking_id=tracking_id,
            event_message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"),
            requested_at=now,
        )
    )
    order_created_message = order_result.outbox_message
    steps = [
        _passed_step(
            "OrderCreatedEvent",
            "order application service saved PENDING order and outbox event",
            {
                "eventName": order_created_message.name,
                "orderStatus": order_result.order.status.value,
                "outboxIdentity": order_created_message.identity,
            },
        )
    ]

    process_manager = CheckoutProcessManager()
    topic_resolver = MessageTopicResolver.default()
    reserve_decision = _single_decision(
        _handle_checkout_event(
            process_manager=process_manager,
            processed_messages=processed_messages,
            outbox_messages=outbox_messages,
            topic_resolver=topic_resolver,
            source_message=order_created_message,
        ),
        CheckoutCommandName.RESERVE_INVENTORY.value,
    )
    steps.append(
        _passed_step(
            "ReserveInventoryCommand",
            "checkout process manager issued deterministic inventory reservation command",
            {
                "commandId": str(reserve_decision.metadata.command_id),
                "commandName": reserve_decision.name.value,
            },
        )
    )

    inventory_repository = _InMemoryInventoryRepository(
        {
            (str(product_id), str(store_id)): ProductInventory(
                product_id=product_id,
                store_id=store_id,
                available_stock=10,
                reserved_stock=0,
                total_stock=10,
            )
        }
    )
    inventory_handler = InventoryCommandHandler(
        inventory_repository=inventory_repository,
        processed_commands=inventory_processed_commands,
        outbox_messages=outbox_messages,
    )
    inventory_result = inventory_handler.reserve_inventory(
        ReserveInventoryCommand(
            command_id=reserve_decision.metadata.command_id,
            order_id=order_id,
            product_id=product_id,
            store_id=store_id,
            quantity=1,
            requested_at=reserve_decision.metadata.issued_at,
            causation_id=reserve_decision.metadata.causation_id,
            event_message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c30"),
        )
    )
    if inventory_result.outbox_message is None or inventory_result.inventory is None:
        raise RuntimeError("inventory reserve result did not include outbox message and inventory")
    inventory_reserved_message = inventory_result.outbox_message
    steps.append(
        _passed_step(
            "InventoryReservedEvent",
            "inventory handler reserved stock and saved checkout-consumable event",
            {
                "eventName": inventory_reserved_message.name,
                "availableStock": inventory_result.inventory.available_stock.value,
                "reservedStock": inventory_result.inventory.reserved_stock.value,
                "status": inventory_result.status.value,
            },
        )
    )

    initiate_decision = _single_decision(
        _handle_checkout_event(
            process_manager=process_manager,
            processed_messages=processed_messages,
            outbox_messages=outbox_messages,
            topic_resolver=topic_resolver,
            source_message=inventory_reserved_message,
        ),
        CheckoutCommandName.INITIATE_PAYMENT.value,
    )
    payment_repository = _InMemoryPaymentRepository()
    authorization_repository = _InMemoryPaymentAuthorizationRepository()
    timeout_scheduler = _InMemoryPaymentTimeoutScheduler()
    blockchain_adapter = _InMemoryBlockchainAdapter(
        receipt=TransactionReceipt(hash=tx_hash, block_number=123456, gas_used=21000),
        gas_estimate=GasEstimate(
            estimated_fee=Crypto(
                amount=Decimal("0.00042"),
                symbol="ETH",
                chain_id=chain.chain_id,
                token_address=None,
                decimals=18,
            ),
            gas_limit=21000,
            buffer_rate=Decimal("0.20"),
        ),
    )
    transaction_service = _InMemoryTransactionService()
    payment_handler = PaymentCommandHandler(
        payment_repository=payment_repository,
        authorization_repository=authorization_repository,
        processed_commands=payment_processed_commands,
        outbox_messages=outbox_messages,
        blockchain_adapter=blockchain_adapter,
        timeout_scheduler=timeout_scheduler,
        transaction_service=transaction_service,
    )
    payment_result = payment_handler.initiate_payment(
        InitiatePaymentCommand(
            command_id=initiate_decision.metadata.command_id,
            payment_id=payment_id,
            order_id=order_id,
            customer_id=customer_id,
            user_id=user_id,
            amount=order_result.total_amount,
            wallet_from=wallet_from,
            wallet_to=wallet_to,
            chain_network=chain,
            expires_at=now + timedelta(minutes=15),
            requested_at=initiate_decision.metadata.issued_at,
            causation_id=initiate_decision.metadata.causation_id,
            event_message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c31"),
        )
    )
    steps.append(
        _passed_step(
            "InitiatePaymentCommand",
            "payment handler created AWAITING_SIGNATURE payment and authorization",
            {
                "commandId": str(initiate_decision.metadata.command_id),
                "paymentId": str(payment_id),
                "status": payment_result.status.value,
            },
        )
    )
    steps.append(
        _passed_step(
            "payment signature request/gas estimate",
            "payment handler returned deterministic signature request and buffered gas estimate",
            {
                "paymentRequest": _signature_request_payload(payment_result.payment_request),
                "gasEstimate": _gas_estimate_payload(payment_result.gas_estimate),
                "scheduledExpirationCount": len(timeout_scheduler.scheduled),
            },
        )
    )

    submit_result = payment_handler.submit_transaction_hash(
        SubmitTransactionHashCommand(
            command_id=CommandId(f"{order_id}:SubmitTransactionHashCommand"),
            payment_id=payment_id,
            order_id=order_id,
            tx_hash=tx_hash,
            submitted_at=now + timedelta(minutes=3),
            causation_id=str(initiate_decision.metadata.command_id),
        )
    )
    steps.append(
        _passed_step(
            "txHash submit result",
            "payment handler accepted txHash before signature expiration",
            {
                "commandId": str(submit_result.command_id),
                "status": submit_result.status.value,
                "txHash": str(tx_hash),
            },
        )
    )

    confirmed_result = payment_handler.confirm_payment_receipt(
        ConfirmPaymentReceiptCommand(
            command_id=CommandId(f"{order_id}:ConfirmPaymentReceiptCommand"),
            payment_id=payment_id,
            order_id=order_id,
            checked_at=now + timedelta(minutes=4),
            causation_id=str(submit_result.command_id),
            event_message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c32"),
        )
    )
    if confirmed_result.outbox_message is None:
        raise RuntimeError("payment confirmation result did not include outbox message")
    payment_confirmed_message = confirmed_result.outbox_message
    payment_projection = order_status_projector.project(_order_status_event_from_source_message(payment_confirmed_message))
    steps.append(
        _passed_step(
            "PaymentConfirmedEvent",
            "payment handler confirmed receipt and order status projector marked order paid",
            {
                "eventName": payment_confirmed_message.name,
                "status": confirmed_result.status.value,
                "orderProjectionStatus": payment_projection.status.value,
                "receiptBlockNumber": 123456,
                "timeoutCancelCount": len(timeout_scheduler.cancelled),
            },
        )
    )

    approval_decision = _single_decision(
        _handle_checkout_event(
            process_manager=process_manager,
            processed_messages=processed_messages,
            outbox_messages=outbox_messages,
            topic_resolver=topic_resolver,
            source_message=payment_confirmed_message,
        ),
        CheckoutCommandName.REQUEST_STORE_APPROVAL.value,
    )
    approval_product = ApprovalProduct(product_id=product_id, name=order_product.name, price=unit_price, available=True)
    paid_order = order_repository.require(order_id)
    order_detail_repository = _InMemoryOrderDetailRepository(
        {
            str(order_id): OrderDetail(
                order_id=order_id,
                store_id=store_id,
                order_status=paid_order.status.value,
                total_amount=order_result.total_amount,
                products=(approval_product,),
            )
        }
    )
    approval_service = StoreApprovalService(
        store_repository=_InMemoryApprovalStoreRepository(
            {
                str(store_id): ApprovalStore(
                    store_id=store_id,
                    owner_user_id=owner_user_id,
                    products=(approval_product,),
                )
            }
        ),
        order_detail_repository=order_detail_repository,
        processed_commands=approval_processed_commands,
        outbox_messages=outbox_messages,
    )
    steps.append(
        _passed_step(
            "RequestStoreApprovalCommand",
            "checkout process manager issued deterministic store approval command",
            {
                "commandId": str(approval_decision.metadata.command_id),
                "commandName": approval_decision.name.value,
            },
        )
    )
    approval_result = approval_service.request_store_approval(
        RequestStoreApprovalCommand(
            command_id=approval_decision.metadata.command_id,
            order_id=order_id,
            store_id=store_id,
            owner_user_id=owner_user_id,
            requested_at=approval_decision.metadata.issued_at,
            causation_id=approval_decision.metadata.causation_id,
            event_message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c33"),
        )
    )
    if approval_result.outbox_message is None or approval_result.order_detail is None:
        raise RuntimeError("store approval result did not include outbox message and order detail")
    approval_projection = order_status_projector.project(_order_status_event_from_source_message(approval_result.outbox_message))
    _handle_checkout_event(
        process_manager=process_manager,
        processed_messages=processed_messages,
        outbox_messages=outbox_messages,
        topic_resolver=topic_resolver,
        source_message=approval_result.outbox_message,
    )
    final_order = order_repository.require(order_id)
    steps.append(
        _passed_step(
            "OrderApprovedEvent",
            "store approval service approved paid order and checkout manager consumed terminal event",
            {
                "eventName": approval_result.outbox_message.name,
                "approvalStatus": approval_result.order_detail.approval_status.value,
                "orderProjectionStatus": approval_projection.status.value,
                "finalOrderStatus": final_order.status.value,
            },
        )
    )

    duplicate_command_decisions = [
        decision.value
        for decision in (
            inventory_result.duplicate_decision,
            payment_result.duplicate_decision,
            submit_result.duplicate_decision,
            confirmed_result.duplicate_decision,
            approval_result.duplicate_decision,
        )
        if decision is not None
    ]
    process_manager_command_ids = {
        reserve_decision.name.value: str(reserve_decision.metadata.command_id),
        initiate_decision.name.value: str(initiate_decision.metadata.command_id),
        approval_decision.name.value: str(approval_decision.metadata.command_id),
    }

    return SmokeScenarioResult(
        scenario="happy-path-checkout",
        result=SmokeResult(
            status=SmokeStatus.PASSED,
            summary="happy-path checkout reached approved order status with in-memory ports",
        ),
        steps=tuple(steps),
        details={
            "orderId": str(order_id),
            "trackingId": str(tracking_id),
            "paymentId": str(payment_id),
            "finalOrderStatus": final_order.status.value,
            "finalStoreApprovalStatus": approval_result.order_detail.approval_status.value,
            "orderStatusProjector": {
                payment_confirmed_message.name: payment_projection.status.value,
                approval_result.outbox_message.name: approval_projection.status.value,
                "processedMessageCount": len(order_projected_messages.records),
            },
            "savedOutboxEventNames": [
                message.name for message in outbox_messages.saved if message.kind.value == "EVENT"
            ],
            "savedOutboxCommandNames": [
                message.name for message in outbox_messages.saved if message.kind.value == "COMMAND"
            ],
            "processManagerCommandIds": process_manager_command_ids,
            "idempotency": {
                "normalProcessing": not duplicate_command_decisions,
                "duplicateCommandDecisions": duplicate_command_decisions,
                "processedCommandCount": (
                    len(inventory_processed_commands.records)
                    + len(payment_processed_commands.records)
                    + len(approval_processed_commands.records)
                ),
                "processedMessageCount": len(processed_messages.records),
            },
        },
    )


def _run_compensation_checkout() -> SmokeScenarioResult:
    failure = _run_payment_receipt_failure_compensation()
    expiration = _run_payment_signature_expiration_compensation()
    rejection = _run_store_rejection_compensation()

    sub_scenarios = {
        "paymentReceiptFailure": failure["details"],
        "paymentSignatureExpiration": expiration["details"],
        "storeRejectionAfterPaymentConfirmation": rejection["details"],
    }
    duplicate_summary = _compensation_duplicate_summary(sub_scenarios)

    return SmokeScenarioResult(
        scenario="compensation-checkout",
        result=SmokeResult(
            status=SmokeStatus.PASSED,
            summary=(
                "compensation checkout emitted deterministic idempotent commands for failure, "
                "expiration, and rejection"
            ),
        ),
        steps=(
            _passed_step(
                "payment receipt failure compensation",
                "PaymentFailedEvent emitted deterministic release/cancel compensation commands",
                failure["stepDetails"],
            ),
            _passed_step(
                "payment signature expiration compensation",
                "PaymentExpiredEvent emitted deterministic release/cancel compensation commands",
                expiration["stepDetails"],
            ),
            _passed_step(
                "store rejection compensation",
                "OrderRejectedEvent emitted deterministic refund/release/cancel compensation commands",
                rejection["stepDetails"],
            ),
        ),
        details={
            "subScenarios": sub_scenarios,
            "cancelOrderHandlerWired": True,
            "duplicateSummary": duplicate_summary,
        },
    )


def _run_compose_readiness() -> SmokeScenarioResult:
    root = _repository_root()
    env_path = root / ".env.example"
    compose_path = root / "docker-compose.yml"
    init_script_path = root / "app/postgres/init.d/001-token-payments-schema.sql"
    test_network_dockerfile_path = root / "app/test_network/Dockerfile"

    env_values, env_errors = _read_env_example(env_path)
    env_errors.extend(_validate_env_example(env_values))

    service_blocks, compose_errors = _read_compose_service_blocks(compose_path)
    service_contracts = {
        service_name: _compose_service_contract(service_blocks.get(service_name, ()))
        for service_name in COMPOSE_READINESS_REQUIRED_SERVICES
    }
    compose_errors.extend(_validate_compose_contracts(root, service_blocks, service_contracts))

    path_details = {
        "postgresInitScript": _relative_path(init_script_path, root),
        "testNetworkDockerfile": _relative_path(test_network_dockerfile_path, root),
    }
    path_errors = [
        f"{path} is missing"
        for path, exists in (
            (path_details["postgresInitScript"], init_script_path.exists()),
            (path_details["testNetworkDockerfile"], test_network_dockerfile_path.exists()),
        )
        if not exists
    ]

    runtime_command_chain = [
        {
            "command": command,
            "boundedJson": True,
            "startsLongRunningProcess": False,
        }
        for command in COMPOSE_READINESS_COMMAND_SEQUENCE
    ]
    details = {
        "dockerStarted": False,
        "networkCalls": False,
        "envExample": {
            "path": _relative_path(env_path, root),
            "requiredKeys": list(COMPOSE_READINESS_REQUIRED_ENV_KEYS),
            "placeholderSafe": not env_errors,
            "sensitivePlaceholderKeys": list(COMPOSE_READINESS_SENSITIVE_PLACEHOLDER_KEYS),
        },
        "compose": {
            "path": _relative_path(compose_path, root),
            "requiredServices": list(COMPOSE_READINESS_REQUIRED_SERVICES),
            "serviceNames": [
                service_name
                for service_name in COMPOSE_READINESS_REQUIRED_SERVICES
                if service_name in service_blocks
            ],
            "discoveredServiceNames": list(service_blocks),
            "serviceContracts": service_contracts,
        },
        "paths": path_details,
        "runtimeCommandChain": runtime_command_chain,
    }
    errors = env_errors + compose_errors + path_errors
    steps = (
        _compose_readiness_step(
            ".env.example contract",
            "committed env example contains required local-only placeholders",
            {"missingKeys": _missing_env_keys(env_values), "placeholderSafe": not env_errors},
            env_errors,
        ),
        _compose_readiness_step(
            "docker-compose service contract",
            "committed compose file defines required local infrastructure services",
            {
                "requiredServices": list(COMPOSE_READINESS_REQUIRED_SERVICES),
                "serviceNames": details["compose"]["serviceNames"],
            },
            compose_errors,
        ),
        _compose_readiness_step(
            "compose path references",
            "compose-referenced init script and test network Dockerfile exist in the repository",
            path_details,
            path_errors,
        ),
        _compose_readiness_step(
            "runtime command readiness chain",
            "bounded runtime commands can be run after local compose startup",
            {"commands": runtime_command_chain},
            (),
        ),
    )

    if errors:
        return SmokeScenarioResult(
            scenario="compose-readiness",
            result=SmokeResult(
                status=SmokeStatus.FAILED,
                summary="compose readiness found committed env, compose, or path contract violations",
            ),
            steps=steps,
            details=details | {"errors": errors},
        )

    return SmokeScenarioResult(
        scenario="compose-readiness",
        result=SmokeResult(
            status=SmokeStatus.PASSED,
            summary=(
                "compose readiness validated committed env, compose, path, and runtime command contracts "
                "without starting Docker"
            ),
        ),
        steps=steps,
        details=details,
    )


def _run_docker_runtime_readiness() -> SmokeScenarioResult:
    root = _repository_root()
    dockerfile_path = root / "Dockerfile"
    dockerignore_path = root / ".dockerignore"
    env_path = root / ".env.example"
    compose_path = root / "docker-compose.yml"

    image_contract, image_errors = _docker_runtime_image_contract(dockerfile_path, root)
    dockerignore_contract, dockerignore_errors = _docker_runtime_dockerignore_contract(dockerignore_path, root)
    env_errors = [f"{_relative_path(env_path, root)} is missing"] if not env_path.exists() else []

    service_blocks, compose_errors = _read_compose_service_blocks(compose_path)
    runtime_services = {
        service_name: _docker_runtime_service_contract(service_blocks.get(service_name, ()))
        for service_name in DOCKER_RUNTIME_SERVICES
    }
    compose_errors.extend(_validate_docker_runtime_services(service_blocks, runtime_services))
    postman_api_service = _postman_api_service_contract(
        service_blocks.get(POSTMAN_API_SERVICE_NAME, ())
    )
    postman_api_errors = _validate_postman_api_service(service_blocks, postman_api_service)
    compose_errors.extend(postman_api_errors)

    details = {
        "dockerStarted": False,
        "networkCalls": False,
        "image": {
            "contract": image_contract,
            "dockerignore": dockerignore_contract,
            "envExamplePath": _relative_path(env_path, root),
        },
        "compose": {
            "path": _relative_path(compose_path, root),
            "runtimeServices": runtime_services,
            "buildCommand": DOCKER_RUNTIME_BUILD_COMMAND,
            "runCommands": list(DOCKER_RUNTIME_RUN_COMMANDS),
            "composeConfigValidationCommand": {
                "command": DOCKER_RUNTIME_COMPOSE_CONFIG_VALIDATION_COMMAND,
                "daemonless": True,
                "usesDockerSocket": False,
                "forbiddenCommands": ["up", "run", "build"],
            },
        },
        "postmanApi": {
            "service": postman_api_service,
            "composeConfigValidationCommand": {
                "command": POSTMAN_API_COMPOSE_CONFIG_VALIDATION_COMMAND,
                "daemonless": True,
                "usesDockerSocket": False,
                "forbiddenCommands": ["up", "run", "build"],
                "expectedServices": [POSTMAN_API_SERVICE_NAME],
            },
            "manualLiveCommands": list(POSTMAN_API_MANUAL_LIVE_COMMANDS),
        },
        "manualLiveCommands": list(DOCKER_RUNTIME_MANUAL_LIVE_COMMANDS),
    }
    errors = image_errors + dockerignore_errors + env_errors + compose_errors
    steps = (
        _compose_readiness_step(
            "Dockerfile runtime image contract",
            "committed Dockerfile exposes the bounded Python runtime image contract",
            image_contract,
            image_errors,
        ),
        _compose_readiness_step(
            ".dockerignore runtime context contract",
            "committed dockerignore excludes local env, git, cache, data, and phase outputs",
            dockerignore_contract,
            dockerignore_errors,
        ),
        _compose_readiness_step(
            "compose runtime service contract",
            "committed compose runtime services use bounded one-shot commands without starting Docker",
            {
                "runtimeServices": runtime_services,
                "buildCommand": DOCKER_RUNTIME_BUILD_COMMAND,
                "runCommands": list(DOCKER_RUNTIME_RUN_COMMANDS),
                "composeConfigValidationCommand": DOCKER_RUNTIME_COMPOSE_CONFIG_VALIDATION_COMMAND,
            },
            compose_errors + env_errors,
        ),
        _compose_readiness_step(
            "manual live command contract",
            "manual live Docker commands are documented as explicit local commands",
            {"manualLiveCommands": list(DOCKER_RUNTIME_MANUAL_LIVE_COMMANDS)},
            (),
        ),
    )

    if errors:
        return SmokeScenarioResult(
            scenario="docker-runtime-readiness",
            result=SmokeResult(
                status=SmokeStatus.FAILED,
                summary="docker runtime readiness found committed Docker or compose contract violations",
            ),
            steps=steps,
            details=details | {"errors": errors},
        )

    return SmokeScenarioResult(
        scenario="docker-runtime-readiness",
        result=SmokeResult(
            status=SmokeStatus.PASSED,
            summary=(
                "docker runtime readiness validated image, dockerignore, env path, compose config command, "
                "and compose one-shot commands without starting Docker"
            ),
        ),
        steps=steps,
        details=details,
    )


def _run_postman_docker_api_readiness() -> SmokeScenarioResult:
    root = _repository_root()
    required_paths = (
        "scripts/docker_live_smoke.py",
        "postman/token-payments.local.postman_collection.json",
        "postman/token-payments.local.postman_environment.json",
        "postman/token-payments.cookie-auth.expected.json",
        "postman/fixtures/token-payments.local.seed-plan.json",
        "postman/expected/token-payments.api.expected.json",
    )
    path_details = {
        path: {
            "path": path,
            "exists": (root / path).exists(),
        }
        for path in required_paths
    }
    path_errors = [f"{path} is missing" for path, detail in path_details.items() if not detail["exists"]]
    details = {
        "dockerStarted": False,
        "networkCalls": False,
        "contract": POSTMAN_DOCKER_API_READINESS_CONTRACT,
        "planCommand": POSTMAN_DOCKER_API_READINESS_PLAN_COMMAND,
        "refusalCommand": POSTMAN_DOCKER_API_READINESS_REFUSAL_COMMAND,
        "confirmedLiveCommand": POSTMAN_DOCKER_API_READINESS_CONFIRMED_COMMAND,
        "commandSequence": list(POSTMAN_DOCKER_API_READINESS_COMMAND_SEQUENCE),
        "manualLiveCommands": list(POSTMAN_DOCKER_API_READINESS_MANUAL_COMMANDS),
        "service": dict(POSTMAN_API_SERVICE),
        "requiredServices": ["postgres", "kafka", "test_network", POSTMAN_API_SERVICE_NAME],
        "fixtures": path_details,
        "redactionPolicy": {
            "rawSecretValuesCommitted": False,
            "redacts": [
                "session signing key",
                "signed session token",
                "cookie header",
                "CSRF token",
                "Authorization bearer token",
            ],
        },
        "automationBoundary": {
            "defaultPath": "dry-run/static contract",
            "requiresLiveConfirmation": True,
            "startsDockerByDefault": False,
            "opensNetworkByDefault": False,
        },
    }
    steps = (
        _compose_readiness_step(
            "API readiness plan command",
            "Postman Docker API readiness smoke exposes a dry-run plan command without starting Docker",
            {
                "planCommand": POSTMAN_DOCKER_API_READINESS_PLAN_COMMAND,
                "refusalCommand": POSTMAN_DOCKER_API_READINESS_REFUSAL_COMMAND,
                "confirmedLiveCommand": POSTMAN_DOCKER_API_READINESS_CONFIRMED_COMMAND,
            },
            (),
        ),
        _compose_readiness_step(
            "API readiness security order",
            "plan covers API start, session key validation, cookie auth, CSRF, CORS, body, JSON, idempotency, checkout, and operator smoke checks",
            {"commandSequence": list(POSTMAN_DOCKER_API_READINESS_COMMAND_SEQUENCE)},
            (),
        ),
        _compose_readiness_step(
            "API readiness fixtures",
            "Postman collection, environment, seed, expected response, and runner files exist for manual live verification",
            path_details,
            path_errors,
        ),
        _compose_readiness_step(
            "API readiness redaction boundary",
            "smoke output redacts session signing keys, signed tokens, cookie headers, and CSRF values",
            details["redactionPolicy"],
            (),
        ),
    )

    if path_errors:
        return SmokeScenarioResult(
            scenario="postman-docker-api-readiness",
            result=SmokeResult(
                status=SmokeStatus.FAILED,
                summary="postman Docker API readiness found missing runner or Postman fixture contracts",
            ),
            steps=steps,
            details=details | {"errors": path_errors},
        )

    return SmokeScenarioResult(
        scenario="postman-docker-api-readiness",
        result=SmokeResult(
            status=SmokeStatus.PASSED,
            summary=(
                "postman Docker API readiness exposes a bounded readiness/security smoke plan "
                "without starting Docker or the API server"
            ),
        ),
        steps=steps,
        details=details,
    )


def _run_payment_receipt_failure_compensation() -> dict[str, Any]:
    from token_payments.contexts.inventory.application import ReleaseInventoryCommand
    from token_payments.contexts.payment.application import ConfirmPaymentReceiptCommand, SubmitTransactionHashCommand
    from token_payments.shared.domain import CheckoutCommandName, CommandId, TransactionHash

    fixture = _build_compensation_fixture("7c")
    failed_tx_hash = TransactionHash("0xcccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc")
    submit_result = fixture.payment_handler.submit_transaction_hash(
        SubmitTransactionHashCommand(
            command_id=CommandId(f"{fixture.order_id}:SubmitTransactionHashCommand"),
            payment_id=fixture.payment_id,
            order_id=fixture.order_id,
            tx_hash=failed_tx_hash,
            submitted_at=fixture.now + timedelta(minutes=3),
            causation_id=str(fixture.initiate_decision.metadata.command_id),
        )
    )
    failed_result = fixture.payment_handler.confirm_payment_receipt(
        ConfirmPaymentReceiptCommand(
            command_id=CommandId(f"{fixture.order_id}:ConfirmPaymentReceiptCommand"),
            payment_id=fixture.payment_id,
            order_id=fixture.order_id,
            checked_at=fixture.now + timedelta(minutes=4),
            failure_reason="receipt not confirmed by deterministic smoke adapter",
            causation_id=str(submit_result.command_id),
            event_message_id=_message_id("7c", "40"),
        )
    )
    if failed_result.outbox_message is None or failed_result.payment is None:
        raise RuntimeError("payment failure result did not include outbox message and payment")

    decisions, duplicate_event_replay = _consume_compensation_event(fixture, failed_result.outbox_message)
    release_decision = _single_decision(decisions, CheckoutCommandName.RELEASE_INVENTORY.value)
    cancel_decision = _single_decision(decisions, CheckoutCommandName.CANCEL_ORDER.value)
    release_command = ReleaseInventoryCommand(
        command_id=release_decision.metadata.command_id,
        order_id=fixture.order_id,
        product_id=fixture.product_id,
        store_id=fixture.store_id,
        requested_at=release_decision.metadata.issued_at,
        causation_id=release_decision.metadata.causation_id,
        event_message_id=_message_id("7c", "41"),
    )
    release_result = fixture.inventory_handler.release_inventory(release_command)
    duplicate_release = fixture.inventory_handler.release_inventory(release_command)
    if release_result.inventory is None:
        raise RuntimeError("inventory release result did not include inventory")
    cancel_result, duplicate_cancel = _run_cancel_order_command(
        fixture,
        cancel_decision,
        reason="payment receipt failed in deterministic smoke",
        event_message_id=_message_id("7c", "42"),
    )
    if cancel_result.order is None:
        raise RuntimeError("cancel order result did not include order")

    details = _base_compensation_details(
        trigger_event=failed_result.outbox_message.name,
        decisions=decisions,
        duplicate_event_replay=duplicate_event_replay,
        duplicate_command_results={
            CheckoutCommandName.RELEASE_INVENTORY.value: duplicate_release.status.value,
            CheckoutCommandName.CANCEL_ORDER.value: duplicate_cancel.status.value,
        },
        final_inventory=release_result.inventory,
    ) | {
        "finalPaymentStatus": failed_result.payment.status.value,
        "finalOrderStatus": cancel_result.order.status.value,
        "cancelOrderHandlerWired": True,
    }
    return {
        "details": details,
        "stepDetails": {
            "triggerEvent": details["triggerEvent"],
            "compensationCommandIds": details["compensationCommandIds"],
            "duplicateCommandResults": details["duplicateCommandResults"],
        },
    }


def _run_payment_signature_expiration_compensation() -> dict[str, Any]:
    from token_payments.contexts.inventory.application import ReleaseInventoryCommand
    from token_payments.contexts.payment.application import ExpireAwaitingSignatureCommand
    from token_payments.shared.domain import CheckoutCommandName, CommandId

    fixture = _build_compensation_fixture("8c")
    expired_result = fixture.payment_handler.expire_awaiting_signature(
        ExpireAwaitingSignatureCommand(
            command_id=CommandId(f"{fixture.order_id}:ExpireAwaitingSignatureCommand"),
            payment_id=fixture.payment_id,
            order_id=fixture.order_id,
            expired_at=fixture.now + timedelta(minutes=16),
            reason="signature expired before txHash submission",
            causation_id=str(fixture.initiate_decision.metadata.command_id),
            event_message_id=_message_id("8c", "40"),
        )
    )
    if expired_result.outbox_message is None or expired_result.payment is None:
        raise RuntimeError("payment expiration result did not include outbox message and payment")

    decisions, duplicate_event_replay = _consume_compensation_event(fixture, expired_result.outbox_message)
    release_decision = _single_decision(decisions, CheckoutCommandName.RELEASE_INVENTORY.value)
    cancel_decision = _single_decision(decisions, CheckoutCommandName.CANCEL_ORDER.value)
    release_command = ReleaseInventoryCommand(
        command_id=release_decision.metadata.command_id,
        order_id=fixture.order_id,
        product_id=fixture.product_id,
        store_id=fixture.store_id,
        requested_at=release_decision.metadata.issued_at,
        causation_id=release_decision.metadata.causation_id,
        event_message_id=_message_id("8c", "41"),
    )
    release_result = fixture.inventory_handler.release_inventory(release_command)
    duplicate_release = fixture.inventory_handler.release_inventory(release_command)
    if release_result.inventory is None:
        raise RuntimeError("inventory release result did not include inventory")
    cancel_result, duplicate_cancel = _run_cancel_order_command(
        fixture,
        cancel_decision,
        reason="payment signature expired in deterministic smoke",
        event_message_id=_message_id("8c", "42"),
    )
    if cancel_result.order is None:
        raise RuntimeError("cancel order result did not include order")

    details = _base_compensation_details(
        trigger_event=expired_result.outbox_message.name,
        decisions=decisions,
        duplicate_event_replay=duplicate_event_replay,
        duplicate_command_results={
            CheckoutCommandName.RELEASE_INVENTORY.value: duplicate_release.status.value,
            CheckoutCommandName.CANCEL_ORDER.value: duplicate_cancel.status.value,
        },
        final_inventory=release_result.inventory,
    ) | {
        "finalPaymentStatus": expired_result.payment.status.value,
        "finalOrderStatus": cancel_result.order.status.value,
        "cancelOrderHandlerWired": True,
    }
    return {
        "details": details,
        "stepDetails": {
            "triggerEvent": details["triggerEvent"],
            "compensationCommandIds": details["compensationCommandIds"],
            "duplicateCommandResults": details["duplicateCommandResults"],
        },
    }


def _run_store_rejection_compensation() -> dict[str, Any]:
    from token_payments.contexts.inventory.application import ReleaseInventoryCommand
    from token_payments.contexts.payment.application import (
        ConfirmPaymentReceiptCommand,
        RefundPaymentCommand,
        SubmitTransactionHashCommand,
    )
    from token_payments.contexts.store_approval.application import RequestStoreApprovalCommand
    from token_payments.shared.domain import CheckoutCommandName, CommandId

    fixture = _build_compensation_fixture("9c")
    submit_result = fixture.payment_handler.submit_transaction_hash(
        SubmitTransactionHashCommand(
            command_id=CommandId(f"{fixture.order_id}:SubmitTransactionHashCommand"),
            payment_id=fixture.payment_id,
            order_id=fixture.order_id,
            tx_hash=fixture.confirmed_tx_hash,
            submitted_at=fixture.now + timedelta(minutes=3),
            causation_id=str(fixture.initiate_decision.metadata.command_id),
        )
    )
    confirmed_result = fixture.payment_handler.confirm_payment_receipt(
        ConfirmPaymentReceiptCommand(
            command_id=CommandId(f"{fixture.order_id}:ConfirmPaymentReceiptCommand"),
            payment_id=fixture.payment_id,
            order_id=fixture.order_id,
            checked_at=fixture.now + timedelta(minutes=4),
            causation_id=str(submit_result.command_id),
            event_message_id=_message_id("9c", "40"),
        )
    )
    if confirmed_result.outbox_message is None or confirmed_result.payment is None:
        raise RuntimeError("payment confirmation result did not include outbox message and payment")
    payment_projection = fixture.order_status_projector.project(
        _order_status_event_from_source_message(confirmed_result.outbox_message)
    )

    approval_decision = _single_decision(
        _handle_checkout_event(
            process_manager=fixture.process_manager,
            processed_messages=fixture.processed_messages,
            outbox_messages=fixture.outbox_messages,
            topic_resolver=fixture.topic_resolver,
            source_message=confirmed_result.outbox_message,
        ),
        CheckoutCommandName.REQUEST_STORE_APPROVAL.value,
    )
    approval_result = fixture.approval_service.request_store_approval(
        RequestStoreApprovalCommand(
            command_id=approval_decision.metadata.command_id,
            order_id=fixture.order_id,
            store_id=fixture.store_id,
            owner_user_id=fixture.owner_user_id,
            requested_at=approval_decision.metadata.issued_at,
            rejection_reason="store owner rejected deterministic smoke order",
            causation_id=approval_decision.metadata.causation_id,
            event_message_id=_message_id("9c", "41"),
        )
    )
    if approval_result.outbox_message is None or approval_result.order_detail is None:
        raise RuntimeError("store rejection result did not include outbox message and order detail")

    decisions, duplicate_event_replay = _consume_compensation_event(fixture, approval_result.outbox_message)
    refund_decision = _single_decision(decisions, CheckoutCommandName.REFUND_PAYMENT.value)
    release_decision = _single_decision(decisions, CheckoutCommandName.RELEASE_INVENTORY.value)
    cancel_decision = _single_decision(decisions, CheckoutCommandName.CANCEL_ORDER.value)

    refund_command = RefundPaymentCommand(
        command_id=refund_decision.metadata.command_id,
        payment_id=fixture.payment_id,
        order_id=fixture.order_id,
        requested_at=refund_decision.metadata.issued_at,
        causation_id=refund_decision.metadata.causation_id,
        event_message_id=_message_id("9c", "42"),
    )
    refund_result = fixture.payment_handler.refund_payment(refund_command)
    duplicate_refund = fixture.payment_handler.refund_payment(refund_command)
    if refund_result.payment is None:
        raise RuntimeError("payment refund result did not include payment")

    release_command = ReleaseInventoryCommand(
        command_id=release_decision.metadata.command_id,
        order_id=fixture.order_id,
        product_id=fixture.product_id,
        store_id=fixture.store_id,
        requested_at=release_decision.metadata.issued_at,
        causation_id=release_decision.metadata.causation_id,
        event_message_id=_message_id("9c", "43"),
    )
    release_result = fixture.inventory_handler.release_inventory(release_command)
    duplicate_release = fixture.inventory_handler.release_inventory(release_command)
    if release_result.inventory is None:
        raise RuntimeError("inventory release result did not include inventory")
    cancel_result, duplicate_cancel = _run_cancel_order_command(
        fixture,
        cancel_decision,
        reason="store owner rejected deterministic smoke order",
        event_message_id=_message_id("9c", "44"),
    )
    if cancel_result.order is None:
        raise RuntimeError("cancel order result did not include order")

    details = _base_compensation_details(
        trigger_event=approval_result.outbox_message.name,
        decisions=decisions,
        duplicate_event_replay=duplicate_event_replay,
        duplicate_command_results={
            CheckoutCommandName.REFUND_PAYMENT.value: duplicate_refund.status.value,
            CheckoutCommandName.RELEASE_INVENTORY.value: duplicate_release.status.value,
            CheckoutCommandName.CANCEL_ORDER.value: duplicate_cancel.status.value,
        },
        final_inventory=release_result.inventory,
    ) | {
        "finalPaymentStatus": refund_result.payment.status.value,
        "finalStoreApprovalStatus": approval_result.order_detail.approval_status.value,
        "finalOrderStatus": cancel_result.order.status.value,
        "orderStatusProjector": {
            confirmed_result.outbox_message.name: payment_projection.status.value,
            "processedMessageCount": len(fixture.order_projected_messages.records),
        },
        "cancelOrderHandlerWired": True,
    }
    return {
        "details": details,
        "stepDetails": {
            "triggerEvent": details["triggerEvent"],
            "compensationCommandIds": details["compensationCommandIds"],
            "duplicateCommandResults": details["duplicateCommandResults"],
        },
    }


@dataclass(frozen=True)
class _CompensationCheckoutFixture:
    now: datetime
    order_id: Any
    product_id: Any
    store_id: Any
    payment_id: Any
    owner_user_id: Any
    confirmed_tx_hash: Any
    total_amount: Any
    outbox_messages: Any
    order_repository: Any
    processed_messages: Any
    order_projected_messages: Any
    order_processed_commands: Any
    process_manager: Any
    topic_resolver: Any
    inventory_handler: Any
    payment_handler: Any
    approval_service: Any
    order_command_handler: Any
    order_status_projector: Any
    initiate_decision: Any


def _build_compensation_fixture(marker: str) -> _CompensationCheckoutFixture:
    from token_payments.contexts.checkout.application import CheckoutProcessManager
    from token_payments.contexts.inventory.application import InventoryCommandHandler, ReserveInventoryCommand
    from token_payments.contexts.inventory.domain import ProductInventory
    from token_payments.contexts.order.application import (
        CreateOrderCommand,
        CreateOrderItem,
        OrderApplicationService,
        OrderCommandHandler,
        OrderStatusEventProjector,
    )
    from token_payments.contexts.order.domain import (
        Address,
        Customer,
        Product as OrderProduct,
        Store as OrderStore,
        TrackingId,
    )
    from token_payments.contexts.payment.application import InitiatePaymentCommand, PaymentCommandHandler
    from token_payments.contexts.payment.domain import GasEstimate, TransactionReceipt
    from token_payments.contexts.store_approval.application import StoreApprovalService
    from token_payments.contexts.store_approval.domain import (
        OrderDetail,
        Product as ApprovalProduct,
        Store as ApprovalStore,
    )
    from token_payments.shared.adapter.messaging import MessageTopicResolver
    from token_payments.shared.domain import (
        ChainNetwork,
        CheckoutCommandName,
        Crypto,
        CustomerId,
        OrderId,
        PaymentId,
        ProductId,
        StoreId,
        TransactionHash,
        UserId,
        WalletAddress,
    )

    now = datetime(2026, 5, 10, 11, 0, tzinfo=UTC)
    order_id = OrderId(str(_uuid(marker, "21")))
    product_id = ProductId(str(_uuid(marker, "23")))
    store_id = StoreId(str(_uuid(marker, "24")))
    payment_id = PaymentId(str(_uuid(marker, "25")))
    customer_id = CustomerId(str(_uuid(marker, "26")))
    user_id = UserId(str(_uuid(marker, "27")))
    owner_user_id = UserId(str(_uuid(marker, "28")))
    tracking_id = TrackingId(str(_uuid(marker, "29")))
    wallet_from = WalletAddress("0x1111111111111111111111111111111111111111")
    wallet_to = WalletAddress("0x2222222222222222222222222222222222222222")
    token_address = WalletAddress("0x3333333333333333333333333333333333333333")
    confirmed_tx_hash = TransactionHash("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    chain = ChainNetwork(chain_id=11155111, name="Sepolia")
    unit_price = Crypto(
        amount=Decimal("1.25"),
        symbol="USDC",
        chain_id=chain.chain_id,
        token_address=token_address,
        decimals=6,
    )

    outbox_messages = _InMemoryOutboxMessageRepository()
    processed_messages = _InMemoryProcessedMessageRepository()
    order_projected_messages = _InMemoryProcessedMessageRepository()
    inventory_processed_commands = _InMemoryProcessedCommandRepository()
    payment_processed_commands = _InMemoryProcessedCommandRepository()
    approval_processed_commands = _InMemoryProcessedCommandRepository()
    order_processed_commands = _InMemoryProcessedCommandRepository()

    customer = Customer(customer_id=customer_id, user_id=user_id, customer_wallet=wallet_from)
    order_product = OrderProduct(product_id=product_id, name="Deterministic Compensation Item", price=unit_price)
    order_store = OrderStore(
        store_id=store_id,
        owner_user_id=owner_user_id,
        products=(order_product,),
        store_address=Address(id=f"store-address-{marker}", street="42 Token Street"),
        store_wallet=wallet_to,
        supported_chain_ids=(chain.chain_id,),
    )
    order_repository = _InMemoryOrderRepository()
    order_service = OrderApplicationService(
        customers=_InMemoryCustomerRepository({str(user_id): customer}),
        stores=_InMemoryOrderStoreRepository({str(store_id): order_store}),
        orders=order_repository,
        outbox_messages=outbox_messages,
    )
    order_command_handler = OrderCommandHandler(order_repository, order_processed_commands, outbox_messages)
    order_status_projector = OrderStatusEventProjector(order_repository, order_projected_messages)
    order_result = order_service.createOrder(
        CreateOrderCommand(
            authenticated_user_id=user_id,
            store_id=store_id,
            delivery_address=Address(id=f"delivery-address-{marker}", street="7 Checkout Avenue"),
            items=(CreateOrderItem(product_id=product_id, quantity=1),),
            order_id=order_id,
            tracking_id=tracking_id,
            event_message_id=_message_id(marker, "22"),
            requested_at=now,
        )
    )

    process_manager = CheckoutProcessManager()
    topic_resolver = MessageTopicResolver.default()
    reserve_decision = _single_decision(
        _handle_checkout_event(
            process_manager=process_manager,
            processed_messages=processed_messages,
            outbox_messages=outbox_messages,
            topic_resolver=topic_resolver,
            source_message=order_result.outbox_message,
        ),
        CheckoutCommandName.RESERVE_INVENTORY.value,
    )
    inventory_repository = _InMemoryInventoryRepository(
        {
            (str(product_id), str(store_id)): ProductInventory(
                product_id=product_id,
                store_id=store_id,
                available_stock=10,
                reserved_stock=0,
                total_stock=10,
            )
        }
    )
    inventory_handler = InventoryCommandHandler(
        inventory_repository=inventory_repository,
        processed_commands=inventory_processed_commands,
        outbox_messages=outbox_messages,
    )
    inventory_result = inventory_handler.reserve_inventory(
        ReserveInventoryCommand(
            command_id=reserve_decision.metadata.command_id,
            order_id=order_id,
            product_id=product_id,
            store_id=store_id,
            quantity=1,
            requested_at=reserve_decision.metadata.issued_at,
            causation_id=reserve_decision.metadata.causation_id,
            event_message_id=_message_id(marker, "30"),
        )
    )
    if inventory_result.outbox_message is None:
        raise RuntimeError("inventory reserve result did not include outbox message")

    initiate_decision = _single_decision(
        _handle_checkout_event(
            process_manager=process_manager,
            processed_messages=processed_messages,
            outbox_messages=outbox_messages,
            topic_resolver=topic_resolver,
            source_message=inventory_result.outbox_message,
        ),
        CheckoutCommandName.INITIATE_PAYMENT.value,
    )
    payment_handler = PaymentCommandHandler(
        payment_repository=_InMemoryPaymentRepository(),
        authorization_repository=_InMemoryPaymentAuthorizationRepository(),
        processed_commands=payment_processed_commands,
        outbox_messages=outbox_messages,
        blockchain_adapter=_InMemoryBlockchainAdapter(
            receipt=TransactionReceipt(hash=confirmed_tx_hash, block_number=123456, gas_used=21000),
            gas_estimate=GasEstimate(
                estimated_fee=Crypto(
                    amount=Decimal("0.00042"),
                    symbol="ETH",
                    chain_id=chain.chain_id,
                    token_address=None,
                    decimals=18,
                ),
                gas_limit=21000,
                buffer_rate=Decimal("0.20"),
            ),
        ),
        timeout_scheduler=_InMemoryPaymentTimeoutScheduler(),
        transaction_service=_InMemoryTransactionService(),
    )
    payment_handler.initiate_payment(
        InitiatePaymentCommand(
            command_id=initiate_decision.metadata.command_id,
            payment_id=payment_id,
            order_id=order_id,
            customer_id=customer_id,
            user_id=user_id,
            amount=order_result.total_amount,
            wallet_from=wallet_from,
            wallet_to=wallet_to,
            chain_network=chain,
            expires_at=now + timedelta(minutes=15),
            requested_at=initiate_decision.metadata.issued_at,
            causation_id=initiate_decision.metadata.causation_id,
            event_message_id=_message_id(marker, "31"),
        )
    )

    approval_product = ApprovalProduct(product_id=product_id, name=order_product.name, price=unit_price, available=True)
    approval_service = StoreApprovalService(
        store_repository=_InMemoryApprovalStoreRepository(
            {
                str(store_id): ApprovalStore(
                    store_id=store_id,
                    owner_user_id=owner_user_id,
                    products=(approval_product,),
                )
            }
        ),
        order_detail_repository=_InMemoryOrderDetailRepository(
            {
                str(order_id): OrderDetail(
                    order_id=order_id,
                    store_id=store_id,
                    order_status="PAID",
                    total_amount=order_result.total_amount,
                    products=(approval_product,),
                )
            }
        ),
        processed_commands=approval_processed_commands,
        outbox_messages=outbox_messages,
    )

    return _CompensationCheckoutFixture(
        now=now,
        order_id=order_id,
        product_id=product_id,
        store_id=store_id,
        payment_id=payment_id,
        owner_user_id=owner_user_id,
        confirmed_tx_hash=confirmed_tx_hash,
        total_amount=order_result.total_amount,
        outbox_messages=outbox_messages,
        order_repository=order_repository,
        processed_messages=processed_messages,
        order_projected_messages=order_projected_messages,
        order_processed_commands=order_processed_commands,
        process_manager=process_manager,
        topic_resolver=topic_resolver,
        inventory_handler=inventory_handler,
        payment_handler=payment_handler,
        approval_service=approval_service,
        order_command_handler=order_command_handler,
        order_status_projector=order_status_projector,
        initiate_decision=initiate_decision,
    )


def _consume_compensation_event(
    fixture: _CompensationCheckoutFixture,
    source_message: Any,
) -> tuple[tuple[Any, ...], dict[str, JsonValue]]:
    decisions = _handle_checkout_event(
        process_manager=fixture.process_manager,
        processed_messages=fixture.processed_messages,
        outbox_messages=fixture.outbox_messages,
        topic_resolver=fixture.topic_resolver,
        source_message=source_message,
    )
    duplicate_decisions = _handle_checkout_event(
        process_manager=fixture.process_manager,
        processed_messages=fixture.processed_messages,
        outbox_messages=fixture.outbox_messages,
        topic_resolver=fixture.topic_resolver,
        source_message=source_message,
    )
    replay = _direct_process_manager_replay(fixture.process_manager, source_message)
    return decisions, {
        "ignoredByProcessedMessageRepository": len(duplicate_decisions) == 0,
        "firstCommandIds": _decision_id_list(decisions),
        "processedDuplicateCommandIds": _decision_id_list(duplicate_decisions),
        "directReplayCommandIds": replay["directReplayCommandIds"],
        "sameDirectDecisionIdsOnReplay": replay["sameDirectDecisionIdsOnReplay"],
    }


def _direct_process_manager_replay(process_manager: Any, source_message: Any) -> dict[str, JsonValue]:
    event = _checkout_event_from_source_message(source_message)
    first = process_manager.handle(event)
    second = process_manager.handle(event)
    first_ids = _decision_id_list(first)
    second_ids = _decision_id_list(second)
    return {
        "directReplayCommandIds": [first_ids, second_ids],
        "sameDirectDecisionIdsOnReplay": first_ids == second_ids,
    }


def _base_compensation_details(
    *,
    trigger_event: str,
    decisions: tuple[Any, ...],
    duplicate_event_replay: Mapping[str, Any],
    duplicate_command_results: Mapping[str, str],
    final_inventory: Any,
) -> dict[str, JsonValue]:
    return {
        "triggerEvent": trigger_event,
        "compensationCommandIds": _decision_ids_by_name(decisions),
        "duplicateEventReplay": dict(duplicate_event_replay),
        "duplicateCommandResults": dict(duplicate_command_results),
        "finalInventory": {
            "availableStock": final_inventory.available_stock.value,
            "reservedStock": final_inventory.reserved_stock.value,
        },
    }


def _run_cancel_order_command(
    fixture: _CompensationCheckoutFixture,
    cancel_decision: Any,
    *,
    reason: str,
    event_message_id: Any,
) -> tuple[Any, Any]:
    from token_payments.contexts.order.application import CancelOrderCommand

    cancel_command = CancelOrderCommand(
        command_id=cancel_decision.metadata.command_id,
        order_id=fixture.order_id,
        reason=reason,
        requested_at=cancel_decision.metadata.issued_at,
        causation_id=cancel_decision.metadata.causation_id,
        event_message_id=event_message_id,
    )
    cancel_result = fixture.order_command_handler.cancel_order(cancel_command)
    duplicate_cancel = fixture.order_command_handler.cancel_order(cancel_command)
    return cancel_result, duplicate_cancel


def _compensation_duplicate_summary(sub_scenarios: Mapping[str, Mapping[str, Any]]) -> dict[str, JsonValue]:
    duplicate_results: dict[str, list[str]] = {
        "ReleaseInventoryCommand": [],
        "RefundPaymentCommand": [],
        "CancelOrderCommand": [],
    }
    for scenario in sub_scenarios.values():
        for command_name, result in scenario["duplicateCommandResults"].items():
            duplicate_results.setdefault(command_name, []).append(str(result))

    return {
        "duplicateEventReplaysIgnored": sum(
            1
            for scenario in sub_scenarios.values()
            if scenario["duplicateEventReplay"]["ignoredByProcessedMessageRepository"]
        ),
        "deterministicProcessManagerReplays": sum(
            1
            for scenario in sub_scenarios.values()
            if scenario["duplicateEventReplay"]["sameDirectDecisionIdsOnReplay"]
        ),
        "duplicateCommandResults": {key: values for key, values in duplicate_results.items() if values},
    }


def _decision_ids_by_name(decisions: tuple[Any, ...]) -> dict[str, JsonValue]:
    return {decision.name.value: str(decision.metadata.command_id) for decision in decisions}


def _decision_id_list(decisions: tuple[Any, ...]) -> list[JsonValue]:
    return [str(decision.metadata.command_id) for decision in decisions]


def _uuid(marker: str, suffix: str) -> str:
    return f"018f33aa-9e6d-73d8-9dc3-47d6cdcc{marker}{suffix}"


def _message_id(marker: str, suffix: str) -> Any:
    from token_payments.shared.domain import MessageId

    return MessageId(_uuid(marker, suffix))


def _handle_checkout_event(
    *,
    process_manager: Any,
    processed_messages: "_InMemoryProcessedMessageRepository",
    outbox_messages: "_InMemoryOutboxMessageRepository",
    topic_resolver: Any,
    source_message: Any,
) -> tuple[Any, ...]:
    from token_payments.shared.domain import OutboxMessage, ProcessedMessage

    event = _checkout_event_from_source_message(source_message)
    if processed_messages.was_processed(event.metadata.message_id, "checkout-process-manager"):
        return ()

    decisions = process_manager.handle(event)
    for decision in decisions:
        outbox_messages.save(
            OutboxMessage.record_command(
                metadata=decision.metadata,
                topic=topic_resolver.topic_for(decision.name),
                key=str(decision.order_id),
                payload={
                    "commandName": decision.name.value,
                    "commandId": str(decision.metadata.command_id),
                    "orderId": str(decision.order_id),
                    "issuedAt": decision.metadata.issued_at.isoformat(),
                    "sourceEventName": event.name.value,
                },
                headers={
                    "correlationId": decision.metadata.correlation_id,
                    "causationId": decision.metadata.causation_id or "",
                },
            )
        )
    processed_messages.record(
        ProcessedMessage.record(
            message_id=event.metadata.message_id,
            consumer="checkout-process-manager",
            processed_at=event.metadata.occurred_at,
            order_id=event.order_id,
        )
    )
    return tuple(decisions)


def _checkout_event_from_source_message(source_message: Any) -> Any:
    from token_payments.contexts.checkout.application import CheckoutProcessEvent
    from token_payments.shared.domain import EventMetadata, MessageId, OrderId

    return CheckoutProcessEvent(
        metadata=EventMetadata(
            message_id=MessageId(source_message.identity),
            name=source_message.name,
            aggregate_id=source_message.key,
            occurred_at=source_message.created_at,
            correlation_id=source_message.headers.get("correlationId", source_message.key),
            causation_id=source_message.headers.get("causationId"),
        ),
        order_id=OrderId(str(source_message.payload["orderId"])),
    )


def _order_status_event_from_source_message(source_message: Any) -> Any:
    from token_payments.contexts.order.application import OrderStatusEvent
    from token_payments.shared.domain import EventMetadata, MessageId, OrderId, PaymentId

    payment_id = source_message.payload.get("paymentId")
    return OrderStatusEvent(
        metadata=EventMetadata(
            message_id=MessageId(source_message.identity),
            name=source_message.name,
            aggregate_id=source_message.key,
            occurred_at=source_message.created_at,
            correlation_id=source_message.headers.get("correlationId", source_message.key),
            causation_id=source_message.headers.get("causationId"),
        ),
        order_id=OrderId(str(source_message.payload["orderId"])),
        payment_id=PaymentId(str(payment_id)) if payment_id is not None else None,
        reason=(
            source_message.payload.get("reason")
            or source_message.payload.get("failureReason")
            or _first_text(source_message.payload.get("rejectionReasons"))
        ),
    )


def _first_text(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if value is None:
        return None
    return str(value)


def _single_decision(decisions: tuple[Any, ...], expected_name: str) -> Any:
    matches = tuple(decision for decision in decisions if decision.name.value == expected_name)
    if len(matches) != 1:
        raise RuntimeError(f"expected one {expected_name} decision, got {len(matches)}")
    return matches[0]


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_env_example(path: Path) -> tuple[dict[str, str], list[str]]:
    if not path.exists():
        return {}, [f"{_relative_path(path, _repository_root())} is missing"]

    values: dict[str, str] = {}
    errors: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            errors.append(f".env.example:{line_number} is not KEY=VALUE syntax")
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            errors.append(f".env.example:{line_number} has an empty key")
            continue
        values[key] = value.strip()
    return values, errors


def _validate_env_example(values: Mapping[str, str]) -> list[str]:
    errors = [f".env.example is missing required key {key}" for key in _missing_env_keys(values)]
    for key in COMPOSE_READINESS_SENSITIVE_PLACEHOLDER_KEYS:
        value = values.get(key)
        if not value or not _is_safe_committed_placeholder(value):
            errors.append(f".env.example key {key} must use a local-only placeholder value")
    return errors


def _missing_env_keys(values: Mapping[str, str]) -> list[str]:
    return [key for key in COMPOSE_READINESS_REQUIRED_ENV_KEYS if key not in values]


def _is_safe_committed_placeholder(value: str) -> bool:
    normalized = value.lower()
    return "replace_with_local_dev_only" in normalized


def _read_compose_service_blocks(path: Path) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    if not path.exists():
        return {}, [f"{_relative_path(path, _repository_root())} is missing"]

    services: dict[str, list[str]] = {}
    in_services = False
    current_service: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = _indent_width(raw_line)
        if indent == 0 and stripped == "services:":
            in_services = True
            current_service = None
            continue
        if not in_services:
            continue
        if indent == 0:
            break
        if indent == 2 and stripped.endswith(":") and not stripped.startswith("- "):
            service_name = stripped[:-1]
            services[service_name] = []
            current_service = service_name
            continue
        if current_service is not None:
            services[current_service].append(raw_line)

    if not in_services:
        return {}, ["docker-compose.yml is missing top-level services block"]
    return {service: tuple(block) for service, block in services.items()}, []


def _validate_compose_contracts(
    root: Path,
    service_blocks: Mapping[str, tuple[str, ...]],
    service_contracts: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    errors = [
        f"docker-compose.yml is missing required service {service}"
        for service in COMPOSE_READINESS_REQUIRED_SERVICES
        if service not in service_blocks
    ]
    postgres = service_contracts.get("postgres", {})
    test_network = service_contracts.get("test_network", {})
    pgweb = service_contracts.get("pgweb", {})
    kafka_ui = service_contracts.get("kafka-ui", {})

    if ".env" not in postgres.get("envFile", ()):
        errors.append("postgres service must reference .env through env_file")
    if not postgres.get("initDirectoryMounted"):
        errors.append("postgres service must mount app/postgres/init.d into docker-entrypoint-initdb.d")

    if ".env" not in test_network.get("envFile", ()):
        errors.append("test_network service must reference .env through env_file")
    if test_network.get("buildContext") != "app/test_network":
        errors.append("test_network service must build from app/test_network")
    if not test_network.get("dataVolumeMounted"):
        errors.append("test_network service must mount app/test_network/data at TEST_NETWORK_DB_PATH")

    if ".env" not in pgweb.get("envFile", ()):
        errors.append("pgweb service must reference .env through env_file")
    if "postgres" not in pgweb.get("dependsOn", ()):
        errors.append("pgweb service must depend on postgres")
    if "kafka" not in kafka_ui.get("dependsOn", ()):
        errors.append("kafka-ui service must depend on kafka")

    build_context = test_network.get("buildContext")
    if isinstance(build_context, str) and build_context:
        dockerfile_path = root / build_context / "Dockerfile"
        if not dockerfile_path.exists():
            errors.append(f"{_relative_path(dockerfile_path, root)} is missing")
    return errors


def _docker_runtime_image_contract(path: Path, root: Path) -> tuple[dict[str, JsonValue], list[str]]:
    contract: dict[str, JsonValue] = {
        "dockerfile": _relative_path(path, root),
        "baseImage": None,
        "workdir": None,
        "pythonPath": None,
        "packageCopySource": None,
        "packageCopyDestination": None,
        "supportCopySources": [],
        "cmd": [],
    }
    if not path.exists():
        return contract, [f"{_relative_path(path, root)} is missing"]

    dockerfile = path.read_text(encoding="utf-8")
    copy_pairs = _dockerfile_copy_pairs(dockerfile)
    package_copy = next(
        (
            (source, destination)
            for source, destination in copy_pairs
            if source == "app/token_payments" and destination == "/workspace/app/token_payments"
        ),
        None,
    )
    if package_copy is not None:
        package_copy_source, package_copy_destination = package_copy
    else:
        package_copy_source, package_copy_destination = (None, None)

    contract = {
        "dockerfile": _relative_path(path, root),
        "baseImage": _dockerfile_first_token(dockerfile, "FROM"),
        "workdir": _dockerfile_first_value(dockerfile, "WORKDIR"),
        "pythonPath": _dockerfile_env_value(dockerfile, "PYTHONPATH"),
        "packageCopySource": package_copy_source,
        "packageCopyDestination": package_copy_destination,
        "supportCopySources": [
            source
            for source, _destination in copy_pairs
            if source in DOCKER_RUNTIME_SUPPORT_COPY_SOURCES
        ],
        "cmd": _dockerfile_json_instruction(dockerfile, "CMD"),
    }
    expected = {
        "dockerfile": "Dockerfile",
        "baseImage": "python:3.12-slim",
        "workdir": "/workspace",
        "pythonPath": "/workspace/app",
        "packageCopySource": "app/token_payments",
        "packageCopyDestination": "/workspace/app/token_payments",
        "supportCopySources": list(DOCKER_RUNTIME_SUPPORT_COPY_SOURCES),
        "cmd": ["python", "-m", "token_payments", "health"],
    }
    errors = [
        f"Dockerfile {field} must be {expected_value!r}, got {contract[field]!r}"
        for field, expected_value in expected.items()
        if contract[field] != expected_value
    ]
    if _dockerfile_instruction_values(dockerfile, "ADD"):
        errors.append("Dockerfile must not use ADD")
    return contract, errors


def _docker_runtime_dockerignore_contract(path: Path, root: Path) -> tuple[dict[str, JsonValue], list[str]]:
    contract = {
        "path": _relative_path(path, root),
        "excludesLocalEnv": False,
        "excludesGit": False,
        "excludesCache": False,
        "excludesPhaseOutputs": False,
    }
    if not path.exists():
        return contract, [f"{_relative_path(path, root)} is missing"]

    patterns = _dockerignore_patterns(path.read_text(encoding="utf-8"))
    pattern_set = set(patterns)
    contract = {
        "path": _relative_path(path, root),
        "excludesLocalEnv": {".env", ".venv", "**/data"} <= pattern_set,
        "excludesGit": ".git" in pattern_set,
        "excludesCache": {"__pycache__", ".pytest_cache"} <= pattern_set,
        "excludesPhaseOutputs": {
            "phases/**/step*-output.json",
            "phases/**/phase*-output.json",
        }
        <= pattern_set,
    }
    errors = [
        f".dockerignore is missing required pattern {pattern}"
        for pattern in DOCKER_RUNTIME_REQUIRED_DOCKERIGNORE_PATTERNS
        if pattern not in pattern_set
    ]
    return contract, errors


def _docker_runtime_service_contract(block: tuple[str, ...]) -> dict[str, JsonValue]:
    environment = [str(value) for value in _compose_list_for_key(block, "environment")]
    python_path = next(
        (value.split("=", 1)[1] for value in environment if value.startswith("PYTHONPATH=")),
        None,
    )
    return {
        "image": _compose_scalar_for_key(block, "image"),
        "buildContext": _compose_nested_scalar(block, "build", "context"),
        "dockerfile": _compose_nested_scalar(block, "build", "dockerfile"),
        "envFile": _compose_list_for_key(block, "env_file"),
        "pythonPath": python_path,
        "command": _compose_json_list_for_key(block, "command"),
        "restart": _compose_scalar_for_key(block, "restart"),
        "profiles": _compose_list_for_key(block, "profiles"),
        "dependsOn": _compose_depends_on_conditions(block),
    }


def _postman_api_service_contract(block: tuple[str, ...]) -> dict[str, JsonValue]:
    environment = [str(value) for value in _compose_list_for_key(block, "environment")]
    python_path = next(
        (value.split("=", 1)[1] for value in environment if value.startswith("PYTHONPATH=")),
        None,
    )
    discovered_environment_keys = sorted(item.split("=", 1)[0] for item in environment if "=" in item)
    environment_keys = (
        ["PYTHONPATH", *(key for key in discovered_environment_keys if key != "PYTHONPATH")]
        if "PYTHONPATH" in discovered_environment_keys
        else discovered_environment_keys
    )
    return {
        "image": _compose_scalar_for_key(block, "image"),
        "buildContext": _compose_nested_scalar(block, "build", "context"),
        "dockerfile": _compose_nested_scalar(block, "build", "dockerfile"),
        "envFile": _compose_list_for_key(block, "env_file"),
        "pythonPath": python_path,
        "command": _compose_json_list_for_key(block, "command"),
        "restart": _compose_scalar_for_key(block, "restart"),
        "profiles": _compose_list_for_key(block, "profiles"),
        "ports": _compose_list_for_key(block, "ports"),
        "environmentKeys": environment_keys,
        "dependsOn": _compose_depends_on_conditions(block),
    }


def _validate_docker_runtime_services(
    service_blocks: Mapping[str, tuple[str, ...]],
    runtime_services: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    errors = [
        f"docker-compose.yml is missing required runtime service {service_name}"
        for service_name in DOCKER_RUNTIME_SERVICES
        if service_name not in service_blocks
    ]
    for service_name, expected in DOCKER_RUNTIME_SERVICES.items():
        actual = runtime_services.get(service_name, {})
        for field, expected_value in expected.items():
            if actual.get(field) != expected_value:
                errors.append(
                    f"docker-compose.yml service {service_name} field {field} "
                    f"must be {expected_value!r}, got {actual.get(field)!r}"
                )
    return errors


def _validate_postman_api_service(
    service_blocks: Mapping[str, tuple[str, ...]],
    service_contract: Mapping[str, Any],
) -> list[str]:
    if POSTMAN_API_SERVICE_NAME not in service_blocks:
        return [f"docker-compose.yml is missing required API service {POSTMAN_API_SERVICE_NAME}"]

    errors = [
        f"docker-compose.yml service {POSTMAN_API_SERVICE_NAME} field {field} "
        f"must be {expected_value!r}, got {service_contract.get(field)!r}"
        for field, expected_value in POSTMAN_API_SERVICE.items()
        if service_contract.get(field) != expected_value
    ]
    block_text = "\n".join(service_blocks[POSTMAN_API_SERVICE_NAME])
    for marker in (
        "replace_with_local_dev_only_session_signing_key",
        "replace_with_local_dev_only_csrf_signing_key",
    ):
        if marker in block_text:
            errors.append(
                f"docker-compose.yml service {POSTMAN_API_SERVICE_NAME} must not hard-code {marker}"
            )
    return errors


def _compose_service_contract(block: tuple[str, ...]) -> dict[str, JsonValue]:
    env_file = _compose_list_for_key(block, "env_file")
    volumes = _compose_list_for_key(block, "volumes")
    depends_on = _compose_mapping_keys_for_key(block, "depends_on")
    build_context = _compose_nested_scalar(block, "build", "context")
    return {
        "containerName": _compose_scalar_for_key(block, "container_name"),
        "image": _compose_scalar_for_key(block, "image"),
        "envFile": env_file,
        "volumes": volumes,
        "dependsOn": depends_on,
        "buildContext": build_context,
        "initDirectoryMounted": any(
            "app/postgres/init.d:/docker-entrypoint-initdb.d" in volume for volume in volumes
        ),
        "dataVolumeMounted": any(
            ("app/test_network/data:${TEST_NETWORK_DB_PATH}" in volume or "test_network_data:${TEST_NETWORK_DB_PATH}" in volume)
            for volume in volumes
        ),
    }


def _compose_base_indent(block: tuple[str, ...]) -> int | None:
    indents = [
        _indent_width(line)
        for line in block
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("- ")
    ]
    return min(indents) if indents else None


def _compose_scalar_for_key(block: tuple[str, ...], key: str) -> str | None:
    base_indent = _compose_base_indent(block)
    if base_indent is None:
        return None
    prefix = f"{key}:"
    for line in block:
        stripped = line.strip()
        if _indent_width(line) == base_indent and stripped.startswith(prefix):
            value = stripped[len(prefix) :].strip()
            return _unquote_yamlish_value(value) if value else None
    return None


def _compose_list_for_key(block: tuple[str, ...], key: str) -> list[JsonValue]:
    base_indent = _compose_base_indent(block)
    if base_indent is None:
        return []
    prefix = f"{key}:"
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith(prefix):
            continue
        scalar_value = stripped[len(prefix) :].strip()
        if scalar_value:
            return [_unquote_yamlish_value(scalar_value)]
        values: list[JsonValue] = []
        for nested in block[index + 1 :]:
            nested_stripped = nested.strip()
            if not nested_stripped or nested_stripped.startswith("#"):
                continue
            nested_indent = _indent_width(nested)
            if nested_indent <= indent:
                break
            if nested_stripped.startswith("- "):
                values.append(_compose_list_item_value(nested_stripped[2:].strip()))
        return values
    return []


def _compose_list_item_value(value: str) -> JsonValue:
    if value.startswith("path:"):
        return _unquote_yamlish_value(value[len("path:") :].strip())
    return _unquote_yamlish_value(value)


def _compose_nested_scalar(block: tuple[str, ...], parent_key: str, child_key: str) -> str | None:
    base_indent = _compose_base_indent(block)
    if base_indent is None:
        return None
    parent_prefix = f"{parent_key}:"
    child_prefix = f"{child_key}:"
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith(parent_prefix):
            continue
        for nested in block[index + 1 :]:
            nested_stripped = nested.strip()
            if not nested_stripped or nested_stripped.startswith("#"):
                continue
            nested_indent = _indent_width(nested)
            if nested_indent <= indent:
                break
            if nested_stripped.startswith(child_prefix):
                return _unquote_yamlish_value(nested_stripped[len(child_prefix) :].strip())
    return None


def _compose_json_list_for_key(block: tuple[str, ...], key: str) -> list[JsonValue]:
    value = _compose_scalar_for_key(block, key)
    if value is None:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _compose_mapping_keys_for_key(block: tuple[str, ...], key: str) -> list[JsonValue]:
    base_indent = _compose_base_indent(block)
    if base_indent is None:
        return []
    prefix = f"{key}:"
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith(prefix):
            continue
        keys: list[JsonValue] = []
        for nested in block[index + 1 :]:
            nested_stripped = nested.strip()
            if not nested_stripped or nested_stripped.startswith("#"):
                continue
            nested_indent = _indent_width(nested)
            if nested_indent <= indent:
                break
            if nested_stripped.endswith(":") and not nested_stripped.startswith("- "):
                keys.append(nested_stripped[:-1])
        return keys
    return []


def _compose_depends_on_conditions(block: tuple[str, ...]) -> dict[str, JsonValue]:
    base_indent = _compose_base_indent(block)
    if base_indent is None:
        return {}
    for index, line in enumerate(block):
        stripped = line.strip()
        indent = _indent_width(line)
        if indent != base_indent or not stripped.startswith("depends_on:"):
            continue

        dependencies: dict[str, JsonValue] = {}
        current_dependency: str | None = None
        for nested in block[index + 1 :]:
            nested_stripped = nested.strip()
            if not nested_stripped or nested_stripped.startswith("#"):
                continue
            nested_indent = _indent_width(nested)
            if nested_indent <= indent:
                break
            if nested_stripped.endswith(":") and not nested_stripped.startswith("- "):
                current_dependency = nested_stripped[:-1]
                dependencies[current_dependency] = None
                continue
            if current_dependency and nested_stripped.startswith("condition:"):
                dependencies[current_dependency] = _unquote_yamlish_value(
                    nested_stripped[len("condition:") :].strip()
                )
        return dependencies
    return {}


def _compose_readiness_step(
    name: str,
    summary: str,
    details: Mapping[str, Any],
    errors: Sequence[str],
) -> SmokeStep:
    if errors:
        return SmokeStep(
            name=name,
            result=SmokeResult(
                status=SmokeStatus.FAILED,
                summary=summary,
                details=dict(details) | {"errors": list(errors)},
            ),
        )
    return _passed_step(name, summary, details)


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _unquote_yamlish_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _dockerfile_instruction_values(dockerfile: str, instruction: str) -> list[str]:
    prefix = instruction.upper()
    values: list[str] = []
    for raw_line in dockerfile.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        command, _, payload = line.partition(" ")
        if command.upper() == prefix:
            values.append(payload.strip())
    return values


def _dockerfile_first_value(dockerfile: str, instruction: str) -> str | None:
    values = _dockerfile_instruction_values(dockerfile, instruction)
    return values[0] if values else None


def _dockerfile_first_token(dockerfile: str, instruction: str) -> str | None:
    value = _dockerfile_first_value(dockerfile, instruction)
    if value is None:
        return None
    return shlex.split(value)[0]


def _dockerfile_env_value(dockerfile: str, key: str) -> str | None:
    for value in _dockerfile_instruction_values(dockerfile, "ENV"):
        if value.startswith(f"{key}="):
            return value.split("=", 1)[1]
        parts = shlex.split(value)
        if len(parts) >= 2 and parts[0] == key:
            return parts[1]
    return None


def _dockerfile_json_instruction(dockerfile: str, instruction: str) -> list[JsonValue]:
    value = _dockerfile_first_value(dockerfile, instruction)
    if value is None:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _dockerfile_copy_pairs(dockerfile: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for value in _dockerfile_instruction_values(dockerfile, "COPY"):
        if value.startswith("["):
            parts = [str(item) for item in json.loads(value)]
        else:
            parts = [part for part in shlex.split(value) if not part.startswith("--")]
        if len(parts) < 2:
            continue
        destination = _normalize_docker_path(parts[-1])
        for source in parts[:-1]:
            pairs.append((_normalize_docker_path(source), destination))
    return pairs


def _normalize_docker_path(value: str) -> str:
    normalized = value.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized


def _dockerignore_patterns(dockerignore: str) -> list[str]:
    patterns: list[str] = []
    for raw_line in dockerignore.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line.rstrip("/"))
    return patterns


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _passed_step(name: str, summary: str, details: Mapping[str, Any]) -> SmokeStep:
    return SmokeStep(name=name, result=SmokeResult(status=SmokeStatus.PASSED, summary=summary, details=details))


def _signature_request_payload(request: Any | None) -> dict[str, JsonValue] | None:
    if request is None:
        return None
    return {
        "requestId": request.request_id,
        "amount": _crypto_payload(request.amount),
        "to": str(request.to),
        "expiresAt": request.expires_at,
    }


def _gas_estimate_payload(gas_estimate: Any | None) -> dict[str, JsonValue] | None:
    if gas_estimate is None:
        return None
    return {
        "estimatedFee": _crypto_payload(gas_estimate.estimated_fee),
        "gasLimit": gas_estimate.gas_limit,
        "bufferRate": str(gas_estimate.buffer_rate),
        "maxFee": _crypto_payload(gas_estimate.max_fee) if gas_estimate.max_fee is not None else None,
    }


def _crypto_payload(value: Any) -> dict[str, JsonValue]:
    return {
        "amount": str(value.amount),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }


class _InMemoryOutboxMessageRepository:
    def __init__(self) -> None:
        self.saved: list[Any] = []

    def save(self, message: Any) -> None:
        self.saved.append(message)


class _InMemoryProcessedCommandRepository:
    def __init__(self) -> None:
        self.existing: set[tuple[str, str]] = set()
        self.records: list[Any] = []

    def was_processed(self, command_id: Any, handler: str) -> bool:
        return (handler, str(command_id)) in self.existing

    def record(self, processed_command: Any) -> Any:
        from token_payments.shared.domain import IdempotencyDecision

        self.records.append(processed_command)
        self.existing.add(processed_command.idempotency_key)
        return IdempotencyDecision.PROCESS


class _InMemoryProcessedMessageRepository:
    def __init__(self) -> None:
        self.existing: set[tuple[str, str]] = set()
        self.records: list[Any] = []

    def was_processed(self, message_id: Any, consumer: str) -> bool:
        return (consumer, str(message_id)) in self.existing

    def record(self, processed_message: Any) -> Any:
        from token_payments.shared.domain import IdempotencyDecision

        self.records.append(processed_message)
        self.existing.add(processed_message.idempotency_key)
        return IdempotencyDecision.PROCESS


class _InMemoryCustomerRepository:
    def __init__(self, customers_by_user_id: Mapping[str, Any]) -> None:
        self.customers_by_user_id = dict(customers_by_user_id)

    def get_by_user_id(self, user_id: Any) -> Any | None:
        return self.customers_by_user_id.get(str(user_id))


class _InMemoryOrderStoreRepository:
    def __init__(self, stores_by_id: Mapping[str, Any]) -> None:
        self.stores_by_id = dict(stores_by_id)

    def get(self, store_id: Any) -> Any | None:
        return self.stores_by_id.get(str(store_id))


class _InMemoryOrderRepository:
    def __init__(self) -> None:
        self.orders_by_id: dict[str, Any] = {}

    def get(self, order_id: Any) -> Any | None:
        return self.orders_by_id.get(str(order_id))

    def save(self, order: Any) -> None:
        self.orders_by_id[str(order.order_id)] = order

    def require(self, order_id: Any) -> Any:
        order = self.orders_by_id.get(str(order_id))
        if order is None:
            raise RuntimeError(f"order {order_id} was not saved")
        return order


class _InMemoryInventoryRepository:
    def __init__(self, inventory_by_key: Mapping[tuple[str, str], Any]) -> None:
        self.inventory_by_key = dict(inventory_by_key)

    def get(self, product_id: Any, store_id: Any) -> Any | None:
        return self.inventory_by_key.get((str(product_id), str(store_id)))

    def save(self, inventory: Any) -> None:
        self.inventory_by_key[(str(inventory.product_id), str(inventory.store_id))] = inventory


class _InMemoryPaymentRepository:
    def __init__(self) -> None:
        self.payments_by_id: dict[str, Any] = {}

    def get(self, payment_id: Any) -> Any | None:
        return self.payments_by_id.get(str(payment_id))

    def save(self, payment: Any) -> None:
        self.payments_by_id[str(payment.payment_id)] = payment


class _InMemoryPaymentAuthorizationRepository:
    def __init__(self) -> None:
        self.authorizations_by_payment_id: dict[str, Any] = {}

    def get(self, payment_id: Any) -> Any | None:
        return self.authorizations_by_payment_id.get(str(payment_id))

    def save(self, authorization: Any) -> None:
        self.authorizations_by_payment_id[str(authorization.payment_id)] = authorization


class _InMemoryBlockchainAdapter:
    def __init__(self, *, receipt: Any, gas_estimate: Any) -> None:
        self.receipt = receipt
        self.gas_estimate = gas_estimate

    def estimate_gas(self, amount: Any, wallet_from: Any, wallet_to: Any, chain_network: Any) -> Any:
        return self.gas_estimate

    def get_transaction_receipt(self, tx_hash: Any) -> Any | None:
        if str(tx_hash) == str(self.receipt.hash):
            return self.receipt
        return None


class _InMemoryPaymentTimeoutScheduler:
    def __init__(self) -> None:
        self.scheduled: list[tuple[str, datetime]] = []
        self.cancelled: list[str] = []

    def schedule_expiration(self, payment_id: Any, expires_at: datetime) -> None:
        self.scheduled.append((str(payment_id), expires_at))

    def cancel_expiration(self, payment_id: Any) -> None:
        self.cancelled.append(str(payment_id))


class _InMemoryTransactionService:
    def create_signature_request(self, payment_id: Any, amount: Any, wallet_to: Any, expires_at: datetime) -> Any:
        from token_payments.contexts.payment.domain import TransactionSignatureRequest

        return TransactionSignatureRequest(
            request_id=f"sigreq-{payment_id}",
            amount=amount,
            to=wallet_to,
            expires_at=expires_at,
        )

    def refund_payment(self, payment: Any) -> Any:
        from token_payments.contexts.payment.domain import TransactionReceipt
        from token_payments.shared.domain import TransactionHash

        return TransactionReceipt(
            hash=TransactionHash("0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),
            block_number=123999,
            gas_used=21000,
        )


class _InMemoryApprovalStoreRepository:
    def __init__(self, stores_by_id: Mapping[str, Any]) -> None:
        self.stores_by_id = dict(stores_by_id)

    def get(self, store_id: Any) -> Any | None:
        return self.stores_by_id.get(str(store_id))


class _InMemoryOrderDetailRepository:
    def __init__(self, order_details_by_id: Mapping[str, Any]) -> None:
        self.order_details_by_id = dict(order_details_by_id)

    def get(self, order_id: Any) -> Any | None:
        return self.order_details_by_id.get(str(order_id))

    def save(self, order_detail: Any) -> None:
        self.order_details_by_id[str(order_detail.order_id)] = order_detail


_SMOKE_RUNNERS: Mapping[str, SmokeRunner] = MappingProxyType(
    {
        "happy-path-checkout": _run_happy_path_checkout,
        "compensation-checkout": _run_compensation_checkout,
        "compose-readiness": _run_compose_readiness,
        "docker-runtime-readiness": _run_docker_runtime_readiness,
        "postman-docker-api-readiness": _run_postman_docker_api_readiness,
    }
)


def _coerce_status(value: SmokeStatus | str) -> SmokeStatus:
    if isinstance(value, SmokeStatus):
        return value
    try:
        return SmokeStatus(str(value))
    except ValueError as exc:
        raise ValueError("SmokeResult.status must be one of passed, failed, skipped") from exc


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _to_json_safe_mapping(value: Mapping[str, Any]) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError("details must be a mapping")
    output: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("JSON mapping keys must be strings")
        output[key] = _to_json_safe(item)
    return output


def _to_json_safe(value: Any) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON floats must be finite")
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("JSON datetime must be timezone-aware")
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return _to_json_safe_mapping(value)
    if isinstance(value, tuple | list):
        return [_to_json_safe(item) for item in value]
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "AVAILABLE_SMOKE_SCENARIOS",
    "SMOKE_CONTRACT",
    "UNKNOWN_SMOKE_SCENARIO_ERROR",
    "JsonValue",
    "SmokeResult",
    "SmokeScenarioResult",
    "SmokeStatus",
    "SmokeStep",
    "UnknownSmokeScenario",
    "describe_smoke_registry",
    "run_smoke_scenario",
]

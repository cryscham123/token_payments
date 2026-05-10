"""Deterministic smoke scenario contracts for integration readiness."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
import math
from types import MappingProxyType
from typing import Any, Callable, Mapping
from uuid import UUID


SMOKE_CONTRACT = "CommandDispatchResult.details.smoke"
UNKNOWN_SMOKE_SCENARIO_ERROR = "UNKNOWN_SMOKE_SCENARIO"
AVAILABLE_SMOKE_SCENARIOS = ("happy-path-checkout", "compensation-checkout", "compose-readiness")

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
    from token_payments.contexts.order.application import CreateOrderCommand, CreateOrderItem, OrderApplicationService
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
    order_repository.save(order_repository.require(order_id).confirm_payment(payment_id))
    payment_confirmed_message = confirmed_result.outbox_message
    steps.append(
        _passed_step(
            "PaymentConfirmedEvent",
            "payment handler confirmed receipt and saved checkout event",
            {
                "eventName": payment_confirmed_message.name,
                "status": confirmed_result.status.value,
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
    order_repository.save(order_repository.require(order_id).approve())
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


def _handle_checkout_event(
    *,
    process_manager: Any,
    processed_messages: "_InMemoryProcessedMessageRepository",
    outbox_messages: "_InMemoryOutboxMessageRepository",
    topic_resolver: Any,
    source_message: Any,
) -> tuple[Any, ...]:
    from token_payments.contexts.checkout.application import CheckoutProcessEvent
    from token_payments.shared.domain import EventMetadata, MessageId, OrderId, OutboxMessage, ProcessedMessage

    event = CheckoutProcessEvent(
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


def _single_decision(decisions: tuple[Any, ...], expected_name: str) -> Any:
    matches = tuple(decision for decision in decisions if decision.name.value == expected_name)
    if len(matches) != 1:
        raise RuntimeError(f"expected one {expected_name} decision, got {len(matches)}")
    return matches[0]


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

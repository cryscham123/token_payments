"""Pure order creation application service."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from token_payments.contexts.order.domain import Customer, Order, OrderCancelledEvent, OrderItem, OrderStatus, Store
from token_payments.shared.domain import (
    CheckoutEventName,
    CommandId,
    Crypto,
    EventMetadata,
    IdempotencyDecision,
    OrderId,
    OutboxMessage,
    ProcessedCommand,
    ProcessedMessage,
    ProductId,
)
from token_payments.shared.domain import MessageId, PaymentId

from .commands import CancelOrderCommand, CreateOrderCommand
from .ports import (
    CustomerRepository,
    OrderCreationResult,
    OrderRepository,
    OutboxMessageRepository,
    ProcessedCommandRepository,
    ProcessedMessageRepository,
    StoreRepository,
)


ORDER_EVENT_TOPIC = "order.events"


class OrderErrorCode(StrEnum):
    CUSTOMER_NOT_FOUND = "CUSTOMER_NOT_FOUND"
    STORE_NOT_FOUND = "STORE_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class OrderApplicationError(Exception):
    def __init__(self, code: OrderErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class OrderCommandStatus(StrEnum):
    CANCELLED = "CANCELLED"
    ALREADY_CANCELLED = "ALREADY_CANCELLED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"


class OrderCommandRejectionReason(StrEnum):
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    INVALID_STATE = "INVALID_STATE"


class OrderCommandRejected(Exception):
    def __init__(
        self,
        reason: OrderCommandRejectionReason,
        command_id: CommandId,
        order_id: OrderId,
        message: str,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.command_id = command_id
        self.order_id = order_id


@dataclass(frozen=True)
class OrderCommandResult:
    command_id: CommandId
    order_id: OrderId
    status: OrderCommandStatus
    order: Order | None = None
    outbox_message: OutboxMessage | None = None
    duplicate_decision: IdempotencyDecision | None = None


class OrderProjectionStatus(StrEnum):
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    ORDER_APPROVED = "ORDER_APPROVED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    IGNORED = "IGNORED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"


class OrderProjectionRejectionReason(StrEnum):
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    INVALID_STATE = "INVALID_STATE"
    INVALID_EVENT = "INVALID_EVENT"


class OrderProjectionRejected(Exception):
    def __init__(
        self,
        reason: OrderProjectionRejectionReason,
        message_id: MessageId,
        order_id: OrderId,
        message: str,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.message_id = message_id
        self.order_id = order_id


@dataclass(frozen=True)
class OrderStatusEvent:
    metadata: EventMetadata
    order_id: OrderId
    payment_id: PaymentId | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, EventMetadata):
            raise ValueError("OrderStatusEvent.metadata must be an EventMetadata")
        if not isinstance(self.order_id, OrderId):
            raise ValueError("OrderStatusEvent.order_id must be an OrderId")
        if self.payment_id is not None and not isinstance(self.payment_id, PaymentId):
            raise ValueError("OrderStatusEvent.payment_id must be a PaymentId or None")
        if self.reason is not None:
            object.__setattr__(self, "reason", _require_text(self.reason, "OrderStatusEvent.reason"))

    @property
    def name(self) -> CheckoutEventName | str:
        if isinstance(self.metadata.name, CheckoutEventName):
            return self.metadata.name
        try:
            return CheckoutEventName(str(self.metadata.name))
        except ValueError:
            return self.metadata.name


@dataclass(frozen=True)
class OrderProjectionResult:
    message_id: MessageId
    order_id: OrderId
    status: OrderProjectionStatus
    order: Order | None = None
    duplicate_decision: IdempotencyDecision | None = None


class OrderApplicationService:
    """Create customer orders and start checkout via an outbox event."""

    def __init__(
        self,
        *,
        customers: CustomerRepository,
        stores: StoreRepository,
        orders: OrderRepository,
        outbox_messages: OutboxMessageRepository,
    ) -> None:
        self._customers = customers
        self._stores = stores
        self._orders = orders
        self._outbox_messages = outbox_messages

    def createOrder(self, command: CreateOrderCommand) -> OrderCreationResult:
        customer = self._customers.get_by_user_id(command.authenticated_user_id)
        if customer is None:
            raise OrderApplicationError(
                OrderErrorCode.CUSTOMER_NOT_FOUND,
                f"customer for user {command.authenticated_user_id} was not found",
            )

        store = self._stores.get(command.store_id)
        if store is None:
            raise OrderApplicationError(
                OrderErrorCode.STORE_NOT_FOUND,
                f"store {command.store_id} was not found",
            )

        try:
            order = Order.initialize_order(
                order_id=command.order_id,
                customer=customer,
                store=store,
                delivery_address=command.delivery_address,
                product_quantities=_product_quantities(command),
                created_at=command.requested_at,
                tracking_id=command.tracking_id,
            )
            total_amount = _total_amount(order.items)
            outbox_message = _record_order_created(command, customer, store, order, total_amount)
        except ValueError as exc:
            raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, str(exc)) from exc

        self._orders.save(order)
        self._outbox_messages.save(outbox_message)
        return OrderCreationResult(order=order, total_amount=total_amount, outbox_message=outbox_message)


class OrderCommandHandler:
    HANDLER_NAME = "order-command-handler"

    def __init__(
        self,
        orders: OrderRepository,
        processed_commands: ProcessedCommandRepository,
        outbox_messages: OutboxMessageRepository,
    ) -> None:
        self._orders = orders
        self._processed_commands = processed_commands
        self._outbox_messages = outbox_messages

    def cancel_order(self, command: CancelOrderCommand) -> OrderCommandResult:
        if self._is_duplicate(command.command_id):
            return OrderCommandResult(
                command_id=command.command_id,
                order_id=command.order_id,
                status=OrderCommandStatus.DUPLICATE_IGNORED,
                duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
            )

        order = self._load_order(command)
        if order.status is OrderStatus.CANCELLED:
            self._record_processed(command)
            return OrderCommandResult(
                command_id=command.command_id,
                order_id=command.order_id,
                status=OrderCommandStatus.ALREADY_CANCELLED,
                order=order,
            )

        try:
            cancelled = order.cancel(command.reason)
            event = cancelled.record_cancelled(command.requested_at)
        except ValueError as exc:
            raise OrderCommandRejected(
                reason=OrderCommandRejectionReason.INVALID_STATE,
                command_id=command.command_id,
                order_id=command.order_id,
                message=str(exc),
            ) from exc

        outbox_message = _record_order_cancelled(command, event)
        self._orders.save(cancelled)
        self._outbox_messages.save(outbox_message)
        self._record_processed(command)
        return OrderCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=OrderCommandStatus.CANCELLED,
            order=cancelled,
            outbox_message=outbox_message,
        )

    def _is_duplicate(self, command_id: CommandId) -> bool:
        return self._processed_commands.was_processed(command_id, self.HANDLER_NAME)

    def _load_order(self, command: CancelOrderCommand) -> Order:
        order = self._orders.get(command.order_id)
        if order is None:
            raise OrderCommandRejected(
                reason=OrderCommandRejectionReason.ORDER_NOT_FOUND,
                command_id=command.command_id,
                order_id=command.order_id,
                message=f"order {command.order_id} was not found",
            )
        return order

    def _record_processed(self, command: CancelOrderCommand) -> None:
        self._processed_commands.record(
            ProcessedCommand.record(
                command_id=command.command_id,
                handler=self.HANDLER_NAME,
                processed_at=command.requested_at,
                order_id=command.order_id,
            )
        )


class OrderStatusEventProjector:
    CONSUMER_NAME = "order-status-projector"

    def __init__(
        self,
        orders: OrderRepository,
        processed_messages: ProcessedMessageRepository,
    ) -> None:
        self._orders = orders
        self._processed_messages = processed_messages

    def project(self, event: OrderStatusEvent) -> OrderProjectionResult:
        if self._processed_messages.was_processed(event.metadata.message_id, self.CONSUMER_NAME):
            return OrderProjectionResult(
                message_id=event.metadata.message_id,
                order_id=event.order_id,
                status=OrderProjectionStatus.DUPLICATE_IGNORED,
                duplicate_decision=IdempotencyDecision.IGNORE_DUPLICATE,
            )

        if event.name is CheckoutEventName.PAYMENT_CONFIRMED:
            result = self._project_payment_confirmed(event)
        elif event.name is CheckoutEventName.ORDER_APPROVED:
            result = self._project_order_approved(event)
        elif event.name in {
            CheckoutEventName.PAYMENT_FAILED,
            CheckoutEventName.PAYMENT_EXPIRED,
            CheckoutEventName.ORDER_REJECTED,
            CheckoutEventName.ORDER_CANCELLED,
        }:
            result = OrderProjectionResult(
                message_id=event.metadata.message_id,
                order_id=event.order_id,
                status=OrderProjectionStatus.IGNORED,
            )
        else:
            result = OrderProjectionResult(
                message_id=event.metadata.message_id,
                order_id=event.order_id,
                status=OrderProjectionStatus.IGNORED,
            )

        self._record_processed(event)
        return result

    def _project_payment_confirmed(self, event: OrderStatusEvent) -> OrderProjectionResult:
        if event.payment_id is None:
            raise OrderProjectionRejected(
                reason=OrderProjectionRejectionReason.INVALID_EVENT,
                message_id=event.metadata.message_id,
                order_id=event.order_id,
                message="PaymentConfirmedEvent requires payment_id",
            )

        order = self._load_order(event)
        if order.status is OrderStatus.PENDING:
            paid = order.confirm_payment(event.payment_id)
            self._orders.save(paid)
            return OrderProjectionResult(
                message_id=event.metadata.message_id,
                order_id=event.order_id,
                status=OrderProjectionStatus.PAYMENT_CONFIRMED,
                order=paid,
            )
        if order.status in {OrderStatus.PAID, OrderStatus.APPROVED} and order.payment_id == event.payment_id:
            return OrderProjectionResult(
                message_id=event.metadata.message_id,
                order_id=event.order_id,
                status=OrderProjectionStatus.ALREADY_APPLIED,
                order=order,
            )
        raise OrderProjectionRejected(
            reason=OrderProjectionRejectionReason.INVALID_STATE,
            message_id=event.metadata.message_id,
            order_id=event.order_id,
            message=f"cannot project PaymentConfirmedEvent for order in {order.status} status",
        )

    def _project_order_approved(self, event: OrderStatusEvent) -> OrderProjectionResult:
        order = self._load_order(event)
        if order.status is OrderStatus.PAID:
            approved = order.approve()
            self._orders.save(approved)
            return OrderProjectionResult(
                message_id=event.metadata.message_id,
                order_id=event.order_id,
                status=OrderProjectionStatus.ORDER_APPROVED,
                order=approved,
            )
        if order.status is OrderStatus.APPROVED:
            return OrderProjectionResult(
                message_id=event.metadata.message_id,
                order_id=event.order_id,
                status=OrderProjectionStatus.ALREADY_APPLIED,
                order=order,
            )
        raise OrderProjectionRejected(
            reason=OrderProjectionRejectionReason.INVALID_STATE,
            message_id=event.metadata.message_id,
            order_id=event.order_id,
            message=f"cannot project OrderApprovedEvent for order in {order.status} status",
        )

    def _load_order(self, event: OrderStatusEvent) -> Order:
        order = self._orders.get(event.order_id)
        if order is None:
            raise OrderProjectionRejected(
                reason=OrderProjectionRejectionReason.ORDER_NOT_FOUND,
                message_id=event.metadata.message_id,
                order_id=event.order_id,
                message=f"order {event.order_id} was not found",
            )
        return order

    def _record_processed(self, event: OrderStatusEvent) -> None:
        self._processed_messages.record(
            ProcessedMessage.record(
                message_id=event.metadata.message_id,
                consumer=self.CONSUMER_NAME,
                processed_at=event.metadata.occurred_at,
                order_id=event.order_id,
            )
        )


def _product_quantities(command: CreateOrderCommand) -> dict[ProductId, int]:
    quantities: dict[ProductId, int] = {}
    for item in command.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    return quantities


def _record_order_created(
    command: CreateOrderCommand,
    customer: Customer,
    store: Store,
    order: Order,
    total_amount: Crypto,
) -> OutboxMessage:
    metadata = EventMetadata(
        message_id=command.event_message_id,
        name=CheckoutEventName.ORDER_CREATED,
        aggregate_id=str(order.order_id),
        occurred_at=command.requested_at,
        correlation_id=str(order.order_id),
        causation_id=command.causation_id,
    )
    headers = {
        "correlationId": str(order.order_id),
        "userId": str(command.authenticated_user_id),
    }
    if command.causation_id is not None:
        headers["causationId"] = command.causation_id

    return OutboxMessage.record_event(
        metadata=metadata,
        topic=ORDER_EVENT_TOPIC,
        key=str(order.order_id),
        payload=_order_created_payload(command, customer, store, order, total_amount),
        headers=headers,
    )


def _record_order_cancelled(command: CancelOrderCommand, event: OrderCancelledEvent) -> OutboxMessage:
    order = event.order
    metadata = EventMetadata(
        message_id=command.event_message_id,
        name=CheckoutEventName.ORDER_CANCELLED,
        aggregate_id=str(order.order_id),
        occurred_at=event.created_at,
        correlation_id=str(order.order_id),
        causation_id=str(command.command_id),
    )
    headers = {
        "correlationId": str(order.order_id),
        "causationId": str(command.command_id),
    }
    if command.causation_id is not None:
        headers["sourceCausationId"] = command.causation_id

    return OutboxMessage.record_event(
        metadata=metadata,
        topic=ORDER_EVENT_TOPIC,
        key=str(order.order_id),
        payload=_order_cancelled_payload(command, event),
        headers=headers,
    )


def _order_created_payload(
    command: CreateOrderCommand,
    customer: Customer,
    store: Store,
    order: Order,
    total_amount: Crypto,
) -> dict[str, Any]:
    if store.store_wallet is None:
        raise ValueError("store wallet is required to start checkout")

    primary_item = order.items[0]
    return {
        "eventName": CheckoutEventName.ORDER_CREATED.value,
        "orderId": str(order.order_id),
        "customerId": str(order.customer_id),
        "userId": str(command.authenticated_user_id),
        "storeId": str(order.store_id),
        "trackingId": str(order.tracking_id),
        "status": order.status.value,
        "deliveryAddress": {
            "id": order.delivery_address.id,
            "street": order.delivery_address.street,
        },
        "items": [_item_payload(item) for item in order.items],
        "productId": str(primary_item.product_snapshot.product_id),
        "quantity": primary_item.quantity,
        "amount": _crypto_payload(total_amount),
        "walletFrom": str(customer.customer_wallet),
        "walletTo": str(store.store_wallet),
        "chain": _chain_payload(total_amount),
        "occurredAt": command.requested_at.isoformat(),
        "correlationId": str(order.order_id),
        "causationId": command.causation_id,
    }


def _order_cancelled_payload(command: CancelOrderCommand, event: OrderCancelledEvent) -> dict[str, Any]:
    order = event.order
    return {
        "eventName": CheckoutEventName.ORDER_CANCELLED.value,
        "orderId": str(order.order_id),
        "status": order.status.value,
        "reason": command.reason,
        "failureMessages": list(order.failure_messages),
        "occurredAt": event.created_at.isoformat(),
        "correlationId": str(order.order_id),
        "causationId": str(command.command_id),
    }


def _item_payload(item: OrderItem) -> dict[str, Any]:
    snapshot = item.product_snapshot
    return {
        "orderItemId": str(item.order_item_id),
        "productId": str(snapshot.product_id),
        "name": snapshot.name,
        "quantity": item.quantity,
        "unitPrice": _crypto_payload(snapshot.price),
        "subTotal": _crypto_payload(item.sub_total),
    }


def _total_amount(items: tuple[OrderItem, ...]) -> Crypto:
    first = items[0].sub_total
    amount = Decimal("0")
    for item in items:
        subtotal = item.sub_total
        if (
            subtotal.symbol != first.symbol
            or subtotal.chain_id != first.chain_id
            or subtotal.token_address != first.token_address
            or subtotal.decimals != first.decimals
        ):
            raise ValueError("order items must use a single crypto asset")
        amount += subtotal.amount

    return Crypto(
        amount=amount,
        symbol=first.symbol,
        chain_id=first.chain_id,
        token_address=first.token_address,
        decimals=first.decimals,
    )


def _crypto_payload(value: Crypto) -> dict[str, Any]:
    return {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }


def _chain_payload(value: Crypto) -> dict[str, Any]:
    return {"chainId": value.chain_id, "name": f"chain-{value.chain_id}"}


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()

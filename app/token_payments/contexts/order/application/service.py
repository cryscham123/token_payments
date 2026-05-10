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
    ProductId,
)

from .commands import CancelOrderCommand, CreateOrderCommand
from .ports import (
    CustomerRepository,
    OrderCreationResult,
    OrderRepository,
    OutboxMessageRepository,
    ProcessedCommandRepository,
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

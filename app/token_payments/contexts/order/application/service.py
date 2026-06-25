"""Pure order creation application service."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping

from token_payments.contexts.auth.domain.wallet import UserWallet, WalletId
from token_payments.contexts.order.domain import (
    Address,
    Customer,
    Order,
    OrderCancelledEvent,
    OrderItem,
    OrderStatus,
    Product,
    ProductOptionValuePrice,
    ProductVariantPrice,
    Store,
)
from token_payments.contexts.payment.domain import PaymentAsset, PaymentAssetRegistry
from token_payments.shared.domain import (
    CheckoutEventName,
    CommandId,
    Crypto,
    EventMetadata,
    ExchangeRate,
    IdempotencyDecision,
    MessageId,
    Money,
    OrderId,
    OutboxMessage,
    PaymentId,
    PriceConversion,
    ProcessedCommand,
    ProcessedMessage,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
)

from .commands import CancelOrderCommand, CreateOrderCommand, CreateOrderItem
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
    OPEN_ORDER_EXISTS = "OPEN_ORDER_EXISTS"


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
        wallets: Any | None = None,
        payment_assets: PaymentAssetRegistry | None = None,
        exchange_rate: ExchangeRate | None = None,
    ) -> None:
        self._customers = customers
        self._stores = stores
        self._orders = orders
        self._outbox_messages = outbox_messages
        self._wallets = wallets
        self._payment_assets = payment_assets
        self._exchange_rate = exchange_rate

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
            selected_asset = _selected_asset(self._payment_assets, command.payment_asset_id)
            is_modern_pricing = (
                self._exchange_rate is not None
                and len(store.products) > 0
                and isinstance(store.products[0].price, Money)
            )
            if is_modern_pricing:
                conversion = self._price_conversion(store, selected_asset)
            else:
                conversion = command.payment_asset_id
                if selected_asset is not None:
                    store = _store_with_asset_prices(store, selected_asset)
            selected_wallet = self._resolve_wallet(command, selected_asset)
            order = Order.initialize_order(
                order_id=command.order_id,
                customer=customer,
                store=store,
                delivery_address=command.delivery_address,
                item_requests=command.items,
                created_at=command.requested_at,
                tracking_id=command.tracking_id,
                conversion=conversion,
            )
            total_amount = _total_amount(order.items)
            if selected_asset is not None:
                _require_asset_matches_amount(selected_asset, total_amount)
            if selected_wallet is None:
                selected_wallet = self._resolve_wallet_for_amount(command, total_amount)
            _require_wallet_matches_amount(selected_wallet, total_amount)
            outbox_message = _record_order_created(command, customer, store, order, total_amount, selected_wallet)
        except ValueError as exc:
            raise OrderApplicationError(OrderErrorCode.VALIDATION_ERROR, str(exc)) from exc

        self._orders.save(order)
        self._outbox_messages.save(outbox_message)
        return OrderCreationResult(order=order, total_amount=total_amount, outbox_message=outbox_message)

    def _price_conversion(self, store: Store, selected_asset: PaymentAsset | None) -> PriceConversion:
        if selected_asset is None:
            raise ValueError("a payment asset must be selected to price the order")
        if store.supported_payment_asset_ids and selected_asset.asset_id not in store.supported_payment_asset_ids:
            raise ValueError(
                f"payment asset {selected_asset.asset_id} is not supported by store {store.store_id}"
            )
        if self._exchange_rate is None:
            raise ValueError("an exchange rate is required to price the order")
        return PriceConversion(
            rate=self._exchange_rate,
            asset_id=selected_asset.asset_id,
            symbol=selected_asset.symbol,
            chain_id=selected_asset.chain_id,
            token_address=selected_asset.contract_address,
            decimals=selected_asset.decimals,
        )

    def _resolve_wallet(self, command: CreateOrderCommand, selected_asset: PaymentAsset | None) -> UserWallet | None:
        if command.wallet_id is None and selected_asset is None:
            return None
        if self._wallets is None:
            raise ValueError("wallet repository is required for walletId/paymentAssetId checkout")
        chain_id = selected_asset.chain_id if selected_asset is not None else None
        if command.wallet_id is not None:
            wallet = self._wallets.get_by_id(command.wallet_id)
            if wallet is None:
                raise ValueError("selected wallet was not found")
            _require_owned_active_wallet(command.authenticated_user_id, wallet)
            if chain_id is not None and wallet.chain_id != chain_id:
                raise ValueError("selected wallet chain must match selected payment asset chain")
            return wallet
        if chain_id is None:
            return None
        wallet = self._primary_wallet(command.authenticated_user_id, chain_id)
        if wallet is None:
            raise ValueError(f"no primary wallet found for chain {chain_id}")
        return wallet

    def _resolve_wallet_for_amount(self, command: CreateOrderCommand, amount: Crypto) -> UserWallet | None:
        if self._wallets is None:
            return None
        if command.wallet_id is not None:
            wallet = self._wallets.get_by_id(command.wallet_id)
            if wallet is None:
                raise ValueError("selected wallet was not found")
            _require_owned_active_wallet(command.authenticated_user_id, wallet)
            return wallet
        wallet = self._primary_wallet(command.authenticated_user_id, amount.chain_id)
        if wallet is None:
            if command.payment_asset_id is None:
                return None
            raise ValueError(f"no primary wallet found for chain {amount.chain_id}")
        return wallet

    def _primary_wallet(self, user_id: Any, chain_id: int) -> UserWallet | None:
        get_primary = getattr(self._wallets, "get_primary_for_user_chain", None)
        if callable(get_primary):
            return get_primary(user_id, chain_id)
        list_for_user = getattr(self._wallets, "list_for_user", None)
        if callable(list_for_user):
            for wallet in list_for_user(user_id):
                if getattr(wallet, "chain_id", None) == chain_id and getattr(wallet, "primary", False) and wallet.is_active():
                    return wallet
        return None


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
    payer_wallet: UserWallet | None = None,
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
        payload=_order_created_payload(command, customer, store, order, total_amount, payer_wallet),
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
    payer_wallet: UserWallet | None = None,
) -> dict[str, Any]:
    if store.store_wallet is None:
        raise ValueError("store wallet is required to start checkout")
    wallet_from = payer_wallet.address if payer_wallet is not None else customer.customer_wallet
    if wallet_from is None:
        raise ValueError("payer wallet is required to start checkout")

    primary_item = order.items[0]
    payload = {
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
        "items": [_item_payload(item, command.payment_asset_id) for item in order.items],
        "productId": str(primary_item.product_snapshot.product_id),
        "publicVariantId": primary_item.product_snapshot.public_variant_id,
        "quantity": primary_item.quantity,
        "amount": _crypto_payload(total_amount, asset_id=command.payment_asset_id),
        "paymentAssetId": command.payment_asset_id,
        "payerWalletId": str(payer_wallet.wallet_id) if payer_wallet is not None else None,
        "walletFrom": str(wallet_from),
        "walletTo": str(store.store_wallet),
        "chain": _chain_payload(total_amount),
        "occurredAt": command.requested_at.isoformat(),
        "correlationId": str(order.order_id),
        "causationId": command.causation_id,
    }
    if payer_wallet is not None:
        payload["payerWallet"] = _payer_wallet_payload(payer_wallet)
    return payload


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


def _item_payload(item: OrderItem, asset_id: str | None = None) -> dict[str, Any]:
    snapshot = item.product_snapshot
    payload = {
        "orderItemId": str(item.order_item_id),
        "productId": str(snapshot.product_id),
        "name": snapshot.name,
        "quantity": item.quantity,
        "unitPrice": _crypto_payload(snapshot.price, asset_id=asset_id),
        "subTotal": _crypto_payload(item.sub_total, asset_id=asset_id),
        "media": list(snapshot.media),
    }
    if snapshot.public_variant_id is not None or snapshot.selected_options:
        payload["orderLineKey"] = item.line_key
    if snapshot.public_variant_id is not None:
        payload["publicVariantId"] = snapshot.public_variant_id
    if snapshot.selected_options:
        payload["selectedOptions"] = dict(snapshot.selected_options)
    return payload


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


def _crypto_payload(value: Crypto, *, asset_id: str | None = None) -> dict[str, Any]:
    payload = {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }
    if asset_id is not None:
        payload["assetId"] = asset_id
        payload["amountMinorUnits"] = str(_crypto_minor_units(value))
    return payload


def _chain_payload(value: Crypto) -> dict[str, Any]:
    return {"chainId": value.chain_id, "name": f"chain-{value.chain_id}"}




def _selected_asset(registry: PaymentAssetRegistry | None, payment_asset_id: str | None) -> PaymentAsset | None:
    if payment_asset_id is None:
        return None
    if registry is None:
        raise ValueError("payment asset registry is required for paymentAssetId checkout")
    return registry.require_enabled_asset(payment_asset_id)


def _require_asset_matches_amount(asset: PaymentAsset, amount: Crypto) -> None:
    if asset.chain_id != amount.chain_id:
        raise ValueError("selected payment asset chain must match order amount chain")
    if asset.symbol != amount.symbol or asset.decimals != amount.decimals or asset.contract_address != amount.token_address:
        raise ValueError("selected payment asset metadata must match product price")


def _require_owned_active_wallet(user_id: Any, wallet: UserWallet) -> None:
    if wallet.user_id != user_id:
        raise ValueError("selected wallet does not belong to authenticated user")
    if not wallet.is_active():
        raise ValueError("selected wallet must be a verified active wallet")


def _require_wallet_matches_amount(wallet: UserWallet | None, amount: Crypto) -> None:
    if wallet is None:
        return
    if wallet.chain_id != amount.chain_id:
        raise ValueError("selected wallet chain must match payment asset chain")


def _payer_wallet_payload(wallet: UserWallet) -> dict[str, Any]:
    address = str(wallet.address)
    return {
        "walletId": str(wallet.wallet_id),
        "chainId": wallet.chain_id,
        "addressPreview": f"{address[:6]}...{address[-4:]}",
    }


def _crypto_minor_units(value: Crypto) -> int:
    scale = Decimal(10) ** value.decimals
    scaled = value.amount * scale
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError("amount precision exceeds asset decimals")
    return int(integral)


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _store_with_asset_prices(store: Store, asset: PaymentAsset) -> Store:
    if store.supported_payment_asset_ids and asset.asset_id not in store.supported_payment_asset_ids:
        raise ValueError(f"payment asset {asset.asset_id} is not supported by store {store.store_id}")
    enriched_products: list[Product] = []
    for product in store.products:
        existing = dict(product.asset_prices) if product.asset_prices else {}
        if asset.asset_id not in existing:
            existing[asset.asset_id] = asset.crypto(product.price.amount) if isinstance(product.price, Money) else asset.crypto(product.price.amount)
        variants = _variants_for_asset(product.variants, asset)
        option_values = _option_values_for_asset(product.option_values, asset)
        enriched_products.append(
            replace(product, asset_prices=existing, variants=variants, option_values=option_values)
        )
    return replace(store, products=tuple(enriched_products))


def _variants_for_asset(
    variants: Mapping[str, ProductVariantPrice] | None,
    asset: PaymentAsset,
) -> Mapping[str, ProductVariantPrice] | None:
    if not variants:
        return variants
    return {
        variant_id: replace(variant, price_delta=asset.crypto(variant.price_delta.amount))
        for variant_id, variant in variants.items()
    }


def _option_values_for_asset(
    option_values: Mapping[str, ProductOptionValuePrice] | None,
    asset: PaymentAsset,
) -> Mapping[str, ProductOptionValuePrice] | None:
    if not option_values:
        return option_values
    return {
        key: (
            value
            if value.price_delta is None
            else replace(value, price_delta=asset.crypto(value.price_delta.amount))
        )
        for key, value in option_values.items()
    }

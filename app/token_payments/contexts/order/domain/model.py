"""Domain model for order creation and tracking."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Mapping, Self, TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from token_payments.shared.domain import (
    Crypto,
    CustomerId,
    OrderId,
    PaymentId,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
)


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    APPROVED = "APPROVED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class TrackingId:
    value: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _coerce_uuid(self.value, "TrackingId.value"))

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class OrderItemId:
    value: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _coerce_uuid(self.value, "OrderItemId.value"))

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    @classmethod
    def for_order_product(cls, order_id: OrderId, product_id: ProductId) -> Self:
        if not isinstance(order_id, OrderId):
            raise ValueError("OrderItemId.for_order_product requires an OrderId")
        if not isinstance(product_id, ProductId):
            raise ValueError("OrderItemId.for_order_product requires a ProductId")
        return cls(uuid5(NAMESPACE_URL, f"token-payments/order-item/{order_id}/{product_id}"))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class Address:
    id: str
    street: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _require_text(self.id, "Address.id"))
        object.__setattr__(self, "street", _require_text(self.street, "Address.street"))


@dataclass(frozen=True)
class ProductSnapshot:
    product_id: ProductId
    created_date: datetime
    name: str
    price: Crypto

    def __post_init__(self) -> None:
        if not isinstance(self.product_id, ProductId):
            raise ValueError("ProductSnapshot.product_id must be a ProductId")
        object.__setattr__(
            self,
            "created_date",
            _require_aware_datetime(self.created_date, "ProductSnapshot.created_date"),
        )
        object.__setattr__(self, "name", _require_text(self.name, "ProductSnapshot.name"))
        if not isinstance(self.price, Crypto):
            raise ValueError("ProductSnapshot.price must be a Crypto value")


@dataclass(frozen=True)
class Product:
    product_id: ProductId
    name: str
    price: Crypto
    asset_prices: Mapping[str, Crypto] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.product_id, ProductId):
            raise ValueError("Product.product_id must be a ProductId")
        object.__setattr__(self, "name", _require_text(self.name, "Product.name"))
        if not isinstance(self.price, Crypto):
            raise ValueError("Product.price must be a Crypto value")
        if self.asset_prices is not None:
            if not isinstance(self.asset_prices, Mapping):
                raise ValueError("Product.asset_prices must be a mapping")
            object.__setattr__(
                self,
                "asset_prices",
                {
                    _require_text(str(asset_id), "Product.asset_prices key"): _require_crypto(price)
                    for asset_id, price in self.asset_prices.items()
                },
            )

    def snapshot(self, created_date: datetime | None = None) -> ProductSnapshot:
        return ProductSnapshot(
            product_id=self.product_id,
            created_date=created_date or datetime.now(UTC),
            name=self.name,
            price=self.price,
        )

    def snapshot_for_asset(self, payment_asset_id: str | None, created_date: datetime | None = None) -> ProductSnapshot:
        return ProductSnapshot(
            product_id=self.product_id,
            created_date=created_date or datetime.now(UTC),
            name=self.name,
            price=self.price_for_asset(payment_asset_id),
        )

    def price_for_asset(self, payment_asset_id: str | None) -> Crypto:
        if payment_asset_id is None:
            return self.price
        payment_asset_id = _require_text(payment_asset_id, "payment_asset_id")
        prices = self.asset_prices if self.asset_prices is not None else getattr(self, "_asset_prices", None)
        if not isinstance(prices, Mapping) or payment_asset_id not in prices:
            raise ValueError(f"payment asset {payment_asset_id} is not supported by product {self.product_id}")
        return _require_crypto(prices[payment_asset_id])


@dataclass(frozen=True)
class Customer:
    customer_id: CustomerId
    user_id: UserId

    def __post_init__(self) -> None:
        if not isinstance(self.customer_id, CustomerId):
            raise ValueError("Customer.customer_id must be a CustomerId")
        if not isinstance(self.user_id, UserId):
            raise ValueError("Customer.user_id must be a UserId")

    @property
    def customer_wallet(self) -> WalletAddress | None:
        return getattr(self, "_customer_wallet", None)


@dataclass(frozen=True)
class Store:
    store_id: StoreId
    owner_user_id: UserId
    products: tuple[Product, ...]
    active: bool = True
    store_address: Address | None = None
    store_wallet: WalletAddress | None = None
    supported_chain_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.store_id, StoreId):
            raise ValueError("Store.store_id must be a StoreId")
        if not isinstance(self.owner_user_id, UserId):
            raise ValueError("Store.owner_user_id must be a UserId")
        object.__setattr__(self, "products", _coerce_tuple(self.products, Product, "Store.products"))
        if not isinstance(self.active, bool):
            raise ValueError("Store.active must be a bool")
        if self.store_address is not None and not isinstance(self.store_address, Address):
            raise ValueError("Store.store_address must be an Address or None")
        if self.store_wallet is not None:
            object.__setattr__(self, "store_wallet", _coerce_wallet(self.store_wallet))
        object.__setattr__(
            self,
            "supported_chain_ids",
            tuple(_coerce_positive_int(chain_id, "Store.supported_chain_ids") for chain_id in self.supported_chain_ids),
        )

    def require_product(self, product_id: ProductId) -> Product:
        if not isinstance(product_id, ProductId):
            raise ValueError("Store.require_product requires a ProductId")
        for product in self.products:
            if product.product_id == product_id:
                return product
        raise ValueError(f"product {product_id} does not belong to store {self.store_id}")

    def supports_chain(self, chain_id: int) -> bool:
        chain_id = _coerce_positive_int(chain_id, "chain_id")
        return not self.supported_chain_ids or chain_id in self.supported_chain_ids


@dataclass(frozen=True)
class OrderItem:
    order_item_id: OrderItemId
    order_id: OrderId
    product_snapshot: ProductSnapshot
    quantity: int
    sub_total: Crypto

    def __post_init__(self) -> None:
        if not isinstance(self.order_item_id, OrderItemId):
            raise ValueError("OrderItem.order_item_id must be an OrderItemId")
        if not isinstance(self.order_id, OrderId):
            raise ValueError("OrderItem.order_id must be an OrderId")
        if not isinstance(self.product_snapshot, ProductSnapshot):
            raise ValueError("OrderItem.product_snapshot must be a ProductSnapshot")
        object.__setattr__(self, "quantity", _coerce_positive_int(self.quantity, "OrderItem.quantity"))
        if not isinstance(self.sub_total, Crypto):
            raise ValueError("OrderItem.sub_total must be a Crypto value")

    @classmethod
    def from_product(
        cls,
        order_id: OrderId,
        product: Product,
        quantity: int,
        snapshotted_at: datetime | None = None,
        order_item_id: OrderItemId | None = None,
        payment_asset_id: str | None = None,
    ) -> Self:
        if not isinstance(order_id, OrderId):
            raise ValueError("OrderItem.from_product requires an OrderId")
        if not isinstance(product, Product):
            raise ValueError("OrderItem.from_product requires a Product")
        quantity = _coerce_positive_int(quantity, "quantity")
        snapshot = product.snapshot_for_asset(payment_asset_id, snapshotted_at)
        return cls(
            order_item_id=order_item_id or OrderItemId.for_order_product(order_id, product.product_id),
            order_id=order_id,
            product_snapshot=snapshot,
            quantity=quantity,
            sub_total=_multiply_crypto(snapshot.price, quantity),
        )


@dataclass(frozen=True)
class Order:
    order_id: OrderId
    customer_id: CustomerId
    store_id: StoreId
    delivery_address: Address
    items: tuple[OrderItem, ...]
    tracking_id: TrackingId
    status: OrderStatus = OrderStatus.PENDING
    payment_id: PaymentId | None = None
    failure_messages: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, OrderId):
            raise ValueError("Order.order_id must be an OrderId")
        if not isinstance(self.customer_id, CustomerId):
            raise ValueError("Order.customer_id must be a CustomerId")
        if not isinstance(self.store_id, StoreId):
            raise ValueError("Order.store_id must be a StoreId")
        if not isinstance(self.delivery_address, Address):
            raise ValueError("Order.delivery_address must be an Address")
        object.__setattr__(self, "items", _coerce_tuple(self.items, OrderItem, "Order.items"))
        if not self.items:
            raise ValueError("Order.items must contain at least one item")
        for item in self.items:
            if item.order_id != self.order_id:
                raise ValueError("Order.items must belong to the same OrderId")
        if not isinstance(self.tracking_id, TrackingId):
            raise ValueError("Order.tracking_id must be a TrackingId")
        object.__setattr__(self, "status", _coerce_order_status(self.status))
        if self.payment_id is not None and not isinstance(self.payment_id, PaymentId):
            raise ValueError("Order.payment_id must be a PaymentId or None")
        object.__setattr__(
            self,
            "failure_messages",
            tuple(_require_text(message, "Order.failure_messages") for message in self.failure_messages),
        )

    @classmethod
    def initialize_order(
        cls,
        order_id: OrderId,
        customer: Customer,
        store: Store,
        delivery_address: Address,
        product_quantities: dict[ProductId, int],
        created_at: datetime | None = None,
        tracking_id: TrackingId | None = None,
        payment_asset_id: str | None = None,
    ) -> Self:
        if not isinstance(customer, Customer):
            raise ValueError("Order.initialize_order requires a Customer")
        if not isinstance(store, Store):
            raise ValueError("Order.initialize_order requires a Store")
        if not store.active:
            raise ValueError("inactive stores cannot accept orders")
        if not isinstance(delivery_address, Address):
            raise ValueError("Order.initialize_order requires an Address")
        if not product_quantities:
            raise ValueError("Order.initialize_order requires at least one product")

        snapshotted_at = created_at or datetime.now(UTC)
        snapshotted_at = _require_aware_datetime(snapshotted_at, "created_at")
        items: list[OrderItem] = []
        for product_id, quantity in product_quantities.items():
            product = store.require_product(product_id)
            price = product.price_for_asset(payment_asset_id)
            if not store.supports_chain(price.chain_id):
                raise ValueError(f"store {store.store_id} does not support chain {price.chain_id}")
            items.append(OrderItem.from_product(order_id, product, quantity, snapshotted_at, payment_asset_id=payment_asset_id))

        return cls(
            order_id=order_id,
            customer_id=customer.customer_id,
            store_id=store.store_id,
            delivery_address=delivery_address,
            items=tuple(items),
            tracking_id=tracking_id or TrackingId.new(),
            status=OrderStatus.PENDING,
        )

    def confirm_payment(self, payment_id: PaymentId) -> Self:
        if not isinstance(payment_id, PaymentId):
            raise ValueError("Order.confirm_payment requires a PaymentId")
        self._ensure_status(OrderStatus.PENDING, "confirm payment")
        return replace(self, status=OrderStatus.PAID, payment_id=payment_id)

    def approve(self) -> Self:
        self._ensure_status(OrderStatus.PAID, "approve")
        return replace(self, status=OrderStatus.APPROVED)

    def initiate_refund(self, reason: str) -> Self:
        if self.status is OrderStatus.CANCELLED:
            return self
        return replace(
            self,
            status=OrderStatus.CANCELLING,
            failure_messages=self.failure_messages + (_require_text(reason, "reason"),),
        )

    def cancel(self, reason: str) -> Self:
        reason = _require_text(reason, "reason")
        if self.status is OrderStatus.CANCELLED:
            return self
        return replace(
            self,
            status=OrderStatus.CANCELLED,
            failure_messages=self.failure_messages + (reason,),
        )

    def record_created(self, created_at: datetime | None = None) -> "OrderCreatedEvent":
        return OrderCreatedEvent(order=self, created_at=created_at or datetime.now(UTC))

    def record_paid(self, created_at: datetime | None = None) -> "OrderPaidEvent":
        if self.status is not OrderStatus.PAID:
            raise ValueError("OrderPaidEvent requires a PAID order")
        return OrderPaidEvent(order=self, created_at=created_at or datetime.now(UTC))

    def record_cancelled(self, created_at: datetime | None = None) -> "OrderCancelledEvent":
        if self.status is not OrderStatus.CANCELLED:
            raise ValueError("OrderCancelledEvent requires a CANCELLED order")
        return OrderCancelledEvent(order=self, created_at=created_at or datetime.now(UTC))

    def _ensure_status(self, expected: OrderStatus, action: str) -> None:
        if self.status is not expected:
            raise ValueError(f"cannot {action} order in {self.status} status")


@dataclass(frozen=True)
class OrderCreatedEvent:
    order: Order
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.order, Order):
            raise ValueError("OrderCreatedEvent.order must be an Order")
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "OrderCreatedEvent.created_at"),
        )


@dataclass(frozen=True)
class OrderPaidEvent:
    order: Order
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.order, Order):
            raise ValueError("OrderPaidEvent.order must be an Order")
        if self.order.status is not OrderStatus.PAID:
            raise ValueError("OrderPaidEvent requires a PAID order")
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "OrderPaidEvent.created_at"),
        )


@dataclass(frozen=True)
class OrderCancelledEvent:
    order: Order
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.order, Order):
            raise ValueError("OrderCancelledEvent.order must be an Order")
        if self.order.status is not OrderStatus.CANCELLED:
            raise ValueError("OrderCancelledEvent requires a CANCELLED order")
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "OrderCancelledEvent.created_at"),
        )


OrderEvent: TypeAlias = OrderCreatedEvent | OrderPaidEvent | OrderCancelledEvent


def _multiply_crypto(value: Crypto, quantity: int) -> Crypto:
    return Crypto(
        amount=value.amount * Decimal(quantity),
        symbol=value.symbol,
        chain_id=value.chain_id,
        token_address=value.token_address,
        decimals=value.decimals,
    )


def _coerce_wallet(value: WalletAddress | str) -> WalletAddress:
    return value if isinstance(value, WalletAddress) else WalletAddress(value)


def _coerce_order_status(value: OrderStatus | str) -> OrderStatus:
    if isinstance(value, OrderStatus):
        return value
    try:
        return OrderStatus(str(value))
    except ValueError as exc:
        raise ValueError("Order.status must be an OrderStatus") from exc


def _coerce_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _coerce_tuple(values: tuple[object, ...], item_type: type[object], field_name: str) -> tuple[object, ...]:
    if isinstance(values, list):
        values = tuple(values)
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if not all(isinstance(value, item_type) for value in values):
        raise ValueError(f"{field_name} must contain only {item_type.__name__}")
    return values


def _coerce_uuid(value: UUID | str, field_name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return UUID(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a valid UUID") from exc
    raise ValueError(f"{field_name} must be a non-empty UUID")


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_crypto(value: object) -> Crypto:
    if not isinstance(value, Crypto):
        raise ValueError("asset price must be a Crypto value")
    return value


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value

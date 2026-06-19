"""Domain model for order creation and tracking."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import json
from types import MappingProxyType
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

    @classmethod
    def for_order_line(cls, order_id: OrderId, product_id: ProductId, line_key: str) -> Self:
        if not isinstance(order_id, OrderId):
            raise ValueError("OrderItemId.for_order_line requires an OrderId")
        if not isinstance(product_id, ProductId):
            raise ValueError("OrderItemId.for_order_line requires a ProductId")
        line_key = _require_text(line_key, "line_key")
        return cls(uuid5(NAMESPACE_URL, f"token-payments/order-item/{order_id}/{product_id}/{line_key}"))

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
    public_variant_id: str | None = None
    selected_options: Mapping[str, object] = field(default_factory=dict)

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
        if self.public_variant_id is not None:
            object.__setattr__(self, "public_variant_id", _require_text(self.public_variant_id, "ProductSnapshot.public_variant_id"))
        object.__setattr__(
            self,
            "selected_options",
            MappingProxyType(_canonical_selected_options(self.selected_options)),
        )


@dataclass(frozen=True)
class ProductVariantPrice:
    public_variant_id: str
    option_values: Mapping[str, str]
    price_delta: Crypto
    active: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "public_variant_id", _require_text(self.public_variant_id, "ProductVariantPrice.public_variant_id"))
        if not isinstance(self.option_values, Mapping):
            raise ValueError("ProductVariantPrice.option_values must be a mapping")
        object.__setattr__(
            self,
            "option_values",
            MappingProxyType({
                _require_text(str(key), "ProductVariantPrice.option_values key"): _require_text(str(value), "ProductVariantPrice.option_values value")
                for key, value in self.option_values.items()
            }),
        )
        if not isinstance(self.price_delta, Crypto):
            raise ValueError("ProductVariantPrice.price_delta must be a Crypto value")
        if not isinstance(self.active, bool):
            raise ValueError("ProductVariantPrice.active must be a bool")


@dataclass(frozen=True)
class ProductOptionValuePrice:
    option_key: str
    value_key: str
    display_value: str
    option_type: str
    price_delta: Crypto | None = None
    selection_type: str = "SINGLE"
    active: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_key", _require_text(self.option_key, "ProductOptionValuePrice.option_key"))
        object.__setattr__(self, "value_key", _require_text(self.value_key, "ProductOptionValuePrice.value_key"))
        object.__setattr__(self, "display_value", _require_text(self.display_value, "ProductOptionValuePrice.display_value"))
        object.__setattr__(self, "option_type", _option_type(self.option_type))
        object.__setattr__(self, "selection_type", _selection_type(self.selection_type))
        if self.price_delta is not None and not isinstance(self.price_delta, Crypto):
            raise ValueError("ProductOptionValuePrice.price_delta must be a Crypto value or None")
        if not isinstance(self.active, bool):
            raise ValueError("ProductOptionValuePrice.active must be a bool")


@dataclass(frozen=True)
class Product:
    product_id: ProductId
    name: str
    price: Crypto
    asset_prices: Mapping[str, Crypto] | None = None
    variants: Mapping[str, ProductVariantPrice] | None = None
    option_values: Mapping[str, ProductOptionValuePrice] | None = None

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
        if self.variants is not None:
            if not isinstance(self.variants, Mapping):
                raise ValueError("Product.variants must be a mapping")
            object.__setattr__(
                self,
                "variants",
                {
                    _require_text(str(variant_id), "Product.variants key"): _require_variant_price(variant)
                    for variant_id, variant in self.variants.items()
                },
            )
        if self.option_values is not None:
            if not isinstance(self.option_values, Mapping):
                raise ValueError("Product.option_values must be a mapping")
            object.__setattr__(
                self,
                "option_values",
                {
                    _require_text(str(option_value_key), "Product.option_values key"): _require_option_value_price(value)
                    for option_value_key, value in self.option_values.items()
                },
            )

    def snapshot(self, created_date: datetime | None = None) -> ProductSnapshot:
        return ProductSnapshot(
            product_id=self.product_id,
            created_date=created_date or datetime.now(UTC),
            name=self.name,
            price=self.price,
        )

    def snapshot_for_asset(
        self,
        payment_asset_id: str | None,
        created_date: datetime | None = None,
        *,
        public_variant_id: str | None = None,
        selected_options: Mapping[str, object] | None = None,
    ) -> ProductSnapshot:
        return ProductSnapshot(
            product_id=self.product_id,
            created_date=created_date or datetime.now(UTC),
            name=self.name,
            price=self.price_for_selection(
                payment_asset_id,
                public_variant_id=public_variant_id,
                selected_options=selected_options or {},
            ),
            public_variant_id=public_variant_id,
            selected_options=selected_options or {},
        )

    def price_for_asset(self, payment_asset_id: str | None) -> Crypto:
        if payment_asset_id is None:
            return self.price
        payment_asset_id = _require_text(payment_asset_id, "payment_asset_id")
        prices = self.asset_prices if self.asset_prices is not None else getattr(self, "_asset_prices", None)
        if not isinstance(prices, Mapping) or payment_asset_id not in prices:
            raise ValueError(f"payment asset {payment_asset_id} is not supported by product {self.product_id}")
        return _require_crypto(prices[payment_asset_id])

    def price_for_selection(
        self,
        payment_asset_id: str | None,
        *,
        public_variant_id: str | None = None,
        selected_options: Mapping[str, object] | None = None,
    ) -> Crypto:
        base_price = self.price_for_asset(payment_asset_id)
        selected_options = _canonical_selected_options(selected_options or {})
        unit_price = base_price
        variant = self._variant_for_selection(public_variant_id, selected_options)
        if variant is not None:
            unit_price = _add_crypto(unit_price, variant.price_delta, "variant priceDelta")
        for value in self._selected_add_on_values(selected_options):
            if value.price_delta is not None:
                unit_price = _add_crypto(unit_price, value.price_delta, "add-on priceDelta")
        return unit_price

    def _variant_for_selection(
        self,
        public_variant_id: str | None,
        selected_options: Mapping[str, object],
    ) -> ProductVariantPrice | None:
        variants = self.variants if self.variants is not None else getattr(self, "_variants", None)
        if not isinstance(variants, Mapping) or not variants:
            if public_variant_id is not None:
                raise ValueError(f"product {self.product_id} does not define variants")
            return None
        if public_variant_id is None:
            raise ValueError(f"publicVariantId is required for product {self.product_id}")
        public_variant_id = _require_text(public_variant_id, "publicVariantId")
        variant = variants.get(public_variant_id)
        if not isinstance(variant, ProductVariantPrice):
            raise ValueError(f"publicVariantId {public_variant_id} is not valid for product {self.product_id}")
        if not variant.active:
            raise ValueError(f"publicVariantId {public_variant_id} is not active")
        for option_key, expected_value in variant.option_values.items():
            selected_value = selected_options.get(option_key)
            if selected_value is not None and str(selected_value) != expected_value:
                raise ValueError(f"selected option {option_key} does not match variant {public_variant_id}")
        return variant

    def _selected_add_on_values(self, selected_options: Mapping[str, object]) -> tuple[ProductOptionValuePrice, ...]:
        values = self.option_values if self.option_values is not None else getattr(self, "_option_values", None)
        if not isinstance(values, Mapping):
            return ()
        selected: list[ProductOptionValuePrice] = []
        for option_key, raw_value in selected_options.items():
            option_values = tuple(raw_value) if isinstance(raw_value, list | tuple) else (raw_value,)
            for value_key in option_values:
                value = values.get(f"{option_key}:{value_key}")
                if value is None:
                    continue
                if not isinstance(value, ProductOptionValuePrice):
                    raise ValueError("Product.option_values must contain ProductOptionValuePrice values")
                if not value.active:
                    raise ValueError(f"selected option {option_key}:{value_key} is not active")
                if value.selection_type == "SINGLE" and isinstance(raw_value, list | tuple) and len(raw_value) > 1:
                    raise ValueError(f"selected option {option_key} does not allow multiple values")
                if value.option_type == "ADD_ON":
                    selected.append(value)
        return tuple(selected)


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
    line_key: str = ""

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
        object.__setattr__(self, "line_key", _require_text(self.line_key or _order_line_key(
            self.product_snapshot.product_id,
            self.product_snapshot.public_variant_id,
            self.product_snapshot.selected_options,
        ), "OrderItem.line_key"))

    @classmethod
    def from_product(
        cls,
        order_id: OrderId,
        product: Product,
        quantity: int,
        snapshotted_at: datetime | None = None,
        order_item_id: OrderItemId | None = None,
        payment_asset_id: str | None = None,
        public_variant_id: str | None = None,
        selected_options: Mapping[str, object] | None = None,
    ) -> Self:
        if not isinstance(order_id, OrderId):
            raise ValueError("OrderItem.from_product requires an OrderId")
        if not isinstance(product, Product):
            raise ValueError("OrderItem.from_product requires a Product")
        quantity = _coerce_positive_int(quantity, "quantity")
        selected_options = selected_options or {}
        snapshot = product.snapshot_for_asset(
            payment_asset_id,
            snapshotted_at,
            public_variant_id=public_variant_id,
            selected_options=selected_options,
        )
        line_key = _order_line_key(product.product_id, public_variant_id, selected_options)
        return cls(
            order_item_id=order_item_id or OrderItemId.for_order_line(order_id, product.product_id, line_key),
            order_id=order_id,
            product_snapshot=snapshot,
            quantity=quantity,
            sub_total=_multiply_crypto(snapshot.price, quantity),
            line_key=line_key,
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
        product_quantities: dict[ProductId, int] | None = None,
        item_requests: tuple[object, ...] | None = None,
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
        if not product_quantities and not item_requests:
            raise ValueError("Order.initialize_order requires at least one product")

        snapshotted_at = created_at or datetime.now(UTC)
        snapshotted_at = _require_aware_datetime(snapshotted_at, "created_at")
        items: list[OrderItem] = []
        if item_requests:
            for item_request in item_requests:
                product_id = getattr(item_request, "product_id")
                quantity = getattr(item_request, "quantity")
                public_variant_id = getattr(item_request, "public_variant_id", None)
                selected_options = getattr(item_request, "selected_options", {})
                product = store.require_product(product_id)
                price = product.price_for_selection(
                    payment_asset_id,
                    public_variant_id=public_variant_id,
                    selected_options=selected_options,
                )
                if not store.supports_chain(price.chain_id):
                    raise ValueError(f"store {store.store_id} does not support chain {price.chain_id}")
                items.append(
                    OrderItem.from_product(
                        order_id,
                        product,
                        quantity,
                        snapshotted_at,
                        payment_asset_id=payment_asset_id,
                        public_variant_id=public_variant_id,
                        selected_options=selected_options,
                    )
                )
        else:
            for product_id, quantity in (product_quantities or {}).items():
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


def _add_crypto(left: Crypto, right: Crypto, label: str) -> Crypto:
    if (
        left.symbol != right.symbol
        or left.chain_id != right.chain_id
        or left.token_address != right.token_address
        or left.decimals != right.decimals
    ):
        raise ValueError(f"{label} asset must match product price asset")
    return Crypto(
        amount=left.amount + right.amount,
        symbol=left.symbol,
        chain_id=left.chain_id,
        token_address=left.token_address,
        decimals=left.decimals,
    )


def _order_line_key(product_id: ProductId, public_variant_id: str | None, selected_options: Mapping[str, object]) -> str:
    payload = {
        "productId": str(product_id),
        "publicVariantId": public_variant_id,
        "selectedOptions": _canonical_selected_options(selected_options),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _canonical_selected_options(values: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(values, Mapping):
        raise ValueError("selected_options must be a mapping")
    normalized: dict[str, object] = {}
    for key, value in values.items():
        option_key = _require_text(str(key), "selected_options key")
        if isinstance(value, list | tuple):
            normalized[option_key] = [_require_text(str(item), f"selected_options.{option_key}") for item in value if str(item).strip()]
        elif value is not None and str(value).strip():
            normalized[option_key] = _require_text(str(value), f"selected_options.{option_key}")
    return dict(sorted(normalized.items()))


def _require_variant_price(value: object) -> ProductVariantPrice:
    if not isinstance(value, ProductVariantPrice):
        raise ValueError("Product.variants must contain ProductVariantPrice values")
    return value


def _require_option_value_price(value: object) -> ProductOptionValuePrice:
    if not isinstance(value, ProductOptionValuePrice):
        raise ValueError("Product.option_values must contain ProductOptionValuePrice values")
    return value


def _option_type(value: str) -> str:
    normalized = _require_text(str(value), "option_type").upper()
    if normalized not in {"VARIANT", "ADD_ON"}:
        raise ValueError("option_type must be VARIANT or ADD_ON")
    return normalized


def _selection_type(value: str) -> str:
    normalized = _require_text(str(value), "selection_type").upper()
    if normalized not in {"SINGLE", "MULTI"}:
        raise ValueError("selection_type must be SINGLE or MULTI")
    return normalized


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

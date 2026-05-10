"""PostgreSQL repositories for the order context."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from token_payments.contexts.order.domain import (
    Address,
    Customer,
    Order,
    OrderItem,
    OrderItemId,
    OrderStatus,
    Product,
    ProductSnapshot,
    Store,
    TrackingId,
)
from token_payments.shared.adapter.postgres import PostgresConnection
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


SELECT_CUSTOMER_BY_USER_ID_SQL = """
SELECT
    customer_id,
    user_id,
    wallet_address
FROM order_customers
WHERE user_id = %(user_id)s
"""

SELECT_STORE_SQL = """
SELECT
    store_id,
    owner_user_id,
    active,
    store_address_id,
    store_address_street,
    store_wallet_address,
    supported_chain_ids
FROM order_stores
WHERE store_id = %(store_id)s
"""

SELECT_STORE_PRODUCTS_SQL = """
SELECT
    store_id,
    product_id,
    name,
    price_numeric,
    price_symbol,
    price_chain_id,
    price_token_address,
    price_decimals
FROM order_store_products
WHERE store_id = %(store_id)s
ORDER BY product_id
"""

SELECT_ORDER_SQL = """
SELECT
    order_id,
    customer_id,
    store_id,
    delivery_address_id,
    delivery_address_street,
    tracking_id,
    status,
    payment_id,
    failure_messages
FROM orders
WHERE order_id = %(order_id)s
"""

SELECT_ORDER_ITEMS_SQL = """
SELECT
    order_item_id,
    order_id,
    product_id,
    product_snapshot_created_at,
    product_snapshot_name,
    unit_price_numeric,
    unit_price_symbol,
    unit_price_chain_id,
    unit_price_token_address,
    unit_price_decimals,
    quantity,
    subtotal_numeric,
    subtotal_symbol,
    subtotal_chain_id,
    subtotal_token_address,
    subtotal_decimals
FROM order_items
WHERE order_id = %(order_id)s
ORDER BY order_item_id
"""

UPSERT_ORDER_SQL = """
INSERT INTO orders (
    order_id,
    customer_id,
    store_id,
    delivery_address_id,
    delivery_address_street,
    tracking_id,
    status,
    payment_id,
    failure_messages,
    total_amount_numeric,
    total_amount_symbol,
    total_amount_chain_id,
    total_amount_token_address,
    total_amount_decimals
) VALUES (
    %(order_id)s,
    %(customer_id)s,
    %(store_id)s,
    %(delivery_address_id)s,
    %(delivery_address_street)s,
    %(tracking_id)s,
    %(status)s,
    %(payment_id)s,
    %(failure_messages)s,
    %(total_amount_numeric)s,
    %(total_amount_symbol)s,
    %(total_amount_chain_id)s,
    %(total_amount_token_address)s,
    %(total_amount_decimals)s
)
ON CONFLICT (order_id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    store_id = EXCLUDED.store_id,
    delivery_address_id = EXCLUDED.delivery_address_id,
    delivery_address_street = EXCLUDED.delivery_address_street,
    tracking_id = EXCLUDED.tracking_id,
    status = EXCLUDED.status,
    payment_id = EXCLUDED.payment_id,
    failure_messages = EXCLUDED.failure_messages,
    total_amount_numeric = EXCLUDED.total_amount_numeric,
    total_amount_symbol = EXCLUDED.total_amount_symbol,
    total_amount_chain_id = EXCLUDED.total_amount_chain_id,
    total_amount_token_address = EXCLUDED.total_amount_token_address,
    total_amount_decimals = EXCLUDED.total_amount_decimals,
    updated_at = now()
"""

UPSERT_ORDER_ITEM_SQL = """
INSERT INTO order_items (
    order_item_id,
    order_id,
    product_id,
    product_snapshot_created_at,
    product_snapshot_name,
    unit_price_numeric,
    unit_price_symbol,
    unit_price_chain_id,
    unit_price_token_address,
    unit_price_decimals,
    quantity,
    subtotal_numeric,
    subtotal_symbol,
    subtotal_chain_id,
    subtotal_token_address,
    subtotal_decimals
) VALUES (
    %(order_item_id)s,
    %(order_id)s,
    %(product_id)s,
    %(product_snapshot_created_at)s,
    %(product_snapshot_name)s,
    %(unit_price_numeric)s,
    %(unit_price_symbol)s,
    %(unit_price_chain_id)s,
    %(unit_price_token_address)s,
    %(unit_price_decimals)s,
    %(quantity)s,
    %(subtotal_numeric)s,
    %(subtotal_symbol)s,
    %(subtotal_chain_id)s,
    %(subtotal_token_address)s,
    %(subtotal_decimals)s
)
ON CONFLICT (order_item_id) DO UPDATE SET
    order_id = EXCLUDED.order_id,
    product_id = EXCLUDED.product_id,
    product_snapshot_created_at = EXCLUDED.product_snapshot_created_at,
    product_snapshot_name = EXCLUDED.product_snapshot_name,
    unit_price_numeric = EXCLUDED.unit_price_numeric,
    unit_price_symbol = EXCLUDED.unit_price_symbol,
    unit_price_chain_id = EXCLUDED.unit_price_chain_id,
    unit_price_token_address = EXCLUDED.unit_price_token_address,
    unit_price_decimals = EXCLUDED.unit_price_decimals,
    quantity = EXCLUDED.quantity,
    subtotal_numeric = EXCLUDED.subtotal_numeric,
    subtotal_symbol = EXCLUDED.subtotal_symbol,
    subtotal_chain_id = EXCLUDED.subtotal_chain_id,
    subtotal_token_address = EXCLUDED.subtotal_token_address,
    subtotal_decimals = EXCLUDED.subtotal_decimals,
    updated_at = now()
"""


class PostgresCustomerRepository:
    """Read order customers inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get_by_user_id(self, user_id: UserId) -> Customer | None:
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresCustomerRepository.get_by_user_id requires a UserId")
        row = _fetch_one(self._connection.execute(SELECT_CUSTOMER_BY_USER_ID_SQL, {"user_id": str(user_id)}))
        return _row_to_customer(row) if row is not None else None


class PostgresStoreRepository:
    """Read order stores and product snapshots inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get(self, store_id: StoreId) -> Store | None:
        if not isinstance(store_id, StoreId):
            raise ValueError("PostgresStoreRepository.get requires a StoreId")

        store_row = _fetch_one(self._connection.execute(SELECT_STORE_SQL, {"store_id": str(store_id)}))
        if store_row is None:
            return None

        product_rows = _fetch_all(self._connection.execute(SELECT_STORE_PRODUCTS_SQL, {"store_id": str(store_id)}))
        return Store(
            store_id=StoreId(_row_value(store_row, "store_id")),
            owner_user_id=UserId(_row_value(store_row, "owner_user_id")),
            products=tuple(_row_to_product(row) for row in product_rows),
            active=bool(_row_value(store_row, "active")),
            store_address=_optional_address(
                _row_value(store_row, "store_address_id"),
                _row_value(store_row, "store_address_street"),
            ),
            store_wallet=_optional_wallet(_row_value(store_row, "store_wallet_address")),
            supported_chain_ids=_supported_chain_ids(_row_value(store_row, "supported_chain_ids")),
        )


class PostgresOrderRepository:
    """Persist Order aggregates and item snapshots inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get(self, order_id: OrderId) -> Order | None:
        if not isinstance(order_id, OrderId):
            raise ValueError("PostgresOrderRepository.get requires an OrderId")
        row = _fetch_one(self._connection.execute(SELECT_ORDER_SQL, {"order_id": str(order_id)}))
        if row is None:
            return None
        item_rows = _fetch_all(self._connection.execute(SELECT_ORDER_ITEMS_SQL, {"order_id": str(order_id)}))
        return Order(
            order_id=OrderId(_row_value(row, "order_id")),
            customer_id=CustomerId(_row_value(row, "customer_id")),
            store_id=StoreId(_row_value(row, "store_id")),
            delivery_address=Address(
                id=str(_row_value(row, "delivery_address_id")),
                street=str(_row_value(row, "delivery_address_street")),
            ),
            items=tuple(_row_to_order_item(item_row) for item_row in item_rows),
            tracking_id=TrackingId(_row_value(row, "tracking_id")),
            status=OrderStatus(_row_value(row, "status")),
            payment_id=_optional_payment_id(_row_value(row, "payment_id")),
            failure_messages=_failure_messages(_row_value(row, "failure_messages")),
        )

    def save(self, order: Order) -> None:
        if not isinstance(order, Order):
            raise ValueError("PostgresOrderRepository.save requires an Order")

        self._connection.execute(
            UPSERT_ORDER_SQL,
            {
                "order_id": str(order.order_id),
                "customer_id": str(order.customer_id),
                "store_id": str(order.store_id),
                "delivery_address_id": order.delivery_address.id,
                "delivery_address_street": order.delivery_address.street,
                "tracking_id": str(order.tracking_id),
                "status": order.status.value,
                "payment_id": str(order.payment_id) if order.payment_id is not None else None,
                "failure_messages": list(order.failure_messages),
                **_crypto_params("total_amount", _total_amount(order.items)),
            },
        )

        for item in order.items:
            self._connection.execute(
                UPSERT_ORDER_ITEM_SQL,
                {
                    "order_item_id": str(item.order_item_id),
                    "order_id": str(item.order_id),
                    "product_id": str(item.product_snapshot.product_id),
                    "product_snapshot_created_at": item.product_snapshot.created_date,
                    "product_snapshot_name": item.product_snapshot.name,
                    **_crypto_params("unit_price", item.product_snapshot.price),
                    "quantity": item.quantity,
                    **_crypto_params("subtotal", item.sub_total),
                },
            )


def _row_to_customer(row: Mapping[str, Any] | object) -> Customer:
    return Customer(
        customer_id=CustomerId(_row_value(row, "customer_id")),
        user_id=UserId(_row_value(row, "user_id")),
        customer_wallet=WalletAddress(_row_value(row, "wallet_address")),
    )


def _row_to_product(row: Mapping[str, Any] | object) -> Product:
    return Product(
        product_id=ProductId(_row_value(row, "product_id")),
        name=str(_row_value(row, "name")),
        price=_crypto_from_row(row, "price"),
    )


def _row_to_order_item(row: Mapping[str, Any] | object) -> OrderItem:
    return OrderItem(
        order_item_id=OrderItemId(_row_value(row, "order_item_id")),
        order_id=OrderId(_row_value(row, "order_id")),
        product_snapshot=ProductSnapshot(
            product_id=ProductId(_row_value(row, "product_id")),
            created_date=_row_value(row, "product_snapshot_created_at"),
            name=str(_row_value(row, "product_snapshot_name")),
            price=_crypto_from_row(row, "unit_price"),
        ),
        quantity=int(_row_value(row, "quantity")),
        sub_total=_crypto_from_row(row, "subtotal"),
    )


def _optional_address(address_id: Any, street: Any) -> Address | None:
    if address_id is None and street is None:
        return None
    if address_id is None or street is None:
        raise ValueError("order store address requires both id and street")
    return Address(id=str(address_id), street=str(street))


def _optional_wallet(value: Any) -> WalletAddress | None:
    if value is None:
        return None
    return WalletAddress(value)


def _optional_payment_id(value: Any) -> PaymentId | None:
    if value is None:
        return None
    return PaymentId(value)


def _supported_chain_ids(value: Any) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ValueError("order store supported_chain_ids must be a list")
    return tuple(int(item) for item in value)


def _failure_messages(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ValueError("orders.failure_messages must be a list")
    return tuple(str(item) for item in value)


def _crypto_params(prefix: str, value: Crypto) -> dict[str, Any]:
    return {
        f"{prefix}_numeric": value.amount,
        f"{prefix}_symbol": value.symbol,
        f"{prefix}_chain_id": value.chain_id,
        f"{prefix}_token_address": str(value.token_address) if value.token_address is not None else None,
        f"{prefix}_decimals": value.decimals,
    }


def _crypto_from_row(row: Mapping[str, Any] | object, prefix: str) -> Crypto:
    return Crypto(
        amount=_row_value(row, f"{prefix}_numeric"),
        symbol=str(_row_value(row, f"{prefix}_symbol")),
        chain_id=int(_row_value(row, f"{prefix}_chain_id")),
        token_address=_row_value(row, f"{prefix}_token_address"),
        decimals=int(_row_value(row, f"{prefix}_decimals")),
    )


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


def _fetch_one(result: Any) -> Any:
    if result is None:
        return None
    fetchone = getattr(result, "fetchone", None)
    if callable(fetchone):
        return fetchone()
    iterator = iter(result)
    return next(iterator, None)


def _fetch_all(result: Any) -> list[Any]:
    if result is None:
        return []
    fetchall = getattr(result, "fetchall", None)
    if callable(fetchall):
        return list(fetchall())
    return list(result)


def _row_value(row: Mapping[str, Any] | object, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return getattr(row, key)

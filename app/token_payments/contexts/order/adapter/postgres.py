"""PostgreSQL repositories for the order context."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json
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
from token_payments.contexts.order.application.queries import CheckoutTrackingSnapshot, OutboxStatusSnapshot
from token_payments.contexts.payment.domain import (
    AuthorizationStatus,
    GasEstimate,
    Payment,
    PaymentAuthorization,
    PaymentStatus,
    TransactionReceipt,
    TransactionSignatureRequest,
)
from token_payments.shared.adapter.postgres import PostgresConnection
from token_payments.shared.domain import (
    ChainNetwork,
    Crypto,
    CustomerId,
    OrderId,
    OutboxPublishStatus,
    PaymentId,
    ProductId,
    StoreId,
    TransactionHash,
    UserId,
    WalletAddress,
)


SELECT_CUSTOMER_BY_USER_ID_SQL = """
SELECT
    c.customer_id,
    c.user_id,
    w.wallet_address
FROM order_customers c
LEFT JOIN auth_user_wallets w ON c.user_id = w.user_id AND w."primary" = true
WHERE c.user_id = %(user_id)s
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

SELECT_TRACKING_ORDER_BY_TRACKING_ID_SQL = """
SELECT
    order_id,
    tracking_id,
    status,
    failure_messages,
    updated_at AS order_updated_at
FROM orders
WHERE tracking_id = %(tracking_id)s
"""

SELECT_TRACKING_ORDER_BY_ORDER_ID_SQL = """
SELECT
    order_id,
    tracking_id,
    status,
    failure_messages,
    updated_at AS order_updated_at
FROM orders
WHERE order_id = %(order_id)s
"""

SELECT_TRACKING_PAYMENT_BY_ORDER_ID_SQL = """
SELECT
    payment_id,
    order_id,
    customer_id,
    amount_numeric,
    amount_symbol,
    amount_chain_id,
    amount_token_address,
    amount_decimals,
    status,
    wallet_from,
    wallet_to,
    chain_id,
    chain_name,
    tx_hash,
    gas_estimated_fee,
    gas_fee_symbol,
    gas_fee_chain_id,
    gas_fee_token_address,
    gas_fee_decimals,
    gas_limit,
    gas_buffer_rate,
    gas_max_fee,
    receipt_block_number,
    receipt_gas_used,
    failure_reason,
    refund_tx_hash,
    refund_block_number,
    refund_gas_used,
    expires_at,
    updated_at AS payment_updated_at
FROM payments
WHERE order_id = %(order_id)s
"""

SELECT_TRACKING_AUTHORIZATION_BY_PAYMENT_ID_SQL = """
SELECT
    payment_id,
    user_id,
    wallet_address,
    chain_id,
    chain_name,
    request_id,
    amount_numeric,
    amount_symbol,
    amount_chain_id,
    amount_token_address,
    amount_decimals,
    to_wallet_address,
    status,
    tx_hash,
    expires_at,
    authorized_at,
    updated_at AS authorization_updated_at
FROM payment_authorizations
WHERE payment_id = %(payment_id)s
"""

SELECT_TRACKING_OUTBOX_STATUS_SQL = """
SELECT
    message_identity,
    name,
    status,
    COALESCE(published_at, created_at) AS outbox_updated_at
FROM outbox_messages
WHERE message_key = %(order_id)s
ORDER BY created_at
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
    %(failure_messages)s::jsonb,
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
                "failure_messages": json.dumps(list(order.failure_messages)),
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


class PostgresCheckoutTrackingQuery:
    """Read checkout tracking state without mutating command-side aggregates."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get_by_tracking_id(self, tracking_id: TrackingId) -> CheckoutTrackingSnapshot | None:
        if not isinstance(tracking_id, TrackingId):
            raise ValueError("PostgresCheckoutTrackingQuery.get_by_tracking_id requires a TrackingId")
        order_row = _fetch_one(
            self._connection.execute(SELECT_TRACKING_ORDER_BY_TRACKING_ID_SQL, {"tracking_id": str(tracking_id)})
        )
        return self._snapshot_from_order_row(order_row)

    def get_by_order_id(self, order_id: OrderId) -> CheckoutTrackingSnapshot | None:
        if not isinstance(order_id, OrderId):
            raise ValueError("PostgresCheckoutTrackingQuery.get_by_order_id requires an OrderId")
        order_row = _fetch_one(
            self._connection.execute(SELECT_TRACKING_ORDER_BY_ORDER_ID_SQL, {"order_id": str(order_id)})
        )
        return self._snapshot_from_order_row(order_row)

    def _snapshot_from_order_row(self, order_row: Mapping[str, Any] | object | None) -> CheckoutTrackingSnapshot | None:
        if order_row is None:
            return None

        order_id = OrderId(_row_value(order_row, "order_id"))
        payment_row = _fetch_one(
            self._connection.execute(SELECT_TRACKING_PAYMENT_BY_ORDER_ID_SQL, {"order_id": str(order_id)})
        )
        payment = _tracking_payment_from_row(payment_row) if payment_row is not None else None

        authorization_row = None
        authorization = None
        if payment is not None:
            authorization_row = _fetch_one(
                self._connection.execute(
                    SELECT_TRACKING_AUTHORIZATION_BY_PAYMENT_ID_SQL,
                    {"payment_id": str(payment.payment_id)},
                )
            )
            authorization = _tracking_authorization_from_row(authorization_row) if authorization_row is not None else None

        outbox_rows = _fetch_all(
            self._connection.execute(SELECT_TRACKING_OUTBOX_STATUS_SQL, {"order_id": str(order_id)})
        )
        outbox_statuses = tuple(_tracking_outbox_status_from_row(row) for row in outbox_rows)
        return CheckoutTrackingSnapshot(
            order_id=order_id,
            tracking_id=TrackingId(_row_value(order_row, "tracking_id")),
            order_status=OrderStatus(_row_value(order_row, "status")),
            failure_messages=_failure_messages(_row_value(order_row, "failure_messages")),
            payment=payment,
            authorization=authorization,
            outbox_statuses=outbox_statuses,
            updated_at=_latest_updated_at(order_row, payment_row, authorization_row, outbox_statuses),
        )


def _row_to_customer(row: Mapping[str, Any] | object) -> Customer:
    customer = Customer(
        customer_id=CustomerId(_row_value(row, "customer_id")),
        user_id=UserId(_row_value(row, "user_id")),
    )
    wallet_val = _row_value(row, "wallet_address")
    if wallet_val is not None:
        object.__setattr__(customer, "_customer_wallet", WalletAddress(str(wallet_val)))
    return customer


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
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("orders.failure_messages is not a valid JSON string") from exc
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


def _tracking_payment_from_row(row: Mapping[str, Any] | object) -> Payment:
    return Payment(
        payment_id=PaymentId(_row_value(row, "payment_id")),
        order_id=OrderId(_row_value(row, "order_id")),
        customer_id=CustomerId(_row_value(row, "customer_id")),
        amount=_crypto_from_row(row, "amount"),
        wallet_from=WalletAddress(_row_value(row, "wallet_from")),
        wallet_to=WalletAddress(_row_value(row, "wallet_to")),
        chain_network=ChainNetwork(chain_id=int(_row_value(row, "chain_id")), name=str(_row_value(row, "chain_name"))),
        gas_estimate=_tracking_gas_estimate_from_row(row),
        expires_at=_row_value(row, "expires_at"),
        status=PaymentStatus(_row_value(row, "status")),
        tx_hash=_optional_tx_hash(_row_value(row, "tx_hash")),
        receipt=_tracking_receipt_from_row(row, "tx_hash", "receipt_block_number", "receipt_gas_used"),
        failure_reason=_row_value(row, "failure_reason"),
        refund_receipt=_tracking_receipt_from_row(row, "refund_tx_hash", "refund_block_number", "refund_gas_used"),
    )


def _tracking_authorization_from_row(row: Mapping[str, Any] | object) -> PaymentAuthorization:
    signature_request = TransactionSignatureRequest(
        request_id=str(_row_value(row, "request_id")),
        amount=_crypto_from_row(row, "amount"),
        to=WalletAddress(_row_value(row, "to_wallet_address")),
        expires_at=_row_value(row, "expires_at"),
    )
    return PaymentAuthorization(
        payment_id=PaymentId(_row_value(row, "payment_id")),
        user_id=UserId(_row_value(row, "user_id")),
        wallet=WalletAddress(_row_value(row, "wallet_address")),
        chain_network=ChainNetwork(chain_id=int(_row_value(row, "chain_id")), name=str(_row_value(row, "chain_name"))),
        signature_request=signature_request,
        status=AuthorizationStatus(_row_value(row, "status")),
        tx_hash=_optional_tx_hash(_row_value(row, "tx_hash")),
        authorized_at=_row_value(row, "authorized_at"),
    )


def _tracking_gas_estimate_from_row(row: Mapping[str, Any] | object) -> GasEstimate | None:
    if _row_value(row, "gas_estimated_fee") is None:
        return None
    estimated_fee = Crypto(
        amount=_row_value(row, "gas_estimated_fee"),
        symbol=str(_row_value(row, "gas_fee_symbol")),
        chain_id=int(_row_value(row, "gas_fee_chain_id")),
        token_address=_row_value(row, "gas_fee_token_address"),
        decimals=int(_row_value(row, "gas_fee_decimals")),
    )
    max_fee_amount = _row_value(row, "gas_max_fee")
    max_fee = None
    if max_fee_amount is not None:
        max_fee = Crypto(
            amount=max_fee_amount,
            symbol=estimated_fee.symbol,
            chain_id=estimated_fee.chain_id,
            token_address=estimated_fee.token_address,
            decimals=estimated_fee.decimals,
        )
    return GasEstimate(
        estimated_fee=estimated_fee,
        gas_limit=int(_row_value(row, "gas_limit")),
        buffer_rate=Decimal(str(_row_value(row, "gas_buffer_rate"))),
        max_fee=max_fee,
    )


def _tracking_receipt_from_row(
    row: Mapping[str, Any] | object,
    hash_key: str,
    block_number_key: str,
    gas_used_key: str,
) -> TransactionReceipt | None:
    tx_hash = _optional_tx_hash(_row_value(row, hash_key))
    block_number = _row_value(row, block_number_key)
    gas_used = _row_value(row, gas_used_key)
    if tx_hash is None and block_number is None and gas_used is None:
        return None
    if tx_hash is None or block_number is None or gas_used is None:
        raise ValueError("tracking payment receipt row must include hash, block number, and gas used")
    return TransactionReceipt(hash=tx_hash, block_number=int(block_number), gas_used=int(gas_used))


def _tracking_outbox_status_from_row(row: Mapping[str, Any] | object) -> OutboxStatusSnapshot:
    return OutboxStatusSnapshot(
        message_id=str(_row_value(row, "message_identity")),
        name=str(_row_value(row, "name")),
        status=OutboxPublishStatus(_row_value(row, "status")),
        updated_at=_row_value(row, "outbox_updated_at"),
    )


def _latest_updated_at(
    order_row: Mapping[str, Any] | object,
    payment_row: Mapping[str, Any] | object | None,
    authorization_row: Mapping[str, Any] | object | None,
    outbox_statuses: tuple[OutboxStatusSnapshot, ...],
) -> datetime:
    values = [_row_value(order_row, "order_updated_at")]
    if payment_row is not None:
        values.append(_row_value(payment_row, "payment_updated_at"))
    if authorization_row is not None:
        values.append(_row_value(authorization_row, "authorization_updated_at"))
    values.extend(status.updated_at for status in outbox_statuses)
    return max(values)


def _optional_tx_hash(value: Any) -> TransactionHash | None:
    if value is None:
        return None
    return TransactionHash(value)


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

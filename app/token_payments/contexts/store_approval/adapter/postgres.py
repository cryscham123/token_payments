"""PostgreSQL aggregate repositories for the store approval context."""

from __future__ import annotations

from typing import Any, Mapping

from token_payments.contexts.store_approval.domain import ApprovalStatus, OrderDetail, Product, Store
from token_payments.shared.adapter.postgres import PostgresConnection
from token_payments.shared.domain import Crypto, OrderId, ProductId, StoreId, UserId, WalletAddress


SELECT_STORE_SQL = """
SELECT
    store_id,
    owner_user_id,
    active
FROM store_approval_stores
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
    price_decimals,
    available
FROM store_approval_products
WHERE store_id = %(store_id)s
ORDER BY product_id
"""

SELECT_ORDER_DETAILS_FOR_STORE_SQL = """
SELECT
    order_id,
    store_id,
    order_status,
    total_amount_numeric,
    total_amount_symbol,
    total_amount_chain_id,
    total_amount_token_address,
    total_amount_decimals,
    product_snapshots,
    approval_status,
    rejection_reasons
FROM store_approval_order_details
WHERE store_id = %(store_id)s
ORDER BY order_id
"""

SELECT_ORDER_DETAIL_SQL = """
SELECT
    order_id,
    store_id,
    order_status,
    total_amount_numeric,
    total_amount_symbol,
    total_amount_chain_id,
    total_amount_token_address,
    total_amount_decimals,
    product_snapshots,
    approval_status,
    rejection_reasons
FROM store_approval_order_details
WHERE order_id = %(order_id)s
"""

UPSERT_ORDER_DETAIL_SQL = """
INSERT INTO store_approval_order_details (
    order_id,
    store_id,
    order_status,
    total_amount_numeric,
    total_amount_symbol,
    total_amount_chain_id,
    total_amount_token_address,
    total_amount_decimals,
    product_snapshots,
    approval_status,
    rejection_reasons
) VALUES (
    %(order_id)s,
    %(store_id)s,
    %(order_status)s,
    %(total_amount_numeric)s,
    %(total_amount_symbol)s,
    %(total_amount_chain_id)s,
    %(total_amount_token_address)s,
    %(total_amount_decimals)s,
    %(product_snapshots)s,
    %(approval_status)s,
    %(rejection_reasons)s
)
ON CONFLICT (order_id) DO UPDATE SET
    store_id = EXCLUDED.store_id,
    order_status = EXCLUDED.order_status,
    total_amount_numeric = EXCLUDED.total_amount_numeric,
    total_amount_symbol = EXCLUDED.total_amount_symbol,
    total_amount_chain_id = EXCLUDED.total_amount_chain_id,
    total_amount_token_address = EXCLUDED.total_amount_token_address,
    total_amount_decimals = EXCLUDED.total_amount_decimals,
    product_snapshots = EXCLUDED.product_snapshots,
    approval_status = EXCLUDED.approval_status,
    rejection_reasons = EXCLUDED.rejection_reasons,
    updated_at = now()
"""


class PostgresStoreRepository:
    """Read Store approval aggregates from an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get(self, store_id: StoreId) -> Store | None:
        if not isinstance(store_id, StoreId):
            raise ValueError("PostgresStoreRepository.get requires a StoreId")

        store_row = _fetch_one(self._connection.execute(SELECT_STORE_SQL, {"store_id": str(store_id)}))
        if store_row is None:
            return None

        product_rows = _fetch_all(
            self._connection.execute(SELECT_STORE_PRODUCTS_SQL, {"store_id": str(store_id)})
        )
        order_detail_rows = _fetch_all(
            self._connection.execute(SELECT_ORDER_DETAILS_FOR_STORE_SQL, {"store_id": str(store_id)})
        )
        return Store(
            store_id=StoreId(_row_value(store_row, "store_id")),
            owner_user_id=UserId(_row_value(store_row, "owner_user_id")),
            products=tuple(_product_from_row(row) for row in product_rows),
            active=bool(_row_value(store_row, "active")),
            order_details=tuple(_order_detail_from_row(row) for row in order_detail_rows),
        )


class PostgresOrderDetailRepository:
    """Persist OrderDetail approval aggregates inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get(self, order_id: OrderId) -> OrderDetail | None:
        if not isinstance(order_id, OrderId):
            raise ValueError("PostgresOrderDetailRepository.get requires an OrderId")

        row = _fetch_one(self._connection.execute(SELECT_ORDER_DETAIL_SQL, {"order_id": str(order_id)}))
        if row is None:
            return None
        return _order_detail_from_row(row)

    def save(self, order_detail: OrderDetail) -> None:
        if not isinstance(order_detail, OrderDetail):
            raise ValueError("PostgresOrderDetailRepository.save requires an OrderDetail")

        params = {
            "order_id": str(order_detail.order_id),
            "store_id": str(order_detail.store_id),
            "order_status": order_detail.order_status,
            **_crypto_params("total_amount", order_detail.total_amount),
            "product_snapshots": [_product_payload(product) for product in order_detail.products],
            "approval_status": order_detail.approval_status.value,
            "rejection_reasons": list(order_detail.rejection_reasons),
        }
        self._connection.execute(UPSERT_ORDER_DETAIL_SQL, params)


def _order_detail_from_row(row: Mapping[str, Any] | object) -> OrderDetail:
    snapshots = _row_value(row, "product_snapshots")
    if not isinstance(snapshots, list):
        raise ValueError("store approval order detail product_snapshots must be a list")
    rejection_reasons = _row_value(row, "rejection_reasons")
    if not isinstance(rejection_reasons, list):
        raise ValueError("store approval order detail rejection_reasons must be a list")
    return OrderDetail(
        order_id=OrderId(_row_value(row, "order_id")),
        store_id=StoreId(_row_value(row, "store_id")),
        order_status=str(_row_value(row, "order_status")),
        total_amount=_crypto_from_row(row, "total_amount"),
        products=tuple(_product_from_payload(snapshot) for snapshot in snapshots),
        approval_status=ApprovalStatus(_row_value(row, "approval_status")),
        rejection_reasons=tuple(str(reason) for reason in rejection_reasons),
    )


def _product_from_row(row: Mapping[str, Any] | object) -> Product:
    return Product(
        product_id=ProductId(_row_value(row, "product_id")),
        name=str(_row_value(row, "name")),
        price=_crypto_from_row(row, "price"),
        available=bool(_row_value(row, "available")),
    )


def _product_payload(product: Product) -> dict[str, Any]:
    return {
        "productId": str(product.product_id),
        "name": product.name,
        "price": _crypto_payload(product.price),
        "available": product.available,
    }


def _product_from_payload(payload: Any) -> Product:
    if not isinstance(payload, Mapping):
        raise ValueError("product snapshot must be a mapping")
    price = payload.get("price")
    if not isinstance(price, Mapping):
        raise ValueError("product snapshot price must be a mapping")
    return Product(
        product_id=ProductId(payload["productId"]),
        name=str(payload["name"]),
        price=_crypto_from_payload(price),
        available=bool(payload.get("available", True)),
    )


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


def _crypto_payload(value: Crypto) -> dict[str, Any]:
    return {
        "amount": format(value.amount, "f"),
        "symbol": value.symbol,
        "chainId": value.chain_id,
        "tokenAddress": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }


def _crypto_from_payload(payload: Mapping[str, Any]) -> Crypto:
    return Crypto(
        amount=payload["amount"],
        symbol=str(payload["symbol"]),
        chain_id=int(payload["chainId"]),
        token_address=payload.get("tokenAddress"),
        decimals=int(payload["decimals"]),
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

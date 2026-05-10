"""PostgreSQL aggregate repository for the inventory context."""

from __future__ import annotations

from typing import Any, Mapping

from token_payments.contexts.inventory.domain import (
    InventoryReservation,
    ProductInventory,
    Quantity,
    ReservationId,
    ReservationStatus,
)
from token_payments.shared.adapter.postgres import PostgresConnection
from token_payments.shared.domain import OrderId, ProductId, StoreId


SELECT_INVENTORY_SQL = """
SELECT
    product_id,
    store_id,
    available_stock,
    reserved_stock,
    total_stock
FROM product_inventory
WHERE product_id = %(product_id)s
  AND store_id = %(store_id)s
"""

SELECT_RESERVATIONS_SQL = """
SELECT
    reservation_id,
    product_id,
    store_id,
    order_id,
    reserved_qty,
    status,
    created_at
FROM inventory_reservations
WHERE product_id = %(product_id)s
  AND store_id = %(store_id)s
ORDER BY created_at, reservation_id
"""

UPSERT_INVENTORY_SQL = """
INSERT INTO product_inventory (
    product_id,
    store_id,
    available_stock,
    reserved_stock,
    total_stock
) VALUES (
    %(product_id)s,
    %(store_id)s,
    %(available_stock)s,
    %(reserved_stock)s,
    %(total_stock)s
)
ON CONFLICT (product_id, store_id) DO UPDATE SET
    available_stock = EXCLUDED.available_stock,
    reserved_stock = EXCLUDED.reserved_stock,
    total_stock = EXCLUDED.total_stock,
    version = product_inventory.version + 1,
    updated_at = now()
"""

UPSERT_RESERVATION_SQL = """
INSERT INTO inventory_reservations (
    reservation_id,
    product_id,
    store_id,
    order_id,
    reserved_qty,
    status,
    created_at
) VALUES (
    %(reservation_id)s,
    %(product_id)s,
    %(store_id)s,
    %(order_id)s,
    %(reserved_qty)s,
    %(status)s,
    %(created_at)s
)
ON CONFLICT (reservation_id) DO UPDATE SET
    product_id = EXCLUDED.product_id,
    store_id = EXCLUDED.store_id,
    order_id = EXCLUDED.order_id,
    reserved_qty = EXCLUDED.reserved_qty,
    status = EXCLUDED.status,
    updated_at = now()
"""

DELETE_STALE_RESERVATIONS_SQL = """
DELETE FROM inventory_reservations
WHERE product_id = %(product_id)s
  AND store_id = %(store_id)s
  AND NOT (reservation_id = ANY(%(reservation_ids)s))
"""

DELETE_ALL_RESERVATIONS_SQL = """
DELETE FROM inventory_reservations
WHERE product_id = %(product_id)s
  AND store_id = %(store_id)s
"""


class PostgresInventoryRepository:
    """Persist ProductInventory aggregates inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get(self, product_id: ProductId, store_id: StoreId) -> ProductInventory | None:
        if not isinstance(product_id, ProductId):
            raise ValueError("PostgresInventoryRepository.get requires a ProductId")
        if not isinstance(store_id, StoreId):
            raise ValueError("PostgresInventoryRepository.get requires a StoreId")

        inventory_row = _fetch_one(
            self._connection.execute(
                SELECT_INVENTORY_SQL,
                {
                    "product_id": str(product_id),
                    "store_id": str(store_id),
                },
            )
        )
        if inventory_row is None:
            return None

        reservation_rows = _fetch_all(
            self._connection.execute(
                SELECT_RESERVATIONS_SQL,
                {
                    "product_id": str(product_id),
                    "store_id": str(store_id),
                },
            )
        )
        return ProductInventory(
            product_id=ProductId(_row_value(inventory_row, "product_id")),
            store_id=StoreId(_row_value(inventory_row, "store_id")),
            available_stock=Quantity(int(_row_value(inventory_row, "available_stock"))),
            reserved_stock=Quantity(int(_row_value(inventory_row, "reserved_stock"))),
            total_stock=Quantity(int(_row_value(inventory_row, "total_stock"))),
            reservations=tuple(_row_to_reservation(row) for row in reservation_rows),
        )

    def save(self, inventory: ProductInventory) -> None:
        if not isinstance(inventory, ProductInventory):
            raise ValueError("PostgresInventoryRepository.save requires a ProductInventory")

        product_id = str(inventory.product_id)
        store_id = str(inventory.store_id)
        self._connection.execute(
            UPSERT_INVENTORY_SQL,
            {
                "product_id": product_id,
                "store_id": store_id,
                "available_stock": inventory.available_stock.value,
                "reserved_stock": inventory.reserved_stock.value,
                "total_stock": inventory.total_stock.value,
            },
        )

        reservation_ids = tuple(str(reservation.reservation_id) for reservation in inventory.reservations)
        for reservation in inventory.reservations:
            self._connection.execute(
                UPSERT_RESERVATION_SQL,
                {
                    "reservation_id": str(reservation.reservation_id),
                    "product_id": product_id,
                    "store_id": store_id,
                    "order_id": str(reservation.order_id),
                    "reserved_qty": reservation.reserved_qty.value,
                    "status": reservation.status.value,
                    "created_at": reservation.created_at,
                },
            )

        if reservation_ids:
            self._connection.execute(
                DELETE_STALE_RESERVATIONS_SQL,
                {
                    "product_id": product_id,
                    "store_id": store_id,
                    "reservation_ids": reservation_ids,
                },
            )
        else:
            self._connection.execute(
                DELETE_ALL_RESERVATIONS_SQL,
                {
                    "product_id": product_id,
                    "store_id": store_id,
                },
            )


def _row_to_reservation(row: Mapping[str, Any] | object) -> InventoryReservation:
    return InventoryReservation(
        reservation_id=ReservationId(_row_value(row, "reservation_id")),
        order_id=OrderId(_row_value(row, "order_id")),
        reserved_qty=Quantity(int(_row_value(row, "reserved_qty"))),
        status=ReservationStatus(_row_value(row, "status")),
        created_at=_row_value(row, "created_at"),
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

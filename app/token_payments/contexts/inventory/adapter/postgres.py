"""PostgreSQL aggregate repository for the inventory context."""

from __future__ import annotations

from typing import Any, Mapping

from token_payments.contexts.inventory.domain import (
    InventorySaleStatus,
    InventoryReservation,
    ProductInventory,
    Quantity,
    ReservationId,
    ReservationStatus,
)
from token_payments.contexts.inventory.application import InventoryAuditRecord, InventorySnapshot
from token_payments.shared.adapter.postgres import PostgresConnection
from token_payments.shared.domain import OrderId, ProductId, StoreId, UserId


SELECT_INVENTORY_SQL = """
SELECT
    product_id,
    store_id,
    available_stock,
    reserved_stock,
    total_stock,
    sale_status
FROM product_inventory
WHERE product_id = %(product_id)s
  AND store_id = %(store_id)s
"""

SELECT_INVENTORY_SNAPSHOTS_SQL = """
SELECT
    inv.product_id,
    inv.store_id,
    inv.available_stock,
    inv.reserved_stock,
    COALESCE(confirmed.confirmed_stock, 0) AS confirmed_stock,
    inv.total_stock,
    inv.sale_status,
    inv.updated_at
FROM product_inventory inv
LEFT JOIN (
    SELECT product_id, store_id, SUM(reserved_qty) AS confirmed_stock
    FROM inventory_reservations
    WHERE status = 'CONFIRMED'
    GROUP BY product_id, store_id
) confirmed
  ON confirmed.product_id = inv.product_id
 AND confirmed.store_id = inv.store_id
WHERE (%(store_id)s IS NULL OR inv.store_id = %(store_id)s)
ORDER BY inv.store_id, inv.product_id
"""

SELECT_OWNER_INVENTORY_SNAPSHOTS_SQL = """
SELECT
    inv.product_id,
    inv.store_id,
    inv.available_stock,
    inv.reserved_stock,
    COALESCE(confirmed.confirmed_stock, 0) AS confirmed_stock,
    inv.total_stock,
    inv.sale_status,
    inv.updated_at
FROM product_inventory inv
JOIN order_stores stores
  ON stores.store_id = inv.store_id
LEFT JOIN (
    SELECT product_id, store_id, SUM(reserved_qty) AS confirmed_stock
    FROM inventory_reservations
    WHERE status = 'CONFIRMED'
    GROUP BY product_id, store_id
) confirmed
  ON confirmed.product_id = inv.product_id
 AND confirmed.store_id = inv.store_id
WHERE stores.owner_user_id = %(owner_user_id)s
  AND (%(store_id)s IS NULL OR inv.store_id = %(store_id)s)
ORDER BY inv.store_id, inv.product_id
"""

SELECT_STORE_OWNER_SQL = """
SELECT owner_user_id
FROM order_stores
WHERE store_id = %(store_id)s
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
    total_stock,
    sale_status
) VALUES (
    %(product_id)s,
    %(store_id)s,
    %(available_stock)s,
    %(reserved_stock)s,
    %(total_stock)s,
    %(sale_status)s
)
ON CONFLICT (product_id, store_id) DO UPDATE SET
    available_stock = EXCLUDED.available_stock,
    reserved_stock = EXCLUDED.reserved_stock,
    total_stock = EXCLUDED.total_stock,
    sale_status = EXCLUDED.sale_status,
    version = product_inventory.version + 1,
    updated_at = now()
"""

INSERT_INVENTORY_AUDIT_SQL = """
INSERT INTO inventory_audit_log (
    actor_user_id,
    actor_role,
    store_id,
    product_id,
    action,
    before_available_stock,
    before_reserved_stock,
    before_total_stock,
    before_sale_status,
    after_available_stock,
    after_reserved_stock,
    after_total_stock,
    after_sale_status,
    reason,
    request_id,
    idempotency_key,
    recorded_at
) VALUES (
    %(actor_user_id)s,
    %(actor_role)s,
    %(store_id)s,
    %(product_id)s,
    %(action)s,
    %(before_available_stock)s,
    %(before_reserved_stock)s,
    %(before_total_stock)s,
    %(before_sale_status)s,
    %(after_available_stock)s,
    %(after_reserved_stock)s,
    %(after_total_stock)s,
    %(after_sale_status)s,
    %(reason)s,
    %(request_id)s,
    %(idempotency_key)s,
    %(recorded_at)s
)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING audit_id
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
            sale_status=InventorySaleStatus(_row_value_or_default(inventory_row, "sale_status", InventorySaleStatus.ACTIVE.value)),
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
                "sale_status": inventory.sale_status.value,
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


class PostgresInventoryQueryRepository:
    """Read inventory snapshots and store ownership for API facades."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def list_inventory(self, store_id: StoreId | None = None) -> tuple[InventorySnapshot, ...]:
        if store_id is not None and not isinstance(store_id, StoreId):
            raise ValueError("PostgresInventoryQueryRepository.list_inventory store_id must be a StoreId")
        rows = _fetch_all(
            self._connection.execute(
                SELECT_INVENTORY_SNAPSHOTS_SQL,
                {"store_id": str(store_id) if store_id is not None else None},
            )
        )
        return tuple(_row_to_snapshot(row) for row in rows)

    def list_inventory_for_owner(
        self,
        owner_user_id: UserId,
        store_id: StoreId | None = None,
    ) -> tuple[InventorySnapshot, ...]:
        if not isinstance(owner_user_id, UserId):
            raise ValueError("PostgresInventoryQueryRepository.list_inventory_for_owner requires a UserId")
        if store_id is not None and not isinstance(store_id, StoreId):
            raise ValueError("PostgresInventoryQueryRepository.list_inventory_for_owner store_id must be a StoreId")
        rows = _fetch_all(
            self._connection.execute(
                SELECT_OWNER_INVENTORY_SNAPSHOTS_SQL,
                {
                    "owner_user_id": str(owner_user_id),
                    "store_id": str(store_id) if store_id is not None else None,
                },
            )
        )
        return tuple(_row_to_snapshot(row) for row in rows)

    def owner_for_store(self, store_id: StoreId) -> UserId | None:
        if not isinstance(store_id, StoreId):
            raise ValueError("PostgresInventoryQueryRepository.owner_for_store requires a StoreId")
        row = _fetch_one(self._connection.execute(SELECT_STORE_OWNER_SQL, {"store_id": str(store_id)}))
        if row is None:
            return None
        return UserId(_row_value(row, "owner_user_id"))


class PostgresInventoryAuditRepository:
    """Persist store owner inventory mutation audit records."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def record(self, audit_record: InventoryAuditRecord) -> str | None:
        if not isinstance(audit_record, InventoryAuditRecord):
            raise ValueError("PostgresInventoryAuditRepository.record requires an InventoryAuditRecord")
        row = _fetch_one(
            self._connection.execute(
                INSERT_INVENTORY_AUDIT_SQL,
                {
                    "actor_user_id": str(audit_record.actor_user_id),
                    "actor_role": audit_record.actor_role.value,
                    "store_id": str(audit_record.store_id),
                    "product_id": str(audit_record.product_id),
                    "action": audit_record.action,
                    "before_available_stock": audit_record.before_available_stock,
                    "before_reserved_stock": audit_record.before_reserved_stock,
                    "before_total_stock": audit_record.before_total_stock,
                    "before_sale_status": audit_record.before_sale_status.value,
                    "after_available_stock": audit_record.after_available_stock,
                    "after_reserved_stock": audit_record.after_reserved_stock,
                    "after_total_stock": audit_record.after_total_stock,
                    "after_sale_status": audit_record.after_sale_status.value,
                    "reason": audit_record.reason,
                    "request_id": audit_record.request_id,
                    "idempotency_key": audit_record.idempotency_key,
                    "recorded_at": audit_record.recorded_at,
                },
            )
        )
        return str(_row_value(row, "audit_id")) if row is not None else None


def _row_to_reservation(row: Mapping[str, Any] | object) -> InventoryReservation:
    return InventoryReservation(
        reservation_id=ReservationId(_row_value(row, "reservation_id")),
        order_id=OrderId(_row_value(row, "order_id")),
        reserved_qty=Quantity(int(_row_value(row, "reserved_qty"))),
        status=ReservationStatus(_row_value(row, "status")),
        created_at=_row_value(row, "created_at"),
    )


def _row_to_snapshot(row: Mapping[str, Any] | object) -> InventorySnapshot:
    return InventorySnapshot(
        product_id=ProductId(_row_value(row, "product_id")),
        store_id=StoreId(_row_value(row, "store_id")),
        available_stock=int(_row_value(row, "available_stock")),
        reserved_stock=int(_row_value(row, "reserved_stock")),
        confirmed_stock=int(_row_value(row, "confirmed_stock")),
        total_stock=int(_row_value(row, "total_stock")),
        sale_status=InventorySaleStatus(_row_value(row, "sale_status")),
        updated_at=_row_value(row, "updated_at"),
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


def _row_value_or_default(row: Mapping[str, Any] | object, key: str, default: Any) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    return getattr(row, key, default)

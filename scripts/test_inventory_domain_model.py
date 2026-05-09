from __future__ import annotations

import ast
import sys
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.inventory.domain import (  # noqa: E402
    InventoryConfirmedEvent,
    InventoryReleasedEvent,
    InventoryReservation,
    InventoryReservedEvent,
    ProductInventory,
    Quantity,
    ReservationExpiredEvent,
    ReservationId,
    ReservationStatus,
    StockDecreasedEvent,
    StockIncreasedEvent,
)
from token_payments.shared.domain import OrderId, ProductId, StoreId  # noqa: E402


NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
OTHER_ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
RESERVATION_ID = ReservationId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")


def test_quantity_rejects_negative_and_bool_and_blocks_negative_results() -> None:
    quantity = Quantity(5)

    assert Quantity(0).value == 0
    assert quantity.add(Quantity(2)) == Quantity(7)
    assert quantity.subtract(3) == Quantity(2)

    with pytest.raises(ValueError):
        Quantity(-1)

    with pytest.raises(ValueError):
        Quantity(True)

    with pytest.raises(ValueError):
        Quantity(1).subtract(2)


def test_product_inventory_is_immutable() -> None:
    inventory = _inventory(available=10)

    with pytest.raises(FrozenInstanceError):
        inventory.available_stock = Quantity(0)  # type: ignore[misc]


def test_reserve_inventory_moves_available_to_reserved_and_prevents_duplicates() -> None:
    inventory = _inventory(available=10)

    reserved = inventory.reserve_inventory(
        order_id=ORDER_ID,
        quantity=Quantity(3),
        reservation_id=RESERVATION_ID,
    )
    duplicate = reserved.reserve_inventory(
        order_id=ORDER_ID,
        quantity=Quantity(3),
        reservation_id=ReservationId.new(),
    )

    assert inventory.available_stock == Quantity(10)
    assert inventory.reserved_stock == Quantity(0)
    assert reserved.available_stock == Quantity(7)
    assert reserved.reserved_stock == Quantity(3)
    assert reserved.total_stock == Quantity(10)
    assert len(reserved.reservations) == 1
    assert reserved.reservations[0].reservation_id == RESERVATION_ID
    assert reserved.reservations[0].order_id == ORDER_ID
    assert reserved.reservations[0].reserved_qty == Quantity(3)
    assert reserved.reservations[0].status == ReservationStatus.PENDING
    assert duplicate == reserved


def test_reserve_inventory_rejects_non_positive_or_unavailable_quantities() -> None:
    inventory = _inventory(available=2)

    with pytest.raises(ValueError):
        inventory.reserve_inventory(ORDER_ID, Quantity(0))

    with pytest.raises(ValueError):
        inventory.reserve_inventory(ORDER_ID, Quantity(3))


def test_confirm_reservation_consumes_reserved_stock_and_is_idempotent() -> None:
    reserved = _inventory(available=10).reserve_inventory(ORDER_ID, Quantity(3), RESERVATION_ID)

    confirmed = reserved.confirm_reservation(ORDER_ID)
    confirmed_again = confirmed.confirm_reservation(ORDER_ID)

    assert confirmed.available_stock == Quantity(7)
    assert confirmed.reserved_stock == Quantity(0)
    assert confirmed.total_stock == Quantity(7)
    assert confirmed.reservations[0].status == ReservationStatus.CONFIRMED
    assert confirmed_again == confirmed

    cancelled = reserved.release_reservation(ORDER_ID)
    with pytest.raises(ValueError):
        cancelled.confirm_reservation(ORDER_ID)


def test_release_reservation_restores_available_stock_and_is_idempotent() -> None:
    reserved = _inventory(available=10).reserve_inventory(ORDER_ID, Quantity(3), RESERVATION_ID)

    released = reserved.release_reservation(ORDER_ID)
    released_again = released.release_reservation(ORDER_ID)

    assert released.available_stock == Quantity(10)
    assert released.reserved_stock == Quantity(0)
    assert released.total_stock == Quantity(10)
    assert released.reservations[0].status == ReservationStatus.CANCELLED
    assert released_again == released

    confirmed = reserved.confirm_reservation(ORDER_ID)
    with pytest.raises(ValueError):
        confirmed.release_reservation(ORDER_ID)


def test_stock_adjustments_keep_available_reserved_and_total_consistent() -> None:
    inventory = _inventory(available=10)

    increased = inventory.increase_stock(Quantity(5))
    decreased = increased.decrease_stock(Quantity(4))
    reserved = decreased.reserve_inventory(ORDER_ID, Quantity(8))

    assert increased.available_stock == Quantity(15)
    assert increased.total_stock == Quantity(15)
    assert decreased.available_stock == Quantity(11)
    assert decreased.total_stock == Quantity(11)

    with pytest.raises(ValueError):
        decreased.decrease_stock(Quantity(12))

    with pytest.raises(ValueError):
        reserved.decrease_stock(Quantity(4))


def test_inventory_reservations_and_events_validate_domain_shape() -> None:
    reservation = InventoryReservation.create(
        order_id=ORDER_ID,
        quantity=Quantity(2),
        reservation_id=RESERVATION_ID,
        created_at=NOW,
    )
    reserved = _inventory(available=10).reserve_inventory(ORDER_ID, Quantity(2), RESERVATION_ID)
    confirmed = reserved.confirm_reservation(ORDER_ID)
    released = reserved.reserve_inventory(OTHER_ORDER_ID, Quantity(1)).release_reservation(OTHER_ORDER_ID)
    increased = released.increase_stock(Quantity(1))
    decreased = increased.decrease_stock(Quantity(1))

    assert reservation.created_at == NOW
    assert InventoryReservedEvent(inventory=reserved, order_id=ORDER_ID, created_at=NOW).inventory == reserved
    assert InventoryConfirmedEvent(inventory=confirmed, order_id=ORDER_ID, created_at=NOW).order_id == ORDER_ID
    assert InventoryReleasedEvent(inventory=released, order_id=OTHER_ORDER_ID, created_at=NOW).created_at == NOW
    assert (
        ReservationExpiredEvent(inventory=released, reservation_id=RESERVATION_ID, expired_at=NOW).reservation_id
        == RESERVATION_ID
    )
    assert StockIncreasedEvent(inventory=increased, created_at=NOW).inventory == increased
    assert StockDecreasedEvent(inventory=decreased, created_at=NOW).inventory == decreased

    with pytest.raises(ValueError):
        InventoryReservedEvent(inventory=reserved, order_id=ORDER_ID, created_at=datetime(2026, 5, 9, 12, 0))


def test_inventory_domain_public_contracts_are_exported() -> None:
    import token_payments.contexts.inventory.domain as domain

    assert {
        "InventoryConfirmedEvent",
        "InventoryReleasedEvent",
        "InventoryReservation",
        "InventoryReservedEvent",
        "ProductInventory",
        "Quantity",
        "ReservationExpiredEvent",
        "ReservationId",
        "ReservationStatus",
        "StockDecreasedEvent",
        "StockIncreasedEvent",
    } <= set(domain.__all__)


def test_inventory_domain_does_not_import_external_adapters_or_clients() -> None:
    forbidden_roots = {
        "blockchain",
        "kafka",
        "metamask",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }

    for path in (ROOT / "app/token_payments/contexts/inventory/domain").glob("**/*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        assert imports.isdisjoint(forbidden_roots), f"{path} imports adapter dependency: {imports}"


def _inventory(available: int) -> ProductInventory:
    return ProductInventory(
        product_id=PRODUCT_ID,
        store_id=STORE_ID,
        available_stock=Quantity(available),
        reserved_stock=Quantity(0),
        total_stock=Quantity(available),
        reservations=(),
    )

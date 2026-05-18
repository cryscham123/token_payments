"""Pure domain model for product inventory reservations."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self, TypeAlias
from uuid import UUID, uuid4

from token_payments.shared.domain import OrderId, ProductId, StoreId


class ReservationStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class InventorySaleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


@dataclass(frozen=True)
class ReservationId:
    value: UUID

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _coerce_uuid(self.value, "ReservationId.value"))

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class Quantity:
    value: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _coerce_non_negative_int(self.value, "Quantity.value"))

    @property
    def is_valid(self) -> bool:
        return True

    @property
    def is_positive(self) -> bool:
        return self.value > 0

    def add(self, other: "Quantity | int") -> "Quantity":
        return type(self)(self.value + _coerce_quantity(other).value)

    def subtract(self, other: "Quantity | int") -> "Quantity":
        other_quantity = _coerce_quantity(other)
        if other_quantity.value > self.value:
            raise ValueError("Quantity subtraction cannot produce a negative result")
        return type(self)(self.value - other_quantity.value)

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class InventoryReservation:
    reservation_id: ReservationId
    order_id: OrderId
    reserved_qty: Quantity | int
    status: ReservationStatus = ReservationStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.reservation_id, ReservationId):
            raise ValueError("InventoryReservation.reservation_id must be a ReservationId")
        if not isinstance(self.order_id, OrderId):
            raise ValueError("InventoryReservation.order_id must be an OrderId")
        quantity = _coerce_quantity(self.reserved_qty)
        _require_positive_quantity(quantity, "InventoryReservation.reserved_qty")
        object.__setattr__(self, "reserved_qty", quantity)
        object.__setattr__(self, "status", _coerce_reservation_status(self.status))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "InventoryReservation.created_at"),
        )

    @classmethod
    def create(
        cls,
        order_id: OrderId,
        quantity: Quantity | int,
        reservation_id: ReservationId | None = None,
        created_at: datetime | None = None,
    ) -> Self:
        if not isinstance(order_id, OrderId):
            raise ValueError("InventoryReservation.create requires an OrderId")
        return cls(
            reservation_id=reservation_id or ReservationId.new(),
            order_id=order_id,
            reserved_qty=quantity,
            status=ReservationStatus.PENDING,
            created_at=created_at or datetime.now(UTC),
        )

    def confirm(self) -> Self:
        if self.status is ReservationStatus.CONFIRMED:
            return self
        if self.status is ReservationStatus.CANCELLED:
            raise ValueError("cancelled inventory reservations cannot be confirmed")
        return replace(self, status=ReservationStatus.CONFIRMED)

    def cancel(self) -> Self:
        if self.status is ReservationStatus.CANCELLED:
            return self
        if self.status is ReservationStatus.CONFIRMED:
            raise ValueError("confirmed inventory reservations cannot be cancelled")
        return replace(self, status=ReservationStatus.CANCELLED)


@dataclass(frozen=True)
class ProductInventory:
    product_id: ProductId
    store_id: StoreId
    available_stock: Quantity | int
    reserved_stock: Quantity | int
    total_stock: Quantity | int
    sale_status: InventorySaleStatus | str = InventorySaleStatus.ACTIVE
    reservations: tuple[InventoryReservation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.product_id, ProductId):
            raise ValueError("ProductInventory.product_id must be a ProductId")
        if not isinstance(self.store_id, StoreId):
            raise ValueError("ProductInventory.store_id must be a StoreId")

        available_stock = _coerce_quantity(self.available_stock)
        reserved_stock = _coerce_quantity(self.reserved_stock)
        total_stock = _coerce_quantity(self.total_stock)
        object.__setattr__(self, "available_stock", available_stock)
        object.__setattr__(self, "reserved_stock", reserved_stock)
        object.__setattr__(self, "total_stock", total_stock)
        object.__setattr__(self, "sale_status", _coerce_sale_status(self.sale_status))
        object.__setattr__(
            self,
            "reservations",
            _coerce_reservations(self.reservations),
        )

        if available_stock.add(reserved_stock) != total_stock:
            raise ValueError("ProductInventory.total_stock must equal available_stock + reserved_stock")
        _validate_reservation_identity(self.reservations)
        _validate_reserved_stock_matches_pending_reservations(reserved_stock, self.reservations)

    def reserve_inventory(
        self,
        order_id: OrderId,
        quantity: Quantity | int,
        reservation_id: ReservationId | None = None,
    ) -> Self:
        if not isinstance(order_id, OrderId):
            raise ValueError("ProductInventory.reserve_inventory requires an OrderId")

        quantity = _coerce_quantity(quantity)
        _require_positive_quantity(quantity, "quantity")

        existing = self._find_reservation(order_id)
        if existing is not None:
            return self

        if self.available_stock.value < quantity.value:
            raise ValueError("insufficient available stock to reserve inventory")

        reservation = InventoryReservation.create(
            order_id=order_id,
            quantity=quantity,
            reservation_id=reservation_id,
        )
        return replace(
            self,
            available_stock=self.available_stock.subtract(quantity),
            reserved_stock=self.reserved_stock.add(quantity),
            reservations=self.reservations + (reservation,),
        )

    def release_reservation(self, order_id: OrderId) -> Self:
        reservation = self._require_reservation(order_id, "release")
        if reservation.status is ReservationStatus.CANCELLED:
            return self
        released = reservation.cancel()
        return replace(
            self,
            available_stock=self.available_stock.add(reservation.reserved_qty),
            reserved_stock=self.reserved_stock.subtract(reservation.reserved_qty),
            reservations=self._replace_reservation(released),
        )

    def confirm_reservation(self, order_id: OrderId) -> Self:
        reservation = self._require_reservation(order_id, "confirm")
        if reservation.status is ReservationStatus.CONFIRMED:
            return self
        confirmed = reservation.confirm()
        return replace(
            self,
            reserved_stock=self.reserved_stock.subtract(reservation.reserved_qty),
            total_stock=self.total_stock.subtract(reservation.reserved_qty),
            reservations=self._replace_reservation(confirmed),
        )

    def increase_stock(self, quantity: Quantity | int) -> Self:
        quantity = _coerce_quantity(quantity)
        _require_positive_quantity(quantity, "quantity")
        return replace(
            self,
            available_stock=self.available_stock.add(quantity),
            total_stock=self.total_stock.add(quantity),
        )

    def decrease_stock(self, quantity: Quantity | int) -> Self:
        quantity = _coerce_quantity(quantity)
        _require_positive_quantity(quantity, "quantity")
        return replace(
            self,
            available_stock=self.available_stock.subtract(quantity),
            total_stock=self.total_stock.subtract(quantity),
        )

    def correct_total_stock(self, target_total_stock: Quantity | int) -> Self:
        target = _coerce_quantity(target_total_stock)
        if target.value < self.reserved_stock.value:
            raise ValueError("total stock cannot be lower than reserved stock")
        return replace(
            self,
            available_stock=Quantity(target.value - self.reserved_stock.value),
            total_stock=target,
        )

    def pause_sales(self) -> Self:
        if self.sale_status is InventorySaleStatus.PAUSED:
            return self
        return replace(self, sale_status=InventorySaleStatus.PAUSED)

    def resume_sales(self) -> Self:
        if self.sale_status is InventorySaleStatus.ACTIVE:
            return self
        return replace(self, sale_status=InventorySaleStatus.ACTIVE)

    @property
    def available_for_new_orders(self) -> bool:
        return self.sale_status is InventorySaleStatus.ACTIVE and self.available_stock.value > 0

    def record_reserved(self, order_id: OrderId, created_at: datetime | None = None) -> "InventoryReservedEvent":
        return InventoryReservedEvent(inventory=self, order_id=order_id, created_at=created_at or datetime.now(UTC))

    def record_confirmed(self, order_id: OrderId, created_at: datetime | None = None) -> "InventoryConfirmedEvent":
        return InventoryConfirmedEvent(inventory=self, order_id=order_id, created_at=created_at or datetime.now(UTC))

    def record_released(self, order_id: OrderId, created_at: datetime | None = None) -> "InventoryReleasedEvent":
        return InventoryReleasedEvent(inventory=self, order_id=order_id, created_at=created_at or datetime.now(UTC))

    def record_reservation_expired(
        self,
        reservation_id: ReservationId,
        expired_at: datetime | None = None,
    ) -> "ReservationExpiredEvent":
        return ReservationExpiredEvent(
            inventory=self,
            reservation_id=reservation_id,
            expired_at=expired_at or datetime.now(UTC),
        )

    def record_stock_increased(self, created_at: datetime | None = None) -> "StockIncreasedEvent":
        return StockIncreasedEvent(inventory=self, created_at=created_at or datetime.now(UTC))

    def record_stock_decreased(self, created_at: datetime | None = None) -> "StockDecreasedEvent":
        return StockDecreasedEvent(inventory=self, created_at=created_at or datetime.now(UTC))

    def _find_reservation(self, order_id: OrderId) -> InventoryReservation | None:
        if not isinstance(order_id, OrderId):
            raise ValueError("reservation lookup requires an OrderId")
        for reservation in self.reservations:
            if reservation.order_id == order_id:
                return reservation
        return None

    def _require_reservation(self, order_id: OrderId, action: str) -> InventoryReservation:
        reservation = self._find_reservation(order_id)
        if reservation is None:
            raise ValueError(f"cannot {action} missing inventory reservation for order {order_id}")
        return reservation

    def _replace_reservation(self, replacement: InventoryReservation) -> tuple[InventoryReservation, ...]:
        return tuple(
            replacement if reservation.reservation_id == replacement.reservation_id else reservation
            for reservation in self.reservations
        )


@dataclass(frozen=True)
class InventoryReservedEvent:
    inventory: ProductInventory
    order_id: OrderId
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "created_at",
            _validate_inventory_order_event(self.inventory, self.order_id, self.created_at, type(self).__name__),
        )

    @property
    def inv(self) -> ProductInventory:
        return self.inventory


@dataclass(frozen=True)
class InventoryConfirmedEvent:
    inventory: ProductInventory
    order_id: OrderId
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "created_at",
            _validate_inventory_order_event(self.inventory, self.order_id, self.created_at, type(self).__name__),
        )

    @property
    def inv(self) -> ProductInventory:
        return self.inventory


@dataclass(frozen=True)
class InventoryReleasedEvent:
    inventory: ProductInventory
    order_id: OrderId
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "created_at",
            _validate_inventory_order_event(self.inventory, self.order_id, self.created_at, type(self).__name__),
        )

    @property
    def inv(self) -> ProductInventory:
        return self.inventory


@dataclass(frozen=True)
class ReservationExpiredEvent:
    inventory: ProductInventory
    reservation_id: ReservationId
    expired_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.inventory, ProductInventory):
            raise ValueError("ReservationExpiredEvent.inventory must be a ProductInventory")
        if not isinstance(self.reservation_id, ReservationId):
            raise ValueError("ReservationExpiredEvent.reservation_id must be a ReservationId")
        object.__setattr__(
            self,
            "expired_at",
            _require_aware_datetime(self.expired_at, "ReservationExpiredEvent.expired_at"),
        )

    @property
    def inv(self) -> ProductInventory:
        return self.inventory


@dataclass(frozen=True)
class StockIncreasedEvent:
    inventory: ProductInventory
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.inventory, ProductInventory):
            raise ValueError("StockIncreasedEvent.inventory must be a ProductInventory")
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "StockIncreasedEvent.created_at"),
        )

    @property
    def inv(self) -> ProductInventory:
        return self.inventory


@dataclass(frozen=True)
class StockDecreasedEvent:
    inventory: ProductInventory
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.inventory, ProductInventory):
            raise ValueError("StockDecreasedEvent.inventory must be a ProductInventory")
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "StockDecreasedEvent.created_at"),
        )

    @property
    def inv(self) -> ProductInventory:
        return self.inventory


InventoryEvent: TypeAlias = (
    InventoryReservedEvent
    | InventoryConfirmedEvent
    | InventoryReleasedEvent
    | ReservationExpiredEvent
    | StockIncreasedEvent
    | StockDecreasedEvent
)


def _coerce_quantity(value: Quantity | int) -> Quantity:
    return value if isinstance(value, Quantity) else Quantity(value)


def _require_positive_quantity(quantity: Quantity, field_name: str) -> None:
    if not quantity.is_positive:
        raise ValueError(f"{field_name} must be a positive quantity")


def _coerce_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _coerce_uuid(value: UUID | str, field_name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return UUID(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a valid UUID") from exc
    raise ValueError(f"{field_name} must be a non-empty UUID")


def _coerce_reservation_status(value: ReservationStatus | str) -> ReservationStatus:
    if isinstance(value, ReservationStatus):
        return value
    try:
        return ReservationStatus(str(value))
    except ValueError as exc:
        raise ValueError("InventoryReservation.status must be a ReservationStatus") from exc


def _coerce_sale_status(value: InventorySaleStatus | str) -> InventorySaleStatus:
    if isinstance(value, InventorySaleStatus):
        return value
    try:
        return InventorySaleStatus(str(value))
    except ValueError as exc:
        raise ValueError("ProductInventory.sale_status must be an InventorySaleStatus") from exc


def _coerce_reservations(
    values: tuple[InventoryReservation, ...] | list[InventoryReservation],
) -> tuple[InventoryReservation, ...]:
    if isinstance(values, list):
        values = tuple(values)
    if not isinstance(values, tuple):
        raise ValueError("ProductInventory.reservations must be a tuple")
    if not all(isinstance(value, InventoryReservation) for value in values):
        raise ValueError("ProductInventory.reservations must contain only InventoryReservation")
    return values


def _validate_reservation_identity(reservations: tuple[InventoryReservation, ...]) -> None:
    order_ids = [reservation.order_id for reservation in reservations]
    if len(set(order_ids)) != len(order_ids):
        raise ValueError("ProductInventory.reservations cannot contain duplicate OrderId values")

    reservation_ids = [reservation.reservation_id for reservation in reservations]
    if len(set(reservation_ids)) != len(reservation_ids):
        raise ValueError("ProductInventory.reservations cannot contain duplicate ReservationId values")


def _validate_reserved_stock_matches_pending_reservations(
    reserved_stock: Quantity,
    reservations: tuple[InventoryReservation, ...],
) -> None:
    pending_quantity = Quantity(0)
    for reservation in reservations:
        if reservation.status is ReservationStatus.PENDING:
            pending_quantity = pending_quantity.add(reservation.reserved_qty)

    if pending_quantity != reserved_stock:
        raise ValueError("ProductInventory.reserved_stock must equal pending reservation quantity")


def _validate_inventory_order_event(
    inventory: ProductInventory,
    order_id: OrderId,
    created_at: datetime,
    event_name: str,
) -> datetime:
    if not isinstance(inventory, ProductInventory):
        raise ValueError(f"{event_name}.inventory must be a ProductInventory")
    if not isinstance(order_id, OrderId):
        raise ValueError(f"{event_name}.order_id must be an OrderId")
    return _require_aware_datetime(created_at, f"{event_name}.created_at")


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value

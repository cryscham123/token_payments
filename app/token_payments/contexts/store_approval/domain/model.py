"""Pure domain model for store order approval."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self, TypeAlias

from token_payments.shared.domain import Crypto, OrderId, ProductId, StoreId, UserId


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Product:
    product_id: ProductId
    name: str
    price: Crypto
    available: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.product_id, ProductId):
            raise ValueError("Product.product_id must be a ProductId")
        object.__setattr__(self, "name", _require_text(self.name, "Product.name"))
        if not isinstance(self.price, Crypto):
            raise ValueError("Product.price must be a Crypto value")
        if not isinstance(self.available, bool):
            raise ValueError("Product.available must be a bool")

    def matches_snapshot(self, snapshot: "Product") -> bool:
        if not isinstance(snapshot, Product):
            raise ValueError("Product.matches_snapshot requires a Product snapshot")
        return self.product_id == snapshot.product_id and self.name == snapshot.name and self.price == snapshot.price


@dataclass(frozen=True)
class OrderDetail:
    order_id: OrderId
    store_id: StoreId
    order_status: str
    total_amount: Crypto
    products: tuple[Product, ...]
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, OrderId):
            raise ValueError("OrderDetail.order_id must be an OrderId")
        if not isinstance(self.store_id, StoreId):
            raise ValueError("OrderDetail.store_id must be a StoreId")
        object.__setattr__(self, "order_status", _require_text(self.order_status, "OrderDetail.order_status"))
        if not isinstance(self.total_amount, Crypto):
            raise ValueError("OrderDetail.total_amount must be a Crypto value")
        products = _coerce_products(self.products)
        if not products:
            raise ValueError("OrderDetail.products must contain at least one product")
        object.__setattr__(self, "products", products)
        object.__setattr__(self, "approval_status", _coerce_approval_status(self.approval_status))
        object.__setattr__(
            self,
            "rejection_reasons",
            tuple(_require_text(reason, "OrderDetail.rejection_reasons") for reason in self.rejection_reasons),
        )

    def approve(self) -> Self:
        if self.approval_status is ApprovalStatus.APPROVED:
            return self
        if self.approval_status is ApprovalStatus.REJECTED:
            raise ValueError("rejected order details cannot be approved")
        return replace(self, approval_status=ApprovalStatus.APPROVED, rejection_reasons=())

    def reject(self, reasons: tuple[str, ...] | list[str]) -> Self:
        rejection_reasons = tuple(_require_text(reason, "rejection reason") for reason in reasons)
        if not rejection_reasons:
            raise ValueError("OrderDetail.reject requires at least one rejection reason")
        if self.approval_status is ApprovalStatus.APPROVED:
            raise ValueError("approved order details cannot be rejected")
        if self.approval_status is ApprovalStatus.REJECTED and self.rejection_reasons == rejection_reasons:
            return self
        return replace(
            self,
            approval_status=ApprovalStatus.REJECTED,
            rejection_reasons=rejection_reasons,
        )


@dataclass(frozen=True)
class Store:
    store_id: StoreId
    owner_user_id: UserId
    products: tuple[Product, ...]
    active: bool = True
    order_details: tuple[OrderDetail, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.store_id, StoreId):
            raise ValueError("Store.store_id must be a StoreId")
        if not isinstance(self.owner_user_id, UserId):
            raise ValueError("Store.owner_user_id must be a UserId")
        products = _coerce_products(self.products)
        if not products:
            raise ValueError("Store.products must contain at least one product")
        _validate_unique_products(products)
        object.__setattr__(self, "products", products)
        if not isinstance(self.active, bool):
            raise ValueError("Store.active must be a bool")
        object.__setattr__(self, "order_details", _coerce_order_details(self.order_details))

    def validate_owner(self, owner_user_id: UserId) -> tuple[str, ...]:
        if not isinstance(owner_user_id, UserId):
            raise ValueError("Store.validate_owner requires a UserId")
        if owner_user_id != self.owner_user_id:
            return (f"OWNER_MISMATCH: user {owner_user_id} cannot approve store {self.store_id}",)
        return ()

    def validate_order(self, order_detail: OrderDetail) -> tuple[str, ...]:
        if not isinstance(order_detail, OrderDetail):
            raise ValueError("Store.validate_order requires an OrderDetail")

        reasons: list[str] = []
        if not self.active:
            reasons.append(f"INACTIVE_STORE: store {self.store_id} is inactive")
        if order_detail.store_id != self.store_id:
            reasons.append(f"STORE_MISMATCH: order {order_detail.order_id} does not belong to store {self.store_id}")
        if order_detail.order_status != "PAID":
            reasons.append(f"ORDER_NOT_PAID: order {order_detail.order_id} is {order_detail.order_status}")

        for snapshot in order_detail.products:
            product = self.find_product(snapshot.product_id)
            if product is None:
                reasons.append(f"PRODUCT_MISMATCH: product {snapshot.product_id} is not in store {self.store_id}")
                continue
            if not product.available:
                reasons.append(f"PRODUCT_INACTIVE: product {snapshot.product_id} is inactive")
            if not product.matches_snapshot(snapshot):
                reasons.append(f"PRODUCT_MISMATCH: product {snapshot.product_id} snapshot does not match store catalog")

        if not _total_matches_snapshots(order_detail):
            reasons.append(f"TOTAL_AMOUNT_MISMATCH: order {order_detail.order_id} total does not match product snapshots")

        return tuple(reasons)

    def construct_order_approval(
        self,
        order_detail: OrderDetail,
        owner_user_id: UserId,
        decided_at: datetime | None = None,
        rejection_reason: str | None = None,
    ) -> "OrderApprovedEvent | OrderRejectedEvent":
        decided_at = _require_aware_datetime(decided_at or datetime.now(UTC), "decided_at")
        reasons = list(self.validate_owner(owner_user_id) + self.validate_order(order_detail))
        if rejection_reason is not None:
            reasons.append(f"STORE_REJECTED: {_require_text(rejection_reason, 'rejection_reason')}")

        if reasons:
            rejected = order_detail.reject(tuple(reasons))
            return OrderRejectedEvent(order=rejected, rejection_reasons=tuple(reasons), created_at=decided_at)

        approved = order_detail.approve()
        return OrderApprovedEvent(order=approved, created_at=decided_at)

    def find_product(self, product_id: ProductId) -> Product | None:
        if not isinstance(product_id, ProductId):
            raise ValueError("Store.find_product requires a ProductId")
        for product in self.products:
            if product.product_id == product_id:
                return product
        return None


@dataclass(frozen=True)
class OrderApprovedEvent:
    order: OrderDetail
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.order, OrderDetail):
            raise ValueError("OrderApprovedEvent.order must be an OrderDetail")
        if self.order.approval_status is not ApprovalStatus.APPROVED:
            raise ValueError("OrderApprovedEvent requires an APPROVED order detail")
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "OrderApprovedEvent.created_at"),
        )


@dataclass(frozen=True)
class OrderRejectedEvent:
    order: OrderDetail
    rejection_reasons: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.order, OrderDetail):
            raise ValueError("OrderRejectedEvent.order must be an OrderDetail")
        if self.order.approval_status is not ApprovalStatus.REJECTED:
            raise ValueError("OrderRejectedEvent requires a REJECTED order detail")
        reasons = tuple(_require_text(reason, "OrderRejectedEvent.rejection_reasons") for reason in self.rejection_reasons)
        if not reasons:
            raise ValueError("OrderRejectedEvent.rejection_reasons must not be empty")
        if self.order.rejection_reasons != reasons:
            raise ValueError("OrderRejectedEvent reasons must match order detail rejection reasons")
        object.__setattr__(self, "rejection_reasons", reasons)
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "OrderRejectedEvent.created_at"),
        )


StoreApprovalEvent: TypeAlias = OrderApprovedEvent | OrderRejectedEvent


def _total_matches_snapshots(order_detail: OrderDetail) -> bool:
    total = order_detail.products[0].price
    for product in order_detail.products[1:]:
        if not _same_asset(total, product.price):
            return False
        total = Crypto(
            amount=total.amount + product.price.amount,
            symbol=total.symbol,
            chain_id=total.chain_id,
            token_address=total.token_address,
            decimals=total.decimals,
        )
    return total == order_detail.total_amount


def _same_asset(left: Crypto, right: Crypto) -> bool:
    return (
        left.symbol == right.symbol
        and left.chain_id == right.chain_id
        and left.token_address == right.token_address
        and left.decimals == right.decimals
    )


def _coerce_products(values: tuple[Product, ...] | list[Product]) -> tuple[Product, ...]:
    if isinstance(values, list):
        values = tuple(values)
    if not isinstance(values, tuple):
        raise ValueError("products must be a tuple")
    if not all(isinstance(value, Product) for value in values):
        raise ValueError("products must contain only Product")
    return values


def _coerce_order_details(values: tuple[OrderDetail, ...] | list[OrderDetail]) -> tuple[OrderDetail, ...]:
    if isinstance(values, list):
        values = tuple(values)
    if not isinstance(values, tuple):
        raise ValueError("Store.order_details must be a tuple")
    if not all(isinstance(value, OrderDetail) for value in values):
        raise ValueError("Store.order_details must contain only OrderDetail")
    return values


def _validate_unique_products(products: tuple[Product, ...]) -> None:
    product_ids = [product.product_id for product in products]
    if len(set(product_ids)) != len(product_ids):
        raise ValueError("Store.products cannot contain duplicate ProductId values")


def _coerce_approval_status(value: ApprovalStatus | str) -> ApprovalStatus:
    if isinstance(value, ApprovalStatus):
        return value
    try:
        return ApprovalStatus(str(value))
    except ValueError as exc:
        raise ValueError("OrderDetail.approval_status must be an ApprovalStatus") from exc


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value

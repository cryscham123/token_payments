"""Checkout tracking read model contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from token_payments.contexts.order.domain import OrderStatus, TrackingId
from token_payments.contexts.payment.domain import (
    GasEstimate,
    Payment,
    PaymentAuthorization,
    PaymentStatus,
    TransactionSignatureRequest,
)
from token_payments.shared.domain import OrderId, OutboxPublishStatus, PaymentId, TransactionHash


class CheckoutCurrentStep(StrEnum):
    ORDER_CREATED = "ORDER_CREATED"
    AWAITING_SIGNATURE = "AWAITING_SIGNATURE"
    RECEIPT_PENDING = "RECEIPT_PENDING"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_EXPIRED = "PAYMENT_EXPIRED"
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED"
    ORDER_APPROVED = "ORDER_APPROVED"
    ORDER_CANCELLING = "ORDER_CANCELLING"
    ORDER_CANCELLED = "ORDER_CANCELLED"


class CheckoutPendingAction(StrEnum):
    WAIT_FOR_PAYMENT_REQUEST = "WAIT_FOR_PAYMENT_REQUEST"
    SIGN_PAYMENT = "SIGN_PAYMENT"
    WAIT_FOR_RECEIPT = "WAIT_FOR_RECEIPT"
    WAIT_FOR_STORE_APPROVAL = "WAIT_FOR_STORE_APPROVAL"
    WAIT_FOR_COMPENSATION = "WAIT_FOR_COMPENSATION"


@dataclass(frozen=True)
class OutboxStatusSnapshot:
    message_id: str
    name: str
    status: OutboxPublishStatus
    updated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "message_id", _require_text(self.message_id, "OutboxStatusSnapshot.message_id"))
        object.__setattr__(self, "name", _require_text(self.name, "OutboxStatusSnapshot.name"))
        if not isinstance(self.status, OutboxPublishStatus):
            object.__setattr__(self, "status", OutboxPublishStatus(self.status))
        object.__setattr__(
            self,
            "updated_at",
            _require_aware_datetime(self.updated_at, "OutboxStatusSnapshot.updated_at"),
        )


@dataclass(frozen=True)
class CheckoutTrackingSnapshot:
    order_id: OrderId
    tracking_id: TrackingId
    order_status: OrderStatus
    failure_messages: tuple[str, ...]
    payment: Payment | None
    authorization: PaymentAuthorization | None
    outbox_statuses: tuple[OutboxStatusSnapshot, ...]
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, OrderId):
            raise ValueError("CheckoutTrackingSnapshot.order_id must be an OrderId")
        if not isinstance(self.tracking_id, TrackingId):
            raise ValueError("CheckoutTrackingSnapshot.tracking_id must be a TrackingId")
        if not isinstance(self.order_status, OrderStatus):
            object.__setattr__(self, "order_status", OrderStatus(self.order_status))
        object.__setattr__(
            self,
            "failure_messages",
            tuple(_require_text(message, "CheckoutTrackingSnapshot.failure_messages") for message in self.failure_messages),
        )
        if self.payment is not None and not isinstance(self.payment, Payment):
            raise ValueError("CheckoutTrackingSnapshot.payment must be a Payment or None")
        if self.authorization is not None and not isinstance(self.authorization, PaymentAuthorization):
            raise ValueError("CheckoutTrackingSnapshot.authorization must be a PaymentAuthorization or None")
        object.__setattr__(
            self,
            "outbox_statuses",
            _coerce_tuple(self.outbox_statuses, OutboxStatusSnapshot, "CheckoutTrackingSnapshot.outbox_statuses"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _require_aware_datetime(self.updated_at, "CheckoutTrackingSnapshot.updated_at"),
        )

    @property
    def status(self) -> str:
        if self.order_status in {
            OrderStatus.PAID,
            OrderStatus.APPROVED,
            OrderStatus.CANCELLING,
            OrderStatus.CANCELLED,
        }:
            return self.order_status.value
        if self.payment is not None:
            return self.payment.status.value
        return self.order_status.value

    @property
    def payment_id(self) -> PaymentId | None:
        if self.payment is None:
            return None
        return self.payment.payment_id

    @property
    def current_step(self) -> CheckoutCurrentStep:
        if self.order_status is OrderStatus.APPROVED:
            return CheckoutCurrentStep.ORDER_APPROVED
        if self.order_status is OrderStatus.CANCELLED:
            return CheckoutCurrentStep.ORDER_CANCELLED
        if self.order_status is OrderStatus.CANCELLING:
            return CheckoutCurrentStep.ORDER_CANCELLING
        if self.payment is None:
            return CheckoutCurrentStep.ORDER_CREATED
        return {
            PaymentStatus.INITIATED: CheckoutCurrentStep.ORDER_CREATED,
            PaymentStatus.AWAITING_SIGNATURE: CheckoutCurrentStep.AWAITING_SIGNATURE,
            PaymentStatus.SUBMITTED: CheckoutCurrentStep.RECEIPT_PENDING,
            PaymentStatus.CONFIRMING: CheckoutCurrentStep.RECEIPT_PENDING,
            PaymentStatus.CONFIRMED: CheckoutCurrentStep.PAYMENT_CONFIRMED,
            PaymentStatus.FAILED: CheckoutCurrentStep.PAYMENT_FAILED,
            PaymentStatus.EXPIRED: CheckoutCurrentStep.PAYMENT_EXPIRED,
            PaymentStatus.REFUNDED: CheckoutCurrentStep.PAYMENT_REFUNDED,
        }[self.payment.status]

    @property
    def pending_action(self) -> CheckoutPendingAction | None:
        if self.current_step is CheckoutCurrentStep.ORDER_CREATED:
            return CheckoutPendingAction.WAIT_FOR_PAYMENT_REQUEST
        if self.current_step is CheckoutCurrentStep.AWAITING_SIGNATURE:
            return CheckoutPendingAction.SIGN_PAYMENT
        if self.current_step is CheckoutCurrentStep.RECEIPT_PENDING:
            return CheckoutPendingAction.WAIT_FOR_RECEIPT
        if self.current_step is CheckoutCurrentStep.PAYMENT_CONFIRMED or self.order_status is OrderStatus.PAID:
            return CheckoutPendingAction.WAIT_FOR_STORE_APPROVAL
        if self.current_step in {
            CheckoutCurrentStep.PAYMENT_FAILED,
            CheckoutCurrentStep.PAYMENT_EXPIRED,
            CheckoutCurrentStep.ORDER_CANCELLING,
        }:
            return CheckoutPendingAction.WAIT_FOR_COMPENSATION
        return None

    @property
    def payment_request(self) -> TransactionSignatureRequest | None:
        if self.authorization is not None:
            return self.authorization.signature_request
        if self.payment is None or self.payment.status is not PaymentStatus.AWAITING_SIGNATURE:
            return None
        return TransactionSignatureRequest(
            request_id=str(self.payment.payment_id),
            amount=self.payment.amount,
            to=self.payment.wallet_to,
            expires_at=self.payment.expires_at,
        )

    @property
    def gas_estimate(self) -> GasEstimate | None:
        if self.payment is None:
            return None
        return self.payment.gas_estimate

    @property
    def tx_hash(self) -> TransactionHash | None:
        if self.payment is not None and self.payment.tx_hash is not None:
            return self.payment.tx_hash
        if self.authorization is not None and self.authorization.tx_hash is not None:
            return self.authorization.tx_hash
        return None

    @property
    def failure_reason(self) -> str | None:
        if self.payment is not None and self.payment.failure_reason is not None:
            return self.payment.failure_reason
        if self.failure_messages:
            return self.failure_messages[-1]
        return None


class CheckoutTrackingQueryPort(Protocol):
    def get_by_tracking_id(self, tracking_id: TrackingId) -> CheckoutTrackingSnapshot | None:
        ...

    def get_by_order_id(self, order_id: OrderId) -> CheckoutTrackingSnapshot | None:
        ...


def _coerce_tuple(values: tuple[object, ...], item_type: type, field_name: str):
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if not all(isinstance(value, item_type) for value in values):
        raise ValueError(f"{field_name} must contain only {item_type.__name__}")
    return values


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

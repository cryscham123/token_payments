"""Framework-neutral UI view models for customer and operator screens."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


STATUS_TONES = {
    "APPROVED": "success",
    "CONFIRMED": "success",
    "COMPLETED": "success",
    "PAID": "success",
    "PUBLISHED": "success",
    "SUCCEEDED": "success",
    "SUBMITTED": "progress",
    "CONFIRMING": "progress",
    "PAYMENT_CONFIRMED": "progress",
    "PUBLISHING": "progress",
    "RECEIPT_PENDING": "progress",
    "AWAITING_SIGNATURE": "pending",
    "CANCELLING": "pending",
    "ORDER_CREATED": "pending",
    "PENDING": "pending",
    "READY": "pending",
    "REQUESTED": "pending",
    "FAILED": "danger",
    "ERROR": "danger",
    "EXPIRED": "danger",
    "PAYMENT_EXPIRED": "danger",
    "PAYMENT_FAILED": "danger",
    "REJECTED": "danger",
    "CANCELLED": "neutral",
    "DEGRADED": "neutral",
    "REFUNDED": "neutral",
}


@dataclass(frozen=True)
class StatusBadge:
    label: str
    tone: str | None = None

    def __post_init__(self) -> None:
        label = _require_text(self.label, "StatusBadge.label")
        tone = self.tone or STATUS_TONES.get(label.upper(), "neutral")
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "tone", _require_text(tone, "StatusBadge.tone"))


@dataclass(frozen=True)
class MoneyView:
    amount: str
    symbol: str
    chain_id: int | None = None
    token_address: str | None = None
    decimals: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", _require_text(str(self.amount), "MoneyView.amount"))
        object.__setattr__(self, "symbol", _require_text(self.symbol, "MoneyView.symbol"))
        if self.chain_id is not None:
            object.__setattr__(self, "chain_id", _require_positive_int(self.chain_id, "MoneyView.chain_id"))
        if self.token_address is not None:
            object.__setattr__(self, "token_address", _require_text(self.token_address, "MoneyView.token_address"))
        if self.decimals is not None:
            object.__setattr__(self, "decimals", _require_non_negative_int(self.decimals, "MoneyView.decimals"))

    @property
    def display(self) -> str:
        return f"{self.amount} {self.symbol}"


@dataclass(frozen=True)
class GasEstimateView:
    estimated_fee: MoneyView
    gas_limit: int
    buffer_rate: str
    max_fee: MoneyView | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.estimated_fee, MoneyView):
            raise ValueError("GasEstimateView.estimated_fee must be a MoneyView")
        object.__setattr__(self, "gas_limit", _require_positive_int(self.gas_limit, "GasEstimateView.gas_limit"))
        object.__setattr__(self, "buffer_rate", _require_text(str(self.buffer_rate), "GasEstimateView.buffer_rate"))
        if self.max_fee is not None and not isinstance(self.max_fee, MoneyView):
            raise ValueError("GasEstimateView.max_fee must be a MoneyView or None")


@dataclass(frozen=True)
class CopyToken:
    value: str
    label: str = "identifier"

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _require_text(self.value, "CopyToken.value"))
        object.__setattr__(self, "label", _require_text(self.label, "CopyToken.label"))


@dataclass(frozen=True)
class CheckoutTimelineItem:
    label: str
    status: StatusBadge | str
    message_id: str | None = None
    occurred_at: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _require_text(self.label, "CheckoutTimelineItem.label"))
        if not isinstance(self.status, StatusBadge):
            object.__setattr__(self, "status", StatusBadge(str(self.status)))
        if self.message_id is not None:
            object.__setattr__(self, "message_id", _require_text(self.message_id, "CheckoutTimelineItem.message_id"))
        if self.occurred_at is not None:
            object.__setattr__(self, "occurred_at", _require_text(self.occurred_at, "CheckoutTimelineItem.occurred_at"))
        if self.detail is not None:
            object.__setattr__(self, "detail", _require_text(self.detail, "CheckoutTimelineItem.detail"))


@dataclass(frozen=True)
class CheckoutViewModel:
    order_id: str
    tracking_id: str
    status: StatusBadge | str
    current_step: str
    pending_action: str | None = None
    wallet_address: str | None = None
    network_label: str | None = None
    chain_id: int | None = None
    token_amount: MoneyView | None = None
    gas_estimate: GasEstimateView | None = None
    payment_expires_at: str | None = None
    receiver_wallet: str | None = None
    tx_hash: str | None = None
    failure_reason: str | None = None
    timeline: tuple[CheckoutTimelineItem, ...] = ()
    updated_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "order_id", _require_text(self.order_id, "CheckoutViewModel.order_id"))
        object.__setattr__(self, "tracking_id", _require_text(self.tracking_id, "CheckoutViewModel.tracking_id"))
        if not isinstance(self.status, StatusBadge):
            object.__setattr__(self, "status", StatusBadge(str(self.status)))
        object.__setattr__(self, "current_step", _require_text(self.current_step, "CheckoutViewModel.current_step"))
        for field_name in (
            "pending_action",
            "wallet_address",
            "network_label",
            "payment_expires_at",
            "receiver_wallet",
            "tx_hash",
            "failure_reason",
            "updated_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _require_text(value, f"CheckoutViewModel.{field_name}"))
        if self.chain_id is not None:
            object.__setattr__(self, "chain_id", _require_positive_int(self.chain_id, "CheckoutViewModel.chain_id"))
        if self.token_amount is not None and not isinstance(self.token_amount, MoneyView):
            raise ValueError("CheckoutViewModel.token_amount must be a MoneyView or None")
        if self.gas_estimate is not None and not isinstance(self.gas_estimate, GasEstimateView):
            raise ValueError("CheckoutViewModel.gas_estimate must be a GasEstimateView or None")
        object.__setattr__(self, "timeline", _coerce_tuple(self.timeline, CheckoutTimelineItem, "CheckoutViewModel.timeline"))


@dataclass(frozen=True)
class OperatorFilterState:
    contexts: tuple[str, ...] = ("orders", "payments", "outbox")
    statuses: tuple[str, ...] = ()
    chain_id: int | None = None
    store_id: str | None = None
    failed_only: bool = False
    retry_candidates_only: bool = False
    sort: str = "-updatedAt"

    def __post_init__(self) -> None:
        object.__setattr__(self, "contexts", tuple(_require_text(value, "OperatorFilterState.contexts") for value in self.contexts))
        object.__setattr__(self, "statuses", tuple(_require_text(value, "OperatorFilterState.statuses") for value in self.statuses))
        if self.chain_id is not None:
            object.__setattr__(self, "chain_id", _require_positive_int(self.chain_id, "OperatorFilterState.chain_id"))
        if self.store_id is not None:
            object.__setattr__(self, "store_id", _require_text(self.store_id, "OperatorFilterState.store_id"))
        if not isinstance(self.failed_only, bool):
            raise ValueError("OperatorFilterState.failed_only must be a bool")
        if not isinstance(self.retry_candidates_only, bool):
            raise ValueError("OperatorFilterState.retry_candidates_only must be a bool")
        object.__setattr__(self, "sort", _require_text(self.sort, "OperatorFilterState.sort"))


@dataclass(frozen=True)
class OperatorTableRow:
    resource: str
    identity: str
    status: StatusBadge | str
    primary: str
    secondary: str | None = None
    amount: MoneyView | None = None
    chain_id: int | None = None
    updated_at: str | None = None
    failure_reason: str | None = None
    latest_event: str | None = None
    tx_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource", _require_text(self.resource, "OperatorTableRow.resource"))
        object.__setattr__(self, "identity", _require_text(self.identity, "OperatorTableRow.identity"))
        if not isinstance(self.status, StatusBadge):
            object.__setattr__(self, "status", StatusBadge(str(self.status)))
        object.__setattr__(self, "primary", _require_text(self.primary, "OperatorTableRow.primary"))
        for field_name in ("secondary", "updated_at", "failure_reason", "latest_event", "tx_hash"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _require_text(value, f"OperatorTableRow.{field_name}"))
        if self.amount is not None and not isinstance(self.amount, MoneyView):
            raise ValueError("OperatorTableRow.amount must be a MoneyView or None")
        if self.chain_id is not None:
            object.__setattr__(self, "chain_id", _require_positive_int(self.chain_id, "OperatorTableRow.chain_id"))
        object.__setattr__(self, "metadata", _readonly_mapping(self.metadata, "OperatorTableRow.metadata"))


@dataclass(frozen=True)
class OperatorDetailView:
    title: str
    fields: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _require_text(self.title, "OperatorDetailView.title"))
        object.__setattr__(self, "fields", _readonly_mapping(self.fields, "OperatorDetailView.fields"))


@dataclass(frozen=True)
class OperatorDashboardViewModel:
    filters: OperatorFilterState = field(default_factory=OperatorFilterState)
    orders: tuple[OperatorTableRow, ...] = ()
    payments: tuple[OperatorTableRow, ...] = ()
    outbox: tuple[OperatorTableRow, ...] = ()
    workers: tuple[OperatorTableRow, ...] = ()
    errors: tuple[OperatorTableRow, ...] = ()
    detail: OperatorDetailView | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.filters, OperatorFilterState):
            raise ValueError("OperatorDashboardViewModel.filters must be an OperatorFilterState")
        object.__setattr__(self, "orders", _coerce_tuple(self.orders, OperatorTableRow, "OperatorDashboardViewModel.orders"))
        object.__setattr__(self, "payments", _coerce_tuple(self.payments, OperatorTableRow, "OperatorDashboardViewModel.payments"))
        object.__setattr__(self, "outbox", _coerce_tuple(self.outbox, OperatorTableRow, "OperatorDashboardViewModel.outbox"))
        object.__setattr__(self, "workers", _coerce_tuple(self.workers, OperatorTableRow, "OperatorDashboardViewModel.workers"))
        object.__setattr__(self, "errors", _coerce_tuple(self.errors, OperatorTableRow, "OperatorDashboardViewModel.errors"))
        if self.detail is not None and not isinstance(self.detail, OperatorDetailView):
            raise ValueError("OperatorDashboardViewModel.detail must be an OperatorDetailView or None")


@dataclass(frozen=True)
class RenderedHtml:
    html: str
    content_type: str = "text/html; charset=utf-8"

    def __post_init__(self) -> None:
        object.__setattr__(self, "html", _require_text(self.html, "RenderedHtml.html"))
        object.__setattr__(self, "content_type", _require_text(self.content_type, "RenderedHtml.content_type"))


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _coerce_tuple(values: tuple[object, ...], item_type: type, field_name: str):
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if not all(isinstance(value, item_type) for value in values):
        raise ValueError(f"{field_name} must contain only {item_type.__name__}")
    return values


def _readonly_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    output: dict[str, Any] = {}
    for key, item in value.items():
        output[_require_text(str(key), f"{field_name} key")] = item
    return MappingProxyType(output)


__all__ = [
    "CheckoutTimelineItem",
    "CheckoutViewModel",
    "CopyToken",
    "GasEstimateView",
    "MoneyView",
    "OperatorDashboardViewModel",
    "OperatorDetailView",
    "OperatorFilterState",
    "OperatorTableRow",
    "RenderedHtml",
    "StatusBadge",
]

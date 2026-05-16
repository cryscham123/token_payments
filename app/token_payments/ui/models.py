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
    "OK": "success",
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
    "INVENTORY_RESERVED": "success",
    "ORDER_APPROVED": "success",
    "STORE_APPROVAL": "pending",
    "TX_SUBMITTED": "progress",
    "FAILED": "danger",
    "ERROR": "danger",
    "EXPIRED": "danger",
    "PAYMENT_EXPIRED": "danger",
    "PAYMENT_FAILED": "danger",
    "REJECTED": "danger",
    "UNAVAILABLE": "danger",
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
class CheckoutOrderItemView:
    product_id: str
    name: str
    quantity: int
    unit_price: MoneyView
    sub_total: MoneyView

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", _require_text(self.product_id, "CheckoutOrderItemView.product_id"))
        object.__setattr__(self, "name", _require_text(self.name, "CheckoutOrderItemView.name"))
        object.__setattr__(self, "quantity", _require_positive_int(self.quantity, "CheckoutOrderItemView.quantity"))
        if not isinstance(self.unit_price, MoneyView):
            raise ValueError("CheckoutOrderItemView.unit_price must be a MoneyView")
        if not isinstance(self.sub_total, MoneyView):
            raise ValueError("CheckoutOrderItemView.sub_total must be a MoneyView")


@dataclass(frozen=True)
class CheckoutAction:
    action_id: str
    label: str
    kind: str = "secondary"
    enabled: bool = True
    tooltip: str | None = None
    aria_label: str | None = None
    disabled_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", _require_text(self.action_id, "CheckoutAction.action_id"))
        object.__setattr__(self, "label", _require_text(self.label, "CheckoutAction.label"))
        kind = _require_text(self.kind, "CheckoutAction.kind")
        if kind not in {"primary", "secondary", "danger"}:
            raise ValueError("CheckoutAction.kind must be primary, secondary, or danger")
        object.__setattr__(self, "kind", kind)
        if not isinstance(self.enabled, bool):
            raise ValueError("CheckoutAction.enabled must be a bool")
        for field_name in ("tooltip", "aria_label", "disabled_reason"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _require_text(value, f"CheckoutAction.{field_name}"))


@dataclass(frozen=True)
class OperatorActionIntent:
    action_id: str
    label: str
    kind: str
    method: str
    endpoint: str
    operation_id: str
    target_kind: str
    target_id: str
    reason: str
    enabled: bool
    confirmation: str
    idempotency_key: str
    body_template: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", _require_text(self.action_id, "OperatorActionIntent.action_id"))
        object.__setattr__(self, "label", _require_text(self.label, "OperatorActionIntent.label"))
        kind = _require_text(self.kind, "OperatorActionIntent.kind")
        if kind not in {"primary", "secondary", "danger"}:
            raise ValueError("OperatorActionIntent.kind must be primary, secondary, or danger")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "method", _require_text(self.method, "OperatorActionIntent.method").upper())
        object.__setattr__(
            self,
            "endpoint",
            _require_endpoint_path(self.endpoint, "OperatorActionIntent.endpoint"),
        )
        object.__setattr__(
            self,
            "operation_id",
            _require_text(self.operation_id, "OperatorActionIntent.operation_id"),
        )
        object.__setattr__(self, "target_kind", _require_text(self.target_kind, "OperatorActionIntent.target_kind"))
        object.__setattr__(self, "target_id", _require_text(self.target_id, "OperatorActionIntent.target_id"))
        object.__setattr__(self, "reason", _require_text(self.reason, "OperatorActionIntent.reason"))
        if not isinstance(self.enabled, bool):
            raise ValueError("OperatorActionIntent.enabled must be a bool")
        object.__setattr__(
            self,
            "confirmation",
            _require_text(self.confirmation, "OperatorActionIntent.confirmation"),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _require_text(self.idempotency_key, "OperatorActionIntent.idempotency_key"),
        )
        body_template = _readonly_json_mapping(self.body_template, "OperatorActionIntent.body_template")
        if body_template.get("reason") != self.reason:
            raise ValueError("OperatorActionIntent.body_template must include matching reason")
        if body_template.get("idempotencyKey") != self.idempotency_key:
            raise ValueError("OperatorActionIntent.body_template must include matching idempotencyKey")
        parameters = body_template.get("parameters")
        if not isinstance(parameters, Mapping) or parameters.get("source") != "operator-dashboard":
            raise ValueError(
                "OperatorActionIntent.body_template must include parameters.source=operator-dashboard"
            )
        object.__setattr__(self, "body_template", body_template)


@dataclass(frozen=True)
class CheckoutTimelineItem:
    label: str
    status: StatusBadge | str
    stage: str | None = None
    message_id: str | None = None
    command_id: str | None = None
    occurred_at: str | None = None
    detail: str | None = None
    compensation_status: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _require_text(self.label, "CheckoutTimelineItem.label"))
        if not isinstance(self.status, StatusBadge):
            object.__setattr__(self, "status", StatusBadge(str(self.status)))
        for field_name in ("stage", "message_id", "command_id", "occurred_at", "detail", "compensation_status"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _require_text(value, f"CheckoutTimelineItem.{field_name}"))


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
    payment_expires_in: str | None = None
    receiver_wallet: str | None = None
    tx_hash: str | None = None
    tx_hash_status: StatusBadge | str | None = None
    failure_reason: str | None = None
    order_items: tuple[CheckoutOrderItemView, ...] = ()
    actions: tuple[CheckoutAction, ...] = ()
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
            "payment_expires_in",
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
        if self.tx_hash_status is not None and not isinstance(self.tx_hash_status, StatusBadge):
            object.__setattr__(self, "tx_hash_status", StatusBadge(str(self.tx_hash_status)))
        object.__setattr__(self, "order_items", _coerce_tuple(self.order_items, CheckoutOrderItemView, "CheckoutViewModel.order_items"))
        object.__setattr__(self, "actions", _coerce_tuple(self.actions, CheckoutAction, "CheckoutViewModel.actions"))
        object.__setattr__(self, "timeline", _coerce_tuple(self.timeline, CheckoutTimelineItem, "CheckoutViewModel.timeline"))


@dataclass(frozen=True)
class OperatorFilterState:
    contexts: tuple[str, ...] = ("orders", "payments", "inventory", "store-approvals", "outbox", "workers", "errors")
    statuses: tuple[str, ...] = ()
    chain_id: int | None = None
    store_id: str | None = None
    created_at_from: str | None = None
    created_at_to: str | None = None
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
        for field_name in ("created_at_from", "created_at_to"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _require_text(value, f"OperatorFilterState.{field_name}"))
        if not isinstance(self.failed_only, bool):
            raise ValueError("OperatorFilterState.failed_only must be a bool")
        if not isinstance(self.retry_candidates_only, bool):
            raise ValueError("OperatorFilterState.retry_candidates_only must be a bool")
        object.__setattr__(self, "sort", _require_text(self.sort, "OperatorFilterState.sort"))


@dataclass(frozen=True)
class OperatorSummaryItem:
    key: str
    label: str
    value: int
    status: StatusBadge | str
    detail: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _require_text(self.key, "OperatorSummaryItem.key"))
        object.__setattr__(self, "label", _require_text(self.label, "OperatorSummaryItem.label"))
        object.__setattr__(self, "value", _require_non_negative_int(self.value, "OperatorSummaryItem.value"))
        if not isinstance(self.status, StatusBadge):
            object.__setattr__(self, "status", StatusBadge(str(self.status)))
        if self.detail is not None:
            object.__setattr__(self, "detail", _require_text(self.detail, "OperatorSummaryItem.detail"))


@dataclass(frozen=True)
class OperatorTableRow:
    resource: str
    identity: str
    status: StatusBadge | str
    primary: str
    secondary: str | None = None
    amount: MoneyView | None = None
    quantity: int | None = None
    gas: MoneyView | None = None
    chain_id: int | None = None
    store_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    failure_reason: str | None = None
    latest_event: str | None = None
    tx_hash: str | None = None
    retry_candidate: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource", _require_text(self.resource, "OperatorTableRow.resource"))
        object.__setattr__(self, "identity", _require_text(self.identity, "OperatorTableRow.identity"))
        if not isinstance(self.status, StatusBadge):
            object.__setattr__(self, "status", StatusBadge(str(self.status)))
        object.__setattr__(self, "primary", _require_text(self.primary, "OperatorTableRow.primary"))
        for field_name in ("secondary", "store_id", "created_at", "updated_at", "failure_reason", "latest_event", "tx_hash"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _require_text(value, f"OperatorTableRow.{field_name}"))
        if self.amount is not None and not isinstance(self.amount, MoneyView):
            raise ValueError("OperatorTableRow.amount must be a MoneyView or None")
        if self.quantity is not None:
            object.__setattr__(self, "quantity", _require_non_negative_int(self.quantity, "OperatorTableRow.quantity"))
        if self.gas is not None and not isinstance(self.gas, MoneyView):
            raise ValueError("OperatorTableRow.gas must be a MoneyView or None")
        if self.chain_id is not None:
            object.__setattr__(self, "chain_id", _require_positive_int(self.chain_id, "OperatorTableRow.chain_id"))
        if not isinstance(self.retry_candidate, bool):
            raise ValueError("OperatorTableRow.retry_candidate must be a bool")
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
    summary: tuple[OperatorSummaryItem, ...] = ()
    orders: tuple[OperatorTableRow, ...] = ()
    payments: tuple[OperatorTableRow, ...] = ()
    inventory: tuple[OperatorTableRow, ...] = ()
    store_approvals: tuple[OperatorTableRow, ...] = ()
    outbox: tuple[OperatorTableRow, ...] = ()
    workers: tuple[OperatorTableRow, ...] = ()
    errors: tuple[OperatorTableRow, ...] = ()
    actions: tuple[OperatorActionIntent, ...] = ()
    detail: OperatorDetailView | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.filters, OperatorFilterState):
            raise ValueError("OperatorDashboardViewModel.filters must be an OperatorFilterState")
        object.__setattr__(self, "summary", _coerce_tuple(self.summary, OperatorSummaryItem, "OperatorDashboardViewModel.summary"))
        object.__setattr__(self, "orders", _coerce_tuple(self.orders, OperatorTableRow, "OperatorDashboardViewModel.orders"))
        object.__setattr__(self, "payments", _coerce_tuple(self.payments, OperatorTableRow, "OperatorDashboardViewModel.payments"))
        object.__setattr__(self, "inventory", _coerce_tuple(self.inventory, OperatorTableRow, "OperatorDashboardViewModel.inventory"))
        object.__setattr__(self, "store_approvals", _coerce_tuple(self.store_approvals, OperatorTableRow, "OperatorDashboardViewModel.store_approvals"))
        object.__setattr__(self, "outbox", _coerce_tuple(self.outbox, OperatorTableRow, "OperatorDashboardViewModel.outbox"))
        object.__setattr__(self, "workers", _coerce_tuple(self.workers, OperatorTableRow, "OperatorDashboardViewModel.workers"))
        object.__setattr__(self, "errors", _coerce_tuple(self.errors, OperatorTableRow, "OperatorDashboardViewModel.errors"))
        object.__setattr__(self, "actions", _coerce_tuple(self.actions, OperatorActionIntent, "OperatorDashboardViewModel.actions"))
        if self.detail is not None and not isinstance(self.detail, OperatorDetailView):
            raise ValueError("OperatorDashboardViewModel.detail must be an OperatorDetailView or None")

    @property
    def primary_rows(self) -> tuple[OperatorTableRow, ...]:
        return self.orders + self.payments + self.inventory + self.store_approvals + self.outbox + self.errors

    @property
    def all_rows(self) -> tuple[OperatorTableRow, ...]:
        return self.primary_rows + self.workers


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


def _require_endpoint_path(value: str, field_name: str) -> str:
    endpoint = _require_text(value, field_name)
    if not endpoint.startswith("/") or endpoint.startswith("//") or "://" in endpoint:
        raise ValueError(f"{field_name} must be an absolute path without origin")
    return endpoint


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


class _FrozenJsonMapping(dict):
    def _readonly(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("mapping is read-only")

    __setitem__ = _readonly
    __delitem__ = _readonly
    clear = _readonly
    pop = _readonly
    popitem = _readonly
    setdefault = _readonly
    update = _readonly
    __ior__ = _readonly

    def copy(self) -> dict[str, Any]:
        return dict(self)


def _readonly_json_mapping(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return _freeze_json_value(value, field_name)


def _freeze_json_value(value: object, field_name: str) -> Any:
    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError(f"{field_name} must contain only finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        return _FrozenJsonMapping(
            {
                _require_text(str(key), f"{field_name} key"): _freeze_json_value(item, f"{field_name}.{key}")
                for key, item in value.items()
            }
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze_json_value(item, f"{field_name}[]") for item in value)
    raise ValueError(f"{field_name} must contain only JSON primitive values")


__all__ = [
    "CheckoutAction",
    "CheckoutOrderItemView",
    "CheckoutTimelineItem",
    "CheckoutViewModel",
    "CopyToken",
    "GasEstimateView",
    "MoneyView",
    "OperatorActionIntent",
    "OperatorDashboardViewModel",
    "OperatorDetailView",
    "OperatorFilterState",
    "OperatorSummaryItem",
    "OperatorTableRow",
    "RenderedHtml",
    "StatusBadge",
]

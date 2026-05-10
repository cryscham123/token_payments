"""Customer and operator UI contracts built on framework-neutral API payloads."""

from .mappers import checkout_view_from_api_payload, operator_dashboard_from_api_payload
from .models import (
    CheckoutAction,
    CheckoutOrderItemView,
    CheckoutTimelineItem,
    CheckoutViewModel,
    CopyToken,
    GasEstimateView,
    MoneyView,
    OperatorDashboardViewModel,
    OperatorDetailView,
    OperatorFilterState,
    OperatorSummaryItem,
    OperatorTableRow,
    RenderedHtml,
    StatusBadge,
)
from .preview import (
    AVAILABLE_UI_PREVIEW_VIEWS,
    UI_PREVIEW_CONTRACT,
    UNKNOWN_UI_PREVIEW_ERROR,
    UnknownUiPreviewView,
    render_ui_preview,
)
from .renderers import render_checkout_page, render_operator_dashboard, render_status_badge

__all__ = [
    "AVAILABLE_UI_PREVIEW_VIEWS",
    "CheckoutAction",
    "CheckoutOrderItemView",
    "CheckoutTimelineItem",
    "CheckoutViewModel",
    "CopyToken",
    "GasEstimateView",
    "MoneyView",
    "OperatorDashboardViewModel",
    "OperatorDetailView",
    "OperatorFilterState",
    "OperatorSummaryItem",
    "OperatorTableRow",
    "RenderedHtml",
    "StatusBadge",
    "UI_PREVIEW_CONTRACT",
    "UNKNOWN_UI_PREVIEW_ERROR",
    "UnknownUiPreviewView",
    "checkout_view_from_api_payload",
    "operator_dashboard_from_api_payload",
    "render_checkout_page",
    "render_operator_dashboard",
    "render_status_badge",
    "render_ui_preview",
]

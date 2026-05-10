"""Standard-library HTML renderers for Token Payments UI view models."""

from __future__ import annotations

from html import escape
from typing import Any, Iterable, Mapping

from .models import (
    CheckoutAction,
    CheckoutOrderItemView,
    CheckoutTimelineItem,
    CheckoutViewModel,
    CopyToken,
    MoneyView,
    OperatorDashboardViewModel,
    OperatorDetailView,
    OperatorFilterState,
    OperatorSummaryItem,
    OperatorTableRow,
    RenderedHtml,
    StatusBadge,
)


DEFAULT_CSS = """
:root {
  color-scheme: light;
  --tp-page: #f7f8fa;
  --tp-surface: #ffffff;
  --tp-surface-muted: #eef1f4;
  --tp-border: #d5dbe3;
  --tp-panel-dark: #111827;
  --tp-text: #111827;
  --tp-body: #374151;
  --tp-muted: #6b7280;
  --tp-disabled: #9ca3af;
  --tp-success: #15803d;
  --tp-progress: #2563eb;
  --tp-pending: #b45309;
  --tp-danger: #b91c1c;
  --tp-neutral: #475569;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--tp-page);
  color: var(--tp-text);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
  line-height: 1.5;
}

.tp-shell {
  width: min(100%, 1180px);
  margin: 0 auto;
  padding: 24px;
}

.tp-checkout {
  max-width: 960px;
}

.tp-operator {
  width: 100%;
  max-width: none;
}

.tp-page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.tp-title {
  margin: 0;
  font-size: 28px;
  font-weight: 650;
  letter-spacing: 0;
}

.tp-section-title {
  margin: 0 0 10px;
  font-size: 18px;
  font-weight: 650;
  letter-spacing: 0;
}

.tp-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
  gap: 16px;
  align-items: start;
}

.tp-order-panel {
  order: 1;
}

.tp-payment-panel {
  order: 2;
}

.tp-operator-layout {
  display: grid;
  grid-template-columns: minmax(180px, 240px) minmax(0, 1fr) minmax(240px, 320px);
  gap: 16px;
  align-items: start;
}

.tp-panel {
  background: var(--tp-surface);
  border: 1px solid var(--tp-border);
  border-radius: 8px;
  padding: 16px;
}

.tp-panel-dark {
  background: var(--tp-panel-dark);
  border-color: var(--tp-panel-dark);
  color: #f9fafb;
}

.tp-stack {
  display: grid;
  gap: 12px;
}

.tp-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.tp-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.tp-summary-item {
  min-width: 0;
  border: 1px solid var(--tp-border);
  border-radius: 8px;
  background: var(--tp-surface);
  padding: 10px;
}

.tp-summary-value {
  display: block;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 22px;
  font-weight: 650;
  line-height: 1.2;
}

.tp-field {
  min-width: 0;
}

.tp-field-amount .tp-value,
.tp-field-gas .tp-value,
.tp-value-num {
  text-align: right;
}

.tp-label {
  display: block;
  color: var(--tp-muted);
  font-size: 12px;
  font-weight: 600;
}

.tp-value {
  display: block;
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--tp-body);
}

.tp-money {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 15px;
  font-weight: 600;
  text-align: right;
}

.tp-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.tp-copy {
  display: inline-grid;
  grid-template-columns: minmax(0, 1fr) 36px;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}

.tp-copy-value {
  min-width: 0;
}

.tp-button,
.tp-icon-button {
  border: 1px solid var(--tp-border);
  border-radius: 6px;
  background: var(--tp-surface);
  color: var(--tp-text);
  font: inherit;
  min-height: 36px;
  overflow-wrap: anywhere;
}

.tp-button-primary {
  background: var(--tp-text);
  color: #ffffff;
  border-color: var(--tp-text);
}

.tp-button-danger {
  background: var(--tp-danger);
  color: #ffffff;
  border-color: var(--tp-danger);
}

.tp-icon-button {
  width: 36px;
  height: 36px;
  padding: 0;
}

.tp-button:disabled {
  color: var(--tp-disabled);
  background: var(--tp-surface-muted);
  border-color: var(--tp-border);
  cursor: not-allowed;
}

.tp-action-list {
  display: grid;
  gap: 8px;
}

.tp-action-note {
  color: var(--tp-muted);
  font-size: 12px;
}

.tp-line-items {
  display: grid;
  gap: 8px;
}

.tp-line-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  min-height: 44px;
  align-items: center;
  border-bottom: 1px solid var(--tp-border);
  padding: 8px 0;
}

.tp-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 24px;
  max-width: 100%;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid currentColor;
  font-size: 12px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.tp-badge[data-tone="success"] {
  color: var(--tp-success);
  background: #ecfdf3;
}

.tp-badge[data-tone="progress"] {
  color: var(--tp-progress);
  background: #eff6ff;
}

.tp-badge[data-tone="pending"] {
  color: var(--tp-pending);
  background: #fffbeb;
}

.tp-badge[data-tone="danger"] {
  color: var(--tp-danger);
  background: #fef2f2;
}

.tp-badge[data-tone="neutral"] {
  color: var(--tp-neutral);
  background: var(--tp-surface-muted);
}

.tp-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--tp-border);
  border-radius: 8px;
  background: var(--tp-surface);
}

.tp-table {
  width: 100%;
  min-width: 980px;
  border-collapse: collapse;
  table-layout: fixed;
}

.tp-table th {
  height: 36px;
  padding: 0 10px;
  color: var(--tp-muted);
  font-size: 12px;
  font-weight: 600;
  text-align: left;
  border-bottom: 1px solid var(--tp-border);
}

.tp-table tr {
  height: 48px;
}

.tp-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--tp-border);
  vertical-align: middle;
  overflow-wrap: anywhere;
}

.tp-table .tp-num {
  text-align: right;
}

.tp-operator-empty {
  border: 1px dashed var(--tp-border);
  border-radius: 8px;
  background: var(--tp-surface);
  color: var(--tp-muted);
  padding: 14px;
}

.tp-readonly-note {
  color: var(--tp-muted);
  font-size: 12px;
}

.tp-timeline {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tp-timeline-item {
  min-height: 52px;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 8px 0;
  border-bottom: 1px solid var(--tp-border);
}

.tp-timeline-dot {
  width: 14px;
  height: 14px;
  margin: 5px;
  border-radius: 999px;
  background: var(--tp-neutral);
}

.tp-timeline-item[data-tone="success"] .tp-timeline-dot {
  background: var(--tp-success);
}

.tp-timeline-item[data-tone="progress"] .tp-timeline-dot {
  background: var(--tp-progress);
}

.tp-timeline-item[data-tone="pending"] .tp-timeline-dot {
  background: var(--tp-pending);
}

.tp-timeline-item[data-tone="danger"] .tp-timeline-dot {
  background: var(--tp-danger);
}

.tp-filter-list,
.tp-detail-list {
  display: grid;
  gap: 8px;
  margin: 0;
}

.tp-filter-list div,
.tp-detail-list div {
  min-width: 0;
}

@media (max-width: 860px) {
  .tp-shell {
    padding: 16px;
  }

  .tp-layout,
  .tp-operator-layout {
    grid-template-columns: 1fr;
  }

  .tp-payment-panel {
    order: 1;
  }

  .tp-order-panel {
    order: 2;
  }

  .tp-metrics {
    grid-template-columns: 1fr;
  }

  .tp-summary-grid {
    grid-template-columns: 1fr;
  }
}
""".strip()


SECRET_KEY_MARKERS = ("privatekey", "private_key", "seed", "mnemonic", "secret", "apikey", "api_key")


def render_checkout_page(view: CheckoutViewModel) -> RenderedHtml:
    if not isinstance(view, CheckoutViewModel):
        raise ValueError("render_checkout_page requires a CheckoutViewModel")

    action = view.pending_action or "WAITING"
    body = f"""
<main class="tp-shell tp-checkout" data-view="checkout">
  <header class="tp-page-head">
    <div>
      <h1 class="tp-title">Checkout</h1>
      <span class="tp-value">Order {_copy_html(view.order_id, "order id")}</span>
    </div>
    {render_status_badge(view.status)}
  </header>
  <section class="tp-layout">
    <aside class="tp-panel tp-panel-dark tp-payment-panel">
      <h2 class="tp-section-title">Payment</h2>
      <div class="tp-stack">
        <div class="tp-metrics">
          {_field_html("Tracking", _copy_html(view.tracking_id, "tracking id"))}
          {_field_html("Wallet", _copy_html(view.wallet_address, "wallet address") if view.wallet_address else "not connected")}
          {_field_html("Network", _network_html(view))}
          {_field_html("Amount", _money_html(view.token_amount), "amount", numeric=True)}
          {_field_html("Receiver", _copy_html(view.receiver_wallet, "receiver wallet") if view.receiver_wallet else "pending")}
          {_field_html("Expires", _esc(view.payment_expires_at or "pending"))}
          {_field_html("Countdown", _esc(view.payment_expires_in or "pending"))}
          {_field_html("Gas estimate", _gas_html(view), "gas", numeric=True)}
          {_field_html("txHash", _copy_html(view.tx_hash, "tx hash") if view.tx_hash else "not submitted")}
          {_field_html("txHash status", render_status_badge(view.tx_hash_status) if view.tx_hash_status else "not submitted")}
        </div>
        {_failure_html(view.failure_reason)}
        {_field_html("Current step", render_status_badge(view.current_step))}
        {_field_html("Pending action", _esc(action))}
        {_field_html("Updated", _esc(view.updated_at or "pending"))}
        {_actions_html(view.actions)}
      </div>
    </aside>
    <div class="tp-stack tp-order-panel">
      <section class="tp-panel">
        <h2 class="tp-section-title">Order</h2>
        {_line_items_html(view.order_items)}
      </section>
      <section class="tp-panel">
        <h2 class="tp-section-title">Timeline</h2>
        {_timeline_html(view.timeline)}
      </section>
    </div>
  </section>
</main>
"""
    return RenderedHtml(_document("Token Payments Checkout", body))


def render_operator_dashboard(view: OperatorDashboardViewModel) -> RenderedHtml:
    if not isinstance(view, OperatorDashboardViewModel):
        raise ValueError("render_operator_dashboard requires an OperatorDashboardViewModel")

    body = f"""
<main class="tp-shell tp-operator" data-view="operator">
  <header class="tp-page-head">
    <div>
      <h1 class="tp-title">Operator Dashboard</h1>
      <span class="tp-value">Orders, payments, inventory, store approvals, outbox, workers, errors</span>
      <span class="tp-readonly-note">read-only observability; retry candidates are displayed only</span>
    </div>
    {render_status_badge(_operator_surface_status(view))}
  </header>
  <section class="tp-operator-layout">
    <aside class="tp-panel">
      <h2 class="tp-section-title">Filters</h2>
      {_filters_html(view.filters)}
    </aside>
    <div class="tp-stack">
      {_summary_html(view.summary)}
      {_empty_operator_html(view.primary_rows)}
      {_table_html("Operational status", view.primary_rows)}
      {_table_html("Worker health", view.workers)}
    </div>
    <aside class="tp-panel">
      {_detail_html(view.detail)}
    </aside>
  </section>
</main>
"""
    return RenderedHtml(_document("Token Payments Operator", body))


def render_status_badge(status: StatusBadge | str) -> str:
    badge = status if isinstance(status, StatusBadge) else StatusBadge(status)
    return f'<span class="tp-badge" data-tone="{_esc(badge.tone)}">{_esc(badge.label)}</span>'


def _document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(title)}</title>
  <style>{DEFAULT_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


def _filters_html(filters: OperatorFilterState) -> str:
    fields = {
        "Contexts": ", ".join(filters.contexts),
        "Statuses": ", ".join(filters.statuses) if filters.statuses else "all",
        "Chain": str(filters.chain_id) if filters.chain_id is not None else "all",
        "Store": filters.store_id or "all",
        "Created from": filters.created_at_from or "all",
        "Created to": filters.created_at_to or "all",
        "Failed only": str(filters.failed_only),
        "Retry candidates": str(filters.retry_candidates_only),
        "Sort": filters.sort,
    }
    return _definition_html(fields, "tp-filter-list")


def _summary_html(items: tuple[OperatorSummaryItem, ...]) -> str:
    if not items:
        return ""
    rendered = "".join(_summary_item_html(item) for item in items)
    return f'<section class="tp-summary-grid" aria-label="Operator status summary">{rendered}</section>'


def _summary_item_html(item: OperatorSummaryItem) -> str:
    detail = f'<span class="tp-label">{_esc(item.detail)}</span>' if item.detail else ""
    return f"""
<div class="tp-summary-item" data-summary-key="{_esc(item.key)}">
  <span class="tp-label">{_esc(item.label)}</span>
  <span class="tp-summary-value">{_esc(item.value)}</span>
  {render_status_badge(item.status)}
  {detail}
</div>
"""


def _empty_operator_html(rows: tuple[OperatorTableRow, ...]) -> str:
    if rows:
        return ""
    return '<div class="tp-operator-empty">No operator rows match these filters</div>'


def _table_html(title: str, rows: Iterable[OperatorTableRow]) -> str:
    row_tuple = tuple(rows)
    body = "".join(_row_html(row) for row in row_tuple) or '<tr><td colspan="10">No operator rows match these filters</td></tr>'
    return f"""
<section>
  <h2 class="tp-section-title">{_esc(title)}</h2>
  <div class="tp-table-wrap">
    <table class="tp-table">
      <thead>
        <tr>
          <th>Resource</th>
          <th>Identifier</th>
          <th>Status</th>
          <th>Store</th>
          <th class="tp-num">Amount</th>
          <th class="tp-num">Qty</th>
          <th class="tp-num">Gas</th>
          <th>Chain</th>
          <th>Updated</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>{body}</tbody>
    </table>
  </div>
</section>
"""


def _row_html(row: OperatorTableRow) -> str:
    notes = [
        _esc(row.primary),
        _esc(row.secondary) if row.secondary else None,
        _esc(row.failure_reason) if row.failure_reason else None,
        _esc(row.latest_event) if row.latest_event else None,
        _copy_html(row.tx_hash, "tx hash") if row.tx_hash else None,
        "Retry candidate" if row.retry_candidate else None,
        _metadata_html(row.metadata),
    ]
    return f"""
<tr>
  <td>{_esc(row.resource)}</td>
  <td>{_copy_html(row.identity, row.resource + " id")}</td>
  <td>{render_status_badge(row.status)}</td>
  <td>{_copy_html(row.store_id, "store id") if row.store_id else "-"}</td>
  <td class="tp-num">{_money_html(row.amount)}</td>
  <td class="tp-num">{_esc(row.quantity) if row.quantity is not None else "-"}</td>
  <td class="tp-num">{_money_html(row.gas)}</td>
  <td>{_esc(str(row.chain_id)) if row.chain_id is not None else "-"}</td>
  <td>{_esc(row.updated_at or "-")}</td>
  <td>{_join_html(notes)}</td>
</tr>
"""


def _detail_html(detail: OperatorDetailView | None) -> str:
    if detail is None:
        return '<h2 class="tp-section-title">Detail</h2><span class="tp-value">No selection</span>'
    return f'<h2 class="tp-section-title">{_esc(detail.title)}</h2>{_definition_html(detail.fields, "tp-detail-list")}'


def _definition_html(fields: Mapping[str, Any], class_name: str) -> str:
    items = []
    for key, value in fields.items():
        safe_value = _safe_display_value(str(key), value)
        items.append(
            f"<div>{_field_html(str(key), safe_value)}</div>"
        )
    return f'<dl class="{_esc(class_name)}">{"".join(items)}</dl>'


def _field_html(label: str, value_html: str, modifier: str | None = None, *, numeric: bool = False) -> str:
    field_class = "tp-field" + (f" tp-field-{modifier}" if modifier else "")
    value_class = "tp-value" + (" tp-value-num" if numeric else "")
    return f'<div class="{field_class}"><dt class="tp-label">{_esc(label)}</dt><dd class="{value_class}">{value_html}</dd></div>'


def _line_items_html(items: tuple[CheckoutOrderItemView, ...]) -> str:
    if not items:
        return '<span class="tp-value">No order items</span>'
    return f'<div class="tp-line-items">{"".join(_line_item_html(item) for item in items)}</div>'


def _line_item_html(item: CheckoutOrderItemView) -> str:
    return f"""
<div class="tp-line-item">
  <div>
    <span class="tp-value">{_esc(item.name)}</span>
    <span class="tp-label">Qty {_esc(item.quantity)} / {_money_html(item.unit_price)}</span>
    <span class="tp-mono">{_esc(item.product_id)}</span>
  </div>
  <div class="tp-value tp-value-num">{_money_html(item.sub_total)}</div>
</div>
"""


def _actions_html(actions: tuple[CheckoutAction, ...]) -> str:
    if not actions:
        return f'<button class="tp-button tp-button-primary" type="button">{_esc(_action_label("WAITING"))}</button>'
    return f'<div class="tp-action-list">{"".join(_action_html(action) for action in actions)}</div>'


def _action_html(action: CheckoutAction) -> str:
    kind_class = {
        "primary": " tp-button-primary",
        "danger": " tp-button-danger",
        "secondary": "",
    }[action.kind]
    disabled = ' disabled aria-disabled="true"' if not action.enabled else ' aria-disabled="false"'
    tooltip = action.tooltip or action.label
    aria_label = action.aria_label or action.label
    note = f'<span class="tp-action-note">{_esc(action.disabled_reason)}</span>' if action.disabled_reason else ""
    return (
        f'<button class="tp-button{kind_class}" type="button" data-action-id="{_esc(action.action_id)}" '
        f'aria-label="{_esc(aria_label)}" title="{_esc(tooltip)}"{disabled}>{_esc(action.label)}</button>{note}'
    )


def _timeline_html(items: tuple[CheckoutTimelineItem, ...]) -> str:
    rendered_items = "".join(_timeline_item_html(item) for item in items)
    return f'<ol class="tp-timeline">{rendered_items}</ol>'


def _timeline_item_html(item: CheckoutTimelineItem) -> str:
    detail_parts = [
        _esc(item.detail) if item.detail else None,
        _copy_html(item.message_id, "message id") if item.message_id else None,
        _copy_html(item.command_id, "command id") if item.command_id else None,
        _esc(item.compensation_status) if item.compensation_status else None,
        _esc(item.occurred_at) if item.occurred_at else None,
    ]
    return f"""
<li class="tp-timeline-item" data-tone="{_esc(item.status.tone)}" data-stage="{_esc(item.stage or item.label)}">
  <span class="tp-timeline-dot" aria-hidden="true"></span>
  <div>
    <div>{_esc(item.label)} {render_status_badge(item.status)}</div>
    <div class="tp-value">{_join_html(detail_parts)}</div>
  </div>
</li>
"""


def _metadata_html(metadata: Mapping[str, Any]) -> str:
    if not metadata:
        return ""
    fields = []
    for key, value in metadata.items():
        if value is None:
            continue
        fields.append(f"{_esc(str(key))}={_safe_display_value(str(key), value)}")
    return ", ".join(fields)


def _failure_html(failure_reason: str | None) -> str:
    if not failure_reason:
        return ""
    return f'<div class="tp-field"><dt class="tp-label">Failure reason</dt><dd class="tp-value">{_esc(failure_reason)}</dd></div>'


def _network_html(view: CheckoutViewModel) -> str:
    label = view.network_label or "unknown"
    if view.chain_id is not None:
        return f"{_esc(label)} <span class=\"tp-mono\">{_esc(str(view.chain_id))}</span>"
    return _esc(label)


def _gas_html(view: CheckoutViewModel) -> str:
    if view.gas_estimate is None:
        return "pending"
    max_fee = f" / max {_money_html(view.gas_estimate.max_fee)}" if view.gas_estimate.max_fee else ""
    return (
        f"{_money_html(view.gas_estimate.estimated_fee)}"
        f" / <span class=\"tp-mono\">{_esc(str(view.gas_estimate.gas_limit))}</span>"
        f" / buffer {_esc(view.gas_estimate.buffer_rate)}{max_fee}"
    )


def _money_html(value: MoneyView | None) -> str:
    if value is None:
        return "-"
    return f'<span class="tp-money">{_esc(value.display)}</span>'


def _copy_html(value: str | None, label: str) -> str:
    if value is None:
        return "-"
    token = CopyToken(value=value, label=label)
    display = _shorten(token.value)
    escaped_value = _esc(token.value)
    return (
        '<span class="tp-copy">'
        f'<span class="tp-mono tp-copy-value" data-copy-value="{escaped_value}">{_esc(display)}</span>'
        f'<button class="tp-icon-button" type="button" title="Copy {_esc(token.label)}" '
        f'aria-label="Copy {_esc(token.label)}" data-copy-value="{escaped_value}">Copy</button>'
        "</span>"
    )


def _safe_display_value(key: str, value: Any) -> str:
    if any(marker in key.replace("-", "_").lower() for marker in SECRET_KEY_MARKERS):
        return "REDACTED"
    if isinstance(value, Mapping):
        return _metadata_html(value)
    if isinstance(value, tuple | list):
        return ", ".join(_safe_display_value("item", item) for item in value)
    if isinstance(value, bool | int | float):
        return _esc(str(value))
    if value is None:
        return "-"
    text = str(value)
    return _copy_html(text, key) if _looks_like_identifier(text) else _esc(text)


def _join_html(values: Iterable[str | None]) -> str:
    return " ".join(value for value in values if value)


def _looks_like_identifier(value: str) -> bool:
    return len(value) >= 24 or value.startswith("0x")


def _operator_surface_status(view: OperatorDashboardViewModel) -> str:
    if any(item.status.tone == "danger" and item.value > 0 for item in view.summary):
        return "FAILED"
    if any(row.status.tone == "danger" for row in view.all_rows):
        return "FAILED"
    return "OK"


def _shorten(value: str) -> str:
    if len(value) <= 28:
        return value
    return f"{value[:12]}...{value[-8:]}"


def _action_label(action: str) -> str:
    return {
        "SIGN_PAYMENT": "Sign Payment",
        "WAIT_FOR_RECEIPT": "Receipt Pending",
        "WAIT_FOR_STORE_APPROVAL": "Store Approval Pending",
        "WAIT_FOR_COMPENSATION": "Compensation Pending",
        "WAIT_FOR_PAYMENT_REQUEST": "Payment Request Pending",
    }.get(action, action.replace("_", " ").title())


def _esc(value: object) -> str:
    return escape(str(value), quote=True)


__all__ = [
    "DEFAULT_CSS",
    "render_checkout_page",
    "render_operator_dashboard",
    "render_status_badge",
]

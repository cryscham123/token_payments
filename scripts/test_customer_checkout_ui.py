from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


ORDER_ID = 'order-<script>alert("order")</script>'
TRACKING_ID = "tracking-018f33aa9e6d73d89dc347d6cdcc6c32"
WALLET = '0x1111111111111111111111111111111111111111<script>alert("wallet")</script>'
RECEIVER = "0x2222222222222222222222222222222222222222"
TOKEN = "0x3333333333333333333333333333333333333333"
TX_HASH = '0x' + "ab" * 32 + '<script>alert("tx")</script>'


def test_customer_checkout_payload_maps_order_items_actions_and_fixed_timeline() -> None:
    from token_payments.ui import CheckoutAction, CheckoutOrderItemView, checkout_view_from_api_payload

    view = checkout_view_from_api_payload(_checkout_fixture(), wallet_address=WALLET, network_name="Sepolia")

    assert view.order_id == ORDER_ID
    assert view.wallet_address == WALLET
    assert view.network_label == "Sepolia"
    assert view.chain_id == 11155111
    assert view.payment_expires_in == "00:12:00"
    assert view.tx_hash == TX_HASH

    assert view.order_items == (
        CheckoutOrderItemView(
            product_id="product-ledger-mug",
            name="Ledger Mug <limited>",
            quantity=2,
            unit_price=view.order_items[0].unit_price,
            sub_total=view.order_items[0].sub_total,
        ),
    )
    assert view.order_items[0].unit_price.display == "12.50 USDC"
    assert view.order_items[0].sub_total.display == "25.00 USDC"

    assert view.actions == (
        CheckoutAction(
            action_id="connect-wallet",
            label="Connect Wallet",
            kind="secondary",
            enabled=True,
            tooltip="Connect wallet address",
            aria_label="Connect wallet address",
        ),
        CheckoutAction(
            action_id="sign-payment",
            label="Sign Payment",
            kind="primary",
            enabled=True,
            tooltip="Request MetaMask payment signature",
            aria_label="Request MetaMask payment signature",
        ),
        CheckoutAction(
            action_id="submit-tx-hash",
            label="Submit txHash",
            kind="primary",
            enabled=False,
            tooltip="Submit signed transaction hash",
            aria_label="Submit signed transaction hash",
            disabled_reason="Waiting for wallet signature",
        ),
        CheckoutAction(
            action_id="track-order",
            label="Track Order",
            kind="secondary",
            enabled=True,
            tooltip="Track checkout status",
            aria_label="Track checkout status",
        ),
    )

    assert tuple(item.stage for item in view.timeline) == (
        "ORDER_CREATED",
        "INVENTORY_RESERVED",
        "AWAITING_SIGNATURE",
        "TX_SUBMITTED",
        "PAYMENT_CONFIRMED",
        "STORE_APPROVAL",
        "COMPLETED",
    )
    assert view.timeline[1].command_id == "order-123:ReserveInventory"
    assert view.timeline[3].message_id == "payment-submitted-message"


def test_customer_checkout_html_snapshot_semantics_escaping_and_disabled_actions() -> None:
    from token_payments.ui import checkout_view_from_api_payload, render_checkout_page
    from token_payments.ui.renderers import DEFAULT_CSS

    view = checkout_view_from_api_payload(_checkout_fixture(), wallet_address=WALLET, network_name="Sepolia")
    html = render_checkout_page(view).html

    assert '<main class="tp-shell tp-checkout" data-view="checkout">' in html
    assert "Checkout" in html
    assert "Ledger Mug &lt;limited&gt;" in html
    assert "Qty 2" in html
    assert "25.00 USDC" in html
    assert "0.0100 ETH" in html
    assert "00:12:00" in html
    assert "AWAITING_SIGNATURE" in html
    assert "Submit txHash" in html
    assert "Waiting for wallet signature" in html

    assert "<script>" not in html
    assert "alert(&quot;order&quot;)" in html
    assert "alert(&quot;wallet&quot;)" in html
    assert "alert(&quot;tx&quot;)" in html
    assert f'data-copy-value="{ORDER_ID.replace("<", "&lt;").replace(">", "&gt;").replace(chr(34), "&quot;")}"' in html
    assert 'data-copy-value="0xabab' in html

    assert 'class="tp-field tp-field-amount"' in html
    assert 'class="tp-field tp-field-gas"' in html
    assert 'class="tp-value tp-value-num"' in html
    assert '<span class="tp-badge" data-tone="pending">AWAITING_SIGNATURE</span>' in html
    assert 'data-action-id="submit-tx-hash"' in html
    assert 'disabled aria-disabled="true"' in html
    assert 'aria-label="Submit signed transaction hash"' in html
    assert 'title="Submit signed transaction hash"' in html

    assert ".tp-payment-panel" in DEFAULT_CSS
    assert ".tp-order-panel" in DEFAULT_CSS
    assert "@media (max-width: 860px)" in DEFAULT_CSS
    assert "order: 1" in DEFAULT_CSS
    assert "order: 2" in DEFAULT_CSS


def test_customer_checkout_failure_timeline_shows_compensation_state() -> None:
    from token_payments.ui import checkout_view_from_api_payload, render_checkout_page

    fixture = _checkout_fixture()
    fixture["checkout"]["status"] = "FAILED"
    fixture["checkout"]["currentStep"] = "PAYMENT_FAILED"
    fixture["checkout"]["pendingAction"] = "WAIT_FOR_COMPENSATION"
    fixture["checkout"]["failureReason"] = 'receipt <reverted>'
    fixture["checkout"]["timeline"][4] = {
        "stage": "PAYMENT_CONFIRMED",
        "label": "Payment confirmation",
        "status": "FAILED",
        "occurredAt": "2026-05-10T10:06:00+00:00",
        "messageId": "payment-failed-message",
        "detail": "receipt <reverted>",
        "compensationStatus": "ReleaseInventoryCommand PENDING; CancelOrderCommand PENDING",
    }

    html = render_checkout_page(checkout_view_from_api_payload(fixture, wallet_address=WALLET, network_name="Sepolia")).html

    assert "WAIT_FOR_COMPENSATION" in html
    assert "receipt &lt;reverted&gt;" in html
    assert "ReleaseInventoryCommand PENDING; CancelOrderCommand PENDING" in html
    assert '<span class="tp-badge" data-tone="danger">FAILED</span>' in html


def _checkout_fixture() -> dict[str, object]:
    return {
        "order": {
            "orderId": ORDER_ID,
            "trackingId": TRACKING_ID,
            "status": "PENDING",
            "items": [
                {
                    "orderItemId": "item-1",
                    "productId": "product-ledger-mug",
                    "name": "Ledger Mug <limited>",
                    "quantity": 2,
                    "unitPrice": {
                        "amount": "12.50",
                        "symbol": "USDC",
                        "chainId": 11155111,
                        "tokenAddress": TOKEN,
                        "decimals": 6,
                    },
                    "subTotal": {
                        "amount": "25.00",
                        "symbol": "USDC",
                        "chainId": 11155111,
                        "tokenAddress": TOKEN,
                        "decimals": 6,
                    },
                }
            ],
        },
        "checkout": {
            "orderId": ORDER_ID,
            "trackingId": TRACKING_ID,
            "status": "AWAITING_SIGNATURE",
            "currentStep": "AWAITING_SIGNATURE",
            "pendingAction": "SIGN_PAYMENT",
            "paymentExpiresIn": "00:12:00",
            "paymentRequest": {
                "requestId": "payment-request-123",
                "amount": {
                    "amount": "25.00",
                    "symbol": "USDC",
                    "chainId": 11155111,
                    "tokenAddress": TOKEN,
                    "decimals": 6,
                },
                "to": RECEIVER,
                "expiresAt": "2026-05-10T10:15:00+00:00",
            },
            "gasEstimate": {
                "estimatedFee": {
                    "amount": "0.0100",
                    "symbol": "ETH",
                    "chainId": 11155111,
                    "tokenAddress": None,
                    "decimals": 18,
                },
                "gasLimit": 21000,
                "bufferRate": "0.10",
                "maxFee": {
                    "amount": "0.011000",
                    "symbol": "ETH",
                    "chainId": 11155111,
                    "tokenAddress": None,
                    "decimals": 18,
                },
            },
            "txHash": TX_HASH,
            "txHashStatus": "SUBMITTED",
            "failureReason": None,
            "updatedAt": "2026-05-10T10:08:00+00:00",
            "actions": [
                {
                    "id": "connect-wallet",
                    "label": "Connect Wallet",
                    "kind": "secondary",
                    "enabled": True,
                    "tooltip": "Connect wallet address",
                    "ariaLabel": "Connect wallet address",
                },
                {
                    "id": "sign-payment",
                    "label": "Sign Payment",
                    "kind": "primary",
                    "enabled": True,
                    "tooltip": "Request MetaMask payment signature",
                    "ariaLabel": "Request MetaMask payment signature",
                },
                {
                    "id": "submit-tx-hash",
                    "label": "Submit txHash",
                    "kind": "primary",
                    "enabled": False,
                    "tooltip": "Submit signed transaction hash",
                    "ariaLabel": "Submit signed transaction hash",
                    "disabledReason": "Waiting for wallet signature",
                },
                {
                    "id": "track-order",
                    "label": "Track Order",
                    "kind": "secondary",
                    "enabled": True,
                    "tooltip": "Track checkout status",
                    "ariaLabel": "Track checkout status",
                },
            ],
            "timeline": [
                {
                    "stage": "ORDER_CREATED",
                    "label": "Order created",
                    "status": "ORDER_CREATED",
                    "occurredAt": "2026-05-10T10:00:00+00:00",
                    "messageId": "order-created-message",
                },
                {
                    "stage": "INVENTORY_RESERVED",
                    "label": "Inventory reserved",
                    "status": "CONFIRMED",
                    "occurredAt": "2026-05-10T10:02:00+00:00",
                    "commandId": "order-123:ReserveInventory",
                },
                {
                    "stage": "AWAITING_SIGNATURE",
                    "label": "Payment signature",
                    "status": "AWAITING_SIGNATURE",
                    "occurredAt": "2026-05-10T10:03:00+00:00",
                    "messageId": "payment-started-message",
                },
                {
                    "stage": "TX_SUBMITTED",
                    "label": "tx submitted",
                    "status": "SUBMITTED",
                    "occurredAt": "2026-05-10T10:05:00+00:00",
                    "messageId": "payment-submitted-message",
                },
                {
                    "stage": "PAYMENT_CONFIRMED",
                    "label": "Payment confirmation",
                    "status": "PENDING",
                    "detail": "waiting for receipt",
                },
                {
                    "stage": "STORE_APPROVAL",
                    "label": "Store approval",
                    "status": "PENDING",
                    "detail": "waiting for payment confirmation",
                },
                {
                    "stage": "COMPLETED",
                    "label": "Completed",
                    "status": "PENDING",
                    "detail": "waiting for store approval",
                },
            ],
        },
    }

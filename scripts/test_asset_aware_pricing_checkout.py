from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.domain.wallet import UserWallet, WalletId, WalletType, WalletVerificationStatus  # noqa: E402
from token_payments.contexts.order.application import CreateOrderCommand, CreateOrderItem, OrderApplicationError, OrderApplicationService  # noqa: E402
from token_payments.contexts.order.domain import Address, Customer, Product, Store  # noqa: E402
from token_payments.contexts.payment.domain import PaymentAsset, PaymentAssetRegistry, PaymentChain  # noqa: E402
from token_payments.shared.domain import Crypto, CustomerId, MessageId, OrderId, ProductId, StoreId, UserId, WalletAddress  # noqa: E402


NOW = datetime(2026, 5, 22, 5, 30, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9b01")
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9b02")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9b03")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9b04")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9b05")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9b06")
WALLET_ID = WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9b07")
ETH_WALLET_ID = WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9b08")
USDC = WalletAddress("0x4444444444444444444444444444444444444444")
USDT = WalletAddress("0x5555555555555555555555555555555555555555")
STORE_WALLET = WalletAddress("0x3333333333333333333333333333333333333333")


def test_asset_aware_checkout_uses_selected_asset_price_and_minor_units() -> None:
    outbox = FakeOutboxRepository()
    service = _service(outbox=outbox)

    result = service.createOrder(
        CreateOrderCommand(
            authenticated_user_id=USER_ID,
            store_id=STORE_ID,
            delivery_address=Address("ship", "1 Stable Ave"),
            items=(CreateOrderItem(PRODUCT_ID, 2),),
            wallet_id=WALLET_ID,
            payment_asset_id="local-usdc",
            order_id=ORDER_ID,
            event_message_id=MESSAGE_ID,
            requested_at=NOW,
            causation_id="idem-usdc",
        )
    )

    assert result.total_amount == Crypto(Decimal("25.00"), "USDC", 1337, USDC, 6)
    payload = outbox.saved[0].payload
    assert payload["paymentAssetId"] == "local-usdc"
    assert payload["amount"]["assetId"] == "local-usdc"
    assert payload["amount"]["amountMinorUnits"] == "25000000"
    assert payload["items"][0]["unitPrice"]["assetId"] == "local-usdc"


def test_asset_aware_checkout_rejects_unsupported_disabled_and_wallet_chain_mismatch_assets() -> None:
    for payment_asset_id, wallet_id, expected in (
        ("local-usdt", WALLET_ID, "not supported"),
        ("disabled-usdc", WALLET_ID, "disabled"),
        ("local-eth", WALLET_ID, "not supported"),
    ):
        with pytest.raises(OrderApplicationError) as exc_info:
            _service().createOrder(
                CreateOrderCommand(
                    authenticated_user_id=USER_ID,
                    store_id=STORE_ID,
                    delivery_address=Address("ship", "1 Stable Ave"),
                    items=(CreateOrderItem(PRODUCT_ID, 1),),
                    wallet_id=wallet_id,
                    payment_asset_id=payment_asset_id,
                    order_id=ORDER_ID,
                    event_message_id=MESSAGE_ID,
                    requested_at=NOW,
                )
            )
        assert exc_info.value.code.value == "VALIDATION_ERROR"
        assert expected in str(exc_info.value)


def test_asset_aware_checkout_defaults_wallet_to_selected_asset_chain_primary() -> None:
    wallets = FakeWalletRepository()
    outbox = FakeOutboxRepository()

    _service(wallets=wallets, outbox=outbox).createOrder(
        CreateOrderCommand(
            authenticated_user_id=USER_ID,
            store_id=STORE_ID,
            delivery_address=Address("ship", "1 Stable Ave"),
            items=(CreateOrderItem(PRODUCT_ID, 1),),
            payment_asset_id="local-usdc",
            order_id=ORDER_ID,
            event_message_id=MESSAGE_ID,
            requested_at=NOW,
        )
    )

    assert wallets.primary_calls == [(USER_ID, 1337)]
    assert outbox.saved[0].payload["payerWalletId"] == str(WALLET_ID)


def test_variant_and_addon_deltas_are_reexpressed_in_selected_asset() -> None:
    # A product priced in USDC whose variant delta is stored in USDC must be payable in
    # USDT without "variant priceDelta asset must match product price asset".
    from token_payments.contexts.order.application.service import (
        _option_values_for_asset,
        _store_with_asset_prices,
        _variants_for_asset,
    )
    from token_payments.contexts.order.domain import ProductOptionValuePrice, ProductVariantPrice

    usdt = PaymentAsset.erc20("local-usdt", 1337, "USDT", 6, USDT)

    variant = ProductVariantPrice(
        public_variant_id="var_x",
        option_values={"size": "large"},
        price_delta=Crypto("5", "USDC", 1337, USDC, 6),
    )
    reexpressed = _variants_for_asset({"var_x": variant}, usdt)["var_x"]
    assert reexpressed.price_delta == Crypto("5", "USDT", 1337, USDT, 6)

    add_on = ProductOptionValuePrice(
        option_key="gift", value_key="wrap", display_value="Gift wrap", option_type="ADD_ON",
        price_delta=Crypto("2", "USDC", 1337, USDC, 6),
    )
    reexpressed_addon = _option_values_for_asset({"wrap": add_on}, usdt)["wrap"]
    assert reexpressed_addon.price_delta == Crypto("2", "USDT", 1337, USDT, 6)

    # End-to-end through the store enrichment + domain price computation.
    product = Product(
        PRODUCT_ID,
        "Variant Mug",
        Crypto("12.50", "USDC", 1337, USDC, 6),
        asset_prices={"local-usdc": Crypto("12.50", "USDC", 1337, USDC, 6)},
        variants={"var_x": variant},
    )
    store = Store(
        STORE_ID, USER_ID, products=(product,), active=True, store_wallet=STORE_WALLET,
        supported_chain_ids=(1337,), supported_payment_asset_ids=("local-usdc", "local-usdt"),
    )
    enriched = _store_with_asset_prices(store, usdt)
    price = enriched.products[0].price_for_selection("local-usdt", public_variant_id="var_x", selected_options={"size": "large"})
    assert price == Crypto("17.50", "USDT", 1337, USDT, 6)


def _service(
    *,
    wallets: "FakeWalletRepository | None" = None,
    outbox: "FakeOutboxRepository | None" = None,
) -> OrderApplicationService:
    return OrderApplicationService(
        customers=FakeCustomerRepository(),
        stores=FakeStoreRepository(),
        orders=FakeOrderRepository(),
        outbox_messages=outbox or FakeOutboxRepository(),
        wallets=wallets or FakeWalletRepository(),
        payment_assets=_registry(),
    )


def _registry() -> PaymentAssetRegistry:
    return PaymentAssetRegistry(
        chains=(
            PaymentChain(1337, "Local", "ETH"),
            PaymentChain(11155111, "Sepolia", "ETH"),
        ),
        assets=(
            PaymentAsset.native("local-eth", 11155111, "ETH", 18),
            PaymentAsset.erc20("local-usdc", 1337, "USDC", 6, USDC),
            PaymentAsset.erc20("local-usdt", 1337, "USDT", 6, USDT),
            PaymentAsset.erc20("disabled-usdc", 1337, "USDC", 6, USDC, enabled=False),
        ),
    )


class FakeCustomerRepository:
    def get_by_user_id(self, user_id: UserId) -> Customer | None:
        return Customer(CUSTOMER_ID, USER_ID) if user_id == USER_ID else None


class FakeStoreRepository:
    def get(self, store_id: StoreId) -> Store | None:
        if store_id != STORE_ID:
            return None
        product = Product(PRODUCT_ID, "Stable Mug", Crypto("12.50", "USDC", 1337, USDC, 6))
        object.__setattr__(
            product,
            "_asset_prices",
            {
                "local-usdc": Crypto("12.50", "USDC", 1337, USDC, 6),
            },
        )
        return Store(
            STORE_ID,
            USER_ID,
            products=(product,),
            active=True,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(1337,),
            supported_payment_asset_ids=("local-usdc",),
        )


class FakeWalletRepository:
    def __init__(self) -> None:
        self.primary_calls: list[tuple[UserId, int]] = []

    def get_by_id(self, wallet_id: WalletId) -> UserWallet | None:
        if wallet_id == WALLET_ID:
            return UserWallet(WALLET_ID, USER_ID, "0x1111111111111111111111111111111111111111", 1337, WalletType.EOA, WalletVerificationStatus.VERIFIED, True, NOW)
        if wallet_id == ETH_WALLET_ID:
            return UserWallet(ETH_WALLET_ID, USER_ID, "0x2222222222222222222222222222222222222222", 11155111, WalletType.EOA, WalletVerificationStatus.VERIFIED, True, NOW)
        return None

    def get_primary_for_user_chain(self, user_id: UserId, chain_id: int) -> UserWallet | None:
        self.primary_calls.append((user_id, chain_id))
        if user_id == USER_ID and chain_id == 1337:
            return self.get_by_id(WALLET_ID)
        if user_id == USER_ID and chain_id == 11155111:
            return self.get_by_id(ETH_WALLET_ID)
        return None


class FakeOrderRepository:
    def save(self, order: Any) -> None:
        return None


class FakeOutboxRepository:
    def __init__(self) -> None:
        self.saved: list[Any] = []

    def save(self, message: Any) -> None:
        self.saved.append(message)

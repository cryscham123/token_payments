from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiRequest  # noqa: E402
from token_payments.api.orders import OrdersApi  # noqa: E402
from token_payments.contexts.auth.domain.wallet import (  # noqa: E402
    UserWallet,
    WalletId,
    WalletType,
    WalletVerificationStatus,
)
from token_payments.contexts.order.application import (  # noqa: E402
    CreateOrderCommand,
    CreateOrderItem,
    OrderApplicationError,
    OrderApplicationService,
)
from token_payments.contexts.order.domain import Address, Customer, Product, Store  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    Crypto,
    CustomerId,
    ExchangeRate,
    Money,
    MessageId,
    OrderId,
    ProductId,
    StoreId,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 22, 5, 0, tzinfo=UTC)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a01")
TRACKING_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc9a02"
MESSAGE_ID = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a03")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a04")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a05")
OTHER_USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a06")
STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a07")
PRODUCT_ID = ProductId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a08")
WALLET_ID = WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a09")
OTHER_WALLET_ID = WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a0a")
REVOKED_WALLET_ID = WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a0b")
WRONG_CHAIN_WALLET_ID = WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a0c")
PRIMARY_WALLET_ID = WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9a0d")
WALLET_ADDRESS = WalletAddress("0x1111111111111111111111111111111111111111")
PRIMARY_WALLET_ADDRESS = WalletAddress("0x2222222222222222222222222222222222222222")
STORE_WALLET = WalletAddress("0x3333333333333333333333333333333333333333")
TOKEN_ADDRESS = WalletAddress("0x4444444444444444444444444444444444444444")


def test_checkout_uses_selected_verified_wallet_id_and_preserves_canonical_reference() -> None:
    service, wallets, outbox = _service()

    result = service.createOrder(
        CreateOrderCommand(
            authenticated_user_id=USER_ID,
            store_id=STORE_ID,
            delivery_address=Address(id="ship", street="1 Stable Ave"),
            items=(CreateOrderItem(product_id=PRODUCT_ID, quantity=2),),
            wallet_id=WALLET_ID,
            payment_asset_id="local-usdc",
            order_id=ORDER_ID,
            tracking_id=TRACKING_ID,
            event_message_id=MESSAGE_ID,
            requested_at=NOW,
            causation_id="idem-wallet",
        )
    )

    payload = outbox.saved[0].payload
    assert result.total_amount.amount == Decimal("25.00")
    assert payload["payerWalletId"] == str(WALLET_ID)
    assert payload["walletFrom"] == str(WALLET_ADDRESS)
    assert payload["payerWallet"] == {
        "walletId": str(WALLET_ID),
        "chainId": 1337,
        "addressPreview": "0x1111...1111",
    }
    assert wallets.get_by_id_calls == [WALLET_ID]
    assert wallets.primary_calls == []


def test_checkout_defaults_to_chain_primary_wallet_when_wallet_id_is_omitted() -> None:
    service, wallets, outbox = _service()

    service.createOrder(
        CreateOrderCommand(
            authenticated_user_id=USER_ID,
            store_id=STORE_ID,
            delivery_address=Address(id="ship", street="1 Stable Ave"),
            items=(CreateOrderItem(product_id=PRODUCT_ID, quantity=1),),
            payment_asset_id="local-usdc",
            order_id=ORDER_ID,
            tracking_id=TRACKING_ID,
            event_message_id=MESSAGE_ID,
            requested_at=NOW,
        )
    )

    assert wallets.primary_calls == [(USER_ID, 1337)]
    assert outbox.saved[0].payload["payerWalletId"] == str(PRIMARY_WALLET_ID)
    assert outbox.saved[0].payload["walletFrom"] == str(PRIMARY_WALLET_ADDRESS)


def test_checkout_rejects_foreign_revoked_and_chain_mismatch_wallets() -> None:
    service, _wallets, _outbox = _service()

    for wallet_id, expected in (
        (OTHER_WALLET_ID, "does not belong"),
        (REVOKED_WALLET_ID, "verified active"),
        (WRONG_CHAIN_WALLET_ID, "chain"),
    ):
        try:
            service.createOrder(
                CreateOrderCommand(
                    authenticated_user_id=USER_ID,
                    store_id=STORE_ID,
                    delivery_address=Address(id="ship", street="1 Stable Ave"),
                    items=(CreateOrderItem(product_id=PRODUCT_ID, quantity=1),),
                    wallet_id=wallet_id,
                    payment_asset_id="local-usdc",
                    order_id=ORDER_ID,
                    tracking_id=TRACKING_ID,
                    event_message_id=MESSAGE_ID,
                    requested_at=NOW,
                )
            )
        except OrderApplicationError as exc:
            assert exc.code.value == "VALIDATION_ERROR"
            assert expected in str(exc)
        else:
            raise AssertionError(f"wallet {wallet_id} should have been rejected")


def test_order_api_accepts_wallet_id_without_accepting_raw_wallet_address_selection() -> None:
    api = OrdersApi(CapturingOrderUseCase())

    response = api.create_order(
        ApiRequest(
            request_id="req-wallet-api",
            method="POST",
            path="/orders",
            headers={"X-User-Id": str(USER_ID), "Idempotency-Key": "idem-wallet"},
            body={
                "storeId": str(STORE_ID),
                "walletId": str(WALLET_ID),
                "walletAddress": str(WALLET_ADDRESS),
                "deliveryAddress": {"id": "ship", "street": "1 Stable Ave"},
                "items": [{"productId": str(PRODUCT_ID), "quantity": 1}],
            },
            received_at=NOW,
        )
    )

    assert response.status_code == 201
    command = api._use_case.commands[0]
    assert command.wallet_id == WALLET_ID
    assert not hasattr(command, "wallet_address")


def _wallet_selection_registry():
    from token_payments.contexts.payment.domain import PaymentAsset, PaymentAssetRegistry, PaymentChain
    return PaymentAssetRegistry(
        chains=(PaymentChain(1337, "Local", "ETH"),),
        assets=(PaymentAsset.erc20("local-usdc", 1337, "USDC", 6, TOKEN_ADDRESS),),
    )


def _service() -> tuple[OrderApplicationService, "FakeWalletRepository", "FakeOutboxRepository"]:
    wallets = FakeWalletRepository(
        {
            WALLET_ID: _wallet(WALLET_ID, USER_ID, WALLET_ADDRESS, primary=False),
            PRIMARY_WALLET_ID: _wallet(PRIMARY_WALLET_ID, USER_ID, PRIMARY_WALLET_ADDRESS, primary=True),
            OTHER_WALLET_ID: _wallet(OTHER_WALLET_ID, OTHER_USER_ID, "0x5555555555555555555555555555555555555555"),
            REVOKED_WALLET_ID: _wallet(
                REVOKED_WALLET_ID,
                USER_ID,
                "0x6666666666666666666666666666666666666666",
                status=WalletVerificationStatus.REVOKED,
            ),
            WRONG_CHAIN_WALLET_ID: _wallet(
                WRONG_CHAIN_WALLET_ID,
                USER_ID,
                "0x7777777777777777777777777777777777777777",
                chain_id=11155111,
            ),
        }
    )
    outbox = FakeOutboxRepository()
    return (
        OrderApplicationService(
            customers=FakeCustomerRepository(),
            stores=FakeStoreRepository(),
            orders=FakeOrderRepository(),
            outbox_messages=outbox,
            wallets=wallets,
            exchange_rate=ExchangeRate({"USDC": Decimal(1), "USDT": Decimal(1), "ETH": Decimal(3000)}),
            payment_assets=_wallet_selection_registry(),
        ),
        wallets,
        outbox,
    )


def _wallet(
    wallet_id: WalletId,
    user_id: UserId,
    address: WalletAddress | str,
    *,
    chain_id: int = 1337,
    status: WalletVerificationStatus = WalletVerificationStatus.VERIFIED,
    primary: bool = False,
) -> UserWallet:
    return UserWallet(
        wallet_id=wallet_id,
        user_id=user_id,
        address=WalletAddress(str(address)),
        chain_id=chain_id,
        wallet_type=WalletType.EOA,
        verification_status=status,
        primary=primary,
        linked_at=NOW,
        revoked_at=NOW if status is WalletVerificationStatus.REVOKED else None,
    )


class FakeCustomerRepository:
    def get_by_user_id(self, user_id: UserId) -> Customer | None:
        if user_id != USER_ID:
            return None
        return Customer(customer_id=CUSTOMER_ID, user_id=user_id)


class FakeStoreRepository:
    def get(self, store_id: StoreId) -> Store | None:
        if store_id != STORE_ID:
            return None
        return Store(
            store_id=STORE_ID,
            owner_user_id=OTHER_USER_ID,
            products=(
                Product(
                    product_id=PRODUCT_ID,
                    name="Stable Mug",
                    price=Money("12.50", "USD"),
                ),
            ),
            active=True,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(1337,),
        )


class FakeOrderRepository:
    def __init__(self) -> None:
        self.saved: list[Any] = []

    def save(self, order: Any) -> None:
        self.saved.append(order)


class FakeOutboxRepository:
    def __init__(self) -> None:
        self.saved: list[Any] = []

    def save(self, message: Any) -> None:
        self.saved.append(message)


class FakeWalletRepository:
    def __init__(self, wallets: dict[WalletId, UserWallet]) -> None:
        self.wallets = wallets
        self.get_by_id_calls: list[WalletId] = []
        self.primary_calls: list[tuple[UserId, int]] = []

    def get_by_id(self, wallet_id: WalletId) -> UserWallet | None:
        self.get_by_id_calls.append(wallet_id)
        return self.wallets.get(wallet_id)

    def get_primary_for_user_chain(self, user_id: UserId, chain_id: int) -> UserWallet | None:
        self.primary_calls.append((user_id, chain_id))
        for wallet in self.wallets.values():
            if wallet.user_id == user_id and wallet.chain_id == chain_id and wallet.primary and wallet.is_active():
                return wallet
        return None


class CapturingOrderUseCase:
    def __init__(self) -> None:
        self.commands: list[CreateOrderCommand] = []

    def createOrder(self, command: CreateOrderCommand) -> Any:
        self.commands.append(command)
        order = type(
            "OrderResult",
            (),
            {
                "order_id": ORDER_ID,
                "tracking_id": type("Tracking", (), {"__str__": lambda self: TRACKING_ID})(),
                "customer_id": CUSTOMER_ID,
                "store_id": STORE_ID,
                "status": type("Status", (), {"value": "PENDING"})(),
                "delivery_address": Address(id="ship", street="1 Stable Ave"),
                "items": (),
            },
        )()
        return type("Result", (), {"order": order, "total_amount": Crypto("12.50", "USDC", 1337, TOKEN_ADDRESS, 6)})()

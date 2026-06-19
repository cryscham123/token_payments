from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.store_catalog.application.service import _payment_capability_payload  # noqa: E402
from token_payments.contexts.store_catalog.application.service import StoreCatalogApplicationService  # noqa: E402
from token_payments.contexts.store_catalog.domain import StorePaymentSettings, StoreProfile  # noqa: E402
from token_payments.contexts.payment.domain import PaymentAsset, PaymentAssetRegistry, PaymentChain  # noqa: E402
from token_payments.shared.domain import StoreId, UserId, WalletAddress  # noqa: E402


STORE_ID = StoreId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9d01")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9d02")
STORE_WALLET = WalletAddress("0x3333333333333333333333333333333333333333")
USDC = WalletAddress("0x4444444444444444444444444444444444444444")
USDT = WalletAddress("0x5555555555555555555555555555555555555555")


def test_store_payment_capability_uses_public_supported_chains_and_accepted_assets_dto() -> None:
    store = StoreProfile(
        store_id=STORE_ID,
        owner_user_id=USER_ID,
        display_name="Stable Store",
        created_at=datetime(2026, 5, 22, tzinfo=UTC),
        updated_at=datetime(2026, 5, 22, tzinfo=UTC),
        payment_settings=StorePaymentSettings(
            store_id=STORE_ID,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(1337,),
            supported_payment_asset_ids=("local-usdc", "local-usdt"),
        ),
    )
    payload = _payment_capability_payload(store, asset_registry=_registry())

    assert payload == {
        "supportedChains": [{"chainId": 1337, "displayName": "Local", "nativeSymbol": "ETH"}],
        "acceptedAssets": [
            {
                "assetId": "local-usdc",
                "assetType": "ERC20",
                "chainId": 1337,
                "symbol": "USDC",
                "decimals": 6,
                "tokenContract": {"address": str(USDC)},
            },
            {
                "assetId": "local-usdt",
                "assetType": "ERC20",
                "chainId": 1337,
                "symbol": "USDT",
                "decimals": 6,
                "tokenContract": {"address": str(USDT)},
            },
        ],
        "settlement": {"available": True},
    }
    assert "gasBufferRate" not in str(payload)
    assert "blockchain_gas_buffer_rate" not in str(payload)


def test_public_store_listing_uses_registry_backed_accepted_assets_dto() -> None:
    store = _store()
    service = StoreCatalogApplicationService(repository=_CatalogRepository(store), payment_assets=_registry())

    payload = service.list_public_stores(limit=10, offset=0)

    assets = payload["stores"][0]["paymentCapability"]["acceptedAssets"]
    assert [asset["assetId"] for asset in assets] == ["local-usdc", "local-usdt"]
    assert assets[0]["tokenContract"]["address"] == str(USDC)
    assert assets[1]["tokenContract"]["address"] == str(USDT)


def test_docs_and_postman_examples_do_not_require_chain_name_as_payment_write_field() -> None:
    api_spec = (ROOT / "docs/API_SPEC.md").read_text(encoding="utf-8")
    postman = (ROOT / "postman/token-payments.local.postman_collection.json").read_text(encoding="utf-8")

    assert "paymentAssetId" in api_spec
    assert "acceptedAssets" in api_spec
    assert "walletId" in api_spec
    assert "chainName" not in api_spec
    assert "paymentAssetId" in postman


def _registry() -> PaymentAssetRegistry:
    return PaymentAssetRegistry(
        chains=(PaymentChain(1337, "Local", "ETH"),),
        assets=(
            PaymentAsset.erc20("local-usdc", 1337, "USDC", 6, USDC),
            PaymentAsset.erc20("local-usdt", 1337, "USDT", 6, USDT),
        ),
    )


def _store() -> StoreProfile:
    return StoreProfile(
        store_id=STORE_ID,
        owner_user_id=USER_ID,
        display_name="Stable Store",
        created_at=datetime(2026, 5, 22, tzinfo=UTC),
        updated_at=datetime(2026, 5, 22, tzinfo=UTC),
        payment_settings=StorePaymentSettings(
            store_id=STORE_ID,
            store_wallet=STORE_WALLET,
            supported_chain_ids=(1337,),
            supported_payment_asset_ids=("local-usdc", "local-usdt"),
        ),
    )


class _CatalogRepository:
    def __init__(self, store: StoreProfile) -> None:
        self.stores = {store.store_id: store}

    def list_public_stores(self, *, limit: int, offset: int) -> tuple[StoreProfile, ...]:
        stores = tuple(self.stores.values())
        return stores[offset : offset + limit]

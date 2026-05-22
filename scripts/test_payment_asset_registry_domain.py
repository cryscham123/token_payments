from __future__ import annotations

import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.payment.domain import (  # noqa: E402
    PaymentAsset,
    PaymentAssetRegistry,
    PaymentAssetType,
    PaymentChain,
)
from token_payments.shared.domain import Crypto, WalletAddress  # noqa: E402


LOCAL_USDC = WalletAddress("0x4444444444444444444444444444444444444444")


def test_payment_asset_registry_validates_native_and_erc20_asset_shape() -> None:
    chain = PaymentChain(chain_id=1337, display_name="Local", native_symbol="ETH", enabled=True)
    native = PaymentAsset.native("local-eth", chain_id=1337, symbol="ETH", decimals=18)
    usdc = PaymentAsset.erc20("local-usdc", chain_id=1337, symbol="USDC", decimals=6, contract_address=LOCAL_USDC)

    registry = PaymentAssetRegistry(chains=(chain,), assets=(native, usdc))

    assert registry.require_asset("local-eth").asset_type is PaymentAssetType.NATIVE
    assert registry.require_asset("local-usdc").contract_address == LOCAL_USDC
    assert registry.crypto_for_asset("local-usdc", Decimal("12.34")) == Crypto(
        amount=Decimal("12.34"),
        symbol="USDC",
        chain_id=1337,
        token_address=LOCAL_USDC,
        decimals=6,
    )
    assert registry.minor_units_for_asset("local-usdc", Decimal("12.34")) == 12_340_000

    with pytest.raises(ValueError, match="contract_address"):
        PaymentAsset.erc20("broken-usdc", chain_id=1337, symbol="USDC", decimals=6, contract_address=None)

    with pytest.raises(ValueError, match="must not have contract_address"):
        PaymentAsset.native("broken-native", chain_id=1337, symbol="ETH", decimals=18, contract_address=LOCAL_USDC)

    with pytest.raises(ValueError, match="unknown chain"):
        PaymentAssetRegistry(chains=(chain,), assets=(PaymentAsset.native("other", chain_id=11155111, symbol="ETH", decimals=18),))


def test_registry_rejects_disabled_assets_unknown_assets_and_lossy_amounts() -> None:
    registry = PaymentAssetRegistry(
        chains=(PaymentChain(chain_id=1337, display_name="Local", native_symbol="ETH", enabled=True),),
        assets=(
            PaymentAsset.erc20(
                "local-usdt",
                chain_id=1337,
                symbol="USDT",
                decimals=6,
                contract_address="0x5555555555555555555555555555555555555555",
                enabled=False,
            ),
        ),
    )

    with pytest.raises(ValueError, match="disabled"):
        registry.require_enabled_asset("local-usdt")

    with pytest.raises(ValueError, match="not registered"):
        registry.require_enabled_asset("arbitrary-token")

    with pytest.raises(ValueError, match="precision"):
        registry.minor_units_for_asset("local-usdt", Decimal("1.0000001"))


def test_payment_persistence_schema_uses_chain_id_and_asset_registry_not_chain_name_write_columns() -> None:
    schema = (ROOT / "app/postgres/init.d/001-token-payments-schema.sql").read_text(encoding="utf-8")

    assert re.search(r"CREATE TABLE IF NOT EXISTS chains\b", schema)
    assert re.search(r"CREATE TABLE IF NOT EXISTS payment_assets\b", schema)
    assert "payment_assets" in schema

    payments_block = _table_block(schema, "payments")
    authorizations_block = _table_block(schema, "payment_authorizations")

    assert "chain_id" in payments_block
    assert "chain_id" in authorizations_block
    assert "chain_name" not in payments_block
    assert "chain_name" not in authorizations_block
    assert "payment_asset_id" in authorizations_block
    assert "expected_amount_minor_units" in authorizations_block


def _table_block(schema: str, table_name: str) -> str:
    marker = f"CREATE TABLE IF NOT EXISTS {table_name} ("
    start = schema.index(marker)
    end = schema.index("\n);", start)
    return schema[start:end]

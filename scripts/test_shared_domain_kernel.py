from __future__ import annotations

import ast
import sys
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    Crypto,
    CustomerId,
    MessageId,
    OrderId,
    PaymentId,
    ProductId,
    StoreId,
    TransactionHash,
    UserId,
    WalletAddress,
)


def test_wallet_address_normalizes_valid_evm_address() -> None:
    wallet = WalletAddress("0xABCDabcdABCDabcdABCDabcdABCDabcdABCDabcd")

    assert wallet.address == "0xabcdabcdabcdabcdabcdabcdabcdabcdabcdabcd"
    assert str(wallet) == wallet.address


@pytest.mark.parametrize(
    "address",
    [
        "",
        "abcdabcdabcdabcdabcdabcdabcdabcdabcdabcd",
        "0xnot-hex",
        "0x1234",
    ],
)
def test_wallet_address_rejects_invalid_address(address: str) -> None:
    with pytest.raises(ValueError):
        WalletAddress(address)


def test_value_objects_are_immutable() -> None:
    wallet = WalletAddress("0x1234567890abcdef1234567890abcdef12345678")

    with pytest.raises(FrozenInstanceError):
        wallet.address = "0x0000000000000000000000000000000000000000"  # type: ignore[misc]


def test_chain_network_validates_identity() -> None:
    assert ChainNetwork(chain_id=11155111, name="Sepolia").chain_id == 11155111

    with pytest.raises(ValueError):
        ChainNetwork(chain_id=0, name="Sepolia")

    with pytest.raises(ValueError):
        ChainNetwork(chain_id=1, name=" ")


def test_transaction_hash_normalizes_and_validates() -> None:
    tx_hash = TransactionHash("0x" + "AB" * 32)

    assert tx_hash.hash == "0x" + "ab" * 32

    with pytest.raises(ValueError):
        TransactionHash("0x1234")


def test_crypto_coerces_amount_and_validates_basic_shape() -> None:
    token = WalletAddress("0x2222222222222222222222222222222222222222")
    amount = Crypto(
        amount="1.25",
        symbol="usdc",
        chain_id=1,
        token_address=token,
        decimals=6,
    )

    assert amount.amount == Decimal("1.25")
    assert amount.symbol == "USDC"
    assert amount.token_address == token

    with pytest.raises(ValueError):
        Crypto(amount="-0.01", symbol="USDC", chain_id=1, token_address=token, decimals=6)

    with pytest.raises(ValueError):
        Crypto(amount="1", symbol="", chain_id=1, token_address=token, decimals=6)

    with pytest.raises(ValueError):
        Crypto(amount="1", symbol="USDC", chain_id=1, token_address=token, decimals=-1)


@pytest.mark.parametrize(
    "id_type",
    [OrderId, PaymentId, CustomerId, StoreId, ProductId, UserId, MessageId],
)
def test_domain_ids_accept_uuid_strings_and_generate_typed_ids(id_type: type[OrderId]) -> None:
    raw = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"
    parsed = id_type(raw)
    generated = id_type.new()

    assert parsed.value == UUID(raw)
    assert str(parsed) == raw
    assert isinstance(generated.value, UUID)
    assert isinstance(generated, id_type)


def test_domain_ids_reject_empty_or_invalid_values() -> None:
    with pytest.raises(ValueError):
        OrderId("")

    with pytest.raises(ValueError):
        PaymentId("not-a-uuid")


def test_shared_domain_kernel_does_not_import_external_adapters() -> None:
    forbidden_roots = {
        "blockchain",
        "kafka",
        "metamask",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }

    for path in (ROOT / "app/token_payments/shared/domain").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        assert imports.isdisjoint(forbidden_roots), f"{path} imports adapter dependency: {imports}"

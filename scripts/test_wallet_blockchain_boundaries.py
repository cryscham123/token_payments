from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.adapter.wallet_signature import (  # noqa: E402
    ClientWalletSignatureVerifier,
)
from token_payments.contexts.payment.adapter.blockchain import ClientBlockchainAdapter  # noqa: E402
from token_payments.contexts.payment.adapter.transaction_service import (  # noqa: E402
    ClientTransactionService,
)
from token_payments.contexts.payment.domain import (  # noqa: E402
    GasEstimate,
    Payment,
    PaymentStatus,
    TransactionReceipt,
    TransactionSignatureRequest,
)
from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    Crypto,
    CustomerId,
    OrderId,
    PaymentId,
    TransactionHash,
    WalletAddress,
)


NOW = datetime(2026, 5, 10, 9, 30, tzinfo=UTC)
EXPIRES_AT = NOW + timedelta(minutes=15)
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")
TX_HASH = TransactionHash("0x" + "ab" * 32)
REFUND_TX_HASH = TransactionHash("0x" + "cd" * 32)


def test_wallet_signature_verifier_recovers_normalized_wallet_address() -> None:
    client = FakeWalletSignatureClient("0xABCDabcdABCDabcdABCDabcdABCDabcdABCDabcd")
    verifier = ClientWalletSignatureVerifier(client)

    recovered = verifier.recover_address("Sign in to Token Payments", "0xsignature")

    assert recovered == WalletAddress("0xabcdabcdabcdabcdabcdabcdabcdabcdabcdabcd")
    assert client.calls == [("Sign in to Token Payments", "0xsignature")]


def test_blockchain_adapter_maps_gas_estimate_and_receipt_payloads() -> None:
    client = FakeBlockchainClient(receipt=_receipt_payload())
    adapter = ClientBlockchainAdapter(client)

    estimate = adapter.estimate_gas(_amount(), WALLET_FROM, WALLET_TO, CHAIN)
    receipt = adapter.get_transaction_receipt(TX_HASH)

    assert estimate == GasEstimate(
        estimated_fee=Crypto(
            amount="0.0042",
            symbol="ETH",
            chain_id=CHAIN.chain_id,
            token_address=None,
            decimals=18,
        ),
        gas_limit=21000,
        buffer_rate=Decimal("0.125"),
    )
    assert receipt == TransactionReceipt(hash=TX_HASH, block_number=123456, gas_used=21000)
    assert client.estimate_requests == [
        {
            "amount": {
                "amount": "1.25",
                "symbol": "USDC",
                "chain_id": CHAIN.chain_id,
                "token_address": str(TOKEN_ADDRESS),
                "decimals": 6,
            },
            "wallet_from": str(WALLET_FROM),
            "wallet_to": str(WALLET_TO),
            "chain_id": CHAIN.chain_id,
            "chain_name": CHAIN.name,
        }
    ]
    assert client.receipt_requests == [{"tx_hash": str(TX_HASH)}]


def test_blockchain_adapter_returns_none_for_missing_receipt() -> None:
    adapter = ClientBlockchainAdapter(FakeBlockchainClient(receipt=None))

    assert adapter.get_transaction_receipt(TX_HASH) is None


def test_transaction_service_maps_signature_request_and_refund_receipt() -> None:
    client = FakeTransactionClient()
    service = ClientTransactionService(client)
    payment = _confirmed_payment()

    signature_request = service.create_signature_request(PAYMENT_ID, _amount(), WALLET_TO, EXPIRES_AT)
    refund_receipt = service.refund_payment(payment)

    assert signature_request == TransactionSignatureRequest(
        request_id="client-request-123",
        amount=_amount(),
        to=WALLET_TO,
        expires_at=EXPIRES_AT,
    )
    assert refund_receipt == TransactionReceipt(hash=REFUND_TX_HASH, block_number=123466, gas_used=31000)
    assert client.signature_requests == [
        {
            "payment_id": str(PAYMENT_ID),
            "amount": {
                "amount": "1.25",
                "symbol": "USDC",
                "chain_id": CHAIN.chain_id,
                "token_address": str(TOKEN_ADDRESS),
                "decimals": 6,
            },
            "wallet_to": str(WALLET_TO),
            "expires_at": EXPIRES_AT.isoformat(),
        }
    ]
    assert client.refund_requests == [
        {
            "payment_id": str(PAYMENT_ID),
            "order_id": str(ORDER_ID),
            "amount": {
                "amount": "1.25",
                "symbol": "USDC",
                "chain_id": CHAIN.chain_id,
                "token_address": str(TOKEN_ADDRESS),
                "decimals": 6,
            },
            "wallet_from": str(WALLET_TO),
            "wallet_to": str(WALLET_FROM),
            "chain_id": CHAIN.chain_id,
            "chain_name": CHAIN.name,
            "tx_hash": str(TX_HASH),
        }
    ]


def test_wallet_blockchain_env_uses_placeholders_without_private_key_config() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "ADAPTER_WALLET_SIGNATURE_DOMAIN=token-payments.local" in env_example
    assert "ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL=" in env_example
    assert "ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID=1337" in env_example
    assert "ADAPTER_AUTH_WALLET_SIGNATURE_TIMEOUT_SECONDS=3" in env_example
    assert "ADAPTER_BLOCKCHAIN_RPC_SCHEME=http" in env_example
    assert "ADAPTER_BLOCKCHAIN_RPC_HOST=test_network" in env_example
    assert "ADAPTER_BLOCKCHAIN_RPC_PORT=8545" in env_example
    assert "ADAPTER_BLOCKCHAIN_RPC_URL=" in env_example
    assert "ADAPTER_BLOCKCHAIN_DEPLOYED_CONTRACTS_PATH=/var/chainDB/deployed_contracts.json" in env_example
    assert "ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS" not in env_example
    assert "ADAPTER_BLOCKCHAIN_PRIVATE_KEY" not in env_example
    assert "ADAPTER_BLOCKCHAIN_SEED_PHRASE" not in env_example


def _amount() -> Crypto:
    return Crypto(
        amount="1.25",
        symbol="USDC",
        chain_id=CHAIN.chain_id,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )


def _receipt_payload() -> dict[str, object]:
    return {
        "hash": str(TX_HASH),
        "blockNumber": 123456,
        "gasUsed": 21000,
    }


def _confirmed_payment() -> Payment:
    receipt = TransactionReceipt(hash=TX_HASH, block_number=123456, gas_used=21000)
    return (
        Payment.initialize_payment(
            payment_id=PAYMENT_ID,
            order_id=ORDER_ID,
            customer_id=CUSTOMER_ID,
            amount=_amount(),
            wallet_from=WALLET_FROM,
            wallet_to=WALLET_TO,
            chain_network=CHAIN,
            gas_estimate=None,
            expires_at=EXPIRES_AT,
            status=PaymentStatus.AWAITING_SIGNATURE,
        )
        .submit_tx_hash(TX_HASH)
        .confirm_payment(receipt)
    )


class FakeWalletSignatureClient:
    def __init__(self, recovered_address: str) -> None:
        self.recovered_address = recovered_address
        self.calls: list[tuple[str, str]] = []

    def recover_address(self, message: str, signature: str) -> str:
        self.calls.append((message, signature))
        return self.recovered_address


class FakeBlockchainClient:
    def __init__(self, receipt: dict[str, object] | None) -> None:
        self.receipt = receipt
        self.estimate_requests: list[dict[str, object]] = []
        self.receipt_requests: list[dict[str, object]] = []

    def estimate_gas(self, **request: object) -> dict[str, object]:
        self.estimate_requests.append(dict(request))
        return {
            "estimatedFee": {
                "amount": "0.0042",
                "symbol": "ETH",
                "chainId": CHAIN.chain_id,
                "tokenAddress": None,
                "decimals": 18,
            },
            "gasLimit": 21000,
            "bufferRate": "0.125",
        }

    def get_transaction_receipt(self, **request: object) -> dict[str, object] | None:
        self.receipt_requests.append(dict(request))
        return self.receipt


class FakeTransactionClient:
    def __init__(self) -> None:
        self.signature_requests: list[dict[str, object]] = []
        self.refund_requests: list[dict[str, object]] = []

    def create_signature_request(self, **request: object) -> dict[str, object]:
        self.signature_requests.append(dict(request))
        return {
            "requestId": "client-request-123",
            "amount": request["amount"],
            "to": request["wallet_to"],
            "expiresAt": request["expires_at"],
        }

    def refund_payment(self, **request: object) -> dict[str, object]:
        self.refund_requests.append(dict(request))
        return {
            "hash": str(REFUND_TX_HASH),
            "blockNumber": 123466,
            "gasUsed": 31000,
        }

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.domain.wallet import WalletId  # noqa: E402
from token_payments.contexts.payment.adapter._chain_mapping import (  # noqa: E402
    erc20_transfer_request,
    verify_transfer_receipt,
)
from token_payments.contexts.payment.application import (  # noqa: E402
    ConfirmPaymentReceiptCommand,
    InitiatePaymentCommand,
    PaymentCommandHandler,
    PaymentCommandStatus,
)
from token_payments.contexts.payment.domain import GasEstimate, PaymentStatus, TransactionReceipt  # noqa: E402
from token_payments.shared.domain import ChainNetwork, CommandId, Crypto, CustomerId, MessageId, OrderId, PaymentId, TransactionHash, UserId, WalletAddress  # noqa: E402


NOW = datetime(2026, 5, 22, 6, 0, tzinfo=UTC)
EXPIRES_AT = NOW + timedelta(minutes=15)
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9c01")
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9c02")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9c03")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9c04")
PAYER_WALLET_ID = WalletId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9c05")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN = WalletAddress("0x4444444444444444444444444444444444444444")
CHAIN = ChainNetwork(1337, "Local")
TX_HASH = TransactionHash("0x" + "ab" * 32)


def test_erc20_authorization_preserves_expected_wallet_asset_and_minor_units() -> None:
    handler = _handler(FakeBlockchainAdapter(_transfer_receipt()))

    result = handler.initiate_payment(_initiate_command())

    assert result.status is PaymentCommandStatus.AWAITING_SIGNATURE
    assert result.authorization is not None
    assert result.authorization.payer_wallet_id == PAYER_WALLET_ID
    assert result.authorization.payment_asset_id == "local-usdc"
    assert result.authorization.expected_amount_minor_units == 1_250_000
    assert result.authorization.signature_request.transfer_type == "ERC20_TRANSFER"
    assert result.authorization.signature_request.token_address == TOKEN
    assert result.authorization.signature_request.amount_minor_units == 1_250_000


def test_erc20_transfer_request_and_receipt_verification_validate_terms() -> None:
    request = erc20_transfer_request(
        token_address=TOKEN,
        wallet_from=WALLET_FROM,
        wallet_to=WALLET_TO,
        amount_minor_units=1_250_000,
        chain_id=1337,
    )

    assert request["to"] == str(TOKEN)
    assert request["from"] == str(WALLET_FROM)
    assert request["value"] == "0x0"
    assert request["data"].startswith("0xa9059cbb")
    assert verify_transfer_receipt(
        _transfer_receipt(),
        token_address=TOKEN,
        wallet_from=WALLET_FROM,
        wallet_to=WALLET_TO,
        amount_minor_units=1_250_000,
    ) == {
        "verified": True,
        "reason": None,
        "observedTransfer": {
            "tokenAddress": str(TOKEN),
            "from": str(WALLET_FROM),
            "to": str(WALLET_TO),
            "amountMinorUnits": "1250000",
        },
    }
    assert verify_transfer_receipt(
        _transfer_receipt(token=str(WalletAddress("0x5555555555555555555555555555555555555555"))),
        token_address=TOKEN,
        wallet_from=WALLET_FROM,
        wallet_to=WALLET_TO,
        amount_minor_units=1_250_000,
    )["reason"] == "WRONG_TOKEN"


def test_confirmation_fails_erc20_payment_when_transfer_log_does_not_match_authorization_terms() -> None:
    handler = _handler(FakeBlockchainAdapter(_transfer_receipt(to=str(WalletAddress("0x7777777777777777777777777777777777777777")))))
    handler.initiate_payment(_initiate_command())
    payment = handler.submit_transaction_hash(
        type(
            "Submit",
            (),
            {
                "command_id": CommandId(f"{ORDER_ID}:SubmitTransactionHashCommand"),
                "payment_id": PAYMENT_ID,
                "order_id": ORDER_ID,
                "tx_hash": TX_HASH,
                "submitted_at": NOW,
                "causation_id": None,
            },
        )()
    ).payment

    result = handler.confirm_payment_receipt(
        ConfirmPaymentReceiptCommand(
            command_id=CommandId(f"{ORDER_ID}:ConfirmPaymentReceiptCommand"),
            payment_id=PAYMENT_ID,
            order_id=ORDER_ID,
            checked_at=NOW,
        )
    )

    assert payment is not None and payment.status is PaymentStatus.SUBMITTED
    assert result.status is PaymentCommandStatus.FAILED
    assert result.payment is not None
    assert result.payment.failure_reason == "ERC20_TRANSFER_MISMATCH: WRONG_RECIPIENT"


def _initiate_command() -> InitiatePaymentCommand:
    return InitiatePaymentCommand(
        command_id=CommandId.for_order_action(ORDER_ID, "InitiatePaymentCommand"),
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        user_id=USER_ID,
        amount=Crypto("1.25", "USDC", 1337, TOKEN, 6),
        wallet_from=WALLET_FROM,
        wallet_to=WALLET_TO,
        chain_network=CHAIN,
        expires_at=EXPIRES_AT,
        requested_at=NOW,
        payer_wallet_id=PAYER_WALLET_ID,
        payment_asset_id="local-usdc",
        event_message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc9c06"),
    )


def _handler(blockchain: "FakeBlockchainAdapter") -> PaymentCommandHandler:
    return PaymentCommandHandler(
        payment_repository=FakePaymentRepository(),
        authorization_repository=FakeAuthorizationRepository(),
        processed_commands=FakeProcessedCommandRepository(),
        outbox_messages=FakeOutboxRepository(),
        blockchain_adapter=blockchain,
        timeout_scheduler=FakeTimeoutScheduler(),
        transaction_service=FakeTransactionService(),
    )


def _transfer_receipt(
    *,
    token: str | None = None,
    from_address: str | None = None,
    to: str | None = None,
    amount: int = 1_250_000,
) -> dict[str, object]:
    return {
        "hash": str(TX_HASH),
        "blockNumber": 123,
        "gasUsed": 65000,
        "status": "0x1",
        "logs": [
            {
                "address": token or str(TOKEN),
                "topics": [
                    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                    "0x" + str(from_address or WALLET_FROM).removeprefix("0x").rjust(64, "0"),
                    "0x" + str(to or WALLET_TO).removeprefix("0x").rjust(64, "0"),
                ],
                "data": hex(amount),
            }
        ],
    }


class FakePaymentRepository:
    def __init__(self) -> None:
        self.payments: dict[PaymentId, object] = {}

    def get(self, payment_id: PaymentId) -> object | None:
        return self.payments.get(payment_id)

    def save(self, payment: object) -> None:
        self.payments[payment.payment_id] = payment


class FakeAuthorizationRepository:
    def __init__(self) -> None:
        self.authorizations: dict[PaymentId, object] = {}

    def get(self, payment_id: PaymentId) -> object | None:
        return self.authorizations.get(payment_id)

    def save(self, authorization: object) -> None:
        self.authorizations[authorization.payment_id] = authorization


class FakeProcessedCommandRepository:
    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        return False

    def record(self, processed_command: object) -> None:
        return None


class FakeOutboxRepository:
    def save(self, message: object) -> None:
        return None


class FakeBlockchainAdapter:
    def __init__(self, receipt: dict[str, object]) -> None:
        self.receipt = receipt

    def estimate_gas(self, amount: Crypto, wallet_from: WalletAddress, wallet_to: WalletAddress, chain_network: ChainNetwork) -> GasEstimate:
        return GasEstimate(Crypto("0.01", "ETH", chain_network.chain_id, None, 18), 65000, Decimal("0.10"))

    def get_transaction_receipt(self, tx_hash: TransactionHash) -> TransactionReceipt | dict[str, object] | None:
        return self.receipt


class FakeTimeoutScheduler:
    def schedule_expiration(self, payment_id: PaymentId, expires_at: datetime) -> None:
        return None

    def cancel_expiration(self, payment_id: PaymentId) -> None:
        return None


class FakeTransactionService:
    def create_signature_request(self, payment_id: PaymentId, amount: Crypto, wallet_to: WalletAddress, expires_at: datetime) -> object:
        from token_payments.contexts.payment.domain import TransactionSignatureRequest

        return TransactionSignatureRequest.for_payment_terms(
            request_id=str(payment_id),
            amount=amount,
            to=wallet_to,
            expires_at=expires_at,
            payment_asset_id="local-usdc",
        )

    def refund_payment(self, payment: object) -> TransactionReceipt:
        return TransactionReceipt("0x" + "cd" * 32, 124, 65000)

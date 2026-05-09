"""Application port contracts for the payment bounded context."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from token_payments.contexts.payment.domain import (
    GasEstimate,
    Payment,
    PaymentAuthorization,
    TransactionReceipt,
    TransactionSignatureRequest,
)
from token_payments.shared.domain import (
    ChainNetwork,
    CommandId,
    Crypto,
    OutboxMessage,
    PaymentId,
    ProcessedCommand,
    TransactionHash,
    WalletAddress,
)


class PaymentRepository(Protocol):
    def get(self, payment_id: PaymentId) -> Payment | None:
        ...

    def save(self, payment: Payment) -> None:
        ...


class PaymentAuthorizationRepository(Protocol):
    def get(self, payment_id: PaymentId) -> PaymentAuthorization | None:
        ...

    def save(self, authorization: PaymentAuthorization) -> None:
        ...


class ProcessedCommandRepository(Protocol):
    def was_processed(self, command_id: CommandId, handler: str) -> bool:
        ...

    def record(self, processed_command: ProcessedCommand) -> None:
        ...


class OutboxMessageRepository(Protocol):
    def save(self, message: OutboxMessage) -> None:
        ...


class BlockchainAdapter(Protocol):
    def estimate_gas(
        self,
        amount: Crypto,
        wallet_from: WalletAddress,
        wallet_to: WalletAddress,
        chain_network: ChainNetwork,
    ) -> GasEstimate:
        ...

    def get_transaction_receipt(self, tx_hash: TransactionHash) -> TransactionReceipt | None:
        ...


class PaymentTimeoutScheduler(Protocol):
    def schedule_expiration(self, payment_id: PaymentId, expires_at: datetime) -> None:
        ...

    def cancel_expiration(self, payment_id: PaymentId) -> None:
        ...


class TransactionService(Protocol):
    def create_signature_request(
        self,
        payment_id: PaymentId,
        amount: Crypto,
        wallet_to: WalletAddress,
        expires_at: datetime,
    ) -> TransactionSignatureRequest:
        ...

    def refund_payment(self, payment: Payment) -> TransactionReceipt:
        ...

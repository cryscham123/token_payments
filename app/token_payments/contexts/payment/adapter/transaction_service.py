"""Transaction service adapter boundary backed by an injected client."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from token_payments.contexts.payment.domain import Payment, TransactionReceipt, TransactionSignatureRequest
from token_payments.shared.domain import Crypto, PaymentId, WalletAddress

from ._chain_mapping import (
    call_client,
    payment_refund_payload,
    receipt_from_payload,
    signature_request_from_payload,
    signature_request_payload,
)


class ClientTransactionService:
    """Create signature requests and refund transactions through an injected client."""

    def __init__(self, client: Any) -> None:
        if client is None:
            raise ValueError("ClientTransactionService requires a client")
        self._client = client

    def create_signature_request(
        self,
        payment_id: PaymentId,
        amount: Crypto,
        wallet_to: WalletAddress,
        expires_at: datetime,
    ) -> TransactionSignatureRequest:
        if not isinstance(payment_id, PaymentId):
            raise ValueError("ClientTransactionService.create_signature_request requires a PaymentId")
        if not isinstance(amount, Crypto):
            raise ValueError("ClientTransactionService.create_signature_request requires a Crypto amount")
        if not isinstance(wallet_to, WalletAddress):
            raise ValueError("ClientTransactionService.create_signature_request requires wallet_to as WalletAddress")
        request = signature_request_payload(payment_id, amount, wallet_to, expires_at)
        response = call_client(self._client, "create_signature_request", request)
        return signature_request_from_payload(
            response,
            amount=amount,
            wallet_to=wallet_to,
            expires_at=expires_at,
        )

    def refund_payment(self, payment: Payment) -> TransactionReceipt:
        request = payment_refund_payload(payment)
        response = call_client(self._client, "refund_payment", request)
        receipt = receipt_from_payload(response)
        if receipt is None:
            raise ValueError("refund_payment client must return a transaction receipt")
        return receipt


TransactionService = ClientTransactionService

__all__ = ["ClientTransactionService", "TransactionService"]

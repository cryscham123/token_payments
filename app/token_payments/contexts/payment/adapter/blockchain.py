"""Blockchain adapter boundary backed by an injected client."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from token_payments.contexts.payment.domain import GasEstimate, TransactionReceipt
from token_payments.shared.domain import ChainNetwork, Crypto, TransactionHash, WalletAddress

from ._chain_mapping import call_client, estimate_request, gas_estimate_from_payload, receipt_from_payload


class ClientBlockchainAdapter:
    """Map injected blockchain client payloads into payment domain values."""

    def __init__(self, client: Any, *, default_buffer_rate: Decimal | str | int = Decimal("0")) -> None:
        if client is None:
            raise ValueError("ClientBlockchainAdapter requires a client")
        self._client = client
        self._default_buffer_rate = default_buffer_rate if isinstance(default_buffer_rate, Decimal) else Decimal(str(default_buffer_rate))

    def estimate_gas(
        self,
        amount: Crypto,
        wallet_from: WalletAddress,
        wallet_to: WalletAddress,
        chain_network: ChainNetwork,
    ) -> GasEstimate:
        if not isinstance(amount, Crypto):
            raise ValueError("ClientBlockchainAdapter.estimate_gas requires a Crypto amount")
        if not isinstance(wallet_from, WalletAddress):
            raise ValueError("ClientBlockchainAdapter.estimate_gas requires wallet_from as WalletAddress")
        if not isinstance(wallet_to, WalletAddress):
            raise ValueError("ClientBlockchainAdapter.estimate_gas requires wallet_to as WalletAddress")
        request = estimate_request(amount, wallet_from, wallet_to, chain_network)
        response = call_client(self._client, "estimate_gas", request)
        return gas_estimate_from_payload(
            response,
            default_chain_id=chain_network.chain_id,
            default_buffer_rate=self._default_buffer_rate,
        )

    def get_transaction_receipt(self, tx_hash: TransactionHash) -> TransactionReceipt | None:
        if not isinstance(tx_hash, TransactionHash):
            raise ValueError("ClientBlockchainAdapter.get_transaction_receipt requires a TransactionHash")
        response = call_client(self._client, "get_transaction_receipt", {"tx_hash": str(tx_hash)})
        return receipt_from_payload(response)


BlockchainAdapter = ClientBlockchainAdapter

__all__ = ["BlockchainAdapter", "ClientBlockchainAdapter"]

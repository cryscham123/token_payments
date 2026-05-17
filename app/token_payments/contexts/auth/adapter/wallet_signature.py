"""Wallet signature verification adapter boundary."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from token_payments.contexts.auth.application.ports import (
    WalletSignatureVerificationFailure,
    WalletSignatureVerificationResult,
)
from token_payments.shared.domain import WalletAddress


class ClientWalletSignatureVerifier:
    """Verify EOA wallet signatures through an injected recovery client."""

    def __init__(self, client: Any, *, supported_chain_ids: Iterable[int] | None = None) -> None:
        if client is None:
            raise ValueError("ClientWalletSignatureVerifier requires a client")
        self._client = client
        self._supported_chain_ids = _normalize_supported_chain_ids(supported_chain_ids)

    def verify_signature(
        self,
        wallet: WalletAddress,
        message: str,
        signature: str,
        chain_id: int,
    ) -> WalletSignatureVerificationResult:
        wallet = _coerce_wallet(wallet)
        message = _require_text(message, "message")
        signature = _require_text(signature, "signature")
        chain_id = _require_positive_int(chain_id, "chain_id")
        if self._supported_chain_ids is not None and chain_id not in self._supported_chain_ids:
            return WalletSignatureVerificationResult.failed(
                WalletSignatureVerificationFailure.UNSUPPORTED_CHAIN
            )
        try:
            recovered = self.recover_address(message, signature)
        except Exception:
            return WalletSignatureVerificationResult.failed(
                WalletSignatureVerificationFailure.INVALID_SIGNATURE
            )
        if recovered != wallet:
            return WalletSignatureVerificationResult.failed(
                WalletSignatureVerificationFailure.WALLET_MISMATCH
            )
        return WalletSignatureVerificationResult.verified()

    def recover_address(self, message: str, signature: str) -> WalletAddress:
        message = _require_text(message, "message")
        signature = _require_text(signature, "signature")
        recovered = _recover_address(self._client, message, signature)
        return recovered if isinstance(recovered, WalletAddress) else WalletAddress(str(recovered))


WalletSignatureVerifier = ClientWalletSignatureVerifier

__all__ = ["ClientWalletSignatureVerifier", "WalletSignatureVerifier"]


def _recover_address(client: Any, message: str, signature: str) -> WalletAddress | str:
    recover = getattr(client, "recover_address", None)
    if not callable(recover):
        recover = getattr(client, "recover_message", None)
    if not callable(recover):
        raise TypeError("wallet signature client must expose recover_address or recover_message")
    try:
        return recover(message, signature)
    except TypeError:
        return recover(message=message, signature=signature)


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _coerce_wallet(value: WalletAddress | str) -> WalletAddress:
    return value if isinstance(value, WalletAddress) else WalletAddress(value)


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _normalize_supported_chain_ids(value: Iterable[int] | None) -> frozenset[int] | None:
    if value is None:
        return None
    chain_ids = frozenset(_require_positive_int(chain_id, "supported_chain_id") for chain_id in value)
    if not chain_ids:
        raise ValueError("supported_chain_ids must not be empty when provided")
    return chain_ids

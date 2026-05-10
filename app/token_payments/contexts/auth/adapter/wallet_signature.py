"""Wallet signature verification adapter boundary."""

from __future__ import annotations

from typing import Any

from token_payments.shared.domain import WalletAddress


class ClientWalletSignatureVerifier:
    """Recover MetaMask wallet addresses through an injected client."""

    def __init__(self, client: Any) -> None:
        if client is None:
            raise ValueError("ClientWalletSignatureVerifier requires a client")
        self._client = client

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

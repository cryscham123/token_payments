"""Authentication adapter layer."""

from .wallet_signature import ClientWalletSignatureVerifier, WalletSignatureVerifier

__all__ = ["ClientWalletSignatureVerifier", "WalletSignatureVerifier"]

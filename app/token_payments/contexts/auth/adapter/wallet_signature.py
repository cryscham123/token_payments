"""Wallet signature verification adapter boundary."""

from __future__ import annotations

from collections.abc import Iterable
import importlib
from typing import Any

from token_payments.contexts.auth.application.ports import (
    WalletSignatureVerificationFailure,
    WalletSignatureVerificationResult,
)
from token_payments.shared.domain import WalletAddress


ERC1271_MAGIC_VALUE = "0x1626ba7e"
_ERC1271_IS_VALID_SIGNATURE_SELECTOR = bytes.fromhex(ERC1271_MAGIC_VALUE[2:])
_PROVIDER_UNAVAILABLE = object()
_PROVIDER_ERROR = object()


class ClientWalletSignatureVerifier:
    """Verify EOA and deployed ERC-1271 wallet signatures through an injected client."""

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
        code = _get_code(self._client, wallet, chain_id)
        if code is _PROVIDER_ERROR:
            return WalletSignatureVerificationResult.failed(
                WalletSignatureVerificationFailure.INVALID_SIGNATURE
            )
        if code is not _PROVIDER_UNAVAILABLE and _has_deployed_code(code):
            return self._verify_contract_signature(wallet, message, signature, chain_id)
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

    def _verify_contract_signature(
        self,
        wallet: WalletAddress,
        message: str,
        signature: str,
        chain_id: int,
    ) -> WalletSignatureVerificationResult:
        try:
            digest = _personal_sign_digest(message)
            calldata = _erc1271_is_valid_signature_calldata(digest, signature)
            response = _call_client_method(
                self._client,
                "call_contract",
                {"to": str(wallet), "data": calldata, "chain_id": chain_id},
            )
        except Exception:
            return WalletSignatureVerificationResult.failed(
                WalletSignatureVerificationFailure.INVALID_SIGNATURE
            )
        if _is_erc1271_magic_response(response):
            return WalletSignatureVerificationResult.verified()
        return WalletSignatureVerificationResult.failed(
            WalletSignatureVerificationFailure.INVALID_SIGNATURE
        )

    def recover_address(self, message: str, signature: str) -> WalletAddress:
        message = _require_text(message, "message")
        signature = _require_text(signature, "signature")
        recovered = _recover_address(self._client, message, signature)
        return recovered if isinstance(recovered, WalletAddress) else WalletAddress(str(recovered))


WalletSignatureVerifier = ClientWalletSignatureVerifier

__all__ = ["ClientWalletSignatureVerifier", "ERC1271_MAGIC_VALUE", "WalletSignatureVerifier"]


def _get_code(client: Any, wallet: WalletAddress, chain_id: int) -> object:
    get_code = getattr(client, "get_code", None)
    if not callable(get_code):
        return _PROVIDER_UNAVAILABLE
    try:
        return _call_client_method(client, "get_code", {"address": str(wallet), "chain_id": chain_id})
    except Exception:
        return _PROVIDER_ERROR


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


def _call_client_method(client: Any, method_name: str, request: dict[str, object]) -> Any:
    method = getattr(client, method_name, None)
    if not callable(method):
        raise TypeError(f"wallet signature client must expose {method_name}")
    try:
        return method(**dict(request))
    except TypeError as keyword_error:
        try:
            return method(dict(request))
        except TypeError:
            try:
                if method_name == "get_code":
                    return method(request["address"], request["chain_id"])
                if method_name == "call_contract":
                    return method(request["to"], request["data"], request["chain_id"])
            except TypeError:
                pass
            raise keyword_error


def _has_deployed_code(value: object) -> bool:
    if isinstance(value, dict) and "result" in value:
        value = value["result"]
    if value is None:
        return False
    if isinstance(value, bytes):
        return len(value) > 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized not in {"", "0x", "0x0"}
    return bool(value)


def _personal_sign_digest(message: str) -> bytes:
    messages_module = importlib.import_module("eth_account.messages")
    encoded = messages_module.encode_defunct(text=_require_text(message, "message"))
    hash_eip191_message = getattr(messages_module, "_hash_eip191_message", None)
    if callable(hash_eip191_message):
        digest = hash_eip191_message(encoded)
    else:
        keccak = importlib.import_module("eth_utils.crypto").keccak
        digest = keccak(b"\x19" + encoded.version + encoded.header + encoded.body)
    digest_bytes = bytes(digest)
    if len(digest_bytes) != 32:
        raise ValueError("personal_sign digest must be 32 bytes")
    return digest_bytes


def _erc1271_is_valid_signature_calldata(digest: bytes, signature: str) -> str:
    if len(digest) != 32:
        raise ValueError("ERC-1271 digest must be 32 bytes")
    signature_bytes = _hex_to_bytes(signature, "signature")
    offset = (64).to_bytes(32, "big")
    length = len(signature_bytes).to_bytes(32, "big")
    padding_length = (32 - (len(signature_bytes) % 32)) % 32
    calldata = (
        _ERC1271_IS_VALID_SIGNATURE_SELECTOR
        + digest
        + offset
        + length
        + signature_bytes
        + (b"\x00" * padding_length)
    )
    return "0x" + calldata.hex()


def _is_erc1271_magic_response(value: object) -> bool:
    if isinstance(value, dict) and "result" in value:
        value = value["result"]
    if isinstance(value, bytes):
        response = value
    elif isinstance(value, str):
        response = _hex_to_bytes(value, "ERC-1271 response")
    else:
        return False
    if len(response) == 4:
        return response == _ERC1271_IS_VALID_SIGNATURE_SELECTOR
    if len(response) == 32:
        return (
            response[:4] == _ERC1271_IS_VALID_SIGNATURE_SELECTOR
            and response[4:] == b"\x00" * 28
        )
    return False


def _hex_to_bytes(value: str, field_name: str) -> bytes:
    text = _require_text(value, field_name)
    raw = text[2:] if text.startswith(("0x", "0X")) else text
    if len(raw) % 2 != 0:
        raw = f"0{raw}"
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be hex encoded") from exc


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

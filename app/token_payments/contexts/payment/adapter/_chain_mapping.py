"""Mapping helpers for injected blockchain clients."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from token_payments.contexts.payment.domain import (
    GasEstimate,
    Payment,
    TransactionReceipt,
    TransactionSignatureRequest,
)
from token_payments.shared.domain import ChainNetwork, Crypto, TransactionHash, WalletAddress


_MISSING = object()


def crypto_to_payload(value: Crypto) -> dict[str, object]:
    if not isinstance(value, Crypto):
        raise ValueError("crypto_to_payload requires a Crypto value")
    return {
        "amount": str(value.amount),
        "symbol": value.symbol,
        "chain_id": value.chain_id,
        "token_address": str(value.token_address) if value.token_address is not None else None,
        "decimals": value.decimals,
    }


def crypto_from_payload(payload: Crypto | Mapping[str, Any] | object, *, default_chain_id: int | None = None) -> Crypto:
    if isinstance(payload, Crypto):
        return payload
    chain_id = _field(payload, "chain_id", "chainId", default=default_chain_id)
    if chain_id is None:
        raise ValueError("Crypto payload requires chain_id")
    token_address = _field(payload, "token_address", "tokenAddress", default=None)
    return Crypto(
        amount=_field(payload, "amount"),
        symbol=str(_field(payload, "symbol")),
        chain_id=_coerce_int(chain_id, "chain_id"),
        token_address=None if token_address in {None, ""} else WalletAddress(str(token_address)),
        decimals=_coerce_int(_field(payload, "decimals"), "decimals"),
    )


def gas_estimate_from_payload(
    payload: GasEstimate | Mapping[str, Any] | object,
    *,
    default_chain_id: int,
    default_buffer_rate: Decimal,
) -> GasEstimate:
    if isinstance(payload, GasEstimate):
        return payload
    max_fee_payload = _field(payload, "max_fee", "maxFee", default=None)
    return GasEstimate(
        estimated_fee=crypto_from_payload(
            _field(payload, "estimated_fee", "estimatedFee", "fee"),
            default_chain_id=default_chain_id,
        ),
        gas_limit=_coerce_int(_field(payload, "gas_limit", "gasLimit"), "gas_limit"),
        buffer_rate=_coerce_decimal(
            _field(payload, "buffer_rate", "bufferRate", default=default_buffer_rate),
            "buffer_rate",
        ),
        max_fee=None
        if max_fee_payload is None
        else crypto_from_payload(max_fee_payload, default_chain_id=default_chain_id),
    )


def receipt_from_payload(payload: TransactionReceipt | Mapping[str, Any] | object | None) -> TransactionReceipt | None:
    if payload is None:
        return None
    if isinstance(payload, TransactionReceipt):
        return payload
    return TransactionReceipt(
        hash=TransactionHash(str(_field(payload, "hash", "tx_hash", "txHash", "transactionHash"))),
        block_number=_coerce_int(_field(payload, "block_number", "blockNumber"), "block_number"),
        gas_used=_coerce_int(_field(payload, "gas_used", "gasUsed"), "gas_used"),
    )


def signature_request_from_payload(
    payload: TransactionSignatureRequest | Mapping[str, Any] | object,
    *,
    amount: Crypto,
    wallet_to: WalletAddress,
    expires_at: datetime,
) -> TransactionSignatureRequest:
    if isinstance(payload, TransactionSignatureRequest):
        return payload
    raw_expires_at = _field(payload, "expires_at", "expiresAt", default=expires_at)
    return TransactionSignatureRequest(
        request_id=str(_field(payload, "request_id", "requestId", "id")),
        amount=crypto_from_payload(_field(payload, "amount", default=amount), default_chain_id=amount.chain_id),
        to=WalletAddress(str(_field(payload, "to", "wallet_to", "walletTo", default=str(wallet_to)))),
        expires_at=_coerce_datetime(raw_expires_at, "expires_at"),
    )


def payment_refund_payload(payment: Payment) -> dict[str, object]:
    if not isinstance(payment, Payment):
        raise ValueError("payment_refund_payload requires a Payment")
    if payment.tx_hash is None:
        raise ValueError("refund payment requires an original tx_hash")
    return {
        "payment_id": str(payment.payment_id),
        "order_id": str(payment.order_id),
        "amount": crypto_to_payload(payment.amount),
        "wallet_from": str(payment.wallet_to),
        "wallet_to": str(payment.wallet_from),
        "chain_id": payment.chain_network.chain_id,
        "chain_name": payment.chain_network.name,
        "tx_hash": str(payment.tx_hash),
    }


def call_client(client: Any, method_name: str, request: Mapping[str, object]) -> Any:
    method = getattr(client, method_name, None)
    if not callable(method):
        raise TypeError(f"client must expose {method_name}")
    try:
        return method(**dict(request))
    except TypeError as keyword_error:
        try:
            return method(dict(request))
        except TypeError:
            raise keyword_error


def estimate_request(
    amount: Crypto,
    wallet_from: WalletAddress,
    wallet_to: WalletAddress,
    chain_network: ChainNetwork,
) -> dict[str, object]:
    if not isinstance(chain_network, ChainNetwork):
        raise ValueError("estimate_request requires a ChainNetwork")
    return {
        "amount": crypto_to_payload(amount),
        "wallet_from": str(wallet_from),
        "wallet_to": str(wallet_to),
        "chain_id": chain_network.chain_id,
        "chain_name": chain_network.name,
    }


def signature_request_payload(
    payment_id: object,
    amount: Crypto,
    wallet_to: WalletAddress,
    expires_at: datetime,
) -> dict[str, object]:
    return {
        "payment_id": str(payment_id),
        "amount": crypto_to_payload(amount),
        "wallet_to": str(wallet_to),
        "expires_at": expires_at.isoformat(),
    }


def _field(payload: Mapping[str, Any] | object, *names: str, default: Any = _MISSING) -> Any:
    for name in names:
        if isinstance(payload, Mapping) and name in payload:
            return payload[name]
        if not isinstance(payload, Mapping) and hasattr(payload, name):
            return getattr(payload, name)
    if default is not _MISSING:
        return default
    joined = "/".join(names)
    raise ValueError(f"payload missing required field {joined}")


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _coerce_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field_name} must be decimal-compatible") from exc


def _coerce_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO datetime") from exc
    raise ValueError(f"{field_name} must be a datetime")

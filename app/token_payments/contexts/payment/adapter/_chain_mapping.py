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
    raw_logs = _field(payload, "logs", default=())
    logs = tuple(raw_logs) if isinstance(raw_logs, list | tuple) else ()
    raw_status = _field(payload, "status", default=None)
    status = None if raw_status is None else (_hex_int(raw_status) if isinstance(raw_status, str) else int(raw_status))
    return TransactionReceipt(
        hash=TransactionHash(str(_field(payload, "hash", "tx_hash", "txHash", "transactionHash"))),
        block_number=_coerce_int(_field(payload, "block_number", "blockNumber"), "block_number"),
        gas_used=_coerce_int(_field(payload, "gas_used", "gasUsed"), "gas_used"),
        logs=logs,
        status=status,
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
        payment_asset_id=_field(payload, "payment_asset_id", "paymentAssetId", default=None),
        transfer_type=_field(payload, "transfer_type", "transferType", default=None),
        token_address=_field(payload, "token_address", "tokenAddress", default=None),
        amount_minor_units=_field(payload, "amount_minor_units", "amountMinorUnits", default=None),
        chain_id=_field(payload, "chain_id", "chainId", default=None),
    )


def payment_refund_payload(payment: Payment) -> dict[str, object]:
    if not isinstance(payment, Payment):
        raise ValueError("payment_refund_payload requires a Payment")
    if payment.tx_hash is None:
        raise ValueError("refund payment requires an original tx_hash")
    payload: dict[str, object] = {
        "payment_id": str(payment.payment_id),
        "order_id": str(payment.order_id),
        "amount": crypto_to_payload(payment.amount),
        "wallet_from": str(payment.wallet_to),
        "wallet_to": str(payment.wallet_from),
        "chain_id": payment.chain_network.chain_id,
        "chain_name": payment.chain_network.name,
        "tx_hash": str(payment.tx_hash),
    }
    if payment.payment_asset_id is not None:
        payload["payment_asset_id"] = payment.payment_asset_id
    if payment.payer_wallet_id is not None:
        payload["payer_wallet_id"] = str(payment.payer_wallet_id)
    return payload


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


def erc20_transfer_request(
    *,
    token_address: WalletAddress,
    wallet_from: WalletAddress,
    wallet_to: WalletAddress,
    amount_minor_units: int,
    chain_id: int,
) -> dict[str, object]:
    if not isinstance(token_address, WalletAddress):
        raise ValueError("token_address must be a WalletAddress")
    if not isinstance(wallet_from, WalletAddress):
        raise ValueError("wallet_from must be a WalletAddress")
    if not isinstance(wallet_to, WalletAddress):
        raise ValueError("wallet_to must be a WalletAddress")
    if isinstance(amount_minor_units, bool) or not isinstance(amount_minor_units, int) or amount_minor_units < 0:
        raise ValueError("amount_minor_units must be a non-negative integer")
    if isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id <= 0:
        raise ValueError("chain_id must be a positive integer")
    return {
        "from": str(wallet_from),
        "to": str(token_address),
        "value": "0x0",
        "data": _erc20_transfer_data(str(wallet_to), amount_minor_units),
        "chain_id": chain_id,
    }


def verify_transfer_receipt(
    receipt: Mapping[str, Any],
    *,
    token_address: WalletAddress,
    wallet_from: WalletAddress,
    wallet_to: WalletAddress,
    amount_minor_units: int,
) -> dict[str, Any]:
    status = receipt.get("status")
    if status is not None and _hex_int(status) == 0:
        return {"verified": False, "reason": "REVERTED", "observedTransfer": None}
    logs = receipt.get("logs")
    if not isinstance(logs, list | tuple):
        return {"verified": False, "reason": "TRANSFER_LOG_MISSING", "observedTransfer": None}
    wrong_token_seen = False
    for log in logs:
        if not isinstance(log, Mapping):
            continue
        address = str(log.get("address") or "").lower()
        if address != str(token_address):
            wrong_token_seen = True
            continue
        topics = log.get("topics")
        if not isinstance(topics, list | tuple) or len(topics) < 3:
            continue
        if str(topics[0]).lower() != "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef":
            continue
        observed_from = _topic_address(str(topics[1]))
        observed_to = _topic_address(str(topics[2]))
        observed_amount = _hex_int(log.get("data", "0x0"))
        observed = {
            "tokenAddress": str(token_address),
            "from": observed_from,
            "to": observed_to,
            "amountMinorUnits": str(observed_amount),
        }
        if observed_from != str(wallet_from):
            return {"verified": False, "reason": "WRONG_PAYER", "observedTransfer": observed}
        if observed_to != str(wallet_to):
            return {"verified": False, "reason": "WRONG_RECIPIENT", "observedTransfer": observed}
        if observed_amount < amount_minor_units:
            return {"verified": False, "reason": "INSUFFICIENT_AMOUNT", "observedTransfer": observed}
        return {"verified": True, "reason": None, "observedTransfer": observed}
    reason = "WRONG_TOKEN" if wrong_token_seen else "TRANSFER_LOG_MISSING"
    return {"verified": False, "reason": reason, "observedTransfer": None}


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


def _crypto_minor_units(value: Crypto) -> int:
    scale = Decimal(10) ** value.decimals
    scaled = value.amount * scale
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError("amount has more decimal precision than the token decimals allow")
    return int(integral)


def _erc20_transfer_data(wallet_to: str, amount_minor_units: int) -> str:
    address = wallet_to.removeprefix("0x").removeprefix("0X").lower()
    if len(address) != 40:
        raise ValueError("wallet_to must be an Ethereum address")
    return "0xa9059cbb" + address.rjust(64, "0") + hex(amount_minor_units)[2:].rjust(64, "0")


def _topic_address(topic: str) -> str:
    normalized = topic.removeprefix("0x").removeprefix("0X")
    return "0x" + normalized[-40:].lower()


def _hex_int(value: object) -> int:
    if isinstance(value, str):
        return int(value, 16) if value.startswith("0x") else int(value)
    return int(value)

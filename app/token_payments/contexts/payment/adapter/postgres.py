"""PostgreSQL aggregate repositories for the payment context."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from token_payments.contexts.payment.domain import (
    AuthorizationStatus,
    GasEstimate,
    Payment,
    PaymentAuthorization,
    PaymentStatus,
    TransactionReceipt,
    TransactionSignatureRequest,
)
from token_payments.contexts.payment.application.queries import PaymentHistoryItem
from token_payments.contexts.order.domain import TrackingId
from token_payments.shared.adapter.postgres import PostgresConnection
from token_payments.shared.domain import (
    ChainNetwork,
    Crypto,
    CustomerId,
    OrderId,
    PaymentId,
    TransactionHash,
    UserId,
    WalletAddress,
)


SELECT_PAYMENT_SQL = """
SELECT
    payment_id,
    order_id,
    customer_id,
    amount_numeric,
    amount_symbol,
    amount_chain_id,
    amount_token_address,
    amount_decimals,
    status,
    wallet_from,
    wallet_to,
    chain_id,
    payer_wallet_id,
    payment_asset_id,
    tx_hash,
    gas_estimated_fee,
    gas_fee_symbol,
    gas_fee_chain_id,
    gas_fee_token_address,
    gas_fee_decimals,
    gas_limit,
    gas_buffer_rate,
    gas_max_fee,
    receipt_block_number,
    receipt_gas_used,
    failure_reason,
    refund_tx_hash,
    refund_block_number,
    refund_gas_used,
    expires_at
FROM payments
WHERE payment_id = %(payment_id)s
"""

SELECT_RECEIPT_POLLING_CANDIDATES_SQL = """
SELECT
    payment_id,
    order_id,
    customer_id,
    amount_numeric,
    amount_symbol,
    amount_chain_id,
    amount_token_address,
    amount_decimals,
    status,
    wallet_from,
    wallet_to,
    chain_id,
    payer_wallet_id,
    payment_asset_id,
    tx_hash,
    gas_estimated_fee,
    gas_fee_symbol,
    gas_fee_chain_id,
    gas_fee_token_address,
    gas_fee_decimals,
    gas_limit,
    gas_buffer_rate,
    gas_max_fee,
    receipt_block_number,
    receipt_gas_used,
    failure_reason,
    refund_tx_hash,
    refund_block_number,
    refund_gas_used,
    expires_at
FROM payments
WHERE status IN ('SUBMITTED', 'CONFIRMING')
  AND tx_hash IS NOT NULL
  AND receipt_block_number IS NULL
ORDER BY updated_at ASC, payment_id ASC
LIMIT %(limit)s
"""

SELECT_PAYMENT_HISTORY_FOR_USER_SQL = """
SELECT
    p.payment_id,
    p.order_id,
    o.tracking_id,
    p.customer_id,
    p.amount_numeric,
    p.amount_symbol,
    p.amount_chain_id,
    p.amount_token_address,
    p.amount_decimals,
    p.status,
    p.wallet_from,
    p.wallet_to,
    p.chain_id,
    p.payer_wallet_id,
    p.payment_asset_id,
    p.tx_hash,
    p.gas_estimated_fee,
    p.gas_fee_symbol,
    p.gas_fee_chain_id,
    p.gas_fee_token_address,
    p.gas_fee_decimals,
    p.gas_limit,
    p.gas_buffer_rate,
    p.gas_max_fee,
    p.receipt_block_number,
    p.receipt_gas_used,
    p.failure_reason,
    p.refund_tx_hash,
    p.refund_block_number,
    p.refund_gas_used,
    p.expires_at,
    p.updated_at
FROM payments p
JOIN orders o ON o.order_id = p.order_id
JOIN order_customers c ON c.customer_id = p.customer_id
WHERE c.user_id = %(user_id)s
ORDER BY p.updated_at DESC, p.payment_id DESC
LIMIT %(limit)s
"""

SELECT_PAYMENT_HISTORY_FOR_USER_BY_STATUS_SQL = """
SELECT
    p.payment_id,
    p.order_id,
    o.tracking_id,
    p.customer_id,
    p.amount_numeric,
    p.amount_symbol,
    p.amount_chain_id,
    p.amount_token_address,
    p.amount_decimals,
    p.status,
    p.wallet_from,
    p.wallet_to,
    p.chain_id,
    p.payer_wallet_id,
    p.payment_asset_id,
    p.tx_hash,
    p.gas_estimated_fee,
    p.gas_fee_symbol,
    p.gas_fee_chain_id,
    p.gas_fee_token_address,
    p.gas_fee_decimals,
    p.gas_limit,
    p.gas_buffer_rate,
    p.gas_max_fee,
    p.receipt_block_number,
    p.receipt_gas_used,
    p.failure_reason,
    p.refund_tx_hash,
    p.refund_block_number,
    p.refund_gas_used,
    p.expires_at,
    p.updated_at
FROM payments p
JOIN orders o ON o.order_id = p.order_id
JOIN order_customers c ON c.customer_id = p.customer_id
WHERE c.user_id = %(user_id)s
  AND p.status = ANY(%(statuses)s)
ORDER BY p.updated_at DESC, p.payment_id DESC
LIMIT %(limit)s
"""

UPSERT_PAYMENT_SQL = """
INSERT INTO payments (
    payment_id,
    order_id,
    customer_id,
    amount_numeric,
    amount_symbol,
    amount_chain_id,
    amount_token_address,
    amount_decimals,
    status,
    wallet_from,
    wallet_to,
    chain_id,
    payer_wallet_id,
    payment_asset_id,
    tx_hash,
    gas_estimated_fee,
    gas_fee_symbol,
    gas_fee_chain_id,
    gas_fee_token_address,
    gas_fee_decimals,
    gas_limit,
    gas_buffer_rate,
    gas_max_fee,
    receipt_block_number,
    receipt_gas_used,
    failure_reason,
    refund_tx_hash,
    refund_block_number,
    refund_gas_used,
    expires_at
) VALUES (
    %(payment_id)s,
    %(order_id)s,
    %(customer_id)s,
    %(amount_numeric)s,
    %(amount_symbol)s,
    %(amount_chain_id)s,
    %(amount_token_address)s,
    %(amount_decimals)s,
    %(status)s,
    %(wallet_from)s,
    %(wallet_to)s,
    %(chain_id)s,
    %(payer_wallet_id)s,
    %(payment_asset_id)s,
    %(tx_hash)s,
    %(gas_estimated_fee)s,
    %(gas_fee_symbol)s,
    %(gas_fee_chain_id)s,
    %(gas_fee_token_address)s,
    %(gas_fee_decimals)s,
    %(gas_limit)s,
    %(gas_buffer_rate)s,
    %(gas_max_fee)s,
    %(receipt_block_number)s,
    %(receipt_gas_used)s,
    %(failure_reason)s,
    %(refund_tx_hash)s,
    %(refund_block_number)s,
    %(refund_gas_used)s,
    %(expires_at)s
)
ON CONFLICT (payment_id) DO UPDATE SET
    order_id = EXCLUDED.order_id,
    customer_id = EXCLUDED.customer_id,
    amount_numeric = EXCLUDED.amount_numeric,
    amount_symbol = EXCLUDED.amount_symbol,
    amount_chain_id = EXCLUDED.amount_chain_id,
    amount_token_address = EXCLUDED.amount_token_address,
    amount_decimals = EXCLUDED.amount_decimals,
    status = EXCLUDED.status,
    wallet_from = EXCLUDED.wallet_from,
    wallet_to = EXCLUDED.wallet_to,
    chain_id = EXCLUDED.chain_id,
    payer_wallet_id = EXCLUDED.payer_wallet_id,
    payment_asset_id = EXCLUDED.payment_asset_id,
    tx_hash = EXCLUDED.tx_hash,
    gas_estimated_fee = EXCLUDED.gas_estimated_fee,
    gas_fee_symbol = EXCLUDED.gas_fee_symbol,
    gas_fee_chain_id = EXCLUDED.gas_fee_chain_id,
    gas_fee_token_address = EXCLUDED.gas_fee_token_address,
    gas_fee_decimals = EXCLUDED.gas_fee_decimals,
    gas_limit = EXCLUDED.gas_limit,
    gas_buffer_rate = EXCLUDED.gas_buffer_rate,
    gas_max_fee = EXCLUDED.gas_max_fee,
    receipt_block_number = EXCLUDED.receipt_block_number,
    receipt_gas_used = EXCLUDED.receipt_gas_used,
    failure_reason = EXCLUDED.failure_reason,
    refund_tx_hash = EXCLUDED.refund_tx_hash,
    refund_block_number = EXCLUDED.refund_block_number,
    refund_gas_used = EXCLUDED.refund_gas_used,
    expires_at = EXCLUDED.expires_at,
    updated_at = now()
"""

SELECT_AUTHORIZATION_SQL = """
SELECT
    payment_id,
    user_id,
    payer_wallet_id,
    wallet_address,
    chain_id,
    payment_asset_id,
    expected_amount_minor_units,
    request_id,
    amount_numeric,
    amount_symbol,
    amount_chain_id,
    amount_token_address,
    amount_decimals,
    to_wallet_address,
    status,
    tx_hash,
    expires_at,
    authorized_at
FROM payment_authorizations
WHERE payment_id = %(payment_id)s
"""

UPSERT_AUTHORIZATION_SQL = """
INSERT INTO payment_authorizations (
    payment_id,
    user_id,
    payer_wallet_id,
    wallet_address,
    chain_id,
    payment_asset_id,
    expected_amount_minor_units,
    request_id,
    amount_numeric,
    amount_symbol,
    amount_chain_id,
    amount_token_address,
    amount_decimals,
    to_wallet_address,
    status,
    tx_hash,
    expires_at,
    authorized_at
) VALUES (
    %(payment_id)s,
    %(user_id)s,
    %(payer_wallet_id)s,
    %(wallet_address)s,
    %(chain_id)s,
    %(payment_asset_id)s,
    %(expected_amount_minor_units)s,
    %(request_id)s,
    %(amount_numeric)s,
    %(amount_symbol)s,
    %(amount_chain_id)s,
    %(amount_token_address)s,
    %(amount_decimals)s,
    %(to_wallet_address)s,
    %(status)s,
    %(tx_hash)s,
    %(expires_at)s,
    %(authorized_at)s
)
ON CONFLICT (payment_id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    payer_wallet_id = EXCLUDED.payer_wallet_id,
    wallet_address = EXCLUDED.wallet_address,
    chain_id = EXCLUDED.chain_id,
    payment_asset_id = EXCLUDED.payment_asset_id,
    expected_amount_minor_units = EXCLUDED.expected_amount_minor_units,
    request_id = EXCLUDED.request_id,
    amount_numeric = EXCLUDED.amount_numeric,
    amount_symbol = EXCLUDED.amount_symbol,
    amount_chain_id = EXCLUDED.amount_chain_id,
    amount_token_address = EXCLUDED.amount_token_address,
    amount_decimals = EXCLUDED.amount_decimals,
    to_wallet_address = EXCLUDED.to_wallet_address,
    status = EXCLUDED.status,
    tx_hash = EXCLUDED.tx_hash,
    expires_at = EXCLUDED.expires_at,
    authorized_at = EXCLUDED.authorized_at,
    updated_at = now()
"""


class PostgresPaymentRepository:
    """Persist Payment aggregates inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get(self, payment_id: PaymentId) -> Payment | None:
        if not isinstance(payment_id, PaymentId):
            raise ValueError("PostgresPaymentRepository.get requires a PaymentId")
        row = _fetch_one(self._connection.execute(SELECT_PAYMENT_SQL, {"payment_id": str(payment_id)}))
        if row is None:
            return None
        return _row_to_payment(row)

    def list_receipt_polling_candidates(self, *, limit: int) -> tuple[Payment, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("PostgresPaymentRepository.list_receipt_polling_candidates requires positive limit")
        result = self._connection.execute(SELECT_RECEIPT_POLLING_CANDIDATES_SQL, {"limit": limit})
        return tuple(_row_to_payment(row) for row in _fetch_all(result))

    def save(self, payment: Payment) -> None:
        if not isinstance(payment, Payment):
            raise ValueError("PostgresPaymentRepository.save requires a Payment")

        params = {
            "payment_id": str(payment.payment_id),
            "order_id": str(payment.order_id),
            "customer_id": str(payment.customer_id),
            **_crypto_params("amount", payment.amount),
            "status": payment.status.value,
            "wallet_from": str(payment.wallet_from),
            "wallet_to": str(payment.wallet_to),
            "chain_id": payment.chain_network.chain_id,
            "chain_name": payment.chain_network.name,
            "payer_wallet_id": str(payment.payer_wallet_id) if payment.payer_wallet_id is not None else None,
            "payment_asset_id": payment.payment_asset_id,
            "tx_hash": str(payment.tx_hash) if payment.tx_hash is not None else None,
            **_gas_params(payment.gas_estimate),
            "receipt_block_number": payment.receipt.block_number if payment.receipt is not None else None,
            "receipt_gas_used": payment.receipt.gas_used if payment.receipt is not None else None,
            "failure_reason": payment.failure_reason,
            "refund_tx_hash": str(payment.refund_receipt.hash) if payment.refund_receipt is not None else None,
            "refund_block_number": (
                payment.refund_receipt.block_number if payment.refund_receipt is not None else None
            ),
            "refund_gas_used": payment.refund_receipt.gas_used if payment.refund_receipt is not None else None,
            "expires_at": payment.expires_at,
        }
        self._connection.execute(UPSERT_PAYMENT_SQL, params)


class PostgresPaymentHistoryQuery:
    """Read a customer's payment history from the public payment read model."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def list_for_user(
        self,
        user_id: UserId,
        *,
        statuses: tuple[PaymentStatus, ...] | None = None,
        limit: int = 50,
    ) -> tuple[PaymentHistoryItem, ...]:
        if not isinstance(user_id, UserId):
            raise ValueError("PostgresPaymentHistoryQuery.list_for_user requires a UserId")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("PostgresPaymentHistoryQuery.list_for_user requires a positive limit")
        params: dict[str, Any] = {"user_id": str(user_id), "limit": limit}
        sql = SELECT_PAYMENT_HISTORY_FOR_USER_SQL
        if statuses:
            normalized_statuses = tuple(PaymentStatus(status) for status in statuses)
            params["statuses"] = [status.value for status in normalized_statuses]
            sql = SELECT_PAYMENT_HISTORY_FOR_USER_BY_STATUS_SQL
        return tuple(_history_item_from_row(row) for row in _fetch_all(self._connection.execute(sql, params)))


class PostgresPaymentAuthorizationRepository:
    """Persist PaymentAuthorization aggregates inside an injected transaction."""

    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def get(self, payment_id: PaymentId) -> PaymentAuthorization | None:
        if not isinstance(payment_id, PaymentId):
            raise ValueError("PostgresPaymentAuthorizationRepository.get requires a PaymentId")
        row = _fetch_one(self._connection.execute(SELECT_AUTHORIZATION_SQL, {"payment_id": str(payment_id)}))
        if row is None:
            return None
        payment_asset_id = _optional_row_value(row, "payment_asset_id")
        expected_amount_minor_units = _optional_int_row_value(row, "expected_amount_minor_units")
        include_transfer_terms = payment_asset_id is not None or expected_amount_minor_units is not None
        signature_request = TransactionSignatureRequest(
            request_id=str(_row_value(row, "request_id")),
            amount=_crypto_from_row(row, "amount"),
            to=WalletAddress(_row_value(row, "to_wallet_address")),
            expires_at=_row_value(row, "expires_at"),
            payment_asset_id=payment_asset_id,
            transfer_type=(
                "ERC20_TRANSFER" if _row_value(row, "amount_token_address") is not None else "NATIVE_TRANSFER"
            )
            if include_transfer_terms
            else None,
            token_address=_row_value(row, "amount_token_address") if include_transfer_terms else None,
            amount_minor_units=expected_amount_minor_units,
            chain_id=int(_row_value(row, "chain_id")) if include_transfer_terms else None,
        )
        return PaymentAuthorization(
            payment_id=PaymentId(_row_value(row, "payment_id")),
            user_id=UserId(_row_value(row, "user_id")),
            wallet=WalletAddress(_row_value(row, "wallet_address")),
            chain_network=_chain_network_from_row(row),
            signature_request=signature_request,
            status=AuthorizationStatus(_row_value(row, "status")),
            tx_hash=_optional_tx_hash(_row_value(row, "tx_hash")),
            authorized_at=_row_value(row, "authorized_at"),
            payer_wallet_id=_optional_row_value(row, "payer_wallet_id"),
            payment_asset_id=payment_asset_id,
            expected_amount_minor_units=expected_amount_minor_units,
        )

    def save(self, authorization: PaymentAuthorization) -> None:
        if not isinstance(authorization, PaymentAuthorization):
            raise ValueError("PostgresPaymentAuthorizationRepository.save requires a PaymentAuthorization")

        signature_request = authorization.signature_request
        params = {
            "payment_id": str(authorization.payment_id),
            "user_id": str(authorization.user_id),
            "payer_wallet_id": str(authorization.payer_wallet_id) if authorization.payer_wallet_id is not None else None,
            "wallet_address": str(authorization.wallet),
            "chain_id": authorization.chain_network.chain_id,
            "chain_name": authorization.chain_network.name,
            "payment_asset_id": authorization.payment_asset_id,
            "expected_amount_minor_units": authorization.expected_amount_minor_units,
            "request_id": signature_request.request_id,
            **_crypto_params("amount", signature_request.amount),
            "to_wallet_address": str(signature_request.to),
            "status": authorization.status.value,
            "tx_hash": str(authorization.tx_hash) if authorization.tx_hash is not None else None,
            "expires_at": signature_request.expires_at,
            "authorized_at": authorization.authorized_at,
        }
        self._connection.execute(UPSERT_AUTHORIZATION_SQL, params)


def _row_to_payment(row: Mapping[str, Any] | object) -> Payment:
    return Payment(
        payment_id=PaymentId(_row_value(row, "payment_id")),
        order_id=OrderId(_row_value(row, "order_id")),
        customer_id=CustomerId(_row_value(row, "customer_id")),
        amount=_crypto_from_row(row, "amount"),
        wallet_from=WalletAddress(_row_value(row, "wallet_from")),
        wallet_to=WalletAddress(_row_value(row, "wallet_to")),
        chain_network=_chain_network_from_row(row),
        gas_estimate=_gas_estimate_from_row(row),
        expires_at=_row_value(row, "expires_at"),
        status=PaymentStatus(_row_value(row, "status")),
        tx_hash=_optional_tx_hash(_row_value(row, "tx_hash")),
        receipt=_receipt_from_row(row, "tx_hash", "receipt_block_number", "receipt_gas_used"),
        failure_reason=_row_value(row, "failure_reason"),
        refund_receipt=_receipt_from_row(row, "refund_tx_hash", "refund_block_number", "refund_gas_used"),
        payer_wallet_id=_optional_row_value(row, "payer_wallet_id"),
        payment_asset_id=_optional_row_value(row, "payment_asset_id"),
    )


def _history_item_from_row(row: Mapping[str, Any] | object) -> PaymentHistoryItem:
    return PaymentHistoryItem(
        payment_id=PaymentId(_row_value(row, "payment_id")),
        order_id=OrderId(_row_value(row, "order_id")),
        tracking_id=TrackingId(_row_value(row, "tracking_id")),
        amount=_crypto_from_row(row, "amount"),
        wallet_from=WalletAddress(_row_value(row, "wallet_from")),
        wallet_to=WalletAddress(_row_value(row, "wallet_to")),
        chain_network=_chain_network_from_row(row),
        status=PaymentStatus(_row_value(row, "status")),
        tx_hash=_optional_tx_hash(_row_value(row, "tx_hash")),
        receipt=_receipt_from_row(row, "tx_hash", "receipt_block_number", "receipt_gas_used"),
        failure_reason=_row_value(row, "failure_reason"),
        payment_asset_id=_optional_row_value(row, "payment_asset_id"),
        updated_at=_row_value(row, "updated_at"),
    )


def _crypto_params(prefix: str, value: Crypto) -> dict[str, Any]:
    return {
        f"{prefix}_numeric": value.amount,
        f"{prefix}_symbol": value.symbol,
        f"{prefix}_chain_id": value.chain_id,
        f"{prefix}_token_address": str(value.token_address) if value.token_address is not None else None,
        f"{prefix}_decimals": value.decimals,
    }


def _crypto_from_row(row: Mapping[str, Any] | object, prefix: str) -> Crypto:
    return Crypto(
        amount=_row_value(row, f"{prefix}_numeric"),
        symbol=str(_row_value(row, f"{prefix}_symbol")),
        chain_id=int(_row_value(row, f"{prefix}_chain_id")),
        token_address=_row_value(row, f"{prefix}_token_address"),
        decimals=int(_row_value(row, f"{prefix}_decimals")),
    )


def _gas_params(gas_estimate: GasEstimate | None) -> dict[str, Any]:
    if gas_estimate is None:
        return {
            "gas_estimated_fee": None,
            "gas_fee_symbol": None,
            "gas_fee_chain_id": None,
            "gas_fee_token_address": None,
            "gas_fee_decimals": None,
            "gas_limit": None,
            "gas_buffer_rate": None,
            "gas_max_fee": None,
        }

    estimated_fee = gas_estimate.estimated_fee
    return {
        "gas_estimated_fee": estimated_fee.amount,
        "gas_fee_symbol": estimated_fee.symbol,
        "gas_fee_chain_id": estimated_fee.chain_id,
        "gas_fee_token_address": str(estimated_fee.token_address) if estimated_fee.token_address is not None else None,
        "gas_fee_decimals": estimated_fee.decimals,
        "gas_limit": gas_estimate.gas_limit,
        "gas_buffer_rate": gas_estimate.buffer_rate,
        "gas_max_fee": gas_estimate.max_fee.amount if gas_estimate.max_fee is not None else None,
    }


def _gas_estimate_from_row(row: Mapping[str, Any] | object) -> GasEstimate | None:
    if _row_value(row, "gas_estimated_fee") is None:
        return None
    estimated_fee = Crypto(
        amount=_row_value(row, "gas_estimated_fee"),
        symbol=str(_row_value(row, "gas_fee_symbol")),
        chain_id=int(_row_value(row, "gas_fee_chain_id")),
        token_address=_row_value(row, "gas_fee_token_address"),
        decimals=int(_row_value(row, "gas_fee_decimals")),
    )
    max_fee_amount = _row_value(row, "gas_max_fee")
    max_fee = None
    if max_fee_amount is not None:
        max_fee = Crypto(
            amount=max_fee_amount,
            symbol=estimated_fee.symbol,
            chain_id=estimated_fee.chain_id,
            token_address=estimated_fee.token_address,
            decimals=estimated_fee.decimals,
        )
    return GasEstimate(
        estimated_fee=estimated_fee,
        gas_limit=int(_row_value(row, "gas_limit")),
        buffer_rate=Decimal(str(_row_value(row, "gas_buffer_rate"))),
        max_fee=max_fee,
    )


def _receipt_from_row(
    row: Mapping[str, Any] | object,
    hash_key: str,
    block_number_key: str,
    gas_used_key: str,
) -> TransactionReceipt | None:
    tx_hash = _optional_tx_hash(_row_value(row, hash_key))
    block_number = _row_value(row, block_number_key)
    gas_used = _row_value(row, gas_used_key)
    if block_number is None and gas_used is None and (tx_hash is None or hash_key == "tx_hash"):
        return None
    if tx_hash is None or block_number is None or gas_used is None:
        raise ValueError("payment receipt row must include hash, block number, and gas used")
    return TransactionReceipt(hash=tx_hash, block_number=int(block_number), gas_used=int(gas_used))


def _optional_tx_hash(value: Any) -> TransactionHash | None:
    if value is None:
        return None
    return TransactionHash(value)


def _chain_network_from_row(row: Mapping[str, Any] | object) -> ChainNetwork:
    chain_id = int(_row_value(row, "chain_id"))
    name = _optional_row_value(row, "chain_name") or f"chain-{chain_id}"
    return ChainNetwork(chain_id=chain_id, name=name)


def _optional_row_value(row: Mapping[str, Any] | object, key: str) -> str | None:
    if isinstance(row, Mapping):
        value = row.get(key)
    else:
        value = getattr(row, key, None)
    return str(value) if value is not None else None


def _optional_int_row_value(row: Mapping[str, Any] | object, key: str) -> int | None:
    if isinstance(row, Mapping):
        value = row.get(key)
    else:
        value = getattr(row, key, None)
    return int(value) if value is not None else None


def _fetch_one(result: Any) -> Any:
    if result is None:
        return None
    fetchone = getattr(result, "fetchone", None)
    if callable(fetchone):
        return fetchone()
    iterator = iter(result)
    return next(iterator, None)


def _fetch_all(result: Any) -> tuple[Any, ...]:
    if result is None:
        return ()
    fetchall = getattr(result, "fetchall", None)
    if callable(fetchall):
        return tuple(fetchall())
    return tuple(result)


def _row_value(row: Mapping[str, Any] | object, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return getattr(row, key)

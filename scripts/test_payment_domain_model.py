from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.payment.domain import (  # noqa: E402
    AuthorizationStatus,
    GasEstimate,
    Payment,
    PaymentAuthorization,
    PaymentConfirmedEvent,
    PaymentExpiredEvent,
    PaymentFailedEvent,
    PaymentProcessingStartedEvent,
    PaymentRefundedEvent,
    PaymentStatus,
    TransactionReceipt,
    TransactionSignatureRequest,
)
from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    Crypto,
    CustomerId,
    OrderId,
    PaymentId,
    TransactionHash,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
EXPIRES_AT = NOW + timedelta(minutes=15)
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")
TX_HASH = TransactionHash("0x" + "ab" * 32)
OTHER_TX_HASH = TransactionHash("0x" + "cd" * 32)


def test_initialize_payment_requires_timezone_aware_expiry_and_start_status() -> None:
    initiated = _payment(status=PaymentStatus.INITIATED)
    awaiting = _payment(status=PaymentStatus.AWAITING_SIGNATURE)

    assert initiated.status == PaymentStatus.INITIATED
    assert awaiting.status == PaymentStatus.AWAITING_SIGNATURE
    assert awaiting.expires_at == EXPIRES_AT
    assert awaiting.expires_at.tzinfo is not None

    with pytest.raises(ValueError):
        Payment.initialize_payment(
            payment_id=PAYMENT_ID,
            order_id=ORDER_ID,
            customer_id=CUSTOMER_ID,
            amount=_amount(),
            wallet_from=WALLET_FROM,
            wallet_to=WALLET_TO,
            chain_network=CHAIN,
            gas_estimate=_gas_estimate().apply_buffer(),
            expires_at=datetime(2026, 5, 9, 12, 15),
        )

    with pytest.raises(ValueError):
        Payment.initialize_payment(
            payment_id=PAYMENT_ID,
            order_id=ORDER_ID,
            customer_id=CUSTOMER_ID,
            amount=_amount(),
            wallet_from=WALLET_FROM,
            wallet_to=WALLET_TO,
            chain_network=CHAIN,
            gas_estimate=_gas_estimate().apply_buffer(),
            expires_at=EXPIRES_AT,
            status=PaymentStatus.SUBMITTED,
        )


def test_payment_success_path_is_immutable_and_rejects_invalid_transitions() -> None:
    payment = _payment(status=PaymentStatus.INITIATED)

    awaiting = payment.mark_awaiting_signature()
    submitted = awaiting.submit_tx_hash(TX_HASH)
    receipt = TransactionReceipt(hash=TX_HASH, block_number=12345, gas_used=21000)
    confirmed = submitted.confirm_payment(receipt)

    assert payment.status == PaymentStatus.INITIATED
    assert awaiting.status == PaymentStatus.AWAITING_SIGNATURE
    assert submitted.status == PaymentStatus.SUBMITTED
    assert submitted.tx_hash == TX_HASH
    assert confirmed.status == PaymentStatus.CONFIRMED
    assert confirmed.receipt == receipt
    assert confirmed.confirm_payment(receipt) == confirmed
    assert confirmed.fail_payment("late failure") == confirmed

    with pytest.raises(ValueError):
        payment.submit_tx_hash(TX_HASH)

    with pytest.raises(ValueError):
        awaiting.confirm_payment(receipt)

    with pytest.raises(ValueError):
        submitted.submit_tx_hash(OTHER_TX_HASH)


def test_payment_failure_and_expiry_are_guarded_and_idempotent() -> None:
    submitted = _payment(status=PaymentStatus.AWAITING_SIGNATURE).submit_tx_hash(TX_HASH)
    failed = submitted.fail_payment("receipt reverted")

    assert failed.status == PaymentStatus.FAILED
    assert failed.failure_reason == "receipt reverted"
    assert failed.fail_payment("second failure") == failed
    assert failed.mark_awaiting_signature() == failed

    awaiting = _payment(status=PaymentStatus.AWAITING_SIGNATURE)
    with pytest.raises(ValueError):
        awaiting.expire_awaiting_signature(now=NOW)

    expired = awaiting.expire_awaiting_signature(now=EXPIRES_AT, reason="signature timeout")
    assert expired.status == PaymentStatus.EXPIRED
    assert expired.failure_reason == "signature timeout"
    assert expired.expire_awaiting_signature(now=EXPIRES_AT) == expired

    with pytest.raises(ValueError):
        _payment(status=PaymentStatus.INITIATED).expire_awaiting_signature(now=EXPIRES_AT)


def test_force_cancel_resolves_to_cancelled_before_expiry_unlike_timeout() -> None:
    awaiting = _payment(status=PaymentStatus.AWAITING_SIGNATURE)

    # Customer cancel (force=True) is allowed before expires_at and reads as CANCELLED,
    # distinct from a timeout which only fires past expires_at and reads as EXPIRED.
    cancelled = awaiting.expire_awaiting_signature(now=NOW, reason="cancelled by customer", force=True)
    assert cancelled.status == PaymentStatus.CANCELLED
    assert cancelled.failure_reason == "cancelled by customer"
    # Terminal + idempotent.
    assert cancelled.expire_awaiting_signature(now=EXPIRES_AT) == cancelled


def test_refund_payment_transitions_from_confirmed_once() -> None:
    receipt = TransactionReceipt(hash=TX_HASH, block_number=12345, gas_used=21000)
    refund_receipt = TransactionReceipt(hash=OTHER_TX_HASH, block_number=12355, gas_used=31000)
    confirmed = _payment(status=PaymentStatus.AWAITING_SIGNATURE).submit_tx_hash(TX_HASH).confirm_payment(receipt)

    refunded = confirmed.refund_payment(refund_receipt)

    assert refunded.status == PaymentStatus.REFUNDED
    assert refunded.receipt == receipt
    assert refunded.refund_receipt == refund_receipt
    assert refunded.refund_payment(refund_receipt) == refunded

    with pytest.raises(ValueError):
        _payment(status=PaymentStatus.AWAITING_SIGNATURE).refund_payment(refund_receipt)


def test_gas_estimate_applies_buffer_to_max_fee_deterministically() -> None:
    estimate = _gas_estimate(buffer_rate=Decimal("0.20"))

    buffered = estimate.apply_buffer()

    assert estimate.max_fee is None
    assert buffered.estimated_fee == Crypto(
        amount="0.0100",
        symbol="ETH",
        chain_id=11155111,
        token_address=None,
        decimals=18,
    )
    assert buffered.max_fee == Crypto(
        amount=Decimal("0.012000"),
        symbol="ETH",
        chain_id=11155111,
        token_address=None,
        decimals=18,
    )
    assert buffered.apply_buffer() == buffered

    with pytest.raises(ValueError):
        _gas_estimate(gas_limit=0)

    with pytest.raises(ValueError):
        _gas_estimate(buffer_rate=Decimal("-0.01"))


def test_payment_authorization_requests_signature_authorizes_tx_hash_and_expires() -> None:
    authorization = PaymentAuthorization.request_transaction_signature(
        payment_id=PAYMENT_ID,
        user_id=USER_ID,
        wallet=WALLET_FROM,
        chain_network=CHAIN,
        signature_request=_signature_request(),
    )

    authorized = authorization.authorize_tx_hash(TX_HASH, authorized_at=NOW)

    assert authorization.status == AuthorizationStatus.REQUESTED
    assert authorized.status == AuthorizationStatus.AUTHORIZED
    assert authorized.tx_hash == TX_HASH
    assert authorized.authorized_at == NOW
    assert authorized.authorize_tx_hash(TX_HASH, authorized_at=NOW) == authorized

    with pytest.raises(ValueError):
        authorized.authorize_tx_hash(OTHER_TX_HASH, authorized_at=NOW)

    with pytest.raises(ValueError):
        authorization.authorize_tx_hash(TX_HASH, authorized_at=EXPIRES_AT + timedelta(seconds=1))

    with pytest.raises(ValueError):
        authorization.expire(now=NOW)

    expired = authorization.expire(now=EXPIRES_AT)
    assert expired.status == AuthorizationStatus.EXPIRED
    assert expired.expire(now=EXPIRES_AT) == expired
    assert expired.authorize_tx_hash(TX_HASH, authorized_at=EXPIRES_AT) == expired


def test_payment_events_validate_domain_shape() -> None:
    receipt = TransactionReceipt(hash=TX_HASH, block_number=12345, gas_used=21000)
    refund_receipt = TransactionReceipt(hash=OTHER_TX_HASH, block_number=12355, gas_used=31000)
    awaiting = _payment(status=PaymentStatus.AWAITING_SIGNATURE)
    confirmed = awaiting.submit_tx_hash(TX_HASH).confirm_payment(receipt)
    failed = awaiting.fail_payment("wallet rejected")
    refunded = confirmed.refund_payment(refund_receipt)
    expired = awaiting.expire_awaiting_signature(now=EXPIRES_AT)

    assert PaymentProcessingStartedEvent(payment=awaiting, created_at=NOW).payment == awaiting
    assert PaymentConfirmedEvent.from_payment(confirmed, created_at=NOW).receipt == receipt
    assert PaymentFailedEvent.from_payment(failed, created_at=NOW).failure_reason == "wallet rejected"
    assert PaymentRefundedEvent.from_payment(refunded, created_at=NOW).refund_receipt == refund_receipt
    assert PaymentExpiredEvent.from_payment(expired, expired_at=EXPIRES_AT).reason == "signature expired"

    with pytest.raises(ValueError):
        PaymentConfirmedEvent(
            payment_id=PAYMENT_ID,
            order_id=ORDER_ID,
            tx_hash=OTHER_TX_HASH,
            receipt=receipt,
            created_at=NOW,
        )

    with pytest.raises(ValueError):
        PaymentProcessingStartedEvent(payment=awaiting, created_at=datetime(2026, 5, 9, 12, 0))


def test_payment_domain_public_contracts_are_exported() -> None:
    import token_payments.contexts.payment.domain as domain

    assert {
        "AuthorizationStatus",
        "GasEstimate",
        "Payment",
        "PaymentAuthorization",
        "PaymentConfirmedEvent",
        "PaymentExpiredEvent",
        "PaymentFailedEvent",
        "PaymentProcessingStartedEvent",
        "PaymentRefundedEvent",
        "PaymentStatus",
        "TransactionReceipt",
        "TransactionSignatureRequest",
    } <= set(domain.__all__)


def test_payment_domain_does_not_import_external_adapters_or_clients() -> None:
    forbidden_roots = {
        "blockchain",
        "kafka",
        "metamask",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }

    for path in (ROOT / "app/token_payments/contexts/payment/domain").glob("**/*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        assert imports.isdisjoint(forbidden_roots), f"{path} imports adapter dependency: {imports}"


def _amount() -> Crypto:
    return Crypto(
        amount="1.25",
        symbol="USDC",
        chain_id=11155111,
        token_address=WalletAddress("0x3333333333333333333333333333333333333333"),
        decimals=6,
    )


def _gas_estimate(
    gas_limit: int = 21000,
    buffer_rate: Decimal = Decimal("0.10"),
) -> GasEstimate:
    return GasEstimate(
        estimated_fee=Crypto(
            amount="0.0100",
            symbol="ETH",
            chain_id=11155111,
            token_address=None,
            decimals=18,
        ),
        gas_limit=gas_limit,
        buffer_rate=buffer_rate,
    )


def _signature_request() -> TransactionSignatureRequest:
    return TransactionSignatureRequest(
        request_id="payment-request-123",
        amount=_amount(),
        to=WALLET_TO,
        expires_at=EXPIRES_AT,
    )


def _payment(status: PaymentStatus) -> Payment:
    return Payment.initialize_payment(
        payment_id=PAYMENT_ID,
        order_id=ORDER_ID,
        customer_id=CUSTOMER_ID,
        amount=_amount(),
        wallet_from=WALLET_FROM,
        wallet_to=WALLET_TO,
        chain_network=CHAIN,
        gas_estimate=_gas_estimate().apply_buffer(),
        expires_at=EXPIRES_AT,
        status=status,
    )

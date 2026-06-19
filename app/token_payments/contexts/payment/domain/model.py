"""Pure domain model for crypto payment state transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Mapping, Self, TypeAlias

from token_payments.contexts.auth.domain.wallet import WalletId
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


class PaymentStatus(StrEnum):
    INITIATED = "INITIATED"
    AWAITING_SIGNATURE = "AWAITING_SIGNATURE"
    SUBMITTED = "SUBMITTED"
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"


class AuthorizationStatus(StrEnum):
    REQUESTED = "REQUESTED"
    AUTHORIZED = "AUTHORIZED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class PaymentAssetType(StrEnum):
    NATIVE = "NATIVE"
    ERC20 = "ERC20"


@dataclass(frozen=True)
class PaymentChain:
    chain_id: int
    display_name: str
    native_symbol: str
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "chain_id", _coerce_positive_int(self.chain_id, "PaymentChain.chain_id"))
        object.__setattr__(self, "display_name", _require_text(self.display_name, "PaymentChain.display_name"))
        object.__setattr__(self, "native_symbol", _require_text(self.native_symbol, "PaymentChain.native_symbol").upper())
        if not isinstance(self.enabled, bool):
            raise ValueError("PaymentChain.enabled must be a bool")


@dataclass(frozen=True)
class PaymentAsset:
    asset_id: str
    asset_type: PaymentAssetType | str
    chain_id: int
    symbol: str
    decimals: int
    contract_address: WalletAddress | str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _require_text(self.asset_id, "PaymentAsset.asset_id"))
        object.__setattr__(self, "asset_type", _coerce_asset_type(self.asset_type))
        object.__setattr__(self, "chain_id", _coerce_positive_int(self.chain_id, "PaymentAsset.chain_id"))
        object.__setattr__(self, "symbol", _require_text(self.symbol, "PaymentAsset.symbol").upper())
        object.__setattr__(self, "decimals", _coerce_non_negative_int(self.decimals, "PaymentAsset.decimals"))
        if not isinstance(self.enabled, bool):
            raise ValueError("PaymentAsset.enabled must be a bool")
        if self.contract_address is not None:
            object.__setattr__(self, "contract_address", _coerce_wallet(self.contract_address))
        if self.asset_type is PaymentAssetType.NATIVE and self.contract_address is not None:
            raise ValueError("native PaymentAsset must not have contract_address")
        if self.asset_type is PaymentAssetType.ERC20 and self.contract_address is None:
            raise ValueError("ERC20 PaymentAsset requires contract_address")

    @classmethod
    def native(
        cls,
        asset_id: str,
        chain_id: int,
        symbol: str,
        decimals: int,
        contract_address: WalletAddress | str | None = None,
        *,
        enabled: bool = True,
    ) -> Self:
        return cls(
            asset_id=asset_id,
            asset_type=PaymentAssetType.NATIVE,
            chain_id=chain_id,
            symbol=symbol,
            decimals=decimals,
            contract_address=contract_address,
            enabled=enabled,
        )

    @classmethod
    def erc20(
        cls,
        asset_id: str,
        chain_id: int,
        symbol: str,
        decimals: int,
        contract_address: WalletAddress | str | None,
        *,
        enabled: bool = True,
    ) -> Self:
        return cls(
            asset_id=asset_id,
            asset_type=PaymentAssetType.ERC20,
            chain_id=chain_id,
            symbol=symbol,
            decimals=decimals,
            contract_address=contract_address,
            enabled=enabled,
        )

    def crypto(self, amount: Decimal | str | int) -> Crypto:
        return Crypto(
            amount=amount,
            symbol=self.symbol,
            chain_id=self.chain_id,
            token_address=self.contract_address,
            decimals=self.decimals,
        )

    def minor_units(self, amount: Decimal | str | int) -> int:
        amount_decimal = _coerce_decimal(amount, "amount")
        scale = Decimal(10) ** self.decimals
        scaled = amount_decimal * scale
        integral = scaled.to_integral_value()
        if scaled != integral:
            raise ValueError("amount precision exceeds asset decimals")
        if integral < 0:
            raise ValueError("amount must be non-negative")
        return int(integral)


@dataclass(frozen=True)
class PaymentAssetRegistry:
    chains: tuple[PaymentChain, ...]
    assets: tuple[PaymentAsset, ...]

    def __post_init__(self) -> None:
        chains = tuple(self.chains)
        assets = tuple(self.assets)
        if not all(isinstance(chain, PaymentChain) for chain in chains):
            raise ValueError("PaymentAssetRegistry.chains must contain PaymentChain values")
        if not all(isinstance(asset, PaymentAsset) for asset in assets):
            raise ValueError("PaymentAssetRegistry.assets must contain PaymentAsset values")
        chain_ids = [chain.chain_id for chain in chains]
        if len(set(chain_ids)) != len(chain_ids):
            raise ValueError("PaymentAssetRegistry.chains cannot contain duplicate chain_id")
        asset_ids = [asset.asset_id for asset in assets]
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("PaymentAssetRegistry.assets cannot contain duplicate asset_id")
        known_chains = set(chain_ids)
        for asset in assets:
            if asset.chain_id not in known_chains:
                raise ValueError(f"asset {asset.asset_id} references unknown chain {asset.chain_id}")
        object.__setattr__(self, "chains", chains)
        object.__setattr__(self, "assets", assets)

    def require_chain(self, chain_id: int) -> PaymentChain:
        chain_id = _coerce_positive_int(chain_id, "chain_id")
        for chain in self.chains:
            if chain.chain_id == chain_id:
                return chain
        raise ValueError(f"chain {chain_id} is not registered")

    def require_asset(self, asset_id: str) -> PaymentAsset:
        asset_id = _require_text(asset_id, "asset_id")
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        raise ValueError(f"payment asset {asset_id} is not registered")

    def require_enabled_asset(self, asset_id: str) -> PaymentAsset:
        asset = self.require_asset(asset_id)
        if not asset.enabled:
            raise ValueError(f"payment asset {asset_id} is disabled")
        chain = self.require_chain(asset.chain_id)
        if not chain.enabled:
            raise ValueError(f"payment asset {asset_id} chain is disabled")
        return asset

    def crypto_for_asset(self, asset_id: str, amount: Decimal | str | int) -> Crypto:
        return self.require_enabled_asset(asset_id).crypto(amount)

    def minor_units_for_asset(self, asset_id: str, amount: Decimal | str | int) -> int:
        return self.require_asset(asset_id).minor_units(amount)

    def assets_for_chain(self, chain_id: int) -> tuple[PaymentAsset, ...]:
        chain_id = _coerce_positive_int(chain_id, "chain_id")
        return tuple(asset for asset in self.assets if asset.chain_id == chain_id and asset.enabled)


@dataclass(frozen=True)
class GasEstimate:
    estimated_fee: Crypto
    gas_limit: int
    buffer_rate: Decimal | str | int
    max_fee: Crypto | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.estimated_fee, Crypto):
            raise ValueError("GasEstimate.estimated_fee must be a Crypto value")
        object.__setattr__(self, "gas_limit", _coerce_positive_int(self.gas_limit, "GasEstimate.gas_limit"))
        buffer_rate = _coerce_decimal(self.buffer_rate, "GasEstimate.buffer_rate")
        if not buffer_rate.is_finite() or buffer_rate < Decimal("0"):
            raise ValueError("GasEstimate.buffer_rate must be a finite non-negative decimal")
        object.__setattr__(self, "buffer_rate", buffer_rate)

        if self.max_fee is not None:
            if not isinstance(self.max_fee, Crypto):
                raise ValueError("GasEstimate.max_fee must be a Crypto value or None")
            _require_same_asset(self.estimated_fee, self.max_fee, "GasEstimate.max_fee")
            if self.max_fee.amount < self.estimated_fee.amount:
                raise ValueError("GasEstimate.max_fee cannot be less than estimated_fee")

    def apply_buffer(self) -> Self:
        max_fee = Crypto(
            amount=self.estimated_fee.amount * (Decimal("1") + self.buffer_rate),
            symbol=self.estimated_fee.symbol,
            chain_id=self.estimated_fee.chain_id,
            token_address=self.estimated_fee.token_address,
            decimals=self.estimated_fee.decimals,
        )
        if self.max_fee == max_fee:
            return self
        return replace(self, max_fee=max_fee)


@dataclass(frozen=True)
class TransactionReceipt:
    hash: TransactionHash | str
    block_number: int
    gas_used: int
    # Raw event logs and execution status carried through from the chain receipt so
    # downstream ERC-20 transfer verification can inspect the Transfer log. Optional so
    # existing positional construction (hash, block_number, gas_used) keeps working.
    logs: tuple[Mapping[str, Any], ...] = ()
    status: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hash", _coerce_tx_hash(self.hash))
        object.__setattr__(self, "block_number", _coerce_non_negative_int(self.block_number, "block_number"))
        object.__setattr__(self, "gas_used", _coerce_positive_int(self.gas_used, "gas_used"))
        object.__setattr__(self, "logs", tuple(self.logs) if self.logs else ())


@dataclass(frozen=True)
class TransactionSignatureRequest:
    request_id: str
    amount: Crypto
    to: WalletAddress | str
    expires_at: datetime
    payment_asset_id: str | None = None
    transfer_type: str | None = None
    token_address: WalletAddress | str | None = None
    amount_minor_units: int | None = None
    chain_id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require_text(self.request_id, "TransactionSignatureRequest.request_id"))
        if not isinstance(self.amount, Crypto):
            raise ValueError("TransactionSignatureRequest.amount must be a Crypto value")
        object.__setattr__(self, "to", _coerce_wallet(self.to))
        object.__setattr__(
            self,
            "expires_at",
            _require_aware_datetime(self.expires_at, "TransactionSignatureRequest.expires_at"),
        )
        if self.payment_asset_id is not None:
            object.__setattr__(
                self,
                "payment_asset_id",
                _require_text(self.payment_asset_id, "TransactionSignatureRequest.payment_asset_id"),
            )
        if self.transfer_type is not None:
            object.__setattr__(
                self,
                "transfer_type",
                _require_text(self.transfer_type, "TransactionSignatureRequest.transfer_type"),
            )
        if self.token_address is not None:
            object.__setattr__(self, "token_address", _coerce_wallet(self.token_address))
        if self.amount_minor_units is not None:
            object.__setattr__(
                self,
                "amount_minor_units",
                _coerce_non_negative_int(self.amount_minor_units, "TransactionSignatureRequest.amount_minor_units"),
            )
        if self.chain_id is not None:
            object.__setattr__(
                self,
                "chain_id",
                _coerce_positive_int(self.chain_id, "TransactionSignatureRequest.chain_id"),
            )

    @classmethod
    def for_payment_terms(
        cls,
        *,
        request_id: str,
        amount: Crypto,
        to: WalletAddress | str,
        expires_at: datetime,
        payment_asset_id: str | None = None,
    ) -> Self:
        token_address = amount.token_address
        return cls(
            request_id=request_id,
            amount=amount,
            to=to,
            expires_at=expires_at,
            payment_asset_id=payment_asset_id,
            transfer_type="ERC20_TRANSFER" if token_address is not None else "NATIVE_TRANSFER",
            token_address=token_address,
            amount_minor_units=_crypto_minor_units(amount),
            chain_id=amount.chain_id,
        )


@dataclass(frozen=True)
class Payment:
    payment_id: PaymentId
    order_id: OrderId
    customer_id: CustomerId
    amount: Crypto
    wallet_from: WalletAddress | str
    wallet_to: WalletAddress | str
    chain_network: ChainNetwork
    gas_estimate: GasEstimate | None
    expires_at: datetime
    status: PaymentStatus = PaymentStatus.INITIATED
    tx_hash: TransactionHash | str | None = None
    receipt: TransactionReceipt | None = None
    failure_reason: str | None = None
    refund_receipt: TransactionReceipt | None = None
    payer_wallet_id: WalletId | str | None = None
    payment_asset_id: str | None = None
    items: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.payment_id, PaymentId):
            raise ValueError("Payment.payment_id must be a PaymentId")
        if not isinstance(self.order_id, OrderId):
            raise ValueError("Payment.order_id must be an OrderId")
        if not isinstance(self.customer_id, CustomerId):
            raise ValueError("Payment.customer_id must be a CustomerId")
        if not isinstance(self.amount, Crypto):
            raise ValueError("Payment.amount must be a Crypto value")
        object.__setattr__(self, "wallet_from", _coerce_wallet(self.wallet_from))
        object.__setattr__(self, "wallet_to", _coerce_wallet(self.wallet_to))
        if not isinstance(self.chain_network, ChainNetwork):
            raise ValueError("Payment.chain_network must be a ChainNetwork")
        _require_crypto_on_chain(self.amount, self.chain_network, "Payment.amount")
        if self.gas_estimate is not None:
            if not isinstance(self.gas_estimate, GasEstimate):
                raise ValueError("Payment.gas_estimate must be a GasEstimate or None")
            _require_crypto_on_chain(self.gas_estimate.estimated_fee, self.chain_network, "Payment.gas_estimate")
            if self.gas_estimate.max_fee is not None:
                _require_crypto_on_chain(self.gas_estimate.max_fee, self.chain_network, "Payment.gas_estimate.max_fee")
        object.__setattr__(self, "expires_at", _require_aware_datetime(self.expires_at, "Payment.expires_at"))
        object.__setattr__(self, "status", _coerce_payment_status(self.status))
        if self.tx_hash is not None:
            object.__setattr__(self, "tx_hash", _coerce_tx_hash(self.tx_hash))
        if self.receipt is not None and not isinstance(self.receipt, TransactionReceipt):
            raise ValueError("Payment.receipt must be a TransactionReceipt or None")
        if self.refund_receipt is not None and not isinstance(self.refund_receipt, TransactionReceipt):
            raise ValueError("Payment.refund_receipt must be a TransactionReceipt or None")
        if self.failure_reason is not None:
            object.__setattr__(self, "failure_reason", _require_text(self.failure_reason, "Payment.failure_reason"))
        if self.payer_wallet_id is not None and not isinstance(self.payer_wallet_id, WalletId):
            object.__setattr__(self, "payer_wallet_id", WalletId(str(self.payer_wallet_id)))
        if self.payment_asset_id is not None:
            object.__setattr__(self, "payment_asset_id", _require_text(self.payment_asset_id, "Payment.payment_asset_id"))
        object.__setattr__(self, "items", _coerce_items(self.items, "Payment.items"))
        self._validate_status_shape()

    @classmethod
    def initialize_payment(
        cls,
        payment_id: PaymentId,
        order_id: OrderId,
        customer_id: CustomerId,
        amount: Crypto,
        wallet_from: WalletAddress | str,
        wallet_to: WalletAddress | str,
        chain_network: ChainNetwork,
        gas_estimate: GasEstimate | None,
        expires_at: datetime,
        status: PaymentStatus | str = PaymentStatus.INITIATED,
        payer_wallet_id: WalletId | str | None = None,
        payment_asset_id: str | None = None,
        items: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = (),
    ) -> Self:
        status = _coerce_payment_status(status)
        if status not in {PaymentStatus.INITIATED, PaymentStatus.AWAITING_SIGNATURE}:
            raise ValueError("Payment.initialize_payment can only start INITIATED or AWAITING_SIGNATURE payments")
        return cls(
            payment_id=payment_id,
            order_id=order_id,
            customer_id=customer_id,
            amount=amount,
            wallet_from=wallet_from,
            wallet_to=wallet_to,
            chain_network=chain_network,
            gas_estimate=gas_estimate,
            expires_at=expires_at,
            status=status,
            payer_wallet_id=payer_wallet_id,
            payment_asset_id=payment_asset_id,
            items=items,
        )

    def mark_awaiting_signature(self) -> Self:
        if self.status is PaymentStatus.AWAITING_SIGNATURE:
            return self
        if _is_final_payment_status(self.status):
            return self
        self._ensure_status(PaymentStatus.INITIATED, "mark payment awaiting signature")
        return replace(self, status=PaymentStatus.AWAITING_SIGNATURE)

    def submit_tx_hash(self, tx_hash: TransactionHash | str) -> Self:
        tx_hash = _coerce_tx_hash(tx_hash)
        if self.status is PaymentStatus.SUBMITTED:
            if self.tx_hash == tx_hash:
                return self
            raise ValueError("submitted payments cannot change tx_hash")
        if _is_final_payment_status(self.status):
            return self
        self._ensure_status(PaymentStatus.AWAITING_SIGNATURE, "submit tx hash")
        return replace(self, status=PaymentStatus.SUBMITTED, tx_hash=tx_hash)

    def confirm_payment(self, receipt: TransactionReceipt) -> Self:
        if not isinstance(receipt, TransactionReceipt):
            raise ValueError("Payment.confirm_payment requires a TransactionReceipt")
        if self.status is PaymentStatus.CONFIRMED:
            if self.receipt == receipt:
                return self
            raise ValueError("confirmed payments cannot change receipt")
        if self.status in {PaymentStatus.FAILED, PaymentStatus.EXPIRED, PaymentStatus.REFUNDED}:
            return self
        if self.status not in {PaymentStatus.SUBMITTED, PaymentStatus.CONFIRMING}:
            raise ValueError(f"cannot confirm payment in {self.status} status")
        if self.tx_hash is None:
            raise ValueError("submitted payments require tx_hash before confirmation")
        if receipt.hash != self.tx_hash:
            raise ValueError("payment receipt hash must match submitted tx_hash")
        return replace(self, status=PaymentStatus.CONFIRMED, receipt=receipt)

    def mark_confirming(self) -> Self:
        if self.status is PaymentStatus.CONFIRMING:
            return self
        if self.status is PaymentStatus.CONFIRMED:
            return self
        if self.status in {PaymentStatus.FAILED, PaymentStatus.EXPIRED, PaymentStatus.REFUNDED}:
            return self
        self._ensure_status(PaymentStatus.SUBMITTED, "mark payment confirming")
        if self.tx_hash is None:
            raise ValueError("submitted payments require tx_hash before confirmation")
        return replace(self, status=PaymentStatus.CONFIRMING)

    def fail_payment(self, failure_reason: str) -> Self:
        failure_reason = _require_text(failure_reason, "failure_reason")
        if self.status is PaymentStatus.FAILED:
            return self
        if _is_final_payment_status(self.status):
            return self
        return replace(self, status=PaymentStatus.FAILED, failure_reason=failure_reason)

    def expire_awaiting_signature(
        self,
        now: datetime | None = None,
        reason: str = "signature expired",
    ) -> Self:
        now = _require_aware_datetime(now or datetime.now(UTC), "now")
        reason = _require_text(reason, "reason")
        if self.status is PaymentStatus.EXPIRED:
            return self
        if _is_final_payment_status(self.status):
            return self
        self._ensure_status(PaymentStatus.AWAITING_SIGNATURE, "expire awaiting signature payment")
        if now < self.expires_at:
            raise ValueError("Payment cannot expire before expires_at")
        return replace(self, status=PaymentStatus.EXPIRED, failure_reason=reason)

    def refund_payment(self, refund_receipt: TransactionReceipt) -> Self:
        if not isinstance(refund_receipt, TransactionReceipt):
            raise ValueError("Payment.refund_payment requires a TransactionReceipt")
        if self.status is PaymentStatus.REFUNDED:
            if self.refund_receipt == refund_receipt:
                return self
            raise ValueError("refunded payments cannot change refund_receipt")
        if self.status in {PaymentStatus.FAILED, PaymentStatus.EXPIRED}:
            return self
        self._ensure_status(PaymentStatus.CONFIRMED, "refund payment")
        return replace(self, status=PaymentStatus.REFUNDED, refund_receipt=refund_receipt)

    def record_processing_started(self, created_at: datetime | None = None) -> "PaymentProcessingStartedEvent":
        return PaymentProcessingStartedEvent(payment=self, created_at=created_at or datetime.now(UTC))

    def record_confirmed(self, created_at: datetime | None = None) -> "PaymentConfirmedEvent":
        return PaymentConfirmedEvent.from_payment(self, created_at=created_at or datetime.now(UTC))

    def record_failed(self, created_at: datetime | None = None) -> "PaymentFailedEvent":
        return PaymentFailedEvent.from_payment(self, created_at=created_at or datetime.now(UTC))

    def record_refunded(self, created_at: datetime | None = None) -> "PaymentRefundedEvent":
        return PaymentRefundedEvent.from_payment(self, created_at=created_at or datetime.now(UTC))

    def record_expired(self, expired_at: datetime | None = None) -> "PaymentExpiredEvent":
        return PaymentExpiredEvent.from_payment(self, expired_at=expired_at or datetime.now(UTC))

    def _ensure_status(self, expected: PaymentStatus, action: str) -> None:
        if self.status is not expected:
            raise ValueError(f"cannot {action} in {self.status} status")

    def _validate_status_shape(self) -> None:
        if self.tx_hash is not None and self.status in {PaymentStatus.INITIATED, PaymentStatus.AWAITING_SIGNATURE}:
            raise ValueError(f"{self.status} payments cannot have tx_hash")
        if self.receipt is not None and self.tx_hash is not None and self.receipt.hash != self.tx_hash:
            raise ValueError("Payment.receipt hash must match tx_hash")
        if self.status in {PaymentStatus.SUBMITTED, PaymentStatus.CONFIRMING, PaymentStatus.CONFIRMED}:
            if self.tx_hash is None:
                raise ValueError(f"{self.status} payments require tx_hash")
        if self.status is PaymentStatus.CONFIRMED and self.receipt is None:
            raise ValueError("CONFIRMED payments require receipt")
        if self.status in {PaymentStatus.FAILED, PaymentStatus.EXPIRED} and self.failure_reason is None:
            raise ValueError(f"{self.status} payments require failure_reason")
        if self.status is PaymentStatus.REFUNDED:
            if self.receipt is None:
                raise ValueError("REFUNDED payments require original receipt")
            if self.refund_receipt is None:
                raise ValueError("REFUNDED payments require refund_receipt")


@dataclass(frozen=True)
class PaymentAuthorization:
    payment_id: PaymentId
    user_id: UserId
    wallet: WalletAddress | str
    chain_network: ChainNetwork
    signature_request: TransactionSignatureRequest
    status: AuthorizationStatus = AuthorizationStatus.REQUESTED
    tx_hash: TransactionHash | str | None = None
    authorized_at: datetime | None = None
    payer_wallet_id: WalletId | str | None = None
    payment_asset_id: str | None = None
    expected_amount_minor_units: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.payment_id, PaymentId):
            raise ValueError("PaymentAuthorization.payment_id must be a PaymentId")
        if not isinstance(self.user_id, UserId):
            raise ValueError("PaymentAuthorization.user_id must be a UserId")
        object.__setattr__(self, "wallet", _coerce_wallet(self.wallet))
        if not isinstance(self.chain_network, ChainNetwork):
            raise ValueError("PaymentAuthorization.chain_network must be a ChainNetwork")
        if not isinstance(self.signature_request, TransactionSignatureRequest):
            raise ValueError("PaymentAuthorization.signature_request must be a TransactionSignatureRequest")
        _require_crypto_on_chain(
            self.signature_request.amount,
            self.chain_network,
            "PaymentAuthorization.signature_request.amount",
        )
        object.__setattr__(self, "status", _coerce_authorization_status(self.status))
        if self.tx_hash is not None:
            object.__setattr__(self, "tx_hash", _coerce_tx_hash(self.tx_hash))
        if self.authorized_at is not None:
            object.__setattr__(
                self,
                "authorized_at",
                _require_aware_datetime(self.authorized_at, "PaymentAuthorization.authorized_at"),
            )
        if self.payer_wallet_id is not None and not isinstance(self.payer_wallet_id, WalletId):
            object.__setattr__(self, "payer_wallet_id", WalletId(str(self.payer_wallet_id)))
        if self.payment_asset_id is not None:
            object.__setattr__(
                self,
                "payment_asset_id",
                _require_text(self.payment_asset_id, "PaymentAuthorization.payment_asset_id"),
            )
        if self.expected_amount_minor_units is not None:
            object.__setattr__(
                self,
                "expected_amount_minor_units",
                _coerce_non_negative_int(
                    self.expected_amount_minor_units,
                    "PaymentAuthorization.expected_amount_minor_units",
                ),
            )
        self._validate_status_shape()

    @classmethod
    def request_transaction_signature(
        cls,
        payment_id: PaymentId,
        user_id: UserId,
        wallet: WalletAddress | str,
        chain_network: ChainNetwork,
        signature_request: TransactionSignatureRequest,
        payer_wallet_id: WalletId | str | None = None,
        payment_asset_id: str | None = None,
        expected_amount_minor_units: int | None = None,
    ) -> Self:
        return cls(
            payment_id=payment_id,
            user_id=user_id,
            wallet=wallet,
            chain_network=chain_network,
            signature_request=signature_request,
            status=AuthorizationStatus.REQUESTED,
            payer_wallet_id=payer_wallet_id,
            payment_asset_id=payment_asset_id,
            expected_amount_minor_units=expected_amount_minor_units,
        )

    def authorize_tx_hash(
        self,
        tx_hash: TransactionHash | str,
        authorized_at: datetime | None = None,
    ) -> Self:
        tx_hash = _coerce_tx_hash(tx_hash)
        authorized_at = _require_aware_datetime(authorized_at or datetime.now(UTC), "authorized_at")
        if self.status is AuthorizationStatus.AUTHORIZED:
            if self.tx_hash == tx_hash:
                return self
            raise ValueError("authorized payment requests cannot change tx_hash")
        if self.status in {AuthorizationStatus.EXPIRED, AuthorizationStatus.REJECTED}:
            return self
        if authorized_at >= self.signature_request.expires_at:
            raise ValueError("expired signature requests cannot be authorized")
        return replace(
            self,
            status=AuthorizationStatus.AUTHORIZED,
            tx_hash=tx_hash,
            authorized_at=authorized_at,
        )

    def expire(self, now: datetime | None = None) -> Self:
        now = _require_aware_datetime(now or datetime.now(UTC), "now")
        if self.status is AuthorizationStatus.EXPIRED:
            return self
        if self.status in {AuthorizationStatus.AUTHORIZED, AuthorizationStatus.REJECTED}:
            return self
        if now < self.signature_request.expires_at:
            raise ValueError("PaymentAuthorization cannot expire before signature_request.expires_at")
        return replace(self, status=AuthorizationStatus.EXPIRED)

    def reject(self) -> Self:
        if self.status is AuthorizationStatus.REJECTED:
            return self
        if self.status in {AuthorizationStatus.AUTHORIZED, AuthorizationStatus.EXPIRED}:
            return self
        return replace(self, status=AuthorizationStatus.REJECTED)

    def _validate_status_shape(self) -> None:
        if self.status is AuthorizationStatus.REQUESTED:
            if self.tx_hash is not None or self.authorized_at is not None:
                raise ValueError("REQUESTED authorizations cannot have tx_hash or authorized_at")
        if self.status is AuthorizationStatus.AUTHORIZED:
            if self.tx_hash is None:
                raise ValueError("AUTHORIZED authorizations require tx_hash")
            if self.authorized_at is None:
                raise ValueError("AUTHORIZED authorizations require authorized_at")
            if self.authorized_at >= self.signature_request.expires_at:
                raise ValueError("AUTHORIZED authorizations must occur before signature_request.expires_at")


@dataclass(frozen=True)
class PaymentProcessingStartedEvent:
    payment: Payment
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.payment, Payment):
            raise ValueError("PaymentProcessingStartedEvent.payment must be a Payment")
        if self.payment.status not in {PaymentStatus.INITIATED, PaymentStatus.AWAITING_SIGNATURE}:
            raise ValueError("PaymentProcessingStartedEvent requires an initiated payment")
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "PaymentProcessingStartedEvent.created_at"),
        )


@dataclass(frozen=True)
class PaymentConfirmedEvent:
    payment_id: PaymentId
    order_id: OrderId
    tx_hash: TransactionHash | str
    receipt: TransactionReceipt
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.payment_id, PaymentId):
            raise ValueError("PaymentConfirmedEvent.payment_id must be a PaymentId")
        if not isinstance(self.order_id, OrderId):
            raise ValueError("PaymentConfirmedEvent.order_id must be an OrderId")
        object.__setattr__(self, "tx_hash", _coerce_tx_hash(self.tx_hash))
        if not isinstance(self.receipt, TransactionReceipt):
            raise ValueError("PaymentConfirmedEvent.receipt must be a TransactionReceipt")
        if self.receipt.hash != self.tx_hash:
            raise ValueError("PaymentConfirmedEvent.receipt hash must match tx_hash")
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "PaymentConfirmedEvent.created_at"),
        )

    @classmethod
    def from_payment(cls, payment: Payment, created_at: datetime | None = None) -> Self:
        if not isinstance(payment, Payment):
            raise ValueError("PaymentConfirmedEvent.from_payment requires a Payment")
        if payment.status is not PaymentStatus.CONFIRMED:
            raise ValueError("PaymentConfirmedEvent requires a CONFIRMED payment")
        if payment.tx_hash is None or payment.receipt is None:
            raise ValueError("CONFIRMED payment must contain tx_hash and receipt")
        return cls(
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            tx_hash=payment.tx_hash,
            receipt=payment.receipt,
            created_at=created_at or datetime.now(UTC),
        )


@dataclass(frozen=True)
class PaymentFailedEvent:
    payment_id: PaymentId
    order_id: OrderId
    failure_reason: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.payment_id, PaymentId):
            raise ValueError("PaymentFailedEvent.payment_id must be a PaymentId")
        if not isinstance(self.order_id, OrderId):
            raise ValueError("PaymentFailedEvent.order_id must be an OrderId")
        object.__setattr__(self, "failure_reason", _require_text(self.failure_reason, "failure_reason"))
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "PaymentFailedEvent.created_at"),
        )

    @classmethod
    def from_payment(cls, payment: Payment, created_at: datetime | None = None) -> Self:
        if not isinstance(payment, Payment):
            raise ValueError("PaymentFailedEvent.from_payment requires a Payment")
        if payment.status is not PaymentStatus.FAILED:
            raise ValueError("PaymentFailedEvent requires a FAILED payment")
        if payment.failure_reason is None:
            raise ValueError("FAILED payment must contain failure_reason")
        return cls(
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            failure_reason=payment.failure_reason,
            created_at=created_at or datetime.now(UTC),
        )


@dataclass(frozen=True)
class PaymentRefundedEvent:
    payment_id: PaymentId
    order_id: OrderId
    refund_receipt: TransactionReceipt
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.payment_id, PaymentId):
            raise ValueError("PaymentRefundedEvent.payment_id must be a PaymentId")
        if not isinstance(self.order_id, OrderId):
            raise ValueError("PaymentRefundedEvent.order_id must be an OrderId")
        if not isinstance(self.refund_receipt, TransactionReceipt):
            raise ValueError("PaymentRefundedEvent.refund_receipt must be a TransactionReceipt")
        object.__setattr__(
            self,
            "created_at",
            _require_aware_datetime(self.created_at, "PaymentRefundedEvent.created_at"),
        )

    @classmethod
    def from_payment(cls, payment: Payment, created_at: datetime | None = None) -> Self:
        if not isinstance(payment, Payment):
            raise ValueError("PaymentRefundedEvent.from_payment requires a Payment")
        if payment.status is not PaymentStatus.REFUNDED:
            raise ValueError("PaymentRefundedEvent requires a REFUNDED payment")
        if payment.refund_receipt is None:
            raise ValueError("REFUNDED payment must contain refund_receipt")
        return cls(
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            refund_receipt=payment.refund_receipt,
            created_at=created_at or datetime.now(UTC),
        )


@dataclass(frozen=True)
class PaymentExpiredEvent:
    payment_id: PaymentId
    order_id: OrderId
    reason: str
    expired_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.payment_id, PaymentId):
            raise ValueError("PaymentExpiredEvent.payment_id must be a PaymentId")
        if not isinstance(self.order_id, OrderId):
            raise ValueError("PaymentExpiredEvent.order_id must be an OrderId")
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))
        object.__setattr__(
            self,
            "expired_at",
            _require_aware_datetime(self.expired_at, "PaymentExpiredEvent.expired_at"),
        )

    @classmethod
    def from_payment(cls, payment: Payment, expired_at: datetime | None = None) -> Self:
        if not isinstance(payment, Payment):
            raise ValueError("PaymentExpiredEvent.from_payment requires a Payment")
        if payment.status is not PaymentStatus.EXPIRED:
            raise ValueError("PaymentExpiredEvent requires an EXPIRED payment")
        return cls(
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            reason=payment.failure_reason or "signature expired",
            expired_at=expired_at or datetime.now(UTC),
        )


PaymentEvent: TypeAlias = (
    PaymentProcessingStartedEvent
    | PaymentConfirmedEvent
    | PaymentFailedEvent
    | PaymentRefundedEvent
    | PaymentExpiredEvent
)


def _coerce_payment_status(value: PaymentStatus | str) -> PaymentStatus:
    if isinstance(value, PaymentStatus):
        return value
    try:
        return PaymentStatus(str(value))
    except ValueError as exc:
        raise ValueError("Payment.status must be a PaymentStatus") from exc


def _coerce_authorization_status(value: AuthorizationStatus | str) -> AuthorizationStatus:
    if isinstance(value, AuthorizationStatus):
        return value
    try:
        return AuthorizationStatus(str(value))
    except ValueError as exc:
        raise ValueError("PaymentAuthorization.status must be an AuthorizationStatus") from exc


def _coerce_asset_type(value: PaymentAssetType | str) -> PaymentAssetType:
    if isinstance(value, PaymentAssetType):
        return value
    try:
        return PaymentAssetType(str(value))
    except ValueError as exc:
        raise ValueError("PaymentAsset.asset_type must be a PaymentAssetType") from exc


def _is_final_payment_status(status: PaymentStatus) -> bool:
    return status in {
        PaymentStatus.CONFIRMED,
        PaymentStatus.FAILED,
        PaymentStatus.EXPIRED,
        PaymentStatus.REFUNDED,
    }


def _coerce_wallet(value: WalletAddress | str) -> WalletAddress:
    return value if isinstance(value, WalletAddress) else WalletAddress(value)


def _coerce_tx_hash(value: TransactionHash | str) -> TransactionHash:
    return value if isinstance(value, TransactionHash) else TransactionHash(value)


def _coerce_decimal(value: Decimal | str | int, field_name: str) -> Decimal:
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be decimal-compatible") from exc


def _coerce_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _coerce_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a non-negative integer") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return parsed


def _require_crypto_on_chain(value: Crypto, chain_network: ChainNetwork, field_name: str) -> None:
    if value.chain_id != chain_network.chain_id:
        raise ValueError(f"{field_name} must use chain_id {chain_network.chain_id}")


def _require_same_asset(left: Crypto, right: Crypto, field_name: str) -> None:
    if (
        left.symbol != right.symbol
        or left.chain_id != right.chain_id
        or left.token_address != right.token_address
        or left.decimals != right.decimals
    ):
        raise ValueError(f"{field_name} must use the same crypto asset as estimated_fee")


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _coerce_items(
    values: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    field_name: str,
) -> tuple[dict[str, Any], ...]:
    if isinstance(values, list):
        values = tuple(values)
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    items: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, Mapping):
            raise ValueError(f"{field_name} must contain JSON objects")
        items.append(dict(item))
    return tuple(items)


def _crypto_minor_units(value: Crypto) -> int:
    scale = Decimal(10) ** value.decimals
    scaled = value.amount * scale
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError("Crypto.amount has more precision than decimals allow")
    return int(integral)


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value

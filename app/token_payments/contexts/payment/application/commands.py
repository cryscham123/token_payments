"""Input DTOs for payment command handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from token_payments.shared.domain import (
    ChainNetwork,
    CommandId,
    Crypto,
    CustomerId,
    MessageId,
    OrderId,
    PaymentId,
    TransactionHash,
    UserId,
    WalletAddress,
)


@dataclass(frozen=True)
class InitiatePaymentCommand:
    command_id: CommandId
    payment_id: PaymentId
    order_id: OrderId
    customer_id: CustomerId
    user_id: UserId
    amount: Crypto
    wallet_from: WalletAddress | str
    wallet_to: WalletAddress | str
    chain_network: ChainNetwork
    expires_at: datetime
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)

    def __post_init__(self) -> None:
        _validate_command_identity(self)
        if not isinstance(self.customer_id, CustomerId):
            raise ValueError("InitiatePaymentCommand.customer_id must be a CustomerId")
        if not isinstance(self.user_id, UserId):
            raise ValueError("InitiatePaymentCommand.user_id must be a UserId")
        if not isinstance(self.amount, Crypto):
            raise ValueError("InitiatePaymentCommand.amount must be a Crypto value")
        object.__setattr__(self, "wallet_from", _coerce_wallet(self.wallet_from, "wallet_from"))
        object.__setattr__(self, "wallet_to", _coerce_wallet(self.wallet_to, "wallet_to"))
        if not isinstance(self.chain_network, ChainNetwork):
            raise ValueError("InitiatePaymentCommand.chain_network must be a ChainNetwork")
        if self.amount.chain_id != self.chain_network.chain_id:
            raise ValueError("InitiatePaymentCommand.amount must use chain_network.chain_id")
        object.__setattr__(
            self,
            "expires_at",
            _require_aware_datetime(self.expires_at, "InitiatePaymentCommand.expires_at"),
        )
        object.__setattr__(
            self,
            "requested_at",
            _require_aware_datetime(self.requested_at, "InitiatePaymentCommand.requested_at"),
        )
        _validate_optional_causation(self)
        _validate_event_message_id(self)


@dataclass(frozen=True)
class SubmitTransactionHashCommand:
    command_id: CommandId
    payment_id: PaymentId
    order_id: OrderId
    tx_hash: TransactionHash | str
    submitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None

    def __post_init__(self) -> None:
        _validate_command_identity(self)
        object.__setattr__(self, "tx_hash", _coerce_tx_hash(self.tx_hash))
        object.__setattr__(
            self,
            "submitted_at",
            _require_aware_datetime(self.submitted_at, "SubmitTransactionHashCommand.submitted_at"),
        )
        _validate_optional_causation(self)


@dataclass(frozen=True)
class ConfirmPaymentReceiptCommand:
    command_id: CommandId
    payment_id: PaymentId
    order_id: OrderId
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    failure_reason: str = "receipt not confirmed"
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)

    def __post_init__(self) -> None:
        _validate_command_identity(self)
        object.__setattr__(
            self,
            "checked_at",
            _require_aware_datetime(self.checked_at, "ConfirmPaymentReceiptCommand.checked_at"),
        )
        object.__setattr__(
            self,
            "failure_reason",
            _require_text(self.failure_reason, "ConfirmPaymentReceiptCommand.failure_reason"),
        )
        _validate_optional_causation(self)
        _validate_event_message_id(self)


@dataclass(frozen=True)
class ExpireAwaitingSignatureCommand:
    command_id: CommandId
    payment_id: PaymentId
    order_id: OrderId
    expired_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reason: str = "signature expired"
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)

    def __post_init__(self) -> None:
        _validate_command_identity(self)
        object.__setattr__(
            self,
            "expired_at",
            _require_aware_datetime(self.expired_at, "ExpireAwaitingSignatureCommand.expired_at"),
        )
        object.__setattr__(self, "reason", _require_text(self.reason, "ExpireAwaitingSignatureCommand.reason"))
        _validate_optional_causation(self)
        _validate_event_message_id(self)


@dataclass(frozen=True)
class RefundPaymentCommand:
    command_id: CommandId
    payment_id: PaymentId
    order_id: OrderId
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    causation_id: str | None = None
    event_message_id: MessageId = field(default_factory=MessageId.new)

    def __post_init__(self) -> None:
        _validate_command_identity(self)
        object.__setattr__(
            self,
            "requested_at",
            _require_aware_datetime(self.requested_at, "RefundPaymentCommand.requested_at"),
        )
        _validate_optional_causation(self)
        _validate_event_message_id(self)


PaymentCommand = (
    InitiatePaymentCommand
    | SubmitTransactionHashCommand
    | ConfirmPaymentReceiptCommand
    | ExpireAwaitingSignatureCommand
    | RefundPaymentCommand
)


def _validate_command_identity(command: PaymentCommand) -> None:
    if not isinstance(command.command_id, CommandId):
        raise ValueError(f"{type(command).__name__}.command_id must be a CommandId")
    if not isinstance(command.payment_id, PaymentId):
        raise ValueError(f"{type(command).__name__}.payment_id must be a PaymentId")
    if not isinstance(command.order_id, OrderId):
        raise ValueError(f"{type(command).__name__}.order_id must be an OrderId")


def _validate_event_message_id(
    command: InitiatePaymentCommand | ConfirmPaymentReceiptCommand | ExpireAwaitingSignatureCommand | RefundPaymentCommand,
) -> None:
    if not isinstance(command.event_message_id, MessageId):
        raise ValueError(f"{type(command).__name__}.event_message_id must be a MessageId")


def _validate_optional_causation(command: PaymentCommand) -> None:
    if command.causation_id is not None:
        object.__setattr__(
            command,
            "causation_id",
            _require_text(command.causation_id, f"{type(command).__name__}.causation_id"),
        )


def _coerce_wallet(value: WalletAddress | str, field_name: str) -> WalletAddress:
    try:
        return value if isinstance(value, WalletAddress) else WalletAddress(value)
    except ValueError as exc:
        raise ValueError(f"InitiatePaymentCommand.{field_name} must be a WalletAddress") from exc


def _coerce_tx_hash(value: TransactionHash | str) -> TransactionHash:
    try:
        return value if isinstance(value, TransactionHash) else TransactionHash(value)
    except ValueError as exc:
        raise ValueError("SubmitTransactionHashCommand.tx_hash must be a TransactionHash") from exc


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()

"""Payment read-model contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from token_payments.contexts.order.domain import TrackingId
from token_payments.contexts.payment.domain import PaymentStatus
from token_payments.shared.domain import ChainNetwork, Crypto, OrderId, PaymentId, TransactionHash, UserId, WalletAddress


@dataclass(frozen=True)
class PaymentHistoryItem:
    payment_id: PaymentId
    order_id: OrderId
    tracking_id: TrackingId
    amount: Crypto
    wallet_from: WalletAddress
    wallet_to: WalletAddress
    chain_network: ChainNetwork
    status: PaymentStatus
    tx_hash: TransactionHash | None
    receipt: Any | None
    failure_reason: str | None
    payment_asset_id: str | None
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.payment_id, PaymentId):
            object.__setattr__(self, "payment_id", PaymentId(str(self.payment_id)))
        if not isinstance(self.order_id, OrderId):
            object.__setattr__(self, "order_id", OrderId(str(self.order_id)))
        if not isinstance(self.tracking_id, TrackingId):
            object.__setattr__(self, "tracking_id", TrackingId(str(self.tracking_id)))
        if not isinstance(self.amount, Crypto):
            raise ValueError("PaymentHistoryItem.amount must be a Crypto value")
        if not isinstance(self.wallet_from, WalletAddress):
            object.__setattr__(self, "wallet_from", WalletAddress(str(self.wallet_from)))
        if not isinstance(self.wallet_to, WalletAddress):
            object.__setattr__(self, "wallet_to", WalletAddress(str(self.wallet_to)))
        if not isinstance(self.chain_network, ChainNetwork):
            raise ValueError("PaymentHistoryItem.chain_network must be a ChainNetwork value")
        if not isinstance(self.status, PaymentStatus):
            object.__setattr__(self, "status", PaymentStatus(self.status))
        if self.tx_hash is not None and not isinstance(self.tx_hash, TransactionHash):
            object.__setattr__(self, "tx_hash", TransactionHash(str(self.tx_hash)))
        if self.failure_reason is not None:
            object.__setattr__(self, "failure_reason", _require_text(self.failure_reason, "failure_reason"))
        if self.payment_asset_id is not None:
            object.__setattr__(self, "payment_asset_id", _require_text(self.payment_asset_id, "payment_asset_id"))
        object.__setattr__(self, "updated_at", _require_aware_datetime(self.updated_at, "updated_at"))


class PaymentHistoryQueryPort(Protocol):
    def list_for_user(
        self,
        user_id: UserId,
        *,
        statuses: tuple[PaymentStatus, ...] | None = None,
        limit: int = 50,
    ) -> tuple[PaymentHistoryItem, ...]:
        ...


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value

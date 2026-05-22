from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Self

from token_payments.shared.domain import UserId, WalletAddress
from token_payments.shared.domain.ids import _UuidIdentifier


@dataclass(frozen=True)
class WalletId(_UuidIdentifier):
    pass


class WalletType(StrEnum):
    EOA = "EOA"
    SMART_WALLET = "SMART_WALLET"


class WalletVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PENDING = "PENDING"
    REVOKED = "REVOKED"


@dataclass(frozen=True)
class UserWallet:
    wallet_id: WalletId
    user_id: UserId
    address: WalletAddress
    chain_id: int
    wallet_type: WalletType
    verification_status: WalletVerificationStatus
    primary: bool
    linked_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.wallet_id, WalletId):
            raise TypeError("wallet_id must be a WalletId")
        if not isinstance(self.user_id, UserId):
            raise TypeError("user_id must be a UserId")
        if not isinstance(self.chain_id, int) or self.chain_id <= 0:
            raise ValueError("chain_id must be a positive integer")
        if not isinstance(self.address, WalletAddress):
            object.__setattr__(self, "address", WalletAddress(self.address))
        if self.linked_at.tzinfo is None or self.linked_at.utcoffset() is None:
            raise ValueError("linked_at must be timezone-aware")
        if self.revoked_at is not None and (self.revoked_at.tzinfo is None or self.revoked_at.utcoffset() is None):
            raise ValueError("revoked_at must be timezone-aware")

    def is_active(self) -> bool:
        return self.verification_status is WalletVerificationStatus.VERIFIED and self.revoked_at is None

    def revoke(self, now: datetime) -> UserWallet:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("revoked_at must be timezone-aware")
        return replace(
            self,
            verification_status=WalletVerificationStatus.REVOKED,
            revoked_at=now,
        )

    def mark_primary(self) -> UserWallet:
        if self.verification_status is WalletVerificationStatus.REVOKED:
            raise ValueError("cannot make revoked wallet primary")
        return replace(self, primary=True)

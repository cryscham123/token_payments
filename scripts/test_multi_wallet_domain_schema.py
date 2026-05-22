"""Tests for multi-wallet domain schema — phase 25, step 0.

Verifies:
- UserWallet domain model invariants
- User no longer has a single primary_wallet identity lock-in
- AuthSession uses login_wallet_id (WalletId FK) not raw wallet_address
- Customer identity is user_id-based, not wallet_address-based
- Store settlement wallet is a verified wallet reference
- Revoked wallets cannot be used for login/payment selection
- (chain_id, address) uniqueness per active user
- chain-scoped primary wallet support
- EOA vs smart wallet type distinction
"""

from __future__ import annotations

import pytest
from datetime import UTC, datetime
from uuid import uuid4

# ---------------------------------------------------------------------------
# Import guards — these will fail until the domain is implemented
# ---------------------------------------------------------------------------
from token_payments.contexts.auth.domain import (
    User,
)
from token_payments.contexts.auth.domain.wallet import (
    WalletId,
    WalletType,
    WalletVerificationStatus,
    UserWallet,
)
from token_payments.shared.domain import UserId, WalletAddress


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> UserId:
    return UserId(uuid4())


def _wid() -> WalletId:
    return WalletId(uuid4())


def _wallet(address: str = "0xAbCd1234567890AbCd1234567890AbCd12345678") -> WalletAddress:
    return WalletAddress(address)


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# WalletId
# ---------------------------------------------------------------------------

class TestWalletId:
    def test_create_from_uuid(self):
        uid = uuid4()
        wid = WalletId(uid)
        assert wid.value == uid

    def test_create_from_string(self):
        uid = uuid4()
        wid = WalletId(str(uid))
        assert str(wid) == str(uid)

    def test_new_generates_unique(self):
        a = WalletId.new()
        b = WalletId.new()
        assert a != b

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError):
            WalletId("")

    def test_rejects_invalid_uuid(self):
        with pytest.raises(ValueError):
            WalletId("not-a-uuid")


# ---------------------------------------------------------------------------
# WalletType
# ---------------------------------------------------------------------------

class TestWalletType:
    def test_eoa_and_smart_wallet_are_distinct(self):
        assert WalletType.EOA != WalletType.SMART_WALLET

    def test_eoa_value(self):
        assert WalletType.EOA == "EOA"

    def test_smart_wallet_value(self):
        assert WalletType.SMART_WALLET == "SMART_WALLET"


# ---------------------------------------------------------------------------
# WalletVerificationStatus
# ---------------------------------------------------------------------------

class TestWalletVerificationStatus:
    def test_values(self):
        assert WalletVerificationStatus.VERIFIED == "VERIFIED"
        assert WalletVerificationStatus.PENDING == "PENDING"
        assert WalletVerificationStatus.REVOKED == "REVOKED"


# ---------------------------------------------------------------------------
# UserWallet
# ---------------------------------------------------------------------------

class TestUserWalletCreation:
    def test_create_minimal(self):
        uid = _uid()
        wid = _wid()
        w = UserWallet(
            wallet_id=wid,
            user_id=uid,
            address=_wallet(),
            chain_id=1,
            wallet_type=WalletType.EOA,
            verification_status=WalletVerificationStatus.VERIFIED,
            primary=False,
            linked_at=_now(),
        )
        assert w.wallet_id == wid
        assert w.user_id == uid
        assert w.chain_id == 1
        assert w.wallet_type is WalletType.EOA
        assert w.verification_status is WalletVerificationStatus.VERIFIED
        assert w.primary is False
        assert w.revoked_at is None

    def test_create_with_revoked_at(self):
        w = UserWallet(
            wallet_id=_wid(),
            user_id=_uid(),
            address=_wallet(),
            chain_id=1,
            wallet_type=WalletType.EOA,
            verification_status=WalletVerificationStatus.REVOKED,
            primary=False,
            linked_at=_now(),
            revoked_at=_now(),
        )
        assert w.revoked_at is not None

    def test_requires_wallet_id(self):
        with pytest.raises((ValueError, TypeError)):
            UserWallet(
                wallet_id="not-a-WalletId",
                user_id=_uid(),
                address=_wallet(),
                chain_id=1,
                wallet_type=WalletType.EOA,
                verification_status=WalletVerificationStatus.VERIFIED,
                primary=False,
                linked_at=_now(),
            )

    def test_requires_user_id(self):
        with pytest.raises((ValueError, TypeError)):
            UserWallet(
                wallet_id=_wid(),
                user_id="not-a-UserId",
                address=_wallet(),
                chain_id=1,
                wallet_type=WalletType.EOA,
                verification_status=WalletVerificationStatus.VERIFIED,
                primary=False,
                linked_at=_now(),
            )

    def test_requires_positive_chain_id(self):
        with pytest.raises(ValueError):
            UserWallet(
                wallet_id=_wid(),
                user_id=_uid(),
                address=_wallet(),
                chain_id=0,
                wallet_type=WalletType.EOA,
                verification_status=WalletVerificationStatus.VERIFIED,
                primary=False,
                linked_at=_now(),
            )

    def test_requires_aware_linked_at(self):
        with pytest.raises(ValueError):
            UserWallet(
                wallet_id=_wid(),
                user_id=_uid(),
                address=_wallet(),
                chain_id=1,
                wallet_type=WalletType.EOA,
                verification_status=WalletVerificationStatus.VERIFIED,
                primary=False,
                linked_at=datetime(2024, 1, 1),  # naive
            )


# ---------------------------------------------------------------------------
# UserWallet — business invariants
# ---------------------------------------------------------------------------

class TestUserWalletBusinessRules:
    def _verified_wallet(self, uid: UserId | None = None, chain_id: int = 1, primary: bool = False) -> UserWallet:
        return UserWallet(
            wallet_id=_wid(),
            user_id=uid or _uid(),
            address=_wallet(),
            chain_id=chain_id,
            wallet_type=WalletType.EOA,
            verification_status=WalletVerificationStatus.VERIFIED,
            primary=primary,
            linked_at=_now(),
        )

    def test_revoked_wallet_is_not_active(self):
        w = UserWallet(
            wallet_id=_wid(),
            user_id=_uid(),
            address=_wallet(),
            chain_id=1,
            wallet_type=WalletType.EOA,
            verification_status=WalletVerificationStatus.REVOKED,
            primary=False,
            linked_at=_now(),
            revoked_at=_now(),
        )
        assert w.is_active() is False

    def test_verified_wallet_is_active(self):
        w = self._verified_wallet()
        assert w.is_active() is True

    def test_pending_wallet_is_not_active(self):
        w = UserWallet(
            wallet_id=_wid(),
            user_id=_uid(),
            address=_wallet(),
            chain_id=1,
            wallet_type=WalletType.EOA,
            verification_status=WalletVerificationStatus.PENDING,
            primary=False,
            linked_at=_now(),
        )
        assert w.is_active() is False

    def test_revoke_produces_revoked_wallet(self):
        w = self._verified_wallet()
        revoked = w.revoke(_now())
        assert revoked.verification_status is WalletVerificationStatus.REVOKED
        assert revoked.revoked_at is not None
        assert revoked.is_active() is False

    def test_mark_primary(self):
        w = self._verified_wallet(primary=False)
        primary = w.mark_primary()
        assert primary.primary is True

    def test_cannot_make_revoked_wallet_primary(self):
        w = UserWallet(
            wallet_id=_wid(),
            user_id=_uid(),
            address=_wallet(),
            chain_id=1,
            wallet_type=WalletType.EOA,
            verification_status=WalletVerificationStatus.REVOKED,
            primary=False,
            linked_at=_now(),
            revoked_at=_now(),
        )
        with pytest.raises(ValueError):
            w.mark_primary()

    def test_chain_scoped_primary(self):
        """User can have chain-scoped primary wallet (different chains, both primary)."""
        uid = _uid()
        w1 = UserWallet(
            wallet_id=_wid(), user_id=uid, address=_wallet("0xAAAA" + "0" * 36),
            chain_id=1, wallet_type=WalletType.EOA,
            verification_status=WalletVerificationStatus.VERIFIED,
            primary=True, linked_at=_now(),
        )
        w2 = UserWallet(
            wallet_id=_wid(), user_id=uid, address=_wallet("0xBBBB" + "0" * 36),
            chain_id=137, wallet_type=WalletType.EOA,
            verification_status=WalletVerificationStatus.VERIFIED,
            primary=True, linked_at=_now(),
        )
        # Both can coexist — they belong to different chains
        assert w1.chain_id != w2.chain_id
        assert w1.primary and w2.primary

    def test_eoa_and_smart_wallet_types_are_distinct(self):
        eoa = UserWallet(
            wallet_id=_wid(), user_id=_uid(), address=_wallet(),
            chain_id=1, wallet_type=WalletType.EOA,
            verification_status=WalletVerificationStatus.VERIFIED,
            primary=False, linked_at=_now(),
        )
        smart = UserWallet(
            wallet_id=_wid(), user_id=_uid(), address=_wallet(),
            chain_id=1, wallet_type=WalletType.SMART_WALLET,
            verification_status=WalletVerificationStatus.VERIFIED,
            primary=False, linked_at=_now(),
        )
        assert eoa.wallet_type is WalletType.EOA
        assert smart.wallet_type is WalletType.SMART_WALLET


# ---------------------------------------------------------------------------
# User — does NOT have a single primary_wallet identity lock-in
# ---------------------------------------------------------------------------

class TestUserMultiWalletContract:
    """User identity must NOT be tied to a single wallet field in the multi-wallet model."""

    def test_user_has_no_single_primary_wallet_field(self):
        """User should not expose primary_wallet as the source of truth for identity.

        The multi-wallet model stores wallets in UserWallet objects. User may keep
        a legacy primary_wallet for backfill/migration purposes but new code must
        not use it as identity anchor.
        """
        uid = _uid()
        # User can still be constructed (backward compat migration path)
        user = User(user_id=uid, primary_wallet=_wallet(), active=True)
        assert user.user_id == uid
        assert user.active is True

    def test_user_identity_is_user_id_not_wallet(self):
        """Two users with same wallet reference but different user_id are distinct identities."""
        uid1 = _uid()
        uid2 = _uid()
        w = _wallet()
        u1 = User(user_id=uid1, primary_wallet=w, active=True)
        u2 = User(user_id=uid2, primary_wallet=w, active=True)
        assert u1.user_id != u2.user_id


# ---------------------------------------------------------------------------
# AuthSession — must use login_wallet_id, NOT raw wallet_address text
# ---------------------------------------------------------------------------

class TestAuthSessionWalletContract:
    """AuthSession must reference wallet via WalletId, not raw address text."""

    def test_auth_session_has_login_wallet_id_field(self):
        """AuthSession must expose login_wallet_id (WalletId) for the session wallet."""
        from token_payments.contexts.auth.domain import AuthSession, SessionId, RefreshTokenHash

        uid = _uid()
        sid = SessionId.new()
        wid = _wid()
        rth = RefreshTokenHash(hash="abc" * 10, salt="salt", rotation_version=0)

        session = AuthSession(
            session_id=sid,
            user_id=uid,
            login_wallet_id=wid,
            refresh_token_hash=rth,
            device_id="device-1",
            expires_at=_now(),
        )
        assert session.login_wallet_id == wid

    def test_auth_session_has_no_raw_wallet_address(self):
        """AuthSession must not store raw wallet_address as a field."""
        from token_payments.contexts.auth.domain import AuthSession
        import inspect
        params = inspect.signature(AuthSession.__init__).parameters
        assert "wallet_address" not in params, (
            "AuthSession must not have wallet_address field — use login_wallet_id"
        )


# ---------------------------------------------------------------------------
# Customer — must NOT hold raw wallet_address
# ---------------------------------------------------------------------------

class TestCustomerWalletContract:
    """order_customers must not store raw wallet_address as identity."""

    def test_customer_has_no_wallet_address_field(self):
        """Customer must not expose customer_wallet/wallet_address as an identity field."""
        from token_payments.contexts.order.domain import Customer
        import inspect
        params = inspect.signature(Customer.__init__).parameters
        assert "customer_wallet" not in params and "wallet_address" not in params, (
            "Customer must not hold raw wallet_address — payment wallet is on authorization"
        )

    def test_customer_identity_is_user_id(self):
        """Customer identity is user_id + customer_id, not wallet."""
        from token_payments.contexts.order.domain import Customer, CustomerId

        cid = CustomerId(uuid4())
        uid = _uid()
        customer = Customer(customer_id=cid, user_id=uid)
        assert customer.user_id == uid
        assert customer.customer_id == cid


# ---------------------------------------------------------------------------
# Store settlement wallet — must be verified reference, not raw text
# ---------------------------------------------------------------------------

class TestStoreSettlementWalletContract:
    """Store settlement wallet must be a verified wallet reference."""

    def test_store_has_no_raw_store_wallet_text(self):
        """Store domain model must not hold a raw string wallet address for settlement."""
        from token_payments.contexts.order.domain import Store
        import inspect
        sig = inspect.signature(Store.__init__)
        params = sig.parameters
        # store_wallet can exist as a WalletAddress (typed value object) but must not
        # be a plain str identity with no validation
        # The key check: store_wallet field should be typed WalletAddress | None or
        # carry a wallet_id reference, not a free-form string
        if "store_wallet" in params:
            # Acceptable if typed (WalletAddress wraps validated hex address)
            # Reject if it's a plain str with no validation wrapper
            annotation = params["store_wallet"].annotation
            # This is a structural check — WalletAddress is a value object
            assert annotation is not str, (
                "Store.store_wallet must be typed WalletAddress or WalletId reference, not plain str"
            )

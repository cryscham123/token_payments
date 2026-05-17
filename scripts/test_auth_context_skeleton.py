from __future__ import annotations

import ast
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import get_type_hints

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.application import (  # noqa: E402
    AuthEventPublisher,
    AuthSessionRepository,
    AuthUseCase,
    LoginChallengeRepository,
    TokenIssuer,
    UserRepository,
    WalletSignatureVerificationResult,
    WalletSignatureVerifier,
)
from token_payments.contexts.auth.domain import (  # noqa: E402
    AuthNonce,
    ChallengeStatus,
    LoginChallenge,
    LoginChallengeRejected,
    LoginFailureReason,
    User,
)
from token_payments.shared.domain import UserId, WalletAddress  # noqa: E402


WALLET = "0xABCDabcdABCDabcdABCDabcdABCDabcdABCDabcd"


def test_login_challenge_verifies_once_and_rejects_nonce_reuse() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    challenge = LoginChallenge.issue(
        wallet=WALLET,
        nonce=AuthNonce(value="nonce-123", expires_at=now + timedelta(minutes=5)),
        issued_at=now,
    )

    verified = challenge.verify_signature(WALLET.lower(), now=now + timedelta(seconds=30))

    assert verified.status == ChallengeStatus.VERIFIED
    assert verified.verified_at == now + timedelta(seconds=30)

    with pytest.raises(LoginChallengeRejected) as exc:
        verified.verify_signature(WALLET, now=now + timedelta(seconds=45))

    assert exc.value.reason == LoginFailureReason.REUSED_NONCE

    with pytest.raises(LoginChallengeRejected) as expired_reuse:
        verified.verify_signature(WALLET, now=now + timedelta(minutes=6))

    assert expired_reuse.value.reason == LoginFailureReason.REUSED_NONCE


def test_login_challenge_rejects_expired_nonce_before_wallet_verification() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    challenge = LoginChallenge.issue(
        wallet=WALLET,
        nonce=AuthNonce(value="nonce-123", expires_at=now + timedelta(minutes=5)),
        issued_at=now,
    )

    with pytest.raises(LoginChallengeRejected) as exc:
        challenge.verify_signature(WALLET, now=now + timedelta(minutes=6))

    expired = challenge.expire(now + timedelta(minutes=6))

    assert exc.value.reason == LoginFailureReason.EXPIRED_CHALLENGE
    assert expired.status == ChallengeStatus.EXPIRED


def test_login_challenge_compares_wallet_addresses_after_normalization() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    challenge = LoginChallenge.issue(
        wallet=WALLET,
        nonce=AuthNonce(value="nonce-123", expires_at=now + timedelta(minutes=5)),
        issued_at=now,
    )

    verified = challenge.verify_signature(
        "0xabcdabcdabcdabcdabcdabcdabcdabcdabcdabcd",
        now=now + timedelta(seconds=10),
    )

    assert challenge.wallet == WalletAddress(WALLET.lower())
    assert verified.status == ChallengeStatus.VERIFIED


def test_login_challenge_rejects_wallet_mismatch() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    challenge = LoginChallenge.issue(
        wallet=WALLET,
        nonce=AuthNonce(value="nonce-123", expires_at=now + timedelta(minutes=5)),
        issued_at=now,
    )

    with pytest.raises(LoginChallengeRejected) as exc:
        challenge.verify_signature(
            "0x9999999999999999999999999999999999999999",
            now=now + timedelta(seconds=10),
        )

    assert exc.value.reason == LoginFailureReason.WALLET_MISMATCH


def test_user_register_by_wallet_normalizes_primary_wallet() -> None:
    user = User.register_by_wallet(UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"), WALLET)

    assert user.primary_wallet == WalletAddress(WALLET.lower())
    assert user.active is True


def test_auth_input_and_output_ports_are_defined_as_protocol_contracts() -> None:
    assert hasattr(AuthUseCase, "requestLoginChallenge")
    assert hasattr(AuthUseCase, "loginWithMetaMask")
    assert hasattr(AuthUseCase, "refreshSession")
    assert hasattr(AuthUseCase, "logout")
    assert hasattr(AuthUseCase, "getCurrentUser")

    for port in (
        UserRepository,
        LoginChallengeRepository,
        AuthSessionRepository,
        WalletSignatureVerifier,
        TokenIssuer,
        AuthEventPublisher,
    ):
        assert getattr(port, "_is_protocol", False), f"{port.__name__} must be a Protocol"

    hints = get_type_hints(WalletSignatureVerifier.verify_signature)
    assert hints["wallet"] is WalletAddress
    assert hints["message"] is str
    assert hints["signature"] is str
    assert hints["chain_id"] is int
    assert hints["return"] is WalletSignatureVerificationResult


def test_auth_context_does_not_import_external_adapters_or_clients() -> None:
    forbidden_roots = {
        "blockchain",
        "kafka",
        "metamask",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }

    for path in (ROOT / "app/token_payments/contexts/auth").glob("**/*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        assert imports.isdisjoint(forbidden_roots), f"{path} imports adapter dependency: {imports}"

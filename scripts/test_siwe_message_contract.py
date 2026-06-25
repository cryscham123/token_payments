from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiRequest  # noqa: E402
from token_payments.api.auth import AuthApi  # noqa: E402
from token_payments.contexts.auth.application import (  # noqa: E402
    AuthApplicationError,
    AuthApplicationService,
    AuthErrorCode,
    LoginWithMetaMaskCommand,
    RequestLoginChallengeCommand,
    WalletSignatureVerificationFailure,
    WalletSignatureVerificationResult,
)
from token_payments.contexts.auth.domain import (  # noqa: E402
    AuthNonce,
    AuthSession,
    ChallengeStatus,
    IssuedToken,
    LoginChallenge,
    RefreshTokenHash,
    SessionId,
    User,
)
from token_payments.contexts.auth.domain.wallet import WalletId
from token_payments.shared.domain import UserId, WalletAddress  # noqa: E402


NOW = datetime(2026, 5, 18, 0, 0, tzinfo=UTC)
WALLET = "0xABCDabcdABCDabcdABCDabcdABCDabcdABCDabcd"
NORMALIZED_WALLET = "0xabcdabcdabcdabcdabcdabcdabcdabcdabcdabcd"
CHECKSUM_WALLET = "0xABCDabcdABcDabcDaBCDAbcdABcdAbCdABcDABCd"
OTHER_WALLET = "0x9999999999999999999999999999999999999999"
DOMAIN = "token-payments.local"
CHAIN_ID = 1337
USER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"
SESSION_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"
SIWE_URI = f"https://{DOMAIN}"


def test_challenge_response_contains_siwe_required_fields_and_message() -> None:
    service, _repositories, _verifier = _service(nonces=("nonce-001",))
    api = AuthApi(service)

    response = api.request_login_challenge(
        ApiRequest(
            request_id="req-siwe-challenge",
            method="POST",
            path="/auth/challenges",
            body={"walletAddress": WALLET, "domain": DOMAIN, "chainId": CHAIN_ID},
            received_at=NOW,
        )
    )

    assert response.status_code == 201
    body = response.body
    assert body["walletAddress"] == CHECKSUM_WALLET
    assert body["domain"] == DOMAIN
    assert body["address"] == CHECKSUM_WALLET
    assert body["uri"] == SIWE_URI
    assert body["version"] == "1"
    assert body["chainId"] == CHAIN_ID
    assert re.fullmatch(r"[A-Za-z0-9]{8,}", body["nonce"])
    assert body["issuedAt"] == NOW.isoformat()
    assert body["expirationTime"] == (NOW + timedelta(minutes=5)).isoformat()
    assert body["expiresAt"] == body["expirationTime"]
    assert body["signingMessage"].splitlines() == [
        f"{DOMAIN} wants you to sign in with your Ethereum account:",
        NORMALIZED_WALLET,
        "",
        f"URI: {SIWE_URI}",
        "Version: 1",
        f"Chain ID: {CHAIN_ID}",
        f"Nonce: {body['nonce']}",
        f"Issued At: {NOW.isoformat()}",
        f"Expiration Time: {(NOW + timedelta(minutes=5)).isoformat()}",
    ]


@pytest.mark.parametrize(
    ("mutate_message", "expected_code"),
    [
        (
            lambda message: message.replace(
                f"{DOMAIN} wants you to sign in with your Ethereum account:",
                "evil.example wants you to sign in with your Ethereum account:",
            ),
            AuthErrorCode.SIWE_MESSAGE_MISMATCH,
        ),
        (
            lambda message: message.replace(f"Chain ID: {CHAIN_ID}", "Chain ID: 1"),
            AuthErrorCode.SIWE_MESSAGE_MISMATCH,
        ),
        (
            lambda message: message.replace(NORMALIZED_WALLET, OTHER_WALLET),
            AuthErrorCode.WALLET_MISMATCH,
        ),
        (
            lambda message: message.replace(
                f"Expiration Time: {(NOW + timedelta(minutes=5)).isoformat()}",
                f"Expiration Time: {(NOW + timedelta(minutes=10)).isoformat()}",
            ),
            AuthErrorCode.SIWE_MESSAGE_MISMATCH,
        ),
    ],
)
def test_login_rejects_siwe_message_context_mismatch(
    mutate_message: Any,
    expected_code: AuthErrorCode,
) -> None:
    service, repositories, verifier = _service(nonces=("nonce-001",))
    challenge = service.requestLoginChallenge(
        RequestLoginChallengeCommand(wallet_address=WALLET, domain=DOMAIN, chain_id=CHAIN_ID)
    )
    verifier.recovered_wallet = NORMALIZED_WALLET

    with pytest.raises(AuthApplicationError) as exc:
        service.loginWithMetaMask(
            LoginWithMetaMaskCommand(
                wallet_address=WALLET,
                message=mutate_message(challenge.signing_message),
                signature="signature-valid",
                device_id="browser-1",
            )
        )

    assert exc.value.code is expected_code
    assert repositories.challenges.get_by_nonce(challenge.challenge.nonce).status is ChallengeStatus.REJECTED
    assert repositories.sessions.sessions_by_id == {}


@dataclass
class FakeRepositories:
    users: "FakeUserRepository"
    challenges: "FakeLoginChallengeRepository"
    sessions: "FakeAuthSessionRepository"
    events: "FakeAuthEventPublisher"


def _service(
    *,
    nonces: tuple[str, ...],
) -> tuple[AuthApplicationService, FakeRepositories, "FakeWalletSignatureVerifier"]:
    repositories = FakeRepositories(
        users=FakeUserRepository(),
        challenges=FakeLoginChallengeRepository(),
        sessions=FakeAuthSessionRepository(),
        events=FakeAuthEventPublisher(),
    )
    clock = FakeClock(NOW)
    verifier = FakeWalletSignatureVerifier()
    service = AuthApplicationService(
        clock=clock,
        nonce_generator=SequenceGenerator(nonces),
        user_id_generator=SequenceGenerator((USER_ID,)),
        session_id_generator=SequenceGenerator((SESSION_ID,)),
        users=repositories.users,
        login_challenges=repositories.challenges,
        sessions=repositories.sessions,
        signature_verifier=verifier,
        token_issuer=DeterministicTokenIssuer(clock),
        event_publisher=repositories.events,
    )
    return service, repositories, verifier


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


class SequenceGenerator:
    def __init__(self, values: tuple[str, ...]) -> None:
        self._values = list(values)

    def new_id(self) -> str:
        if not self._values:
            raise AssertionError("generator exhausted")
        return self._values.pop(0)


class FakeWalletSignatureVerifier:
    def __init__(self) -> None:
        self.recovered_wallet: str | None = None

    def verify_signature(
        self,
        wallet: WalletAddress,
        message: str,
        signature: str,
        chain_id: int,
    ) -> WalletSignatureVerificationResult:
        if signature != "signature-valid" or self.recovered_wallet is None:
            return WalletSignatureVerificationResult.failed(
                WalletSignatureVerificationFailure.INVALID_SIGNATURE
            )
        if WalletAddress(self.recovered_wallet) != wallet:
            return WalletSignatureVerificationResult.failed(
                WalletSignatureVerificationFailure.WALLET_MISMATCH
            )
        return WalletSignatureVerificationResult.verified()


class DeterministicTokenIssuer:
    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock

    def issue_tokens(self, user: User, session: AuthSession) -> IssuedToken:
        return IssuedToken(
            access_token=f"access:{user.user_id}:{session.session_id}",
            refresh_token=f"refresh:{session.session_id}",
            expires_at=self._clock.now() + timedelta(minutes=15),
        )

    def refresh_tokens(self, session: AuthSession) -> IssuedToken:
        return IssuedToken(
            access_token=f"access:{session.user_id}:{session.session_id}:refresh",
            refresh_token=f"refresh:{session.session_id}:refresh",
            expires_at=self._clock.now() + timedelta(minutes=15),
        )


class FakeUserRepository:
    def __init__(self) -> None:
        self.users_by_id: dict[str, User] = {}
        self.wallets: dict[tuple[str, str], WalletId] = {}

    def save(self, user: User) -> None:
        self.users_by_id[str(user.user_id)] = user

    def get_by_id(self, user_id: UserId) -> User | None:
        return self.users_by_id.get(str(user_id))

    def get_by_wallet(self, wallet: WalletAddress) -> User | None:
        return next((user for user in self.users_by_id.values() if user.primary_wallet == wallet), None)

    def get_wallet_id_for_address(self, user_id: UserId, wallet: WalletAddress) -> WalletId:
        key = (str(user_id), str(wallet))
        if key not in self.wallets:
            self.wallets[key] = WalletId.new()
        return self.wallets[key]


class FakeLoginChallengeRepository:
    def __init__(self) -> None:
        self.challenges_by_nonce: dict[str, LoginChallenge] = {}

    def save(self, challenge: LoginChallenge) -> None:
        self.challenges_by_nonce[challenge.nonce.value] = challenge

    def get_by_nonce(self, nonce: AuthNonce) -> LoginChallenge | None:
        return self.challenges_by_nonce.get(nonce.value)

    def get_issued_by_wallet(self, wallet: WalletAddress) -> LoginChallenge | None:
        issued = [
            challenge
            for challenge in self.challenges_by_nonce.values()
            if challenge.wallet == wallet and challenge.status is ChallengeStatus.ISSUED
        ]
        issued.sort(key=lambda challenge: challenge.issued_at, reverse=True)
        return issued[0] if issued else None


class FakeAuthSessionRepository:
    def __init__(self) -> None:
        self.sessions_by_id: dict[str, AuthSession] = {}

    def save(self, session: AuthSession) -> None:
        self.sessions_by_id[str(session.session_id)] = session

    def get_by_id(self, session_id: SessionId) -> AuthSession | None:
        return self.sessions_by_id.get(str(session_id))

    def get_by_refresh_token_hash(self, refresh_token_hash: RefreshTokenHash) -> AuthSession | None:
        return next(
            (
                session
                for session in self.sessions_by_id.values()
                if session.refresh_token_hash == refresh_token_hash
            ),
            None,
        )


class FakeAuthEventPublisher:
    def __init__(self) -> None:
        self.published: list[object] = []

    def publish(self, event: object) -> None:
        self.published.append(event)

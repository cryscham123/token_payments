from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import get_type_hints

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.adapter.wallet_signature import (  # noqa: E402
    ClientWalletSignatureVerifier,
)
from token_payments.contexts.auth.application import (  # noqa: E402
    AuthApplicationError,
    AuthApplicationService,
    AuthErrorCode,
    LoginWithMetaMaskCommand,
    RequestLoginChallengeCommand,
    WalletSignatureVerificationFailure,
    WalletSignatureVerificationResult,
    WalletSignatureVerifier,
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
from token_payments.shared.domain import UserId, WalletAddress  # noqa: E402


NOW = datetime(2026, 5, 18, 2, 0, tzinfo=UTC)
WALLET = WalletAddress("0x1111111111111111111111111111111111111111")
OTHER_WALLET = WalletAddress("0x2222222222222222222222222222222222222222")
DOMAIN = "token-payments.local"
CHAIN_ID = 1337
USER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"
SESSION_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"


def test_application_wallet_signature_port_is_account_type_neutral() -> None:
    hints = get_type_hints(WalletSignatureVerifier.verify_signature)

    assert hasattr(WalletSignatureVerifier, "verify_signature")
    assert not hasattr(WalletSignatureVerifier, "recover_address")
    assert hints["wallet"] is WalletAddress
    assert hints["message"] is str
    assert hints["signature"] is str
    assert hints["chain_id"] is int
    assert hints["return"] is WalletSignatureVerificationResult


def test_eoa_verifier_compares_recovered_wallet_to_requested_wallet() -> None:
    client = RecoveringWalletClient(recovered_wallet="0x" + str(WALLET)[2:].upper())
    verifier = ClientWalletSignatureVerifier(client, supported_chain_ids=(CHAIN_ID,))

    result = verifier.verify_signature(
        wallet=WALLET,
        message="Sign in to Token Payments",
        signature="0xsignature",
        chain_id=CHAIN_ID,
    )

    assert result == WalletSignatureVerificationResult.verified()
    assert client.calls == [("Sign in to Token Payments", "0xsignature")]


def test_eoa_verifier_maps_invalid_signature_to_bounded_failure() -> None:
    verifier = ClientWalletSignatureVerifier(RaisingWalletClient(), supported_chain_ids=(CHAIN_ID,))

    result = verifier.verify_signature(
        wallet=WALLET,
        message="Sign in to Token Payments",
        signature="0xbad",
        chain_id=CHAIN_ID,
    )

    assert result == WalletSignatureVerificationResult.failed(
        WalletSignatureVerificationFailure.INVALID_SIGNATURE
    )


def test_eoa_verifier_maps_recovered_wallet_mismatch_to_bounded_failure() -> None:
    verifier = ClientWalletSignatureVerifier(RecoveringWalletClient(str(OTHER_WALLET)), supported_chain_ids=(CHAIN_ID,))

    result = verifier.verify_signature(
        wallet=WALLET,
        message="Sign in to Token Payments",
        signature="0xsignature",
        chain_id=CHAIN_ID,
    )

    assert result == WalletSignatureVerificationResult.failed(
        WalletSignatureVerificationFailure.WALLET_MISMATCH
    )


def test_eoa_verifier_maps_unsupported_chain_without_recovering_signature() -> None:
    client = RecoveringWalletClient(str(WALLET))
    verifier = ClientWalletSignatureVerifier(client, supported_chain_ids=(1,))

    result = verifier.verify_signature(
        wallet=WALLET,
        message="Sign in to Token Payments",
        signature="0xsignature",
        chain_id=CHAIN_ID,
    )

    assert result == WalletSignatureVerificationResult.failed(
        WalletSignatureVerificationFailure.UNSUPPORTED_CHAIN
    )
    assert client.calls == []


def test_auth_service_uses_verifier_result_instead_of_recovered_address() -> None:
    service, repositories, verifier = _service(VerificationOnlyVerifier(WalletSignatureVerificationResult.verified()))
    challenge = service.requestLoginChallenge(
        RequestLoginChallengeCommand(wallet_address=WALLET, domain=DOMAIN, chain_id=CHAIN_ID)
    )

    result = service.loginWithMetaMask(
        LoginWithMetaMaskCommand(
            wallet_address=WALLET,
            message=challenge.signing_message,
            signature="signature-valid",
            device_id="browser-1",
        )
    )

    assert result.user.primary_wallet == WALLET
    assert repositories.challenges.get_by_nonce(challenge.challenge.nonce).status is ChallengeStatus.VERIFIED
    assert verifier.calls == [(WALLET, challenge.signing_message, "signature-valid", CHAIN_ID)]


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (WalletSignatureVerificationFailure.INVALID_SIGNATURE, AuthErrorCode.INVALID_SIGNATURE),
        (WalletSignatureVerificationFailure.WALLET_MISMATCH, AuthErrorCode.WALLET_MISMATCH),
        (WalletSignatureVerificationFailure.UNSUPPORTED_CHAIN, AuthErrorCode.INVALID_SIGNATURE),
    ],
)
def test_auth_service_maps_verifier_failures_to_auth_errors(
    failure: WalletSignatureVerificationFailure,
    expected_code: AuthErrorCode,
) -> None:
    service, repositories, _verifier = _service(
        VerificationOnlyVerifier(WalletSignatureVerificationResult.failed(failure))
    )
    challenge = service.requestLoginChallenge(
        RequestLoginChallengeCommand(wallet_address=WALLET, domain=DOMAIN, chain_id=CHAIN_ID)
    )

    with pytest.raises(AuthApplicationError) as exc:
        service.loginWithMetaMask(
            LoginWithMetaMaskCommand(
                wallet_address=WALLET,
                message=challenge.signing_message,
                signature="signature-invalid",
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
    verifier: "VerificationOnlyVerifier",
) -> tuple[AuthApplicationService, FakeRepositories, "VerificationOnlyVerifier"]:
    repositories = FakeRepositories(
        users=FakeUserRepository(),
        challenges=FakeLoginChallengeRepository(),
        sessions=FakeAuthSessionRepository(),
        events=FakeAuthEventPublisher(),
    )
    clock = FakeClock(NOW)
    service = AuthApplicationService(
        clock=clock,
        nonce_generator=SequenceGenerator(("nonce-001",)),
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


class VerificationOnlyVerifier:
    def __init__(self, result: WalletSignatureVerificationResult) -> None:
        self.result = result
        self.calls: list[tuple[WalletAddress, str, str, int]] = []

    def verify_signature(
        self,
        wallet: WalletAddress,
        message: str,
        signature: str,
        chain_id: int,
    ) -> WalletSignatureVerificationResult:
        self.calls.append((wallet, message, signature, chain_id))
        return self.result


class RecoveringWalletClient:
    def __init__(self, recovered_wallet: str) -> None:
        self.recovered_wallet = recovered_wallet
        self.calls: list[tuple[str, str]] = []

    def recover_address(self, message: str, signature: str) -> str:
        self.calls.append((message, signature))
        return self.recovered_wallet


class RaisingWalletClient:
    def recover_address(self, message: str, signature: str) -> str:
        raise ValueError("bad signature")


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

    def save(self, user: User) -> None:
        self.users_by_id[str(user.user_id)] = user

    def get_by_id(self, user_id: UserId) -> User | None:
        return self.users_by_id.get(str(user_id))

    def get_by_wallet(self, wallet: WalletAddress) -> User | None:
        return next((user for user in self.users_by_id.values() if user.primary_wallet == wallet), None)


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

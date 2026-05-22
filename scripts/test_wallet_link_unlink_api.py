from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiAuthContext, ApiRequest  # noqa: E402
from token_payments.api.auth import AuthApi  # noqa: E402
from token_payments.contexts.auth.application import (  # noqa: E402
    AuthApplicationError,
    AuthApplicationService,
    AuthErrorCode,
    LinkWalletCommand,
    RequestWalletLinkChallengeCommand,
    RevokeWalletCommand,
    SetPrimaryWalletCommand,
    WalletSignatureVerificationFailure,
    WalletSignatureVerificationResult,
)
from token_payments.contexts.auth.domain import (  # noqa: E402
    AuthNonce,
    AuthSession,
    ChallengePurpose,
    ChallengeStatus,
    IssuedToken,
    LoginChallenge,
    RefreshTokenHash,
    SessionId,
    User,
    WalletLinkedEvent,
    WalletPrimaryChangedEvent,
    WalletRevokedEvent,
)
from token_payments.contexts.auth.domain.wallet import (  # noqa: E402
    UserWallet,
    WalletId,
    WalletType,
    WalletVerificationStatus,
)
from token_payments.shared.domain import UserId, WalletAddress  # noqa: E402


NOW = datetime(2026, 5, 22, 1, 0, tzinfo=UTC)
USER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"
OTHER_USER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c31"
SESSION_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"
PRIMARY_WALLET_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c41"
SECONDARY_WALLET_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c42"
POLYGON_WALLET_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c43"
DOMAIN = "token-payments.local"
CHAIN_ID = 11155111
POLYGON_CHAIN_ID = 137
PRIMARY_WALLET = "0x1111111111111111111111111111111111111111"
SECONDARY_WALLET = "0x2222222222222222222222222222222222222222"
POLYGON_WALLET = "0x3333333333333333333333333333333333333333"


def test_wallet_link_challenge_requires_authenticated_user() -> None:
    service, _repositories, _verifier = _service(nonces=("link-nonce-1",))
    api = AuthApi(service)

    response = api.request_wallet_link_challenge(
        ApiRequest(
            request_id="req-link-unauthenticated",
            method="POST",
            path="/auth/wallets/challenges",
            body={"walletAddress": SECONDARY_WALLET, "domain": DOMAIN, "chainId": CHAIN_ID},
            received_at=NOW,
        )
    )

    assert response.status_code == 401
    assert response.body["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_wallet_link_challenge_is_siwe_and_distinct_from_login_challenge() -> None:
    service, repositories, _verifier = _service(nonces=("link-nonce-1",))
    api = AuthApi(service)

    response = api.request_wallet_link_challenge(
        ApiRequest(
            request_id="req-link-challenge",
            method="POST",
            path="/auth/wallets/challenges",
            auth_context=_auth_context(),
            body={"walletAddress": SECONDARY_WALLET, "domain": DOMAIN, "chainId": CHAIN_ID},
            received_at=NOW,
        )
    )

    assert response.status_code == 201
    assert response.body["purpose"] == "WALLET_LINK"
    assert response.body["walletAddress"] == SECONDARY_WALLET
    assert response.body["chainId"] == CHAIN_ID
    assert response.body["signingMessage"].splitlines() == [
        f"{DOMAIN} wants you to sign in with your Ethereum account:",
        SECONDARY_WALLET,
        "",
        f"URI: https://{DOMAIN}",
        "Version: 1",
        f"Chain ID: {CHAIN_ID}",
        "Nonce: linknonce1",
        f"Issued At: {NOW.isoformat()}",
        f"Expiration Time: {(NOW + timedelta(minutes=5)).isoformat()}",
    ]
    saved = repositories.challenges.get_by_nonce(AuthNonce("linknonce1", NOW + timedelta(minutes=5)))
    assert saved is not None
    assert saved.purpose is ChallengePurpose.WALLET_LINK
    assert saved.target_user_id == UserId(USER_ID)


def test_link_wallet_requires_challenge_target_wallet_chain_and_authenticated_user_match() -> None:
    service, repositories, verifier = _service(nonces=("link-nonce-1", "link-nonce-2"))
    challenge = service.requestWalletLinkChallenge(
        RequestWalletLinkChallengeCommand(
            actor_user_id=UserId(USER_ID),
            wallet_address=SECONDARY_WALLET,
            domain=DOMAIN,
            chain_id=CHAIN_ID,
        )
    )
    verifier.recovered_wallet = SECONDARY_WALLET

    with pytest.raises(AuthApplicationError) as wrong_chain:
        service.linkWallet(
            LinkWalletCommand(
                actor_user_id=UserId(USER_ID),
                wallet_address=SECONDARY_WALLET,
                message=challenge.signing_message.replace(f"Chain ID: {CHAIN_ID}", "Chain ID: 1"),
                signature="signature-valid",
            )
        )
    assert wrong_chain.value.code is AuthErrorCode.SIWE_MESSAGE_MISMATCH
    assert repositories.wallets.get_active_by_address(CHAIN_ID, WalletAddress(SECONDARY_WALLET)) is None

    repositories.users.save(User.register_by_wallet(UserId(OTHER_USER_ID), POLYGON_WALLET))
    with pytest.raises(AuthApplicationError) as wrong_user:
        service.linkWallet(
            LinkWalletCommand(
                actor_user_id=UserId(OTHER_USER_ID),
                wallet_address=SECONDARY_WALLET,
                message=challenge.signing_message,
                signature="signature-valid",
            )
        )
    assert wrong_user.value.code is AuthErrorCode.WALLET_LINK_CHALLENGE_MISMATCH

    challenge = service.requestWalletLinkChallenge(
        RequestWalletLinkChallengeCommand(
            actor_user_id=UserId(USER_ID),
            wallet_address=SECONDARY_WALLET,
            domain=DOMAIN,
            chain_id=CHAIN_ID,
        )
    )
    linked = service.linkWallet(
        LinkWalletCommand(
            actor_user_id=UserId(USER_ID),
            wallet_address=SECONDARY_WALLET,
            message=challenge.signing_message,
            signature="signature-valid",
        )
    )

    assert linked.wallet.user_id == UserId(USER_ID)
    assert linked.wallet.address == WalletAddress(SECONDARY_WALLET)
    assert linked.wallet.chain_id == CHAIN_ID
    assert linked.wallet.verification_status is WalletVerificationStatus.VERIFIED
    assert isinstance(repositories.events.published[-1], WalletLinkedEvent)


def test_wallet_already_linked_to_another_active_user_cannot_be_linked() -> None:
    service, repositories, _verifier = _service(nonces=("link-nonce-1",))
    repositories.wallets.save(
        _wallet(
            wallet_id=WalletId(SECONDARY_WALLET_ID),
            user_id=UserId(OTHER_USER_ID),
            address=SECONDARY_WALLET,
            chain_id=CHAIN_ID,
        )
    )

    with pytest.raises(AuthApplicationError) as exc:
        service.requestWalletLinkChallenge(
            RequestWalletLinkChallengeCommand(
                actor_user_id=UserId(USER_ID),
                wallet_address=SECONDARY_WALLET,
                domain=DOMAIN,
                chain_id=CHAIN_ID,
            )
        )

    assert exc.value.code is AuthErrorCode.WALLET_ALREADY_LINKED


def test_set_primary_wallet_is_chain_scoped_and_requires_verified_active_wallet() -> None:
    service, repositories, _verifier = _service(nonces=("link-nonce-1",))
    repositories.wallets.save(_wallet(wallet_id=WalletId(PRIMARY_WALLET_ID), address=PRIMARY_WALLET, primary=True))
    repositories.wallets.save(_wallet(wallet_id=WalletId(SECONDARY_WALLET_ID), address=SECONDARY_WALLET, primary=False))
    repositories.wallets.save(
        _wallet(
            wallet_id=WalletId(POLYGON_WALLET_ID),
            address=POLYGON_WALLET,
            chain_id=POLYGON_CHAIN_ID,
            primary=True,
        )
    )

    result = service.setPrimaryWallet(
        SetPrimaryWalletCommand(actor_user_id=UserId(USER_ID), wallet_id=WalletId(SECONDARY_WALLET_ID))
    )

    assert result.wallet.primary is True
    assert repositories.wallets.get_by_id(WalletId(PRIMARY_WALLET_ID)).primary is False
    assert repositories.wallets.get_by_id(WalletId(POLYGON_WALLET_ID)).primary is True
    assert isinstance(repositories.events.published[-1], WalletPrimaryChangedEvent)

    revoked = repositories.wallets.get_by_id(WalletId(SECONDARY_WALLET_ID)).revoke(NOW)
    repositories.wallets.save(revoked)
    with pytest.raises(AuthApplicationError) as exc:
        service.setPrimaryWallet(
            SetPrimaryWalletCommand(actor_user_id=UserId(USER_ID), wallet_id=WalletId(SECONDARY_WALLET_ID))
        )
    assert exc.value.code is AuthErrorCode.WALLET_NOT_ACTIVE


def test_revoke_wallet_blocks_last_verified_wallet_and_publishes_audit_event() -> None:
    service, repositories, _verifier = _service(nonces=("link-nonce-1",))
    repositories.wallets.save(_wallet(wallet_id=WalletId(PRIMARY_WALLET_ID), address=PRIMARY_WALLET, primary=True))
    repositories.wallets.save(_wallet(wallet_id=WalletId(SECONDARY_WALLET_ID), address=SECONDARY_WALLET))

    revoked = service.revokeWallet(
        RevokeWalletCommand(
            actor_user_id=UserId(USER_ID),
            wallet_id=WalletId(SECONDARY_WALLET_ID),
            revoked_at=NOW,
        )
    )

    assert revoked.wallet.verification_status is WalletVerificationStatus.REVOKED
    assert revoked.wallet.revoked_at == NOW
    assert isinstance(repositories.events.published[-1], WalletRevokedEvent)

    with pytest.raises(AuthApplicationError) as exc:
        service.revokeWallet(
            RevokeWalletCommand(
                actor_user_id=UserId(USER_ID),
                wallet_id=WalletId(PRIMARY_WALLET_ID),
                revoked_at=NOW,
            )
        )
    assert exc.value.code is AuthErrorCode.LAST_WALLET_REVOKE_DENIED


@dataclass
class FakeRepositories:
    users: "FakeUserRepository"
    wallets: "FakeUserWalletRepository"
    challenges: "FakeLoginChallengeRepository"
    sessions: "FakeAuthSessionRepository"
    events: "FakeAuthEventPublisher"


def _service(
    *,
    nonces: tuple[str, ...],
) -> tuple[AuthApplicationService, FakeRepositories, "FakeWalletSignatureVerifier"]:
    repositories = FakeRepositories(
        users=FakeUserRepository(),
        wallets=FakeUserWalletRepository(),
        challenges=FakeLoginChallengeRepository(),
        sessions=FakeAuthSessionRepository(),
        events=FakeAuthEventPublisher(),
    )
    repositories.users.save(User.register_by_wallet(UserId(USER_ID), PRIMARY_WALLET))
    clock = FakeClock(NOW)
    verifier = FakeWalletSignatureVerifier()
    service = AuthApplicationService(
        clock=clock,
        nonce_generator=SequenceGenerator(nonces),
        user_id_generator=SequenceGenerator((USER_ID,)),
        session_id_generator=SequenceGenerator((SESSION_ID,)),
        users=repositories.users,
        wallets=repositories.wallets,
        login_challenges=repositories.challenges,
        sessions=repositories.sessions,
        signature_verifier=verifier,
        token_issuer=DeterministicTokenIssuer(clock),
        event_publisher=repositories.events,
    )
    return service, repositories, verifier


def _auth_context() -> ApiAuthContext:
    return ApiAuthContext(user_id=USER_ID, session_id=SESSION_ID, scopes=("user:self",))


def _wallet(
    *,
    wallet_id: WalletId,
    user_id: UserId = UserId(USER_ID),
    address: str,
    chain_id: int = CHAIN_ID,
    primary: bool = False,
) -> UserWallet:
    return UserWallet(
        wallet_id=wallet_id,
        user_id=user_id,
        address=WalletAddress(address),
        chain_id=chain_id,
        wallet_type=WalletType.EOA,
        verification_status=WalletVerificationStatus.VERIFIED,
        primary=primary,
        linked_at=NOW,
    )


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
            return WalletSignatureVerificationResult.failed(WalletSignatureVerificationFailure.INVALID_SIGNATURE)
        if WalletAddress(self.recovered_wallet) != wallet:
            return WalletSignatureVerificationResult.failed(WalletSignatureVerificationFailure.WALLET_MISMATCH)
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

    def save(self, user: User) -> None:
        self.users_by_id[str(user.user_id)] = user

    def get_by_id(self, user_id: UserId) -> User | None:
        return self.users_by_id.get(str(user_id))

    def get_by_wallet(self, wallet: WalletAddress) -> User | None:
        return next((user for user in self.users_by_id.values() if user.primary_wallet == wallet), None)

    def get_wallet_id_for_address(self, user_id: UserId, wallet: WalletAddress) -> WalletId:
        return WalletId(PRIMARY_WALLET_ID)


class FakeUserWalletRepository:
    def __init__(self) -> None:
        self.wallets_by_id: dict[str, UserWallet] = {}

    def save(self, wallet: UserWallet) -> None:
        self.wallets_by_id[str(wallet.wallet_id)] = wallet

    def get_by_id(self, wallet_id: WalletId) -> UserWallet | None:
        return self.wallets_by_id.get(str(wallet_id))

    def get_active_by_address(self, chain_id: int, wallet: WalletAddress) -> UserWallet | None:
        return next(
            (
                item
                for item in self.wallets_by_id.values()
                if item.chain_id == chain_id and item.address == wallet and item.is_active()
            ),
            None,
        )

    def list_for_user(self, user_id: UserId) -> tuple[UserWallet, ...]:
        return tuple(item for item in self.wallets_by_id.values() if item.user_id == user_id)

    def unset_primary_for_chain(self, user_id: UserId, chain_id: int, except_wallet_id: WalletId) -> None:
        for wallet in tuple(self.wallets_by_id.values()):
            if wallet.user_id == user_id and wallet.chain_id == chain_id and wallet.wallet_id != except_wallet_id:
                self.save(UserWallet(**(wallet.__dict__ | {"primary": False})))


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

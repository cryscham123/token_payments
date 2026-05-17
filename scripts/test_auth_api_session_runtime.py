from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiRequest  # noqa: E402
from token_payments.api.auth import AuthApi  # noqa: E402
from token_payments.contexts.auth.adapter import (  # noqa: E402
    PostgresAuthSessionRepository,
    PostgresLoginChallengeRepository,
    PostgresUserRepository,
)
from token_payments.contexts.auth.application import (  # noqa: E402
    AuthApplicationError,
    AuthApplicationService,
    AuthErrorCode,
    CurrentUserQuery,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    RefreshSessionCommand,
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
    LoginRejectedEvent,
    RefreshTokenHash,
    SessionId,
    User,
    UserLoggedInEvent,
    UserRegisteredEvent,
    WalletVerifiedEvent,
)
from token_payments.shared.domain import UserId, WalletAddress  # noqa: E402


NOW = datetime(2026, 5, 10, 6, 0, tzinfo=UTC)
WALLET = "0xABCDabcdABCDabcdABCDabcdABCDabcdABCDabcd"
NORMALIZED_WALLET = "0xabcdabcdabcdabcdabcdabcdabcdabcdabcdabcd"
OTHER_WALLET = "0x9999999999999999999999999999999999999999"
USER_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21"
SESSION_ID = "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"
DOMAIN = "token-payments.local"
CHAIN_ID = 11155111


def test_auth_use_case_issues_challenge_and_signing_message_shape() -> None:
    service, repositories, _verifier, _tokens, _clock = _service(nonces=("nonce-1234",))

    result = service.requestLoginChallenge(
        RequestLoginChallengeCommand(
            wallet_address=WALLET,
            domain=DOMAIN,
            chain_id=CHAIN_ID,
        )
    )

    assert result.challenge.status is ChallengeStatus.ISSUED
    assert result.challenge.wallet == WalletAddress(NORMALIZED_WALLET)
    assert result.challenge.domain == DOMAIN
    assert result.challenge.uri == f"https://{DOMAIN}"
    assert result.challenge.chain_id == CHAIN_ID
    assert result.challenge.nonce.value == "nonce1234"
    assert result.challenge.expires_at == NOW + timedelta(minutes=5)
    assert repositories.challenges.get_by_nonce(result.challenge.nonce) == result.challenge
    assert result.signing_message.splitlines() == [
        f"{DOMAIN} wants you to sign in with your Ethereum account:",
        NORMALIZED_WALLET,
        "",
        f"URI: https://{DOMAIN}",
        "Version: 1",
        f"Chain ID: {CHAIN_ID}",
        "Nonce: nonce1234",
        f"Issued At: {NOW.isoformat()}",
        f"Expiration Time: {(NOW + timedelta(minutes=5)).isoformat()}",
    ]


def test_auth_use_case_logs_in_with_metamask_signature_and_creates_session() -> None:
    service, repositories, verifier, tokens, _clock = _service(nonces=("nonce-1234",))
    challenge = service.requestLoginChallenge(
        RequestLoginChallengeCommand(wallet_address=WALLET, domain=DOMAIN, chain_id=CHAIN_ID)
    )
    verifier.recovered_wallet = NORMALIZED_WALLET

    result = service.loginWithMetaMask(
        LoginWithMetaMaskCommand(
            wallet_address=WALLET,
            message=challenge.signing_message,
            signature="signature-valid",
            device_id="device-1",
        )
    )

    assert result.user.user_id == UserId(USER_ID)
    assert result.user.primary_wallet == WalletAddress(NORMALIZED_WALLET)
    assert result.user.last_login_at == NOW
    assert result.session.session_id == SessionId(SESSION_ID)
    assert result.session.wallet == WalletAddress(NORMALIZED_WALLET)
    assert result.session.device_id == "device-1"
    assert result.session.expires_at == NOW + timedelta(days=30)
    assert result.session.refresh_token_hash.hash != result.issued_token.refresh_token
    assert repositories.challenges.get_by_nonce(challenge.challenge.nonce).status is ChallengeStatus.VERIFIED
    assert repositories.users.get_by_wallet(WalletAddress(NORMALIZED_WALLET)) == result.user
    assert repositories.sessions.get_by_id(SessionId(SESSION_ID)) == result.session
    assert tokens.issued_sessions == [SessionId(SESSION_ID)]
    assert [type(event) for event in repositories.events.published] == [
        UserRegisteredEvent,
        WalletVerifiedEvent,
        UserLoggedInEvent,
    ]
    assert service.getCurrentUser(CurrentUserQuery(user_id=UserId(USER_ID))) == result.user


def test_auth_use_case_rejects_reused_and_expired_challenges() -> None:
    service, repositories, verifier, _tokens, clock = _service(nonces=("nonce-1234", "nonce-4567"))
    issued = service.requestLoginChallenge(
        RequestLoginChallengeCommand(wallet_address=WALLET, domain=DOMAIN, chain_id=CHAIN_ID)
    )
    verifier.recovered_wallet = NORMALIZED_WALLET
    service.loginWithMetaMask(
        LoginWithMetaMaskCommand(
            wallet_address=WALLET,
            message=issued.signing_message,
            signature="signature-valid",
            device_id="device-1",
        )
    )

    with pytest.raises(AuthApplicationError) as reused:
        service.loginWithMetaMask(
            LoginWithMetaMaskCommand(
                wallet_address=WALLET,
                message=issued.signing_message,
                signature="signature-valid",
                device_id="device-1",
            )
        )

    assert reused.value.code is AuthErrorCode.REUSED_NONCE
    assert len(repositories.sessions.sessions_by_id) == 1

    expired = service.requestLoginChallenge(
        RequestLoginChallengeCommand(wallet_address=WALLET, domain=DOMAIN, chain_id=CHAIN_ID)
    )
    clock.current = NOW + timedelta(minutes=6)
    with pytest.raises(AuthApplicationError) as expired_error:
        service.loginWithMetaMask(
            LoginWithMetaMaskCommand(
                wallet_address=WALLET,
                message=expired.signing_message,
                signature="signature-valid",
                device_id="device-1",
            )
        )

    assert expired_error.value.code is AuthErrorCode.EXPIRED_CHALLENGE
    assert repositories.challenges.get_by_nonce(expired.challenge.nonce).status is ChallengeStatus.EXPIRED
    assert isinstance(repositories.events.published[-1], LoginRejectedEvent)


def test_auth_use_case_refreshes_and_logs_out_sessions() -> None:
    service, repositories, verifier, _tokens, clock = _service(nonces=("nonce-1234",))
    challenge = service.requestLoginChallenge(
        RequestLoginChallengeCommand(wallet_address=WALLET, domain=DOMAIN, chain_id=CHAIN_ID)
    )
    verifier.recovered_wallet = NORMALIZED_WALLET
    login = service.loginWithMetaMask(
        LoginWithMetaMaskCommand(
            wallet_address=WALLET,
            message=challenge.signing_message,
            signature="signature-valid",
            device_id="device-1",
        )
    )

    clock.current = NOW + timedelta(minutes=10)
    refreshed = service.refreshSession(
        RefreshSessionCommand(
            session_id=login.session.session_id,
            refresh_token_hash=login.session.refresh_token_hash,
        )
    )

    assert refreshed.user == login.user
    assert refreshed.session.session_id == login.session.session_id
    assert refreshed.session.refresh_token_hash.rotation_version == 1
    assert refreshed.session.refresh_token_hash != login.session.refresh_token_hash
    assert refreshed.issued_token.refresh_token.startswith(f"refresh:{SESSION_ID}:1")
    assert repositories.sessions.get_by_refresh_token_hash(login.session.refresh_token_hash) is None

    logged_out = service.logout(LogoutCommand(session_id=login.session.session_id))

    assert logged_out.revoked_at == clock.current
    with pytest.raises(AuthApplicationError) as exc:
        service.refreshSession(
            RefreshSessionCommand(
                session_id=login.session.session_id,
                refresh_token_hash=refreshed.session.refresh_token_hash,
            )
        )
    assert exc.value.code is AuthErrorCode.VALIDATION_ERROR


def test_auth_api_success_responses_and_structured_error_mapping() -> None:
    service, _repositories, verifier, _tokens, _clock = _service(nonces=("nonce-1234",))
    api = AuthApi(service)

    challenge_response = api.request_login_challenge(
        ApiRequest(
            request_id="req-1",
            method="POST",
            path="/auth/login-challenges",
            body={"walletAddress": WALLET, "domain": DOMAIN, "chainId": CHAIN_ID},
            received_at=NOW,
        )
    )

    assert challenge_response.status_code == 201
    assert challenge_response.body["walletAddress"] == NORMALIZED_WALLET
    assert challenge_response.body["nonce"] == "nonce1234"
    assert challenge_response.body["domain"] == DOMAIN
    assert challenge_response.body["address"] == NORMALIZED_WALLET
    assert challenge_response.body["uri"] == f"https://{DOMAIN}"
    assert challenge_response.body["version"] == "1"
    assert challenge_response.body["chainId"] == CHAIN_ID
    assert challenge_response.body["issuedAt"] == NOW.isoformat()
    assert challenge_response.body["expirationTime"] == (NOW + timedelta(minutes=5)).isoformat()
    assert "signingMessage" in challenge_response.body

    verifier.recovered_wallet = NORMALIZED_WALLET
    login_response = api.login_with_metamask(
        ApiRequest(
            request_id="req-2",
            method="POST",
            path="/auth/metamask-login",
            body={
                "walletAddress": WALLET,
                "message": challenge_response.body["signingMessage"],
                "signature": "signature-valid",
                "deviceId": "device-1",
            },
            received_at=NOW,
        )
    )

    assert login_response.status_code == 200
    assert login_response.body["user"]["walletAddress"] == NORMALIZED_WALLET
    assert login_response.body["session"]["sessionId"] == SESSION_ID
    assert login_response.body["token"]["accessToken"].startswith(f"access:{USER_ID}:{SESSION_ID}")

    reuse_response = api.login_with_metamask(
        ApiRequest(
            request_id="req-3",
            method="POST",
            path="/auth/metamask-login",
            body={
                "walletAddress": WALLET,
                "message": challenge_response.body["signingMessage"],
                "signature": "signature-valid",
                "deviceId": "device-1",
            },
            received_at=NOW,
        )
    )

    assert reuse_response.status_code == 409
    assert reuse_response.body == {
        "error": {
            "code": "REUSED_NONCE",
            "message": "login challenge nonce has already been used",
        }
    }

    validation_response = api.request_login_challenge(
        ApiRequest(
            request_id="req-4",
            method="POST",
            path="/auth/login-challenges",
            body={"domain": DOMAIN, "chainId": CHAIN_ID},
            received_at=NOW,
        )
    )

    assert validation_response.status_code == 400
    assert validation_response.body["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        (AuthErrorCode.INVALID_SIGNATURE, 401),
        (AuthErrorCode.EXPIRED_CHALLENGE, 409),
        (AuthErrorCode.REUSED_NONCE, 409),
        (AuthErrorCode.WALLET_MISMATCH, 401),
        (AuthErrorCode.SIWE_MESSAGE_MISMATCH, 401),
        (AuthErrorCode.VALIDATION_ERROR, 400),
    ],
)
def test_auth_api_maps_all_auth_error_codes(code: AuthErrorCode, expected_status: int) -> None:
    api = AuthApi(RejectingUseCase(code))

    response = api.login_with_metamask(
        ApiRequest(
            request_id="req-error",
            method="POST",
            path="/auth/metamask-login",
            body={
                "walletAddress": WALLET,
                "message": "bad message",
                "signature": "bad signature",
                "deviceId": "device-1",
            },
            received_at=NOW,
        )
    )

    assert response.status_code == expected_status
    assert response.body["error"]["code"] == code.value
    assert response.headers["Content-Type"] == "application/json"


def test_auth_postgres_repositories_round_trip_user_challenge_and_session() -> None:
    connection = FakePostgresConnection()
    users = PostgresUserRepository(connection)
    challenges = PostgresLoginChallengeRepository(connection)
    sessions = PostgresAuthSessionRepository(connection)
    user = User.register_by_wallet(UserId(USER_ID), WALLET).record_login(NOW)
    challenge = LoginChallenge.issue(
        wallet=WALLET,
        nonce=AuthNonce("nonce-123", NOW + timedelta(minutes=5)),
        issued_at=NOW,
        domain=DOMAIN,
        uri=f"https://{DOMAIN}",
        chain_id=CHAIN_ID,
    ).verify_signature(NORMALIZED_WALLET, now=NOW + timedelta(seconds=30))
    session = AuthSession.create(
        session_id=SessionId(SESSION_ID),
        user_id=UserId(USER_ID),
        wallet=WALLET,
        refresh_token_hash=RefreshTokenHash("hash-1", "salt-1", 0),
        device_id="device-1",
        expires_at=NOW + timedelta(days=30),
    )

    assert users.get_by_id(UserId(USER_ID)) is None
    assert challenges.get_by_nonce(challenge.nonce) is None
    assert sessions.get_by_id(SessionId(SESSION_ID)) is None

    users.save(user)
    challenges.save(challenge)
    sessions.save(session)

    assert users.get_by_id(UserId(USER_ID)) == user
    assert users.get_by_wallet(WalletAddress(NORMALIZED_WALLET)) == user
    assert challenges.get_by_nonce(challenge.nonce) == challenge
    assert challenges.get_issued_by_wallet(WalletAddress(NORMALIZED_WALLET)) is None
    assert sessions.get_by_id(SessionId(SESSION_ID)) == session
    assert sessions.get_by_refresh_token_hash(RefreshTokenHash("hash-1", "salt-1", 0)) == session
    normalized_sql = _normalize_sql("\n".join(statement.sql for statement in connection.statements))
    assert "insert into auth_users" in normalized_sql
    assert "insert into auth_login_challenges" in normalized_sql
    assert "insert into auth_sessions" in normalized_sql
    assert "commit" not in normalized_sql
    assert "rollback" not in normalized_sql


def test_auth_schema_exports_and_import_boundaries() -> None:
    import token_payments.contexts.auth.adapter as auth_adapter

    schema = (ROOT / "app/postgres/init.d/001-token-payments-schema.sql").read_text(encoding="utf-8")
    normalized = schema.lower()

    assert {
        "PostgresUserRepository",
        "PostgresLoginChallengeRepository",
        "PostgresAuthSessionRepository",
    } <= set(auth_adapter.__all__)
    for table in ("auth_users", "auth_login_challenges", "auth_sessions"):
        assert f"create table if not exists {table}" in normalized

    violations: dict[str, list[str]] = {}
    for layer in ("domain", "application"):
        for path in (ROOT / f"app/token_payments/contexts/auth/{layer}").glob("**/*.py"):
            illegal = sorted(
                module
                for module in _imported_modules(path)
                if module.startswith("token_payments.api")
                or module.startswith("token_payments.contexts.auth.adapter")
                or module.startswith("token_payments.shared.adapter")
                or ".adapter" in module
            )
            if illegal:
                violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


@dataclass
class FakeRepositories:
    users: "FakeUserRepository"
    challenges: "FakeLoginChallengeRepository"
    sessions: "FakeAuthSessionRepository"
    events: "FakeAuthEventPublisher"


def _service(
    *,
    nonces: tuple[str, ...],
) -> tuple[
    AuthApplicationService,
    FakeRepositories,
    "FakeWalletSignatureVerifier",
    "DeterministicTokenIssuer",
    "FakeClock",
]:
    repositories = FakeRepositories(
        users=FakeUserRepository(),
        challenges=FakeLoginChallengeRepository(),
        sessions=FakeAuthSessionRepository(),
        events=FakeAuthEventPublisher(),
    )
    clock = FakeClock(NOW)
    verifier = FakeWalletSignatureVerifier()
    tokens = DeterministicTokenIssuer(clock)
    service = AuthApplicationService(
        clock=clock,
        nonce_generator=SequenceGenerator(nonces),
        user_id_generator=SequenceGenerator((USER_ID,)),
        session_id_generator=SequenceGenerator((SESSION_ID,)),
        users=repositories.users,
        login_challenges=repositories.challenges,
        sessions=repositories.sessions,
        signature_verifier=verifier,
        token_issuer=tokens,
        event_publisher=repositories.events,
    )
    return service, repositories, verifier, tokens, clock


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
        self.issued_sessions: list[SessionId] = []
        self.refreshed_sessions: list[SessionId] = []

    def issue_tokens(self, user: User, session: AuthSession) -> IssuedToken:
        self.issued_sessions.append(session.session_id)
        return IssuedToken(
            access_token=f"access:{user.user_id}:{session.session_id}:0",
            refresh_token=f"refresh:{session.session_id}:0",
            expires_at=self._clock.now() + timedelta(minutes=15),
        )

    def refresh_tokens(self, session: AuthSession) -> IssuedToken:
        self.refreshed_sessions.append(session.session_id)
        next_version = session.refresh_token_hash.rotation_version + 1
        return IssuedToken(
            access_token=f"access:{session.user_id}:{session.session_id}:{next_version}",
            refresh_token=f"refresh:{session.session_id}:{next_version}",
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


class RejectingUseCase:
    def __init__(self, code: AuthErrorCode) -> None:
        self._code = code

    def requestLoginChallenge(self, command: object) -> object:
        raise AuthApplicationError(self._code, "rejected for test")

    def loginWithMetaMask(self, command: object) -> object:
        raise AuthApplicationError(self._code, "rejected for test")

    def refreshSession(self, command: object) -> object:
        raise AuthApplicationError(self._code, "rejected for test")

    def logout(self, command: object) -> object:
        raise AuthApplicationError(self._code, "rejected for test")

    def getCurrentUser(self, query: object) -> object:
        raise AuthApplicationError(self._code, "rejected for test")


@dataclass(frozen=True)
class ExecutedStatement:
    sql: str
    params: Mapping[str, Any]


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class FakePostgresConnection:
    def __init__(self) -> None:
        self.statements: list[ExecutedStatement] = []
        self.users: dict[str, dict[str, Any]] = {}
        self.challenges: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> FakeResult:
        params = dict(params or {})
        self.statements.append(ExecutedStatement(sql=sql, params=params))
        normalized = _normalize_sql(sql)

        if "insert into auth_users" in normalized:
            self.users[str(params["user_id"])] = params
            return FakeResult(rowcount=1)
        if "from auth_users" in normalized and "user_id" in params:
            row = self.users.get(str(params["user_id"]))
            return FakeResult([dict(row)] if row else [], rowcount=1 if row else 0)
        if "from auth_users" in normalized and "wallet_address" in params:
            row = next(
                (
                    user
                    for user in self.users.values()
                    if user["wallet_address"] == str(params["wallet_address"])
                ),
                None,
            )
            return FakeResult([dict(row)] if row else [], rowcount=1 if row else 0)

        if "insert into auth_login_challenges" in normalized:
            self.challenges[str(params["nonce_value"])] = params
            return FakeResult(rowcount=1)
        if "from auth_login_challenges" in normalized and "nonce_value" in params:
            row = self.challenges.get(str(params["nonce_value"]))
            return FakeResult([dict(row)] if row else [], rowcount=1 if row else 0)
        if "from auth_login_challenges" in normalized and "wallet_address" in params:
            rows = [
                dict(row)
                for row in self.challenges.values()
                if row["wallet_address"] == str(params["wallet_address"]) and row["status"] == "ISSUED"
            ]
            rows.sort(key=lambda row: row["issued_at"], reverse=True)
            return FakeResult(rows, rowcount=len(rows))

        if "insert into auth_sessions" in normalized:
            self.sessions[str(params["session_id"])] = params
            return FakeResult(rowcount=1)
        if "from auth_sessions" in normalized and "session_id" in params:
            row = self.sessions.get(str(params["session_id"]))
            return FakeResult([dict(row)] if row else [], rowcount=1 if row else 0)
        if "from auth_sessions" in normalized and "refresh_token_hash" in params:
            row = next(
                (
                    session
                    for session in self.sessions.values()
                    if session["refresh_token_hash"] == str(params["refresh_token_hash"])
                    and session["refresh_token_salt"] == str(params["refresh_token_salt"])
                    and session["refresh_token_rotation_version"] == params["refresh_token_rotation_version"]
                ),
                None,
            )
            return FakeResult([dict(row)] if row else [], rowcount=1 if row else 0)

        raise AssertionError(f"unexpected SQL: {sql}")


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().split())


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules

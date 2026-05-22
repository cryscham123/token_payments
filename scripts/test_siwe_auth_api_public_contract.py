from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import ApiRequest  # noqa: E402
from token_payments.api.auth import AuthApi  # noqa: E402
from token_payments.contexts.auth.application import (  # noqa: E402
    CurrentUserQuery,
    LoginChallengeResult,
    LoginResult,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    RefreshSessionCommand,
    RequestLoginChallengeCommand,
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


API_SPEC_PATH = ROOT / "docs" / "API_SPEC.md"
README_PATH = ROOT / "README.md"
APP_README_PATH = ROOT / "app" / "README.md"
COLLECTION_PATH = ROOT / "postman" / "token-payments.local.postman_collection.json"
ENVIRONMENT_PATH = ROOT / "postman" / "token-payments.local.postman_environment.json"
COOKIE_EXPECTED_PATH = ROOT / "postman" / "token-payments.cookie-auth.expected.json"
API_EXPECTED_PATH = ROOT / "postman" / "expected" / "token-payments.api.expected.json"

NOW = datetime(2026, 5, 18, 4, 0, tzinfo=UTC)
WALLET = WalletAddress("0x1111111111111111111111111111111111111111")
DOMAIN = "token-payments.local"
URI = "https://token-payments.local"
CHAIN_ID = 1337
NONCE = "N0NCE001"
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
SESSION_ID = SessionId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")


def test_auth_api_challenge_and_session_payloads_expose_siwe_metadata_without_secret_values() -> None:
    api = AuthApi(StaticSiweAuthUseCase())

    challenge = api.request_login_challenge(
        ApiRequest(
            request_id="req-siwe-public-contract",
            method="POST",
            path="/auth/challenges",
            body={"walletAddress": str(WALLET), "domain": DOMAIN, "uri": URI, "chainId": CHAIN_ID},
            received_at=NOW,
        )
    )

    assert challenge.status_code == 201
    challenge_body = challenge.body
    assert challenge_body["domain"] == DOMAIN
    assert challenge_body["address"] == str(WALLET)
    assert challenge_body["uri"] == URI
    assert challenge_body["version"] == "1"
    assert challenge_body["chainId"] == CHAIN_ID
    assert challenge_body["issuedAt"] == NOW.isoformat()
    assert challenge_body["expirationTime"] == (NOW + timedelta(minutes=5)).isoformat()
    assert challenge_body["signingMessage"].splitlines() == _siwe_message_lines()
    assert challenge_body["signatureVerification"] == _expected_signature_metadata()

    login = api.login_with_metamask(
        ApiRequest(
            request_id="req-siwe-login-public-contract",
            method="POST",
            path="/auth/sessions",
            body={
                "walletAddress": str(WALLET),
                "message": challenge_body["signingMessage"],
                "signature": "0xredacted-signature",
                "deviceId": "browser-1",
            },
            received_at=NOW,
        )
    )

    assert login.status_code == 200
    assert login.body["signatureVerification"] == _expected_signature_metadata()
    assert login.body["token"]["accessToken"] == "<opaque-access-token>"
    assert "0xredacted-signature" not in json.dumps(login.body, sort_keys=True)
    assert challenge_body["signingMessage"] not in json.dumps(login.body, sort_keys=True)


def test_api_spec_documents_siwe_challenge_session_erc1271_and_cookie_first_runtime_contract() -> None:
    api_spec = API_SPEC_PATH.read_text(encoding="utf-8")

    for required in (
        "SIWE v1 서명용 login challenge",
        '"domain": "token-payments.local"',
        '"address": "0x1111111111111111111111111111111111111111"',
        '"uri": "https://token-payments.local"',
        '"version": "1"',
        '"chainId": 1337',
        '"issuedAt": "2026-05-17T10:00:00+09:00"',
        '"expirationTime": "2026-05-17T10:30:00+09:00"',
        '"signatureVerification"',
        '"signatureVerificationMethod": "SIWE_PERSONAL_SIGN_EOA_OR_ERC1271"',
        '"supportedWalletTypes"',
        '"DEPLOYED_SMART_WALLET"',
        "isValidSignature(bytes32,bytes)",
        "0x1626ba7e",
        "ERC-6492",
        "future scope",
    ):
        assert required in api_spec

    for preserved in (
        "HttpOnly",
        "X-CSRF-Token",
        "Authorization: Bearer <accessToken>`은 non-browser client",
        "CORS_ALLOWED_ORIGINS",
        "Access-Control-Allow-Origin: *` must not be used with credentials",
        "refresh_token` HttpOnly cookie",
        "SESSION_ACTIVE_KEY_ID",
        "SESSION_SIGNING_KEYS",
    ):
        assert preserved in api_spec


def test_postman_fixtures_capture_siwe_fields_and_smart_wallet_metadata_without_raw_signed_material() -> None:
    collection = _read_json(COLLECTION_PATH)
    environment = _read_json(ENVIRONMENT_PATH)
    api_expected = _read_json(API_EXPECTED_PATH)
    cookie_expected = _read_json(COOKIE_EXPECTED_PATH)
    items = _operation_items(collection)

    challenge_request = _postman_json_body(items["requestLoginChallenge"])
    assert challenge_request == {
        "walletAddress": "{{walletAddress}}",
        "domain": "{{loginDomain}}",
        "uri": "{{loginUri}}",
        "chainId": 1337,
    }

    challenge_script = "\n".join(_event_script(items["requestLoginChallenge"], "test"))
    for assertion in (
        "body.domain",
        "body.address",
        "body.uri",
        "body.version",
        "body.chainId",
        "body.issuedAt",
        "body.expirationTime",
        "body.signatureVerification.signatureVerificationMethod",
        "DEPLOYED_SMART_WALLET",
        "future_scope",
    ):
        assert assertion in challenge_script

    challenge_example = _response_body(items["requestLoginChallenge"], 201)
    assert challenge_example["signingMessage"] == "<redacted-siwe-personal-sign-message>"
    assert challenge_example["domain"] == "token-payments.local"
    assert challenge_example["uri"] == "https://token-payments.local"
    assert challenge_example["version"] == "1"
    assert challenge_example["chainId"] == 1337
    assert challenge_example["signatureVerification"] == _expected_signature_metadata()

    login_example = _response_body(items["loginWithMetaMask"], 200)
    assert login_example["signatureVerification"] == _expected_signature_metadata()
    assert login_example["token"]["transport"] == "cookie"

    env_values = {entry["key"]: entry for entry in environment["values"]}
    assert env_values["loginUri"]["value"] == "https://token-payments.local"
    assert env_values["smartWalletVerification"]["value"] == "EOA_OR_DEPLOYED_ERC1271"

    api_routes = {route["operationId"]: route for route in api_expected["routes"]}
    assert api_routes["requestLoginChallenge"]["body"]["signatureVerification"] == _expected_signature_metadata()
    assert api_routes["loginWithMetaMask"]["body"]["signatureVerification"] == _expected_signature_metadata()

    cookie_responses = {response["operationId"]: response for response in cookie_expected["expectedResponses"]}
    assert cookie_responses["requestLoginChallenge"]["body"]["signatureVerification"] == _expected_signature_metadata()
    assert cookie_responses["loginWithMetaMask"]["body"]["signatureVerification"] == _expected_signature_metadata()

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (COLLECTION_PATH, ENVIRONMENT_PATH, API_EXPECTED_PATH, COOKIE_EXPECTED_PATH)
    )
    assert "<redacted-siwe-personal-sign-message>" in combined
    assert "token-payments.local wants you to sign in with your Ethereum account:" not in combined
    assert "0xredacted-signature" not in combined
    assert "Authorization: Bearer" not in combined
    assert "localStorage" not in combined
    assert "sessionStorage" not in combined


def test_cookie_csrf_cors_and_refresh_rotation_contracts_remain_cookie_first() -> None:
    collection = _read_json(COLLECTION_PATH)
    cookie_expected = _read_json(COOKIE_EXPECTED_PATH)
    items = _operation_items(collection)

    for operation_id in ("loginWithMetaMask", "refreshSession", "logout"):
        headers = _headers(items[operation_id]["request"])
        assert headers["X-CSRF-Token"] == "{{csrfToken}}"
        assert "Cookie" not in headers
        assert "Authorization" not in headers

    assert items["refreshSession"]["request"]["body"]["raw"] == "{}"
    assert "cookie jar" in items["refreshSession"]["request"].get("description", "").lower() or "cookie jar" in str(
        items["refreshSession"].get("description", "")
    ).lower()

    expected = {response["operationId"]: response for response in cookie_expected["expectedResponses"]}
    login_cookies = {cookie["name"]: cookie for cookie in expected["loginWithMetaMask"]["setCookie"]}
    refresh_cookies = {cookie["name"]: cookie for cookie in expected["refreshSession"]["setCookie"]}
    assert login_cookies["access_token"]["attributes"]["HttpOnly"] is True
    assert login_cookies["refresh_token"]["attributes"]["HttpOnly"] is True
    assert login_cookies["csrf_token"]["attributes"]["HttpOnly"] is False
    assert refresh_cookies["access_token"]["signedTokenShape"]["payloadType"] == "access"
    assert refresh_cookies["refresh_token"]["signedTokenShape"]["payloadType"] == "refresh"
    assert "rot" in refresh_cookies["refresh_token"]["signedTokenShape"]["payloadClaims"]

    api_spec = API_SPEC_PATH.read_text(encoding="utf-8")
    assert "Credentialed CORS must use an origin allowlist" in api_spec
    assert "CSRF_TOKEN_MISSING" in api_spec
    assert "CSRF_TOKEN_INVALID" in api_spec


def test_readmes_state_supported_login_scope_and_future_wallet_work() -> None:
    for path in (README_PATH, APP_README_PATH):
        text = path.read_text(encoding="utf-8")
        assert "SIWE v1" in text
        assert "EOA" in text
        assert "deployed ERC-1271 smart wallet" in text
        assert "linked wallets" in text
        assert "ERC-6492" in text
        assert "future scope" in text
        assert "cookie-first" in text


@dataclass
class StaticSiweAuthUseCase:
    def requestLoginChallenge(self, command: RequestLoginChallengeCommand) -> LoginChallengeResult:
        challenge = LoginChallenge.issue(
            wallet=command.wallet_address,
            nonce=AuthNonce(NONCE, NOW + timedelta(minutes=5)),
            issued_at=NOW,
            domain=command.domain,
            uri=command.uri,
            chain_id=command.chain_id,
        )
        return LoginChallengeResult(challenge=challenge, signing_message="\n".join(_siwe_message_lines()))

    def loginWithMetaMask(self, command: LoginWithMetaMaskCommand) -> LoginResult:
        from token_payments.contexts.auth.domain.wallet import WalletId
        return LoginResult(
            user=User.register_by_wallet(USER_ID, command.wallet_address),
            session=AuthSession.create(
                session_id=SESSION_ID,
                user_id=USER_ID,
                login_wallet_id=WalletId.new(),
                wallet=command.wallet_address,
                refresh_token_hash=RefreshTokenHash(
                    hash="redacted-refresh-token-hash",
                    salt="redacted-refresh-token-salt",
                    rotation_version=0,
                ),
                device_id=command.device_id,
                expires_at=NOW + timedelta(days=30),
            ),
            issued_token=IssuedToken(
                access_token="<opaque-access-token>",
                refresh_token="<opaque-refresh-token>",
                expires_at=NOW + timedelta(minutes=15),
            ),
        )

    def refreshSession(self, command: RefreshSessionCommand) -> LoginResult:
        raise NotImplementedError

    def logout(self, command: LogoutCommand) -> AuthSession:
        raise NotImplementedError

    def getCurrentUser(self, query: CurrentUserQuery) -> User | None:
        return None


def _expected_signature_metadata() -> dict[str, Any]:
    return {
        "messageFormat": "SIWE_V1",
        "signatureVerificationMethod": "SIWE_PERSONAL_SIGN_EOA_OR_ERC1271",
        "supportedWalletTypes": ["EOA", "DEPLOYED_SMART_WALLET"],
        "smartWalletStandard": "ERC-1271",
        "erc1271MagicValue": "0x1626ba7e",
        "requiresDeployedCode": True,
        "erc6492": "future_scope",
    }


def _siwe_message_lines() -> list[str]:
    return [
        f"{DOMAIN} wants you to sign in with your Ethereum account:",
        str(WALLET),
        "",
        f"URI: {URI}",
        "Version: 1",
        f"Chain ID: {CHAIN_ID}",
        f"Nonce: {NONCE}",
        f"Issued At: {NOW.isoformat()}",
        f"Expiration Time: {(NOW + timedelta(minutes=5)).isoformat()}",
    ]


def _read_json(path: Path) -> Any:
    assert path.exists(), f"{path.relative_to(ROOT)} must be committed"
    return json.loads(path.read_text(encoding="utf-8"))


def _operation_items(collection: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    flattened: list[Mapping[str, Any]] = []
    _flatten_items(collection.get("item", []), flattened)
    return {str(item["id"]): item for item in flattened if "id" in item}


def _flatten_items(items: Iterable[Mapping[str, Any]], output: list[Mapping[str, Any]]) -> None:
    for item in items:
        if "request" in item:
            output.append(item)
        _flatten_items(item.get("item", []), output)


def _headers(request: Mapping[str, Any]) -> dict[str, str]:
    return {
        header["key"]: header.get("value", "")
        for header in request.get("header", [])
        if not header.get("disabled")
    }


def _event_script(item: Mapping[str, Any], listen: str) -> list[str]:
    for event in item.get("event", []):
        if event.get("listen") == listen:
            return list(event.get("script", {}).get("exec", []))
    return []


def _response_body(item: Mapping[str, Any], status_code: int) -> Mapping[str, Any]:
    for response in item.get("response", []):
        if response.get("code") == status_code:
            return json.loads(response["body"])
    raise AssertionError(f"no response example with status {status_code}")


def _postman_json_body(item: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = item["request"]["body"]["raw"]
    return json.loads(raw.replace("{{chainId}}", "1337"))

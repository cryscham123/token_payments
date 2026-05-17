from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
COLLECTION_PATH = ROOT / "postman" / "token-payments.local.postman_collection.json"
ENVIRONMENT_PATH = ROOT / "postman" / "token-payments.local.postman_environment.json"
EXPECTED_PATH = ROOT / "postman" / "token-payments.cookie-auth.expected.json"

REQUIRED_AUTH_FLOW = [
    ("requestLoginChallenge", "POST", "{{baseUrl}}/auth/challenges"),
    ("loginWithMetaMask", "POST", "{{baseUrl}}/auth/sessions"),
    ("refreshSession", "POST", "{{baseUrl}}/auth/sessions/refresh"),
    ("logout", "DELETE", "{{baseUrl}}/auth/sessions"),
    ("getCurrentUser", "GET", "{{baseUrl}}/auth/me"),
]
SESSION_COOKIE_NAMES = {"access_token", "refresh_token"}
REQUIRED_SESSION_CLAIMS = {
    "sub",
    "sessionId",
    "walletAddress",
    "role",
    "iat",
    "exp",
    "typ",
    "jti",
}
FORBIDDEN_SECRET_PATTERNS = (
    re.compile(r"0x[a-fA-F0-9]{64}"),
    re.compile(r"\b(seed phrase|mnemonic|production token|prod token|private_key)\b", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)


def test_postman_cookie_auth_collection_documents_browser_cookie_flow() -> None:
    collection = _read_json(COLLECTION_PATH)
    items = _operation_items(collection)

    assert collection["info"]["schema"].endswith("collection/v2.1.0/collection.json")
    assert "{{baseUrl}}" in json.dumps(collection, sort_keys=True)
    assert "cookie jar" in json.dumps(collection, sort_keys=True).lower()

    positions: list[int] = []
    for operation_id, method, raw_url in REQUIRED_AUTH_FLOW:
        item = items[operation_id]
        request = item["request"]
        positions.append(item["_position"])
        assert request["method"] == method
        assert request["url"]["raw"] == raw_url

    assert positions == sorted(positions), "auth requests must be ordered as the executable cookie flow"

    for operation_id in ("refreshSession", "logout"):
        headers = _headers(items[operation_id]["request"])
        assert headers["X-CSRF-Token"] == "{{csrfToken}}"
        assert "Cookie" not in headers, f"{operation_id} should rely on the Postman cookie jar"
        assert "cookie jar" in str(items[operation_id].get("description", "")).lower()

    auth_me_headers = _headers(items["getCurrentUser"]["request"])
    assert "Cookie" not in auth_me_headers
    assert "Authorization" not in auth_me_headers


def test_postman_scripts_extract_csrf_and_assert_signed_cookie_metadata() -> None:
    collection = _read_json(COLLECTION_PATH)
    items = _operation_items(collection)
    scripts = "\n".join(_script_lines(collection))

    assert 'pm.environment.set("csrfToken"' in scripts
    assert 'pm.environment.set("signingMessage"' in scripts
    assert 'pm.cookies.has("access_token")' in scripts
    assert 'pm.cookies.has("refresh_token")' in scripts
    assert "split(\".\")" in scripts
    assert '"kid"' in scripts
    assert '"HS256"' in scripts
    assert '"TP-SESSION"' in scripts
    assert "signature" in scripts.lower()

    refresh_pre_request = "\n".join(_event_script(items["refreshSession"], "prerequest"))
    logout_pre_request = "\n".join(_event_script(items["logout"], "prerequest"))
    assert "csrfToken" in refresh_pre_request
    assert "csrfToken" in logout_pre_request


def test_postman_expected_cookie_fixture_redacts_signed_tokens_but_keeps_shape_and_attributes() -> None:
    expected = _read_json(EXPECTED_PATH)

    assert expected["postmanCookieJar"]["storesSetCookieAutomatically"] is True
    assert expected["postmanCookieJar"]["manualCookieHeaderForHappyPath"] is False
    assert expected["csrf"]["cookieName"] == "csrf_token"
    assert expected["csrf"]["headerName"] == "X-CSRF-Token"

    session_cookies: list[Mapping[str, Any]] = []
    csrf_cookies: list[Mapping[str, Any]] = []
    for response in expected["expectedResponses"]:
        for cookie in response["setCookie"]:
            if cookie["name"] in SESSION_COOKIE_NAMES:
                session_cookies.append(cookie)
            if cookie["name"] == "csrf_token":
                csrf_cookies.append(cookie)

    assert {cookie["name"] for cookie in session_cookies} == SESSION_COOKIE_NAMES
    assert csrf_cookies

    for cookie in session_cookies:
        if cookie["value"] == "<expired-empty-cookie>":
            assert cookie["rawValueCommitted"] is False
            assert cookie["attributes"]["Max-Age"]["boundedSeconds"] == 0
            assert cookie["attributes"]["Expires"] == "Thu, 01 Jan 1970 00:00:00 GMT"
            assert cookie["attributes"]["HttpOnly"] is True
            assert cookie["attributes"]["Secure"] is False
            assert cookie["attributes"]["SameSite"] == "Lax"
            assert cookie["attributes"]["Path"] == "/"
            continue
        assert cookie["value"] == "<redacted-signed-session-token>"
        assert cookie["rawValueCommitted"] is False
        assert cookie["signedTokenShape"]["segments"] == 3
        assert cookie["signedTokenShape"]["header"] == {
            "alg": "HS256",
            "typ": "TP-SESSION",
            "kid": "present",
            "activeKeyIdSource": "SESSION_ACTIVE_KEY_ID",
        }
        assert REQUIRED_SESSION_CLAIMS <= set(cookie["signedTokenShape"]["payloadClaims"])
        assert cookie["signedTokenShape"]["signature"] == "present"
        assert cookie["attributes"]["HttpOnly"] is True
        assert cookie["attributes"]["Secure"] is False
        assert cookie["attributes"]["SameSite"] == "Lax"
        assert cookie["attributes"]["Path"] == "/"
        assert isinstance(cookie["attributes"]["Max-Age"]["boundedSeconds"], int)
        assert cookie["attributes"]["Max-Age"]["boundedSeconds"] > 0
        assert cookie["attributes"]["Expires"] == "bounded"

    for cookie in csrf_cookies:
        assert cookie["rawValueCommitted"] is False
        assert cookie["attributes"]["HttpOnly"] is False
        assert cookie["attributes"]["Secure"] is False
        assert cookie["attributes"]["SameSite"] == "Lax"
        assert cookie["attributes"]["Path"] == "/"
        assert cookie["attributes"]["Expires"] == "bounded"


def test_postman_negative_cases_cover_expired_and_invalid_signature_tokens() -> None:
    collection = _read_json(COLLECTION_PATH)
    expected = _read_json(EXPECTED_PATH)
    items = _operation_items(collection)

    assert "expiredAccessTokenRejected" in items
    assert "invalidSignatureAccessTokenRejected" in items

    negative_cases = {case["name"]: case for case in expected["negativeCases"]}
    assert set(negative_cases) == {
        "expired access token rejected",
        "invalid signature access token rejected",
    }

    for case in negative_cases.values():
        assert case["expectedResponse"]["status"] == 401
        assert case["expectedResponse"]["body"]["error"]["code"] == "INVALID_AUTH_TOKEN"
        assert case["tokenExpectation"]["kid"] == "present"
        assert case["tokenExpectation"]["signature"] == "present"
        assert case["tokenExpectation"]["rawValueCommitted"] is False

    assert negative_cases["expired access token rejected"]["tokenExpectation"]["expired"] is True
    assert negative_cases["invalid signature access token rejected"]["tokenExpectation"]["signatureValid"] is False


def test_postman_environment_uses_local_placeholders_without_committed_secrets() -> None:
    environment = _read_json(ENVIRONMENT_PATH)
    values = {entry["key"]: entry for entry in environment["values"]}

    assert values["baseUrl"]["value"] == "http://localhost:8000"
    assert values["walletAddress"]["value"] == "0x1111111111111111111111111111111111111111"
    assert values["storeId"]["value"] == "store-001"
    assert values["productId"]["value"] == "product-001"
    assert values["csrfToken"]["value"] == ""

    for secret_key in (
        "metamaskSignature",
        "accessToken",
        "refreshToken",
        "expiredAccessToken",
        "invalidSignatureAccessToken",
    ):
        assert values[secret_key]["value"] in {"", "<paste-personal-sign-signature-here>"}
        assert values[secret_key].get("type") == "secret"


def test_postman_fixtures_do_not_commit_sensitive_material_or_bearer_localstorage_auth() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (COLLECTION_PATH, ENVIRONMENT_PATH, EXPECTED_PATH)
    )

    for pattern in FORBIDDEN_SECRET_PATTERNS:
        assert not pattern.search(combined)
    assert "Authorization: Bearer" not in combined
    assert "localStorage" not in combined
    assert "sessionStorage" not in combined


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
            item = dict(item)
            item["_position"] = len(output)
            output.append(item)
        _flatten_items(item.get("item", []), output)


def _headers(request: Mapping[str, Any]) -> dict[str, str]:
    return {
        header["key"]: header.get("value", "")
        for header in request.get("header", [])
        if not header.get("disabled")
    }


def _script_lines(collection: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            if "event" in value:
                for event in value["event"]:
                    lines.extend(event.get("script", {}).get("exec", []))
            for item in value.get("item", []):
                collect(item)

    collect(collection)
    return lines


def _event_script(item: Mapping[str, Any], listen: str) -> list[str]:
    for event in item.get("event", []):
        if event.get("listen") == listen:
            return list(event.get("script", {}).get("exec", []))
    return []

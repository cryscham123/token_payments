"""HttpOnly cookie session transport and HMAC session token signing."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field, replace
from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
import json
import secrets
from http.cookies import SimpleCookie
from types import MappingProxyType
from typing import Any, Mapping, Self

from token_payments.api.contracts import ApiAuthContext
from token_payments.api.http import HttpRequest


DEFAULT_ACCESS_COOKIE_NAME = "access_token"
DEFAULT_REFRESH_COOKIE_NAME = "refresh_token"
DEFAULT_SESSION_ACTIVE_KEY_ID = "local-dev-placeholder"
DEFAULT_SESSION_SIGNING_KEY = "replace_with_local_dev_only_session_signing_key"
DEFAULT_SESSION_ACCESS_TTL_SECONDS = 900
DEFAULT_SESSION_REFRESH_TTL_SECONDS = 2_592_000
SESSION_KEY_PLACEHOLDER_MARKERS = (
    "placeholder",
    "replace_with",
    "changeme",
    "example",
    "local_dev_only",
    "local-dev",
    "dev_only",
    "do_not_use",
)
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class SessionClaims:
    """Signed session token claims used by browser cookie auth."""

    user_id: str
    session_id: str
    wallet_address: str
    issued_at: datetime
    expires_at: datetime
    token_type: str
    jti: str
    rotation_version: int = 0
    active_group_id: str | None = None
    group_memberships: tuple[Mapping[str, Any], ...] = ()
    scopes: tuple[str, ...] = ()
    role: InitVar[str | None] = None

    def __post_init__(self, role: str | None) -> None:
        if isinstance(role, property):
            role = None
        object.__setattr__(self, "user_id", _require_text(self.user_id, "SessionClaims.user_id"))
        object.__setattr__(self, "session_id", _require_text(self.session_id, "SessionClaims.session_id"))
        object.__setattr__(self, "wallet_address", _require_text(self.wallet_address, "SessionClaims.wallet_address"))
        object.__setattr__(self, "issued_at", _require_aware_datetime(self.issued_at, "SessionClaims.issued_at"))
        object.__setattr__(self, "expires_at", _require_aware_datetime(self.expires_at, "SessionClaims.expires_at"))
        object.__setattr__(self, "token_type", _require_text(self.token_type, "SessionClaims.token_type"))
        object.__setattr__(self, "jti", _require_text(self.jti, "SessionClaims.jti"))
        if (
            isinstance(self.rotation_version, bool)
            or not isinstance(self.rotation_version, int)
            or self.rotation_version < 0
        ):
            raise ValueError("SessionClaims.rotation_version must be a non-negative integer")
        if self.active_group_id is not None:
            object.__setattr__(
                self,
                "active_group_id",
                _require_text(self.active_group_id, "SessionClaims.active_group_id"),
            )
        if not isinstance(self.group_memberships, tuple):
            raise ValueError("SessionClaims.group_memberships must be a tuple")
        object.__setattr__(
            self,
            "group_memberships",
            tuple(_json_object(membership, "SessionClaims.group_memberships") for membership in self.group_memberships),
        )
        if not isinstance(self.scopes, tuple):
            raise ValueError("SessionClaims.scopes must be a tuple")
        object.__setattr__(
            self,
            "scopes",
            tuple(_require_text(scope, "SessionClaims.scopes") for scope in self.scopes),
        )
        object.__setattr__(self, "_legacy_role", _require_text(role, "SessionClaims.role") if role is not None else None)

    @property
    def role(self) -> str | None:
        """Legacy role claim view retained for old local tests."""

        return getattr(self, "_legacy_role", None)

    def with_jti(self, jti: str) -> Self:
        return replace(self, jti=_require_text(jti, "SessionClaims.jti"))

    def to_payload(self) -> dict[str, Any]:
        return {
            "sub": self.user_id,
            "sessionId": self.session_id,
            "walletAddress": self.wallet_address,
            "activeGroupId": self.active_group_id,
            "groupMemberships": list(self.group_memberships),
            "iat": _epoch_seconds(self.issued_at),
            "exp": _epoch_seconds(self.expires_at),
            "typ": self.token_type,
            "jti": self.jti,
            "rot": self.rotation_version,
            "scopes": list(self.scopes),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Self:
        return cls(
            user_id=_payload_text(payload, "sub"),
            session_id=_payload_text(payload, "sessionId"),
            wallet_address=_payload_text(payload, "walletAddress"),
            issued_at=_datetime_from_epoch(_payload_int(payload, "iat")),
            expires_at=_datetime_from_epoch(_payload_int(payload, "exp")),
            token_type=_payload_text(payload, "typ"),
            jti=_payload_text(payload, "jti"),
            rotation_version=_payload_int(payload, "rot", default=0),
            active_group_id=_payload_optional_text(payload, "activeGroupId"),
            group_memberships=tuple(_payload_object_list(payload, "groupMemberships")),
            scopes=tuple(_payload_list(payload, "scopes")),
            role=_payload_optional_text(payload, "role"),
        )


@dataclass(frozen=True)
class SessionKeyRing:
    """Active and previous HMAC signing keys indexed by key id."""

    active_key_id: str
    keys: Mapping[str, str]

    def __post_init__(self) -> None:
        active = _require_text(self.active_key_id, "SessionKeyRing.active_key_id")
        if not isinstance(self.keys, Mapping):
            raise ValueError("SessionKeyRing.keys must be a mapping")
        keys = {
            _require_text(str(kid), "SessionKeyRing.keys.key"): _require_text(str(secret), "SessionKeyRing.keys.secret")
            for kid, secret in self.keys.items()
        }
        if active not in keys:
            raise ValueError("SESSION_ACTIVE_KEY_ID must reference a key in SESSION_SIGNING_KEYS")
        object.__setattr__(self, "active_key_id", active)
        object.__setattr__(self, "keys", MappingProxyType(keys))

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, runtime_environment: str = "local") -> Self:
        active = env.get("SESSION_ACTIVE_KEY_ID")
        raw_keys = env.get("SESSION_SIGNING_KEYS")
        live = is_live_environment(runtime_environment)
        if not active or not raw_keys:
            if live:
                raise ValueError("SESSION_SIGNING_KEYS and SESSION_ACTIVE_KEY_ID are required in live/prod mode")
            active = DEFAULT_SESSION_ACTIVE_KEY_ID
            raw_keys = f"{DEFAULT_SESSION_ACTIVE_KEY_ID}={DEFAULT_SESSION_SIGNING_KEY}"
        key_ring = cls(active_key_id=active, keys=_parse_signing_keys(raw_keys))
        key_ring.validate_for_environment(runtime_environment)
        return key_ring

    def validate_for_environment(self, runtime_environment: str) -> None:
        if not is_live_environment(runtime_environment):
            return
        for kid, secret in self.keys.items():
            if _looks_placeholder(kid) or _looks_placeholder(secret):
                raise ValueError("SESSION_SIGNING_KEYS must not use placeholder or local dev values in live/prod mode")
            if len(secret.encode("utf-8")) < 32:
                raise ValueError("SESSION_SIGNING_KEYS values must be at least 32 bytes in live/prod mode")

    def secret_for(self, kid: str) -> str:
        normalized = _require_text(kid, "kid")
        try:
            return self.keys[normalized]
        except KeyError as exc:
            raise ValueError("unknown session token kid") from exc


@dataclass(frozen=True)
class SessionKeyConfig:
    """Environment-parsed session key and TTL settings."""

    key_ring: SessionKeyRing
    access_ttl_seconds: int = DEFAULT_SESSION_ACCESS_TTL_SECONDS
    refresh_ttl_seconds: int = DEFAULT_SESSION_REFRESH_TTL_SECONDS

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, runtime_environment: str = "local") -> Self:
        return cls(
            key_ring=SessionKeyRing.from_env(env, runtime_environment=runtime_environment),
            access_ttl_seconds=_parse_positive_int(
                env,
                "SESSION_ACCESS_TTL_SECONDS",
                DEFAULT_SESSION_ACCESS_TTL_SECONDS,
            ),
            refresh_ttl_seconds=_parse_positive_int(
                env,
                "SESSION_REFRESH_TTL_SECONDS",
                DEFAULT_SESSION_REFRESH_TTL_SECONDS,
            ),
        )


@dataclass(frozen=True)
class SessionTokenSigner:
    """HMAC-SHA256 signer/verifier for compact session tokens."""

    key_ring: SessionKeyRing
    jti_factory: Any = field(default_factory=lambda: (lambda: secrets.token_urlsafe(18)))

    def __post_init__(self) -> None:
        if not isinstance(self.key_ring, SessionKeyRing):
            raise ValueError("SessionTokenSigner.key_ring must be a SessionKeyRing")
        if not callable(self.jti_factory):
            raise ValueError("SessionTokenSigner.jti_factory must be callable")

    def sign(self, claims: SessionClaims) -> str:
        if not isinstance(claims, SessionClaims):
            raise ValueError("SessionTokenSigner.sign requires SessionClaims")
        claims = claims.with_jti(str(self.jti_factory()))
        header = {"alg": "HS256", "kid": self.key_ring.active_key_id, "typ": "TP-SESSION"}
        header_part = _base64url_json(header)
        payload_part = _base64url_json(claims.to_payload())
        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        signature = hmac.new(
            self.key_ring.secret_for(self.key_ring.active_key_id).encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        return f"{header_part}.{payload_part}.{_base64url_bytes(signature)}"

    def verify(
        self,
        token: str,
        *,
        expected_type: str,
        session_id: str | None = None,
        now: datetime | None = None,
    ) -> SessionClaims:
        token = _require_text(token, "token")
        expected_type = _require_text(expected_type, "expected_type")
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("session token must have header.payload.signature")
        header = _decode_json_part(parts[0], "session token header")
        if header.get("alg") != "HS256":
            raise ValueError("session token alg must be HS256")
        if header.get("typ") != "TP-SESSION":
            raise ValueError("session token typ must be TP-SESSION")
        kid = _payload_text(header, "kid")
        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
        expected_signature = hmac.new(
            self.key_ring.secret_for(kid).encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        actual_signature = _base64url_decode(parts[2], "session token signature")
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise ValueError("session token signature is invalid")
        claims = SessionClaims.from_payload(_decode_json_part(parts[1], "session token payload"))
        if claims.token_type != expected_type:
            raise ValueError("session token type is invalid")
        if session_id is not None and claims.session_id != session_id:
            raise ValueError("session token session id is invalid")
        checked_at = _require_aware_datetime(now or datetime.now(UTC), "now")
        if checked_at >= claims.expires_at:
            raise ValueError("session token is expired")
        return claims


@dataclass(frozen=True)
class CookieSettings:
    """Cookie policy for browser auth transport."""

    access_cookie_name: str = DEFAULT_ACCESS_COOKIE_NAME
    refresh_cookie_name: str = DEFAULT_REFRESH_COOKIE_NAME
    path: str = "/"
    same_site: str = "Lax"
    secure: bool = True
    http_only: bool = True
    access_max_age_seconds: int = DEFAULT_SESSION_ACCESS_TTL_SECONDS
    refresh_max_age_seconds: int = DEFAULT_SESSION_REFRESH_TTL_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(self, "access_cookie_name", _cookie_name(self.access_cookie_name, "access_cookie_name"))
        object.__setattr__(self, "refresh_cookie_name", _cookie_name(self.refresh_cookie_name, "refresh_cookie_name"))
        path = _require_text(self.path, "CookieSettings.path")
        if not path.startswith("/"):
            raise ValueError("CookieSettings.path must start with /")
        object.__setattr__(self, "path", path)
        normalized_same_site = _require_text(self.same_site, "CookieSettings.same_site").capitalize()
        if normalized_same_site not in {"Lax", "Strict", "None"}:
            raise ValueError("CookieSettings.same_site must be Lax, Strict, or None")
        object.__setattr__(self, "same_site", normalized_same_site)
        if not isinstance(self.secure, bool):
            raise ValueError("CookieSettings.secure must be a bool")
        if not isinstance(self.http_only, bool):
            raise ValueError("CookieSettings.http_only must be a bool")
        object.__setattr__(
            self,
            "access_max_age_seconds",
            _require_positive_int(self.access_max_age_seconds, "CookieSettings.access_max_age_seconds"),
        )
        object.__setattr__(
            self,
            "refresh_max_age_seconds",
            _require_positive_int(self.refresh_max_age_seconds, "CookieSettings.refresh_max_age_seconds"),
        )


@dataclass(frozen=True)
class AuthCookiePair:
    access_token: str
    refresh_token: str
    access_cookie: str
    refresh_cookie: str

    @property
    def set_cookie_headers(self) -> tuple[str, str]:
        return (self.access_cookie, self.refresh_cookie)

    @property
    def set_cookie_header_pairs(self) -> tuple[tuple[str, str], ...]:
        return (("Set-Cookie", self.access_cookie), ("Set-Cookie", self.refresh_cookie))


@dataclass(frozen=True)
class CookieSessionTransport:
    """Serialize session tokens as HttpOnly cookies and parse request claims."""

    signer: SessionTokenSigner
    settings: CookieSettings = field(default_factory=CookieSettings)
    clock: Any | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.signer, SessionTokenSigner):
            raise ValueError("CookieSessionTransport.signer must be a SessionTokenSigner")
        if not isinstance(self.settings, CookieSettings):
            raise ValueError("CookieSessionTransport.settings must be CookieSettings")

    @classmethod
    def from_key_config(
        cls,
        key_config: SessionKeyConfig,
        *,
        settings: CookieSettings | None = None,
        clock: Any | None = None,
    ) -> Self:
        if not isinstance(key_config, SessionKeyConfig):
            raise ValueError("CookieSessionTransport.from_key_config requires SessionKeyConfig")
        cookie_settings = settings or CookieSettings(
            access_max_age_seconds=key_config.access_ttl_seconds,
            refresh_max_age_seconds=key_config.refresh_ttl_seconds,
        )
        if not isinstance(cookie_settings, CookieSettings):
            raise ValueError("CookieSessionTransport.from_key_config settings must be CookieSettings")
        return cls(
            signer=SessionTokenSigner(key_config.key_ring),
            settings=cookie_settings,
            clock=clock,
        )

    def issue_cookies(self, *, access_token: str, refresh_token: str, now: datetime | None = None) -> AuthCookiePair:
        issued_at = _require_aware_datetime(now or self._now(), "now")
        access_token = _require_text(access_token, "access_token")
        refresh_token = _require_text(refresh_token, "refresh_token")
        return AuthCookiePair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_cookie=_serialize_cookie(
                self.settings.access_cookie_name,
                access_token,
                settings=self.settings,
                max_age_seconds=self.settings.access_max_age_seconds,
                now=issued_at,
            ),
            refresh_cookie=_serialize_cookie(
                self.settings.refresh_cookie_name,
                refresh_token,
                settings=self.settings,
                max_age_seconds=self.settings.refresh_max_age_seconds,
                now=issued_at,
            ),
        )

    def expire_cookie_header_pairs(self, *, now: datetime | None = None) -> tuple[tuple[str, str], ...]:
        expired_at = _require_aware_datetime(now or self._now(), "now")
        return (
            (
                "Set-Cookie",
                _serialize_expired_cookie(self.settings.access_cookie_name, settings=self.settings, now=expired_at),
            ),
            (
                "Set-Cookie",
                _serialize_expired_cookie(self.settings.refresh_cookie_name, settings=self.settings, now=expired_at),
            ),
        )

    def auth_context_from_http_request(self, request: HttpRequest) -> ApiAuthContext | None:
        if not isinstance(request, HttpRequest):
            raise ValueError("auth_context_from_http_request requires HttpRequest")
        allow_refresh_only = request.path == "/auth/sessions/refresh" or (
            request.path == "/auth/sessions" and request.method == "DELETE"
        )
        return self.extract_auth_context(request.headers, allow_refresh_only=allow_refresh_only)

    def extract_auth_context(
        self,
        headers: Mapping[str, str],
        *,
        allow_refresh_only: bool = False,
    ) -> ApiAuthContext | None:
        cookies = _cookies_from_headers(headers)
        access_token = cookies.get(self.settings.access_cookie_name)
        refresh_token = cookies.get(self.settings.refresh_cookie_name)
        checked_at = self._now()
        access_claims: SessionClaims | None = None
        refresh_claims: SessionClaims | None = None
        access_error: ValueError | None = None

        if access_token:
            try:
                access_claims = self.signer.verify(access_token, expected_type="access", now=checked_at)
            except ValueError as exc:
                access_error = exc
        if refresh_token:
            try:
                refresh_claims = self.signer.verify(refresh_token, expected_type="refresh", now=checked_at)
            except ValueError:
                refresh_claims = None

        claims = access_claims or (refresh_claims if allow_refresh_only else None)
        if claims is None:
            if access_error is not None:
                raise access_error
            return None

        refresh_hash = None
        if refresh_token and refresh_claims is not None:
            refresh_hash = _refresh_token_hash_payload(refresh_token, refresh_claims)
        return ApiAuthContext(
            user_id=claims.user_id,
            session_id=claims.session_id,
            wallet_address=claims.wallet_address,
            active_group_id=claims.active_group_id,
            group_memberships=claims.group_memberships,
            scopes=claims.scopes,
            token_type=claims.token_type,
            refresh_token_hash=refresh_hash,
            role=claims.role,
        )

    def _now(self) -> datetime:
        if self.clock is None:
            return datetime.now(UTC)
        now = getattr(self.clock, "now", None)
        value = now() if callable(now) else self.clock()
        return _require_aware_datetime(value, "clock.now()")


def is_live_environment(value: str) -> bool:
    return _require_text(value, "runtime_environment").lower() in {"live", "prod", "production"}


def _parse_signing_keys(raw: str) -> dict[str, str]:
    raw = _require_text(raw, "SESSION_SIGNING_KEYS")
    if raw.lstrip().startswith("{"):
        parsed = json.loads(raw)
        if not isinstance(parsed, Mapping):
            raise ValueError("SESSION_SIGNING_KEYS JSON must be an object")
        return {str(kid): str(secret) for kid, secret in parsed.items()}
    output: dict[str, str] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise ValueError("SESSION_SIGNING_KEYS entries must use kid=secret")
        kid, secret = part.split("=", 1)
        output[_require_text(kid, "SESSION_SIGNING_KEYS.kid")] = _require_text(
            secret,
            "SESSION_SIGNING_KEYS.secret",
        )
    if not output:
        raise ValueError("SESSION_SIGNING_KEYS must include at least one key")
    return output


def _refresh_token_hash_payload(token: str, claims: SessionClaims) -> dict[str, Any]:
    return {
        "hash": hashlib.sha256(f"{claims.session_id}:{token}".encode("utf-8")).hexdigest(),
        "salt": claims.session_id,
        "rotationVersion": claims.rotation_version,
    }


def _serialize_cookie(
    name: str,
    value: str,
    *,
    settings: CookieSettings,
    max_age_seconds: int,
    now: datetime,
) -> str:
    expires = now + timedelta(seconds=max_age_seconds)
    parts = [
        f"{name}={value}",
        f"Max-Age={max_age_seconds}",
        f"Expires={_format_http_datetime(expires)}",
        f"Path={settings.path}",
    ]
    if settings.secure:
        parts.append("Secure")
    if settings.http_only:
        parts.append("HttpOnly")
    parts.append(f"SameSite={settings.same_site}")
    return "; ".join(parts)


def _format_http_datetime(value: datetime) -> str:
    dt = _require_aware_datetime(value, "cookie expires").astimezone(UTC)
    return (
        f"{_WEEKDAYS[dt.weekday()]}, {dt.day:02d} {_MONTHS[dt.month]} "
        f"{dt.year:04d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} GMT"
    )


def _serialize_expired_cookie(name: str, *, settings: CookieSettings, now: datetime) -> str:
    _require_aware_datetime(now, "now")
    parts = [
        f"{name}=",
        "Max-Age=0",
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
        f"Path={settings.path}",
    ]
    if settings.secure:
        parts.append("Secure")
    if settings.http_only:
        parts.append("HttpOnly")
    parts.append(f"SameSite={settings.same_site}")
    return "; ".join(parts)


def _cookies_from_headers(headers: Mapping[str, str]) -> dict[str, str]:
    cookie_header = None
    for key, value in headers.items():
        if key.lower() == "cookie":
            cookie_header = str(value)
            break
    if not cookie_header:
        return {}
    parsed = SimpleCookie()
    parsed.load(cookie_header)
    return {name: morsel.value for name, morsel in parsed.items()}


def _base64url_json(value: Mapping[str, Any]) -> str:
    return _base64url_bytes(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _base64url_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_json_part(value: str, field_name: str) -> dict[str, Any]:
    try:
        decoded = json.loads(_base64url_decode(value, field_name).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field_name} must be JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return decoded


def _base64url_decode(value: str, field_name: str) -> bytes:
    try:
        return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))
    except Exception as exc:
        raise ValueError(f"{field_name} must be base64url") from exc


def _payload_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"session token claim {key} must be a non-empty string")
    return value.strip()


def _payload_optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"session token claim {key} must be a non-empty string")
    return value.strip()


def _payload_int(payload: Mapping[str, Any], key: str, *, default: int | None = None) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"session token claim {key} must be an integer")
    return value


def _payload_list(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key, ())
    if not isinstance(value, list | tuple):
        raise ValueError(f"session token claim {key} must be a list")
    return tuple(_require_text(str(item), key) for item in value)


def _payload_object_list(payload: Mapping[str, Any], key: str) -> tuple[dict[str, Any], ...]:
    value = payload.get(key, ())
    if not isinstance(value, list | tuple):
        raise ValueError(f"session token claim {key} must be a list")
    return tuple(_json_object(item, key) for item in value)


def _json_object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} items must be JSON objects")
    output: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        if item is not None and not isinstance(item, (str, int, bool, float)):
            raise ValueError(f"{field_name} values must be bounded JSON scalars")
        output[key.strip()] = item
    return output


def _parse_positive_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    return _require_positive_int(value, key)


def _epoch_seconds(value: datetime) -> int:
    return int(_require_aware_datetime(value, "datetime").timestamp())


def _datetime_from_epoch(value: int) -> datetime:
    return datetime.fromtimestamp(value, UTC)


def _cookie_name(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name)
    if any(char in normalized for char in " ;,="):
        raise ValueError(f"CookieSettings.{field_name} must be a valid cookie name")
    return normalized


def _looks_placeholder(value: str) -> bool:
    lower = value.lower()
    return any(marker in lower for marker in SESSION_KEY_PLACEHOLDER_MARKERS)


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


__all__ = [
    "AuthCookiePair",
    "CookieSessionTransport",
    "CookieSettings",
    "DEFAULT_SESSION_ACCESS_TTL_SECONDS",
    "DEFAULT_SESSION_ACTIVE_KEY_ID",
    "DEFAULT_SESSION_REFRESH_TTL_SECONDS",
    "DEFAULT_SESSION_SIGNING_KEY",
    "SessionClaims",
    "SessionKeyConfig",
    "SessionKeyRing",
    "SessionTokenSigner",
    "is_live_environment",
]

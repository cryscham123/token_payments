"""CSRF, credentialed CORS, and request guard contracts for live HTTP adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import base64
import hashlib
import hmac
from http.cookies import SimpleCookie
import secrets
from types import MappingProxyType
from typing import Any, Mapping, Self


DEFAULT_CSRF_COOKIE_NAME = "csrf_token"
DEFAULT_CSRF_HEADER_NAME = "X-CSRF-Token"
DEFAULT_CSRF_ACTIVE_KEY_ID = "local-dev-csrf"
DEFAULT_CSRF_SIGNING_KEY = "replace_with_local_dev_only_csrf_signing_key"
DEFAULT_CSRF_MAX_AGE_SECONDS = 3_600
DEFAULT_CORS_ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:8765")
DEFAULT_REQUEST_BODY_MAX_BYTES = 1024 * 1024
SECURITY_PLACEHOLDER_MARKERS = (
    "placeholder",
    "replace_with",
    "changeme",
    "example",
    "local_dev_only",
    "local-dev",
    "dev_only",
    "do_not_use",
)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
DEFAULT_CORS_METHODS = ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT")
DEFAULT_CORS_HEADERS = (
    "authorization",
    "content-type",
    "idempotency-key",
    "x-csrf-token",
    "x-request-id",
)
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class CsrfTokenMissing(ValueError):
    """Raised when a cookie-authenticated mutating request omitted CSRF material."""


class CsrfTokenInvalid(ValueError):
    """Raised when a submitted CSRF token is mismatched or has an invalid signature."""


@dataclass(frozen=True)
class GuardResponse:
    """Framework-neutral guard response converted by the HTTP adapter."""

    status_code: int
    body: Mapping[str, Any]
    headers: Mapping[str, str] = field(default_factory=dict)
    multi_headers: tuple[tuple[str, str], ...] = ()
    request_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(_string_mapping(self.headers, "GuardResponse.headers")))
        object.__setattr__(
            self,
            "multi_headers",
            tuple((_require_text(name, "GuardResponse.header"), str(value)) for name, value in self.multi_headers),
        )


@dataclass(frozen=True)
class CsrfTokenIssue:
    """A CSRF token plus the cookie header needed for double-submit validation."""

    token: str
    cookie_name: str
    header_name: str
    set_cookie: str

    @property
    def set_cookie_header_pair(self) -> tuple[str, str]:
        return ("Set-Cookie", self.set_cookie)

    def body_fields(self) -> dict[str, Any]:
        return {
            "csrfToken": self.token,
            "csrf": {
                "cookieName": self.cookie_name,
                "headerName": self.header_name,
            },
        }


@dataclass(frozen=True)
class CsrfCookieSettings:
    """Cookie policy for the non-HttpOnly CSRF double-submit cookie."""

    cookie_name: str = DEFAULT_CSRF_COOKIE_NAME
    path: str = "/"
    same_site: str = "Lax"
    secure: bool = True
    http_only: bool = False
    max_age_seconds: int = DEFAULT_CSRF_MAX_AGE_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(self, "cookie_name", _cookie_name(self.cookie_name, "CsrfCookieSettings.cookie_name"))
        path = _require_text(self.path, "CsrfCookieSettings.path")
        if not path.startswith("/"):
            raise ValueError("CsrfCookieSettings.path must start with /")
        object.__setattr__(self, "path", path)
        same_site = _require_text(self.same_site, "CsrfCookieSettings.same_site").capitalize()
        if same_site not in {"Lax", "Strict", "None"}:
            raise ValueError("CsrfCookieSettings.same_site must be Lax, Strict, or None")
        object.__setattr__(self, "same_site", same_site)
        if not isinstance(self.secure, bool):
            raise ValueError("CsrfCookieSettings.secure must be a bool")
        if not isinstance(self.http_only, bool):
            raise ValueError("CsrfCookieSettings.http_only must be a bool")
        object.__setattr__(
            self,
            "max_age_seconds",
            _require_positive_int(self.max_age_seconds, "CsrfCookieSettings.max_age_seconds"),
        )


@dataclass(frozen=True)
class CsrfTokenConfig:
    """Environment-parsed CSRF signing config without exposing secrets in previews."""

    active_key_id: str = DEFAULT_CSRF_ACTIVE_KEY_ID
    signing_key: str = field(default=DEFAULT_CSRF_SIGNING_KEY, repr=False)
    max_age_seconds: int = DEFAULT_CSRF_MAX_AGE_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_key_id", _require_text(self.active_key_id, "CSRF_ACTIVE_KEY_ID"))
        object.__setattr__(self, "signing_key", _require_text(self.signing_key, "CSRF_SIGNING_KEY"))
        object.__setattr__(self, "max_age_seconds", _require_positive_int(self.max_age_seconds, "CSRF_MAX_AGE_SECONDS"))

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, runtime_environment: str = "local") -> Self:
        config = cls(
            active_key_id=env.get("CSRF_ACTIVE_KEY_ID", DEFAULT_CSRF_ACTIVE_KEY_ID),
            signing_key=env.get("CSRF_SIGNING_KEY", DEFAULT_CSRF_SIGNING_KEY),
            max_age_seconds=_parse_positive_int(env, "CSRF_MAX_AGE_SECONDS", DEFAULT_CSRF_MAX_AGE_SECONDS),
        )
        config.validate_for_environment(runtime_environment)
        return config

    def validate_for_environment(self, runtime_environment: str) -> None:
        if not _is_live_environment(runtime_environment):
            return
        if _looks_placeholder(self.active_key_id) or _looks_placeholder(self.signing_key):
            raise ValueError("CSRF_SIGNING_KEY must not use placeholder or local dev values in live/prod mode")
        if len(self.signing_key.encode("utf-8")) < 32:
            raise ValueError("CSRF_SIGNING_KEY must be at least 32 bytes in live/prod mode")

    def to_redacted_dict(self) -> dict[str, Any]:
        return {
            "cookieName": DEFAULT_CSRF_COOKIE_NAME,
            "headerName": DEFAULT_CSRF_HEADER_NAME,
            "activeKeyId": self.active_key_id,
            "signingKeyConfigured": bool(self.signing_key),
            "secretRedacted": True,
            "maxAgeSeconds": self.max_age_seconds,
        }


@dataclass(frozen=True)
class HmacCsrfTokenSigner:
    """HMAC-SHA256 signer/verifier for compact CSRF double-submit tokens."""

    key_id: str
    secret_provider: Callable[[], str]
    nonce_factory: Callable[[], str] = field(default_factory=lambda: (lambda: secrets.token_urlsafe(18)))

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_id", _token_part(self.key_id, "HmacCsrfTokenSigner.key_id"))
        if not callable(self.secret_provider):
            raise ValueError("HmacCsrfTokenSigner.secret_provider must be callable")
        if not callable(self.nonce_factory):
            raise ValueError("HmacCsrfTokenSigner.nonce_factory must be callable")

    def sign(self, nonce: str | None = None) -> str:
        token_nonce = _token_part(nonce or str(self.nonce_factory()), "csrf nonce")
        signing_input = f"{self.key_id}.{token_nonce}".encode("ascii")
        signature = hmac.new(
            _require_text(self.secret_provider(), "CSRF_SIGNING_KEY").encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        return f"{self.key_id}.{token_nonce}.{_base64url_bytes(signature)}"

    def verify(self, token: str) -> bool:
        token = _require_text(token, "csrf token")
        parts = token.split(".")
        if len(parts) != 3:
            return False
        key_id, nonce, signature = parts
        if key_id != self.key_id:
            return False
        try:
            expected = self.sign(nonce).rsplit(".", 1)[1]
            actual = _base64url_bytes(_base64url_decode(signature, "csrf signature"))
        except ValueError:
            return False
        return hmac.compare_digest(expected, actual)


@dataclass(frozen=True)
class CsrfTokenService:
    """Issue and verify signed CSRF tokens using double-submit cookie semantics."""

    signer: HmacCsrfTokenSigner
    cookie_settings: CsrfCookieSettings = field(default_factory=CsrfCookieSettings)
    header_name: str = DEFAULT_CSRF_HEADER_NAME
    clock: Any | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.signer, HmacCsrfTokenSigner):
            raise ValueError("CsrfTokenService.signer must be HmacCsrfTokenSigner")
        if not isinstance(self.cookie_settings, CsrfCookieSettings):
            raise ValueError("CsrfTokenService.cookie_settings must be CsrfCookieSettings")
        object.__setattr__(self, "header_name", _require_text(self.header_name, "CsrfTokenService.header_name"))

    def issue_token(self, *, now: datetime | None = None) -> CsrfTokenIssue:
        issued_at = _require_aware_datetime(now or self._now(), "now")
        token = self.signer.sign()
        return CsrfTokenIssue(
            token=token,
            cookie_name=self.cookie_settings.cookie_name,
            header_name=self.header_name,
            set_cookie=_serialize_cookie(token, settings=self.cookie_settings, now=issued_at),
        )

    def validate_double_submit(self, headers: Mapping[str, str]) -> None:
        cookie_token = _cookies_from_headers(headers).get(self.cookie_settings.cookie_name)
        header_token = _header_value(headers, self.header_name)
        if not cookie_token or not header_token:
            raise CsrfTokenMissing("CSRF token is required for cookie-authenticated mutating requests.")
        if not hmac.compare_digest(cookie_token, header_token):
            raise CsrfTokenInvalid("CSRF token does not match the CSRF cookie.")
        if not self.signer.verify(header_token):
            raise CsrfTokenInvalid("CSRF token signature is invalid.")

    def _now(self) -> datetime:
        if self.clock is None:
            return datetime.now(UTC)
        now = getattr(self.clock, "now", None)
        value = now() if callable(now) else self.clock()
        return _require_aware_datetime(value, "clock.now()")


@dataclass(frozen=True)
class CorsPolicy:
    """Credentialed CORS allowlist contract."""

    allowed_origins: tuple[str, ...] | str = DEFAULT_CORS_ALLOWED_ORIGINS
    allow_credentials: bool = True
    allowed_methods: tuple[str, ...] = DEFAULT_CORS_METHODS
    allowed_headers: tuple[str, ...] = DEFAULT_CORS_HEADERS
    max_age_seconds: int = 600

    def __post_init__(self) -> None:
        origins = _normalize_text_tuple(self.allowed_origins, "CorsPolicy.allowed_origins")
        if self.allow_credentials and "*" in origins:
            raise ValueError("credentialed CORS must not use a wildcard allowed origin")
        if not isinstance(self.allow_credentials, bool):
            raise ValueError("CorsPolicy.allow_credentials must be a bool")
        methods = tuple(_require_text(method, "CorsPolicy.allowed_methods").upper() for method in self.allowed_methods)
        headers = tuple(_require_text(header, "CorsPolicy.allowed_headers").lower() for header in self.allowed_headers)
        object.__setattr__(self, "allowed_origins", origins)
        object.__setattr__(self, "allowed_methods", methods)
        object.__setattr__(self, "allowed_headers", headers)
        object.__setattr__(self, "max_age_seconds", _require_positive_int(self.max_age_seconds, "CorsPolicy.max_age_seconds"))

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        return cls(
            allowed_origins=_parse_csv(env.get("CORS_ALLOWED_ORIGINS"), DEFAULT_CORS_ALLOWED_ORIGINS),
            allow_credentials=_parse_bool(env.get("CORS_ALLOW_CREDENTIALS"), True),
            max_age_seconds=_parse_positive_int(env, "CORS_MAX_AGE_SECONDS", 600),
        )

    def is_allowed_origin(self, origin: str | None) -> bool:
        if origin is None:
            return False
        normalized = origin.strip()
        return normalized in self.allowed_origins

    def actual_response_headers(self, origin: str | None) -> dict[str, str]:
        if not self.is_allowed_origin(origin):
            return {}
        headers = {
            "Vary": "Origin",
            "Access-Control-Allow-Origin": str(origin).strip(),
        }
        if self.allow_credentials:
            headers["Access-Control-Allow-Credentials"] = "true"
        return headers

    def preflight_headers(self, origin: str, request_headers: str | None = None) -> dict[str, str]:
        headers = self.actual_response_headers(origin)
        headers["Access-Control-Allow-Methods"] = ", ".join(self.allowed_methods)
        headers["Access-Control-Allow-Headers"] = _requested_headers(request_headers) or ", ".join(self.allowed_headers)
        headers["Access-Control-Max-Age"] = str(self.max_age_seconds)
        return headers


@dataclass(frozen=True)
class RequestBodyLimit:
    """Maximum HTTP request body size contract."""

    max_bytes: int = DEFAULT_REQUEST_BODY_MAX_BYTES

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_bytes", _require_positive_int(self.max_bytes, "RequestBodyLimit.max_bytes"))

    def is_exceeded_by(self, body: bytes | bytearray | None) -> bool:
        return len(body or b"") > self.max_bytes


@dataclass(frozen=True)
class RequestGuard:
    """Run HTTP boundary checks before facade/application handlers are dispatched."""

    csrf_token_service: CsrfTokenService
    cors_policy: CorsPolicy = field(default_factory=CorsPolicy)
    body_limit: RequestBodyLimit = field(default_factory=RequestBodyLimit)
    auth_cookie_names: tuple[str, ...] = ("access_token", "refresh_token")

    def __post_init__(self) -> None:
        if not isinstance(self.csrf_token_service, CsrfTokenService):
            raise ValueError("RequestGuard.csrf_token_service must be CsrfTokenService")
        if not isinstance(self.cors_policy, CorsPolicy):
            raise ValueError("RequestGuard.cors_policy must be CorsPolicy")
        if not isinstance(self.body_limit, RequestBodyLimit):
            raise ValueError("RequestGuard.body_limit must be RequestBodyLimit")
        object.__setattr__(
            self,
            "auth_cookie_names",
            tuple(_cookie_name(name, "RequestGuard.auth_cookie_names") for name in self.auth_cookie_names),
        )

    def guard(self, request: Any, *, request_id: str) -> GuardResponse | None:
        if self.body_limit.is_exceeded_by(getattr(request, "body", b"")):
            return self._error(
                request,
                status_code=413,
                code="REQUEST_BODY_TOO_LARGE",
                message=f"Request body exceeds {self.body_limit.max_bytes} bytes.",
                request_id=request_id,
            )

        origin = _header_value(getattr(request, "headers", {}), "Origin")
        if self._is_preflight(request):
            return self._preflight_response(request, request_id=request_id, origin=origin)

        if origin is not None and not self.cors_policy.is_allowed_origin(origin):
            return self._error(
                request,
                status_code=403,
                code="CORS_ORIGIN_FORBIDDEN",
                message="Origin is not allowed for credentialed CORS requests.",
                request_id=request_id,
            )

        path = str(getattr(request, "path", ""))
        method = str(getattr(request, "method", "GET")).upper()
        # Pre-auth login flows can't carry a CSRF double-submit token yet, so they are exempt.
        # OAuth routes are intentionally NOT blanket-exempt here: unauthenticated OAuth login
        # (no session cookie) is already exempt by the cookie check below, while authenticated
        # OAuth account-linking (links/authorize in LINK mode) must still pass CSRF.
        if (
            path == "/auth/challenges"
            or (path == "/auth/sessions" and method == "POST")
        ):
            return None

        if method in SAFE_METHODS or not self._has_auth_cookie(getattr(request, "headers", {})):
            return None

        try:
            self.csrf_token_service.validate_double_submit(getattr(request, "headers", {}))
        except CsrfTokenMissing as exc:
            return self._error(
                request,
                status_code=403,
                code="CSRF_TOKEN_MISSING",
                message=str(exc),
                request_id=request_id,
            )
        except CsrfTokenInvalid as exc:
            return self._error(
                request,
                status_code=403,
                code="CSRF_TOKEN_INVALID",
                message=str(exc),
                request_id=request_id,
            )
        return None

    def response_headers(self, request: Any) -> Mapping[str, str]:
        return MappingProxyType(self.cors_policy.actual_response_headers(_header_value(getattr(request, "headers", {}), "Origin")))

    def _is_preflight(self, request: Any) -> bool:
        return (
            str(getattr(request, "method", "")).upper() == "OPTIONS"
            and _header_value(getattr(request, "headers", {}), "Origin") is not None
            and _header_value(getattr(request, "headers", {}), "Access-Control-Request-Method") is not None
        )

    def _preflight_response(self, request: Any, *, request_id: str, origin: str | None) -> GuardResponse:
        if origin is None or not self.cors_policy.is_allowed_origin(origin):
            return self._error(
                request,
                status_code=403,
                code="CORS_ORIGIN_FORBIDDEN",
                message="Origin is not allowed for credentialed CORS requests.",
                request_id=request_id,
            )
        requested_method = _header_value(getattr(request, "headers", {}), "Access-Control-Request-Method")
        if requested_method is None or requested_method.upper() not in self.cors_policy.allowed_methods:
            return self._error(
                request,
                status_code=403,
                code="CORS_METHOD_FORBIDDEN",
                message="Requested CORS method is not allowed.",
                request_id=request_id,
            )
        return _guard_response(
            {},
            status_code=204,
            request_id=request_id,
            headers=self.cors_policy.preflight_headers(
                origin,
                _header_value(getattr(request, "headers", {}), "Access-Control-Request-Headers"),
            ),
        )

    def _has_auth_cookie(self, headers: Mapping[str, str]) -> bool:
        cookies = _cookies_from_headers(headers)
        return any(name in cookies for name in self.auth_cookie_names)

    def _error(
        self,
        request: Any,
        *,
        status_code: int,
        code: str,
        message: str,
        request_id: str,
    ) -> GuardResponse:
        return _guard_response(
            {"error": {"code": code, "message": message}},
            status_code=status_code,
            request_id=request_id,
            headers=self.response_headers(request),
        )


def _serialize_cookie(token: str, *, settings: CsrfCookieSettings, now: datetime) -> str:
    expires = now + timedelta(seconds=settings.max_age_seconds)
    parts = [
        f"{settings.cookie_name}={token}",
        f"Max-Age={settings.max_age_seconds}",
        f"Expires={_format_http_datetime(expires)}",
        f"Path={settings.path}",
    ]
    if settings.secure:
        parts.append("Secure")
    if settings.http_only:
        parts.append("HttpOnly")
    parts.append(f"SameSite={settings.same_site}")
    return "; ".join(parts)


def _guard_response(
    body: Mapping[str, Any],
    *,
    status_code: int,
    request_id: str,
    headers: Mapping[str, str] | None = None,
) -> GuardResponse:
    response_headers = {"Content-Type": "application/json"}
    if headers:
        response_headers.update(_string_mapping(headers, "guard response headers"))
    return GuardResponse(
        status_code=status_code,
        body=body,
        headers=response_headers,
        request_id=request_id,
    )


def _format_http_datetime(value: datetime) -> str:
    dt = _require_aware_datetime(value, "cookie expires").astimezone(UTC)
    return (
        f"{_WEEKDAYS[dt.weekday()]}, {dt.day:02d} {_MONTHS[dt.month]} "
        f"{dt.year:04d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} GMT"
    )


def _string_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    output: dict[str, str] = {}
    for key, item in value.items():
        output[_require_text(key, field_name)] = str(item)
    return output


def _cookies_from_headers(headers: Mapping[str, str]) -> dict[str, str]:
    cookie_header = _header_value(headers, "Cookie")
    if not cookie_header:
        return {}
    parsed = SimpleCookie()
    parsed.load(cookie_header)
    return {name: morsel.value for name, morsel in parsed.items()}


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return str(value)
    return None


def _requested_headers(value: str | None) -> str:
    if not value:
        return ""
    return ", ".join(part.strip().lower() for part in value.split(",") if part.strip())


def _normalize_text_tuple(value: tuple[str, ...] | str, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = tuple(part.strip() for part in value.split(",") if part.strip())
    elif isinstance(value, tuple | list):
        parts = tuple(_require_text(str(part), field_name) for part in value)
    else:
        raise ValueError(f"{field_name} must be a tuple or comma-separated string")
    return tuple(_require_text(part, field_name) for part in parts)


def _parse_csv(raw: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return default
    return _normalize_text_tuple(raw, "CORS_ALLOWED_ORIGINS")


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("CORS_ALLOW_CREDENTIALS must be a boolean")


def _parse_positive_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    return _require_positive_int(value, key)


def _base64url_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str, field_name: str) -> bytes:
    try:
        return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))
    except Exception as exc:
        raise ValueError(f"{field_name} must be base64url") from exc


def _token_part(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name)
    if "." in normalized:
        raise ValueError(f"{field_name} must not contain .")
    return normalized


def _cookie_name(value: str, field_name: str) -> str:
    normalized = _require_text(value, field_name)
    if any(char in normalized for char in " ;,="):
        raise ValueError(f"{field_name} must be a valid cookie name")
    return normalized


def _looks_placeholder(value: str) -> bool:
    lower = value.lower()
    return any(marker in lower for marker in SECURITY_PLACEHOLDER_MARKERS)


def _is_live_environment(value: str) -> bool:
    return _require_text(value, "runtime_environment").lower() in {"live", "prod", "production"}


def _require_text(value: str | None, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


__all__ = [
    "CorsPolicy",
    "CsrfCookieSettings",
    "CsrfTokenConfig",
    "CsrfTokenInvalid",
    "CsrfTokenIssue",
    "CsrfTokenMissing",
    "CsrfTokenService",
    "DEFAULT_CORS_ALLOWED_ORIGINS",
    "DEFAULT_CSRF_ACTIVE_KEY_ID",
    "DEFAULT_CSRF_COOKIE_NAME",
    "DEFAULT_CSRF_HEADER_NAME",
    "DEFAULT_CSRF_MAX_AGE_SECONDS",
    "DEFAULT_CSRF_SIGNING_KEY",
    "DEFAULT_REQUEST_BODY_MAX_BYTES",
    "GuardResponse",
    "HmacCsrfTokenSigner",
    "RequestBodyLimit",
    "RequestGuard",
]

"""Framework-neutral API request/response contracts."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import json
import math
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class ApiAuthContext:
    """Framework-neutral authenticated session claims supplied by the HTTP boundary."""

    user_id: str | None = None
    session_id: str | None = None
    wallet_address: str | None = None
    active_group_id: str | None = None
    group_memberships: tuple[Mapping[str, JsonValue], ...] = ()
    scopes: tuple[str, ...] = ()
    token_type: str | None = None
    refresh_token_hash: Mapping[str, JsonValue] | None = None
    role: InitVar[str | None] = None

    def __post_init__(self, role: str | None) -> None:
        if isinstance(role, property):
            role = None
        if self.user_id is not None:
            object.__setattr__(self, "user_id", _require_text(self.user_id, "ApiAuthContext.user_id"))
        if self.session_id is not None:
            object.__setattr__(self, "session_id", _require_text(self.session_id, "ApiAuthContext.session_id"))
        if self.wallet_address is not None:
            object.__setattr__(
                self,
                "wallet_address",
                _require_text(self.wallet_address, "ApiAuthContext.wallet_address"),
            )
        if self.active_group_id is not None:
            object.__setattr__(self, "active_group_id", _require_text(self.active_group_id, "ApiAuthContext.active_group_id"))
        if not isinstance(self.group_memberships, tuple):
            raise ValueError("ApiAuthContext.group_memberships must be a tuple")
        object.__setattr__(
            self,
            "group_memberships",
            tuple(
                MappingProxyType(_to_json_safe_mapping(membership, "ApiAuthContext.group_memberships"))
                for membership in self.group_memberships
            ),
        )
        if not isinstance(self.scopes, tuple):
            raise ValueError("ApiAuthContext.scopes must be a tuple")
        object.__setattr__(
            self,
            "scopes",
            tuple(_require_text(scope, "ApiAuthContext.scopes") for scope in self.scopes),
        )
        if self.token_type is not None:
            object.__setattr__(self, "token_type", _require_text(self.token_type, "ApiAuthContext.token_type"))
        if self.refresh_token_hash is not None:
            object.__setattr__(
                self,
                "refresh_token_hash",
                MappingProxyType(_to_json_safe_mapping(self.refresh_token_hash, "ApiAuthContext.refresh_token_hash")),
            )
        object.__setattr__(
            self,
            "_legacy_role",
            _require_text(role, "ApiAuthContext.role") if role is not None else None,
        )

    @property
    def role(self) -> str | None:
        """Legacy role claim view retained while tests and old adapters migrate."""

        return getattr(self, "_legacy_role", None)


@dataclass(frozen=True)
class ApiRequest:
    """Pure request DTO independent of an HTTP framework."""

    request_id: str
    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    query: Mapping[str, Any] = field(default_factory=dict)
    body: Any = None
    auth_context: ApiAuthContext | None = None
    local_auth_fallback_enabled: bool = True
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require_text(self.request_id, "ApiRequest.request_id"))
        object.__setattr__(self, "method", _require_text(self.method, "ApiRequest.method").upper())
        path = _require_text(self.path, "ApiRequest.path")
        if not path.startswith("/"):
            raise ValueError("ApiRequest.path must start with /")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "headers", MappingProxyType(_string_mapping(self.headers, "ApiRequest.headers")))
        object.__setattr__(self, "query", MappingProxyType(_to_json_safe_mapping(self.query, "ApiRequest.query")))
        object.__setattr__(self, "body", _to_json_safe(self.body))
        if self.auth_context is not None and not isinstance(self.auth_context, ApiAuthContext):
            raise ValueError("ApiRequest.auth_context must be an ApiAuthContext")
        if not isinstance(self.local_auth_fallback_enabled, bool):
            raise ValueError("ApiRequest.local_auth_fallback_enabled must be a bool")
        object.__setattr__(self, "received_at", _require_aware_datetime(self.received_at, "ApiRequest.received_at"))


@dataclass(frozen=True)
class ApiResponse:
    """Pure response DTO that can be adapted to any web framework."""

    status_code: int
    body: JsonValue
    headers: Mapping[str, str] = field(default_factory=dict)
    multi_headers: tuple[tuple[str, str], ...] = ()
    request_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.status_code, bool) or not isinstance(self.status_code, int):
            raise ValueError("ApiResponse.status_code must be an integer")
        if self.status_code < 100 or self.status_code > 599:
            raise ValueError("ApiResponse.status_code must be between 100 and 599")
        object.__setattr__(self, "body", _to_json_safe(self.body))
        object.__setattr__(self, "headers", MappingProxyType(_string_mapping(self.headers, "ApiResponse.headers")))
        object.__setattr__(
            self,
            "multi_headers",
            _header_pairs(self.multi_headers, "ApiResponse.multi_headers"),
        )
        if self.request_id is not None:
            object.__setattr__(self, "request_id", _require_text(self.request_id, "ApiResponse.request_id"))

    def header_items(self) -> tuple[tuple[str, str], ...]:
        return (*self.headers.items(), *self.multi_headers)

    def to_json(self) -> str:
        return json.dumps(
            {
                "requestId": self.request_id,
                "statusCode": self.status_code,
                "body": self.body,
                "headers": dict(self.headers),
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


def json_response(
    body: Any,
    *,
    status_code: int = 200,
    request_id: str | None = None,
    headers: Mapping[str, str] | None = None,
    multi_headers: tuple[tuple[str, str], ...] = (),
) -> ApiResponse:
    response_headers = {"Content-Type": "application/json"}
    if headers:
        response_headers.update(_string_mapping(headers, "json_response.headers"))
    return ApiResponse(
        status_code=status_code,
        body=_to_json_safe(body),
        headers=response_headers,
        multi_headers=multi_headers,
        request_id=request_id,
    )


def _header_pairs(value: tuple[tuple[str, str], ...], field_name: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    output: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError(f"{field_name} items must be header name/value tuples")
        key, header_value = item
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        output.append((key.strip(), str(header_value)))
    return tuple(output)


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


def _string_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    output: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        output[key] = str(item)
    return output


def _to_json_safe_mapping(value: Mapping[str, Any], field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    output: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{field_name} keys must be non-empty strings")
        output[key] = _to_json_safe(item)
    return output


def _to_json_safe(value: Any) -> JsonValue:
    from token_payments.shared.domain.value_objects import WalletAddress
    if isinstance(value, WalletAddress):
        from eth_utils import to_checksum_address
        return to_checksum_address(value.address)

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON response floats must be finite")
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _require_aware_datetime(value, "JSON response datetime").isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return _to_json_safe_mapping(value, "JSON response mapping")
    if isinstance(value, tuple | list):
        return [_to_json_safe(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _to_json_safe(getattr(value, field.name)) for field in fields(value)}
    raise TypeError(f"{type(value).__name__} is not JSON response serializable")

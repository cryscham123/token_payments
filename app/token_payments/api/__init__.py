"""Framework-neutral API DTOs and response helpers."""

from .auth import AuthApi
from .contracts import ApiRequest, ApiResponse, JsonValue, json_response

__all__ = [
    "AuthApi",
    "ApiRequest",
    "ApiResponse",
    "JsonValue",
    "json_response",
]

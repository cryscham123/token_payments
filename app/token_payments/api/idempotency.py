"""Shared HTTP idempotency key extraction for API facades."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import ApiRequest, ApiResponse, json_response


IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"


class IdempotencyKeyConflict(ValueError):
    """Raised when header and body idempotency identifiers disagree."""

    def __init__(self, *, header_name: str, body_field: str) -> None:
        self.header_name = header_name
        self.body_field = body_field
        super().__init__(f"{header_name} header conflicts with request body {body_field}")

    def to_error(self) -> dict[str, str]:
        return {
            "code": IDEMPOTENCY_KEY_CONFLICT,
            "message": str(self),
            "header": self.header_name,
            "bodyField": self.body_field,
        }


def idempotency_key_from_request(
    request: ApiRequest,
    body: Mapping[str, Any],
    *,
    fallback: str | None = None,
) -> str | None:
    """Return the standard idempotency key from header, body, or fallback."""

    header_value = _header_value(request.headers, IDEMPOTENCY_KEY_HEADER)
    body_idempotency_key = _optional_body_text(body, "idempotencyKey")
    body_command_id = _optional_body_text(body, "commandId")

    if body_idempotency_key is not None and body_command_id is not None and body_idempotency_key != body_command_id:
        raise IdempotencyKeyConflict(header_name="idempotencyKey", body_field="commandId")
    if header_value is not None:
        if body_idempotency_key is not None and body_idempotency_key != header_value:
            raise IdempotencyKeyConflict(header_name=IDEMPOTENCY_KEY_HEADER, body_field="idempotencyKey")
        if body_command_id is not None and body_command_id != header_value:
            raise IdempotencyKeyConflict(header_name=IDEMPOTENCY_KEY_HEADER, body_field="commandId")
        return header_value
    if body_idempotency_key is not None:
        return body_idempotency_key
    if body_command_id is not None:
        return body_command_id
    return fallback


def idempotency_conflict_response(error: IdempotencyKeyConflict, request_id: str | None) -> ApiResponse:
    return json_response(
        {"error": error.to_error()},
        status_code=400,
        request_id=request_id,
    )


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower() and value.strip():
            return value.strip()
    return None


def _optional_body_text(body: Mapping[str, Any], key: str) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


__all__ = [
    "IDEMPOTENCY_KEY_CONFLICT",
    "IDEMPOTENCY_KEY_HEADER",
    "IdempotencyKeyConflict",
    "idempotency_conflict_response",
    "idempotency_key_from_request",
]

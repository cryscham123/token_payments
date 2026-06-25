"""Framework-neutral merchant group membership API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from token_payments.contexts.auth.application import MerchantActor
from token_payments.contexts.auth.domain import InvitationId, RoleId
from token_payments.shared.domain import StoreId, UserId, WalletAddress

from .contracts import ApiRequest, ApiResponse, json_response


class MerchantMembershipApi:
    def __init__(self, use_case: Any) -> None:
        self._use_case = use_case

    def list_members(self, request: ApiRequest) -> ApiResponse:
        try:
            return _result_response(
                self._use_case.list_members(_actor(request), StoreId(_lookup_value(request, "storeId"))),
                request.request_id,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def list_invitations(self, request: ApiRequest) -> ApiResponse:
        try:
            return _result_response(
                self._use_case.list_invitations(_actor(request), StoreId(_lookup_value(request, "storeId"))),
                request.request_id,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def list_user_invitations(self, request: ApiRequest) -> ApiResponse:
        try:
            return _result_response(
                self._use_case.list_user_invitations(_actor(request)),
                request.request_id,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def create_invitation(self, request: ApiRequest) -> ApiResponse:
        try:
            body = _body(request)
            if "targetEmail" in body:
                raise ValueError("targetEmail is not supported; use targetDisplayName, targetUserId, or targetWallet")
            return _result_response(
                self._use_case.create_invitation(
                    _actor(request),
                    StoreId(_lookup_value(request, "storeId")),
                    role_id=RoleId(_required_text(body, "roleId")),
                    target_user_id=_optional_user_id(body.get("targetUserId")),
                    target_wallet=_optional_wallet(body.get("targetWallet")),
                    target_display_name=_optional_text(body.get("targetDisplayName")),
                    expires_at=_optional_datetime(body.get("expiresAt")),
                    requested_at=request.received_at,
                ),
                request.request_id,
                created_status=201,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def accept_invitation(self, request: ApiRequest) -> ApiResponse:
        try:
            body = _body(request) if isinstance(request.body, Mapping) else {}
            return _result_response(
                self._use_case.accept_invitation(
                    _actor(request),
                    InvitationId(_lookup_value(request, "invitationId")),
                    wallet=_optional_wallet(body.get("walletAddress")),
                    accepted_at=request.received_at,
                ),
                request.request_id,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def revoke_invitation(self, request: ApiRequest) -> ApiResponse:
        try:
            return _result_response(
                self._use_case.revoke_invitation(_actor(request), InvitationId(_lookup_value(request, "invitationId"))),
                request.request_id,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def update_member_role(self, request: ApiRequest) -> ApiResponse:
        try:
            body = _body(request)
            return _result_response(
                self._use_case.update_member_role(
                    _actor(request),
                    StoreId(_lookup_value(request, "storeId")),
                    UserId(_lookup_value(request, "userId")),
                    RoleId(_required_text(body, "roleId")),
                ),
                request.request_id,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def remove_member(self, request: ApiRequest) -> ApiResponse:
        try:
            return _result_response(
                self._use_case.remove_member(
                    _actor(request),
                    StoreId(_lookup_value(request, "storeId")),
                    UserId(_lookup_value(request, "userId")),
                ),
                request.request_id,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def role_catalog(self, request: ApiRequest) -> ApiResponse:
        try:
            return _result_response(self._use_case.role_catalog(_actor(request)), request.request_id)
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)

    def search_users(self, request: ApiRequest) -> ApiResponse:
        try:
            query = request.query.get("query", "")
            return _result_response(
                self._use_case.search_users(_actor(request), query),
                request.request_id,
            )
        except ValueError as exc:
            return _error_response("VALIDATION_ERROR", str(exc), 400, request.request_id)


def _actor(request: ApiRequest) -> MerchantActor:
    context = request.auth_context
    if context is None or context.user_id is None:
        raise ValueError("authenticated session is required")
    return MerchantActor(UserId(context.user_id), scopes=context.scopes)


def _result_response(result: Any, request_id: str, *, created_status: int = 200) -> ApiResponse:
    if getattr(result, "status", None) == "rejected":
        code = str(getattr(result, "rejection_reason", "MERCHANT_MEMBER_REJECTED"))
        return json_response(result.payload, status_code=_status_for_error(code), request_id=request_id)
    return json_response(result.payload, status_code=created_status if getattr(result, "status", None) == "created" else 200, request_id=request_id)


def _status_for_error(code: str) -> int:
    if code.endswith("_FORBIDDEN"):
        return 403
    if code.endswith("_NOT_FOUND"):
        return 404
    if code in {"INVITATION_ALREADY_PENDING", "INVITATION_NOT_ACCEPTABLE", "MEMBERSHIP_ALREADY_EXISTS", "OWNER_ROLE_PROTECTED"}:
        return 409
    return 400


def _body(request: ApiRequest) -> Mapping[str, Any]:
    if not isinstance(request.body, Mapping):
        raise ValueError("request body must be an object")
    return request.body


def _lookup_value(request: ApiRequest, key: str) -> str:
    value = request.query.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"{key} is required")


def _required_text(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("optional text values must be non-empty strings")
    return value.strip()


def _optional_user_id(value: Any) -> UserId | None:
    text = _optional_text(value)
    return UserId(text) if text is not None else None


def _optional_wallet(value: Any) -> WalletAddress | None:
    text = _optional_text(value)
    return WalletAddress(text) if text is not None else None


def _optional_datetime(value: Any) -> datetime | None:
    text = _optional_text(value)
    return datetime.fromisoformat(text) if text is not None else None


def _error_response(code: str, message: str, status_code: int, request_id: str) -> ApiResponse:
    return json_response({"error": {"code": code, "message": message}}, status_code=status_code, request_id=request_id)


__all__ = ["MerchantMembershipApi"]

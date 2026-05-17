"""Framework-neutral authentication API handlers."""

from __future__ import annotations

from typing import Any, Mapping

from token_payments.contexts.auth.application import (
    AuthApplicationError,
    AuthErrorCode,
    AuthUseCase,
    CurrentUserQuery,
    LoginChallengeResult,
    LoginResult,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    RefreshSessionCommand,
    RequestLoginChallengeCommand,
)
from token_payments.contexts.auth.domain import AuthSession, RefreshTokenHash, SessionId, User
from token_payments.shared.domain import UserId

from .contracts import ApiRequest, ApiResponse, json_response


class AuthApi:
    """Auth API facade that can be adapted by any HTTP framework."""

    def __init__(self, use_case: AuthUseCase) -> None:
        self._use_case = use_case

    def request_login_challenge(self, request: ApiRequest) -> ApiResponse:
        try:
            body = _request_body(request)
            result = self._use_case.requestLoginChallenge(
                RequestLoginChallengeCommand(
                    wallet_address=_required_text(body, "walletAddress"),
                    domain=_required_text(body, "domain"),
                    chain_id=_required_int(body, "chainId"),
                    issued_at=None,
                )
            )
            return json_response(_challenge_payload(result), status_code=201, request_id=request.request_id)
        except AuthApplicationError as exc:
            return _error_response(exc, request.request_id)

    def login_with_metamask(self, request: ApiRequest) -> ApiResponse:
        try:
            body = _request_body(request)
            result = self._use_case.loginWithMetaMask(
                LoginWithMetaMaskCommand(
                    wallet_address=_required_text(body, "walletAddress"),
                    message=_required_text(body, "message"),
                    signature=_required_text(body, "signature"),
                    device_id=_required_text(body, "deviceId"),
                )
            )
            return json_response(_login_payload(result), status_code=200, request_id=request.request_id)
        except AuthApplicationError as exc:
            return _error_response(exc, request.request_id)

    def refresh_session(self, request: ApiRequest) -> ApiResponse:
        try:
            body = _optional_request_body(request)
            result = self._use_case.refreshSession(
                RefreshSessionCommand(
                    session_id=SessionId(_session_id_from_request(request, body)),
                    refresh_token_hash=_refresh_token_hash_from_body(_refresh_hash_mapping_from_request(request, body)),
                )
            )
            return json_response(_login_payload(result), status_code=200, request_id=request.request_id)
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)

    def logout(self, request: ApiRequest) -> ApiResponse:
        try:
            body = _optional_request_body(request)
            session = self._use_case.logout(LogoutCommand(session_id=SessionId(_session_id_from_request(request, body))))
            return json_response({"session": _session_payload(session)}, status_code=200, request_id=request.request_id)
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)

    def current_user(self, request: ApiRequest) -> ApiResponse:
        try:
            user_id = request.query.get("userId")
            if user_id is None and isinstance(request.body, Mapping):
                user_id = request.body.get("userId")
            if user_id is None and request.auth_context is not None:
                user_id = request.auth_context.user_id
            if not isinstance(user_id, str) or not user_id.strip():
                raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "userId is required")
            user = self._use_case.getCurrentUser(CurrentUserQuery(user_id=UserId(user_id)))
            if user is None:
                return _error_response(
                    AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "current user was not found"),
                    request.request_id,
                    status_code=404,
                )
            return json_response({"user": _user_payload(user)}, status_code=200, request_id=request.request_id)
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)


def _challenge_payload(result: LoginChallengeResult) -> dict[str, Any]:
    challenge = result.challenge
    return {
        "walletAddress": str(challenge.wallet),
        "nonce": challenge.nonce.value,
        "expiresAt": challenge.expires_at.isoformat(),
        "signingMessage": result.signing_message,
    }


def _login_payload(result: LoginResult) -> dict[str, Any]:
    return {
        "user": _user_payload(result.user),
        "session": _session_payload(result.session),
        "token": {
            "accessToken": result.issued_token.access_token,
            "refreshToken": result.issued_token.refresh_token,
            "expiresAt": result.issued_token.expires_at.isoformat(),
        },
    }


def _user_payload(user: User) -> dict[str, Any]:
    return {
        "userId": str(user.user_id),
        "walletAddress": str(user.primary_wallet),
        "role": user.role.value,
        "active": user.active,
        "lastLoginAt": user.last_login_at.isoformat() if user.last_login_at is not None else None,
    }


def _session_payload(session: AuthSession) -> dict[str, Any]:
    return {
        "sessionId": str(session.session_id),
        "userId": str(session.user_id),
        "walletAddress": str(session.wallet),
        "deviceId": session.device_id,
        "expiresAt": session.expires_at.isoformat(),
        "revokedAt": session.revoked_at.isoformat() if session.revoked_at is not None else None,
        "refreshTokenHash": {
            "hash": session.refresh_token_hash.hash,
            "salt": session.refresh_token_hash.salt,
            "rotationVersion": session.refresh_token_hash.rotation_version,
        },
    }


def _refresh_token_hash_from_body(body: Mapping[str, Any]) -> RefreshTokenHash:
    return RefreshTokenHash(
        hash=_required_text(body, "hash"),
        salt=_required_text(body, "salt"),
        rotation_version=_required_int(body, "rotationVersion"),
    )


def _request_body(request: ApiRequest) -> Mapping[str, Any]:
    if not isinstance(request.body, Mapping):
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "request body must be an object")
    return request.body


def _optional_request_body(request: ApiRequest) -> Mapping[str, Any]:
    if request.body is None:
        return {}
    return _request_body(request)


def _required_mapping(body: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = body.get(key)
    if not isinstance(value, Mapping):
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{key} must be an object")
    return value


def _session_id_from_request(request: ApiRequest, body: Mapping[str, Any]) -> str:
    value = body.get("sessionId")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if request.auth_context is not None and request.auth_context.session_id is not None:
        return request.auth_context.session_id
    raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "sessionId is required")


def _refresh_hash_mapping_from_request(request: ApiRequest, body: Mapping[str, Any]) -> Mapping[str, Any]:
    value = body.get("refreshTokenHash")
    if isinstance(value, Mapping):
        return value
    if request.auth_context is not None and request.auth_context.refresh_token_hash is not None:
        return request.auth_context.refresh_token_hash
    raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "refreshTokenHash is required")


def _required_text(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{key} is required")
    return value.strip()


def _required_int(body: Mapping[str, Any], key: str) -> int:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{key} must be an integer")
    return value


def _error_response(
    error: AuthApplicationError,
    request_id: str | None,
    *,
    status_code: int | None = None,
) -> ApiResponse:
    return json_response(
        {
            "error": {
                "code": error.code.value,
                "message": str(error),
            }
        },
        status_code=status_code or _status_for_error(error.code),
        request_id=request_id,
    )


def _status_for_error(code: AuthErrorCode) -> int:
    return {
        AuthErrorCode.INVALID_SIGNATURE: 401,
        AuthErrorCode.WALLET_MISMATCH: 401,
        AuthErrorCode.EXPIRED_CHALLENGE: 409,
        AuthErrorCode.REUSED_NONCE: 409,
        AuthErrorCode.VALIDATION_ERROR: 400,
    }[code]


def _coerce_auth_error(error: AuthApplicationError | ValueError) -> AuthApplicationError:
    if isinstance(error, AuthApplicationError):
        return error
    return AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, str(error))


__all__ = ["AuthApi"]

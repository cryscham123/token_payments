"""Framework-neutral authentication API handlers."""

from __future__ import annotations

from typing import Any, Mapping

from token_payments.contexts.auth.application import (
    AuthApplicationError,
    AuthErrorCode,
    AuthUseCase,
    CurrentUserQuery,
    GetCurrentUserProfileQuery,
    GetUserProfileQuery,
    LinkWalletCommand,
    ListWalletsQuery,
    LoginChallengeResult,
    LoginResult,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    RefreshSessionCommand,
    RequestLoginChallengeCommand,
    RequestWalletLinkChallengeCommand,
    RevokeWalletCommand,
    SetPrimaryWalletCommand,
    UpdateUserProfileCommand,
    WalletLinkChallengeResult,
    WalletResult,
    WalletsResult,
)
from token_payments.contexts.auth.application.siwe import SIWE_VERSION
from token_payments.contexts.auth.domain import AuthSession, RefreshTokenHash, SessionId, User, UserProfile
from token_payments.contexts.auth.domain.wallet import WalletId
from token_payments.shared.domain import UserId

from .contracts import ApiRequest, ApiResponse, json_response


SIGNATURE_VERIFICATION_METADATA: dict[str, Any] = {
    "messageFormat": "SIWE_V1",
    "signatureVerificationMethod": "SIWE_PERSONAL_SIGN_EOA_OR_ERC1271",
    "supportedWalletTypes": ["EOA", "DEPLOYED_SMART_WALLET"],
    "smartWalletStandard": "ERC-1271",
    "erc1271MagicValue": "0x1626ba7e",
    "requiresDeployedCode": True,
    "erc6492": "future_scope",
}


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
                    uri=_optional_text(body, "uri"),
                    issued_at=None,
                )
            )
            return json_response(_challenge_payload(result), status_code=201, request_id=request.request_id)
        except AuthApplicationError as exc:
            return _error_response(exc, request.request_id)

    def request_wallet_link_challenge(self, request: ApiRequest) -> ApiResponse:
        try:
            actor_user_id = _authenticated_user_id(request)
            body = _request_body(request)
            result = self._use_case.requestWalletLinkChallenge(
                RequestWalletLinkChallengeCommand(
                    actor_user_id=UserId(actor_user_id),
                    wallet_address=_required_text(body, "walletAddress"),
                    domain=_required_text(body, "domain"),
                    chain_id=_required_int(body, "chainId"),
                    uri=_optional_text(body, "uri"),
                    issued_at=None,
                )
            )
            return json_response(_wallet_link_challenge_payload(result), status_code=201, request_id=request.request_id)
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)

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

    def link_wallet(self, request: ApiRequest) -> ApiResponse:
        try:
            actor_user_id = _authenticated_user_id(request)
            body = _request_body(request)
            result = self._use_case.linkWallet(
                LinkWalletCommand(
                    actor_user_id=UserId(actor_user_id),
                    wallet_address=_required_text(body, "walletAddress"),
                    message=_required_text(body, "message"),
                    signature=_required_text(body, "signature"),
                    wallet_type=_optional_text(body, "walletType") or "EOA",
                )
            )
            return json_response(_wallet_result_payload(result), status_code=201, request_id=request.request_id)
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)

    def list_wallets(self, request: ApiRequest) -> ApiResponse:
        try:
            actor_user_id = _authenticated_user_id(request)
            result = self._use_case.listWallets(ListWalletsQuery(actor_user_id=UserId(actor_user_id)))
            return json_response(_wallets_payload(result), status_code=200, request_id=request.request_id)
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)

    def set_primary_wallet(self, request: ApiRequest) -> ApiResponse:
        try:
            actor_user_id = _authenticated_user_id(request)
            result = self._use_case.setPrimaryWallet(
                SetPrimaryWalletCommand(
                    actor_user_id=UserId(actor_user_id),
                    wallet_id=WalletId(_required_query_text(request, "walletId")),
                )
            )
            return json_response(_wallet_result_payload(result), status_code=200, request_id=request.request_id)
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)

    def revoke_wallet(self, request: ApiRequest) -> ApiResponse:
        try:
            actor_user_id = _authenticated_user_id(request)
            result = self._use_case.revokeWallet(
                RevokeWalletCommand(
                    actor_user_id=UserId(actor_user_id),
                    wallet_id=WalletId(_required_query_text(request, "walletId")),
                    revoked_at=request.received_at,
                )
            )
            return json_response(_wallet_result_payload(result), status_code=200, request_id=request.request_id)
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)

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

    def current_user_profile(self, request: ApiRequest) -> ApiResponse:
        try:
            actor_user_id = _authenticated_user_id(request)
            profile = self._use_case.getCurrentUserProfile(GetCurrentUserProfileQuery(user_id=UserId(actor_user_id)))
            if profile is None:
                return _profile_error_response(
                    "USER_PROFILE_NOT_FOUND",
                    "user profile was not found",
                    404,
                    request.request_id,
                )
            return json_response(
                {"profile": _profile_payload(profile)},
                status_code=200,
                request_id=request.request_id,
            )
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)

    def get_user_profile(self, request: ApiRequest) -> ApiResponse:
        try:
            target_user_id = _target_profile_user_id(request)
            profile = self._use_case.getUserProfile(GetUserProfileQuery(user_id=UserId(target_user_id)))
            if profile is None:
                return _profile_error_response(
                    "USER_PROFILE_NOT_FOUND",
                    "user profile was not found",
                    404,
                    request.request_id,
                )
            return json_response(
                {"profile": _profile_payload(profile)},
                status_code=200,
                request_id=request.request_id,
            )
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)

    def update_current_user_profile(self, request: ApiRequest) -> ApiResponse:
        try:
            actor_user_id = _authenticated_user_id(request)
            target_user_id = _target_profile_user_id(request, default_user_id=actor_user_id)
            if actor_user_id != target_user_id and not _has_scope(request, "user:manage"):
                return _profile_error_response(
                    "USER_PROFILE_FORBIDDEN",
                    "user:manage permission is required to update another user profile",
                    403,
                    request.request_id,
                )
            body = _request_body(request)
            _reject_unknown_profile_fields(body, {"displayName", "userId"})
            profile = self._use_case.updateUserProfile(
                UpdateUserProfileCommand(
                    actor_user_id=UserId(actor_user_id),
                    target_user_id=UserId(target_user_id),
                    display_name=_optional_profile_text(body, "displayName"),
                    display_name_provided="displayName" in body,
                    requested_at=request.received_at,
                    request_id=request.request_id,
                    actor_scopes=request.auth_context.scopes if request.auth_context is not None else (),
                )
            )
            return json_response(
                {"profile": _profile_payload(profile)},
                status_code=200,
                request_id=request.request_id,
            )
        except (AuthApplicationError, ValueError) as exc:
            return _error_response(_coerce_auth_error(exc), request.request_id)


def _challenge_payload(result: LoginChallengeResult) -> dict[str, Any]:
    challenge = result.challenge
    payload = {
        "walletAddress": str(challenge.wallet),
        "nonce": challenge.nonce.value,
        "expiresAt": challenge.expires_at.isoformat(),
        "signingMessage": result.signing_message,
        "signatureVerification": dict(SIGNATURE_VERIFICATION_METADATA),
    }
    if challenge.domain is not None and challenge.uri is not None and challenge.chain_id is not None:
        payload.update(
            {
                "domain": challenge.domain,
                "address": str(challenge.wallet),
                "uri": challenge.uri,
                "version": SIWE_VERSION,
                "chainId": challenge.chain_id,
                "issuedAt": challenge.issued_at.isoformat(),
                "expirationTime": challenge.expires_at.isoformat(),
            }
        )
    return payload


def _wallet_link_challenge_payload(result: WalletLinkChallengeResult) -> dict[str, Any]:
    payload = _challenge_payload(LoginChallengeResult(result.challenge, result.signing_message))
    payload["purpose"] = result.challenge.purpose.value
    payload["targetUserId"] = str(result.challenge.target_user_id)
    return payload


def _wallet_result_payload(result: WalletResult) -> dict[str, Any]:
    return {"wallet": _wallet_payload(result.wallet)}


def _wallets_payload(result: WalletsResult) -> dict[str, Any]:
    return {"wallets": [_wallet_payload(wallet) for wallet in result.wallets]}


def _wallet_payload(wallet: Any) -> dict[str, Any]:
    return {
        "walletId": str(wallet.wallet_id),
        "userId": str(wallet.user_id),
        "walletAddress": str(wallet.address),
        "chainId": wallet.chain_id,
        "walletType": wallet.wallet_type.value,
        "verificationStatus": wallet.verification_status.value,
        "primary": wallet.primary,
        "linkedAt": wallet.linked_at.isoformat(),
        "revokedAt": wallet.revoked_at.isoformat() if wallet.revoked_at is not None else None,
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
        "signatureVerification": dict(SIGNATURE_VERIFICATION_METADATA),
    }


def _user_payload(user: User) -> dict[str, Any]:
    return {
        "userId": str(user.user_id),
        "walletAddress": str(user.primary_wallet),
        "active": user.active,
        "lastLoginAt": user.last_login_at.isoformat() if user.last_login_at is not None else None,
    }


def _session_payload(session: AuthSession) -> dict[str, Any]:
    return {
        "userId": str(session.user_id),
        "walletAddress": str(session.wallet),
        "deviceId": session.device_id,
        "expiresAt": session.expires_at.isoformat(),
        "revokedAt": session.revoked_at.isoformat() if session.revoked_at is not None else None,
    }


def _profile_payload(profile: UserProfile) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "userId": str(profile.user_id),
        "displayName": profile.display_name,
        "displayNameHtml": profile.display_name_html,
        "status": profile.status.value,
        "createdAt": profile.created_at.isoformat() if profile.created_at is not None else None,
        "updatedAt": profile.updated_at.isoformat() if profile.updated_at is not None else None,
    }
    return payload


def _authenticated_user_id(request: ApiRequest) -> str:
    if request.auth_context is None or request.auth_context.user_id is None:
        raise AuthApplicationError(AuthErrorCode.AUTHENTICATION_REQUIRED, "authenticated session is required")
    return request.auth_context.user_id


def _target_profile_user_id(request: ApiRequest, *, default_user_id: str | None = None) -> str:
    value = request.query.get("userId")
    if value is None and isinstance(request.body, Mapping):
        value = request.body.get("userId")
    if value is None:
        value = default_user_id
    if not isinstance(value, str) or not value.strip():
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, "userId is required")
    return value.strip()


def _has_scope(request: ApiRequest, scope: str) -> bool:
    return request.auth_context is not None and scope in request.auth_context.scopes


def _optional_profile_text(body: Mapping[str, Any], key: str) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{key} must be a string")
    return value


def _reject_unknown_profile_fields(body: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(str(key) for key in body if key not in allowed)
    if unknown:
        raise AuthApplicationError(
            AuthErrorCode.VALIDATION_ERROR,
            f"unknown user profile field(s): {', '.join(unknown)}",
        )


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


def _required_query_text(request: ApiRequest, key: str) -> str:
    value = request.query.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{key} is required")
    return value.strip()


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


def _optional_text(body: Mapping[str, Any], key: str) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, f"{key} must be a non-empty string")
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
        AuthErrorCode.SIWE_MESSAGE_MISMATCH: 401,
        AuthErrorCode.EXPIRED_CHALLENGE: 409,
        AuthErrorCode.REUSED_NONCE: 409,
        AuthErrorCode.VALIDATION_ERROR: 400,
        AuthErrorCode.AUTHENTICATION_REQUIRED: 401,
        AuthErrorCode.USER_PROFILE_FORBIDDEN: 403,
        AuthErrorCode.USER_PROFILE_NOT_FOUND: 404,
        AuthErrorCode.USER_PROFILE_DISPLAY_NAME_CONFLICT: 409,
        AuthErrorCode.WALLET_ALREADY_LINKED: 409,
        AuthErrorCode.WALLET_LINK_CHALLENGE_MISMATCH: 409,
        AuthErrorCode.WALLET_NOT_FOUND: 404,
        AuthErrorCode.WALLET_NOT_ACTIVE: 409,
        AuthErrorCode.LAST_WALLET_REVOKE_DENIED: 409,
    }[code]


def _coerce_auth_error(error: AuthApplicationError | ValueError) -> AuthApplicationError:
    if isinstance(error, AuthApplicationError):
        return error
    return AuthApplicationError(AuthErrorCode.VALIDATION_ERROR, str(error))


def _profile_error_response(
    code: str,
    message: str,
    status_code: int,
    request_id: str | None,
) -> ApiResponse:
    return json_response(
        {"error": {"code": code, "message": message}},
        status_code=status_code,
        request_id=request_id,
    )


__all__ = ["AuthApi"]

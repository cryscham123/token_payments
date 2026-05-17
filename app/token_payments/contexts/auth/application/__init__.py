"""Authentication application layer."""

from .ports import (
    AuthEventPublisher,
    AuthSessionRepository,
    AuthUseCase,
    CurrentUserQuery,
    LoginChallengeRepository,
    LoginChallengeResult,
    LoginResult,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    RefreshSessionCommand,
    RequestLoginChallengeCommand,
    TokenIssuer,
    UserRepository,
    WalletSignatureVerifier,
)
from .service import AuthApplicationError, AuthApplicationService, AuthErrorCode
from .siwe import SIWE_VERSION, SiweMessage, build_siwe_message, parse_siwe_message

__all__ = [
    "AuthApplicationError",
    "AuthApplicationService",
    "AuthErrorCode",
    "AuthEventPublisher",
    "AuthSessionRepository",
    "AuthUseCase",
    "CurrentUserQuery",
    "LoginChallengeRepository",
    "LoginChallengeResult",
    "LoginResult",
    "LoginWithMetaMaskCommand",
    "LogoutCommand",
    "RefreshSessionCommand",
    "RequestLoginChallengeCommand",
    "SIWE_VERSION",
    "SiweMessage",
    "TokenIssuer",
    "UserRepository",
    "WalletSignatureVerifier",
    "build_siwe_message",
    "parse_siwe_message",
]

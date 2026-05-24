"""Authentication adapter layer."""

from .postgres import (
    PostgresAuthRbacRepository,
    PostgresAuthSessionRepository,
    PostgresLoginChallengeRepository,
    PostgresMerchantMembershipRepository,
    PostgresUserProfileRepository,
    PostgresUserRepository,
    PostgresUserWalletRepository,
)
from .wallet_signature import ClientWalletSignatureVerifier, WalletSignatureVerifier
from .projection_listener import StoreMembershipProjectionKafkaListener

__all__ = [
    "ClientWalletSignatureVerifier",
    "PostgresAuthRbacRepository",
    "PostgresAuthSessionRepository",
    "PostgresLoginChallengeRepository",
    "PostgresMerchantMembershipRepository",
    "PostgresUserProfileRepository",
    "PostgresUserRepository",
    "PostgresUserWalletRepository",
    "WalletSignatureVerifier",
    "StoreMembershipProjectionKafkaListener",
]

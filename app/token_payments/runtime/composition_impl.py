"""Live API runtime composition contracts without driver construction."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import importlib
import inspect
import json
import os
from typing import Any, Mapping, Protocol, Self
from urllib.parse import SplitResult, urlsplit, urlunsplit
from uuid import uuid4

from token_payments.contexts.auth.adapter import ClientWalletSignatureVerifier
from token_payments.contexts.auth.adapter import (
    PostgresAuthRbacRepository,
    PostgresAuthSessionRepository,
    PostgresLoginChallengeRepository,
    PostgresMerchantMembershipRepository,
    PostgresOAuthIdentityRepository,
    PostgresUserProfileRepository,
    PostgresUserRepository,
    PostgresUserWalletRepository,
)
from token_payments.contexts.auth.application import (
    AuthApplicationService,
    CompleteOAuthSessionCommand,
    CurrentUserQuery,
    GetCurrentUserProfileQuery,
    GetUserProfileQuery,
    LinkOAuthIdentityCommand,
    LinkWalletCommand,
    ListOAuthIdentitiesQuery,
    ListWalletsQuery,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    MerchantMembershipService,
    RefreshSessionCommand,
    RequestOAuthAuthorizationCommand,
    RequestLoginChallengeCommand,
    RequestWalletLinkChallengeCommand,
    RevokeOAuthIdentityCommand,
    RevokeWalletCommand,
    SetPrimaryWalletCommand,
    UpdateUserProfileCommand,
)
from token_payments.contexts.auth.domain import AuthEvent, AuthSession, IssuedToken, User
from token_payments.contexts.inventory.adapter import (
    PostgresInventoryAuditRepository,
    PostgresInventoryQueryRepository,
    PostgresInventoryRepository,
)
from token_payments.contexts.inventory.application import StoreOwnerInventoryCommandHandler
from token_payments.contexts.order.adapter import (
    PostgresCheckoutTrackingQuery,
    PostgresCustomerRepository,
    PostgresOrderRepository,
    PostgresStoreRepository,
)
from token_payments.contexts.order.application import (
    CancelOrderCommand,
    CreateOrderCommand,
    OrderApplicationService,
    OrderCommandHandler,
)
from token_payments.contexts.order.domain import TrackingId
from token_payments.contexts.payment.adapter.blockchain import ClientBlockchainAdapter
from token_payments.contexts.payment.adapter.postgres import (
    PostgresPaymentAuthorizationRepository,
    PostgresPaymentRepository,
)
from token_payments.contexts.payment.adapter.transaction_service import ClientTransactionService
from token_payments.contexts.payment.application import (
    ConfirmPaymentReceiptCommand,
    ExpireAwaitingSignatureCommand,
    InitiatePaymentCommand,
    PaymentCommandHandler,
    RefundPaymentCommand,
    SubmitTransactionHashCommand,
)
from token_payments.contexts.payment.domain import PaymentAsset, PaymentAssetRegistry, PaymentChain
from token_payments.contexts.store_catalog.adapter import PostgresStoreCatalogRepository
from token_payments.contexts.store_catalog.application import StoreCatalogApplicationService
from token_payments.shared.domain import (
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    CommandMetadata,
    ChainNetwork,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    PaymentId,
    ProcessedCommand,
    UserId,
    WalletAddress,
)
from token_payments.shared.adapter.postgres import (
    PostgresOutboxMessageRepository,
    PostgresProcessedCommandRepository,
    PostgresProcessedMessageRepository,
    ensure_postgres_schema_compatibility,
)

from .contracts import Clock, HealthState, IdGenerator, JsonValue, WorkerLoopOptions
from .observability import PostgresOperatorObservabilityQuery, ReadinessProbe, ReadinessProbeResult
from .security import (
    DEFAULT_CORS_ALLOWED_ORIGINS,
    DEFAULT_CSRF_ACTIVE_KEY_ID,
    DEFAULT_CSRF_COOKIE_NAME,
    DEFAULT_CSRF_HEADER_NAME,
    DEFAULT_CSRF_MAX_AGE_SECONDS,
    DEFAULT_CSRF_SIGNING_KEY,
    DEFAULT_REQUEST_BODY_MAX_BYTES,
    CorsPolicy,
    CsrfCookieSettings,
    CsrfTokenConfig,
    CsrfTokenService,
    HmacCsrfTokenSigner,
    RequestBodyLimit,
    RequestGuard,
)
from .session_transport import (
    DEFAULT_SESSION_ACCESS_TTL_SECONDS,
    DEFAULT_SESSION_REFRESH_TTL_SECONDS,
    CookieSettings,
    CookieSessionTransport,
    SessionClaims,
    SessionKeyConfig,
    SessionKeyRing,
    SessionTokenSigner,
    is_live_environment,
)


DEFAULT_POSTGRES_DSN = "postgresql://token_payments:<redacted>@postgres:5432/token_payments"
DEFAULT_KAFKA_BOOTSTRAP_SERVERS = ("kafka:9092",)
DEFAULT_KAFKA_CLIENT_ID = "token-payments-local"
DEFAULT_WALLET_SIGNATURE_DOMAIN = "token-payments.local"
DEFAULT_WALLET_SIGNATURE_TIMEOUT_SECONDS = 3.0
DEFAULT_BLOCKCHAIN_RPC_SCHEME = "http"
DEFAULT_BLOCKCHAIN_RPC_HOST = "localhost"
DEFAULT_BLOCKCHAIN_RPC_PORT = 8545
DEFAULT_BLOCKCHAIN_RPC_PATH = ""
DEFAULT_BLOCKCHAIN_RPC_URL = "http://localhost:8545"
DEFAULT_BLOCKCHAIN_CHAIN_ID = 1337
DEFAULT_BLOCKCHAIN_NATIVE_SYMBOL = "ETH"
DEFAULT_BLOCKCHAIN_NATIVE_DECIMALS = 18
DEFAULT_BLOCKCHAIN_TOKEN_ADDRESS = None
DEFAULT_BLOCKCHAIN_GAS_BUFFER_RATE = Decimal("0.10")

REQUIRED_LIVE_DEPENDENCIES = (
    "postgres_session_factory",
    "kafka_producer",
    "wallet_signature_client",
    "blockchain_client",
    "clock",
    "id_generator",
)
LIVE_RUNTIME_DEPENDENCY_MISSING = "LIVE_RUNTIME_DEPENDENCY_MISSING"
LIVE_RUNTIME_DRIVER_CONFIGURATION_INVALID = "LIVE_RUNTIME_DRIVER_CONFIGURATION_INVALID"


class PostgresSessionFactory(Protocol):
    """Factory supplied by outer wiring for PostgreSQL connection/session objects."""

    def __call__(self) -> Any:
        ...


class KafkaProducerClient(Protocol):
    """Marker protocol for an injected Kafka producer/client."""


class WalletSignatureClient(Protocol):
    """Marker protocol for an injected wallet signature client."""


class BlockchainClient(Protocol):
    """Marker protocol for an injected blockchain RPC client."""


class LiveRuntimeDriverConfigurationError(ValueError):
    """Bounded validation error for env-backed live runtime driver construction."""

    def __init__(self, field: str, message: str) -> None:
        self.field = _require_text(field, "LiveRuntimeDriverConfigurationError.field")
        super().__init__(_require_text(message, "LiveRuntimeDriverConfigurationError.message"))

    def to_error(self) -> dict[str, JsonValue]:
        return {
            "code": LIVE_RUNTIME_DRIVER_CONFIGURATION_INVALID,
            "field": self.field,
            "message": str(self),
        }


@dataclass(frozen=True)
class LiveRuntimeConfig:
    """API and adapter settings needed by explicit live API wiring."""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    runtime_environment: str = "local"
    request_timeout_seconds: float = 30.0
    postgres_dsn: str = field(default=DEFAULT_POSTGRES_DSN, repr=False)
    kafka_bootstrap_servers: tuple[str, ...] | str = DEFAULT_KAFKA_BOOTSTRAP_SERVERS
    kafka_client_id: str = DEFAULT_KAFKA_CLIENT_ID
    wallet_signature_domain: str = DEFAULT_WALLET_SIGNATURE_DOMAIN
    wallet_signature_rpc_url: str = field(default=DEFAULT_BLOCKCHAIN_RPC_URL, repr=False)
    wallet_signature_chain_id: int = DEFAULT_BLOCKCHAIN_CHAIN_ID
    wallet_signature_timeout_seconds: float = DEFAULT_WALLET_SIGNATURE_TIMEOUT_SECONDS
    blockchain_rpc_url: str = field(default=DEFAULT_BLOCKCHAIN_RPC_URL, repr=False)
    blockchain_chain_id: int = DEFAULT_BLOCKCHAIN_CHAIN_ID
    blockchain_native_symbol: str = DEFAULT_BLOCKCHAIN_NATIVE_SYMBOL
    blockchain_native_decimals: int = DEFAULT_BLOCKCHAIN_NATIVE_DECIMALS
    blockchain_token_address: str | None = field(default=DEFAULT_BLOCKCHAIN_TOKEN_ADDRESS, repr=False)
    blockchain_gas_buffer_rate: Decimal | str | int | float = DEFAULT_BLOCKCHAIN_GAS_BUFFER_RATE
    session_key_ring: SessionKeyRing | None = field(default=None, repr=False)
    session_access_ttl_seconds: int = DEFAULT_SESSION_ACCESS_TTL_SECONDS
    session_refresh_ttl_seconds: int = DEFAULT_SESSION_REFRESH_TTL_SECONDS
    cors_allowed_origins: tuple[str, ...] | str = DEFAULT_CORS_ALLOWED_ORIGINS
    cors_allow_credentials: bool = True
    csrf_key_id: str = DEFAULT_CSRF_ACTIVE_KEY_ID
    csrf_signing_key: str = field(default=DEFAULT_CSRF_SIGNING_KEY, repr=False)
    csrf_max_age_seconds: int = DEFAULT_CSRF_MAX_AGE_SECONDS
    csrf_cookie_name: str = DEFAULT_CSRF_COOKIE_NAME
    csrf_header_name: str = DEFAULT_CSRF_HEADER_NAME
    cookie_secure: bool = True
    cookie_samesite: str = "Lax"
    request_body_max_bytes: int = DEFAULT_REQUEST_BODY_MAX_BYTES
    kafka_request_timeout_seconds: float = 3.0
    worker_batch_size: int = 100
    worker_poll_interval_seconds: float = 1.0
    receipt_poll_interval_seconds: float = 5.0

    def worker_loop_options(self) -> WorkerLoopOptions:
        return WorkerLoopOptions(
            batch_size=self.worker_batch_size,
            poll_interval_seconds=self.worker_poll_interval_seconds,
            receipt_poll_interval_seconds=self.receipt_poll_interval_seconds,
        )

    def __post_init__(self) -> None:
        object.__setattr__(self, "api_host", _require_text(self.api_host, "RUNTIME_API_HOST"))
        object.__setattr__(self, "api_port", _require_port(self.api_port, "RUNTIME_API_PORT"))
        object.__setattr__(
            self,
            "runtime_environment",
            _require_text(self.runtime_environment, "RUNTIME_ENVIRONMENT").lower(),
        )
        object.__setattr__(
            self,
            "request_timeout_seconds",
            _require_positive_number(self.request_timeout_seconds, "RUNTIME_REQUEST_TIMEOUT_SECONDS"),
        )
        object.__setattr__(self, "postgres_dsn", _require_text(self.postgres_dsn, "ADAPTER_POSTGRES_DSN"))
        object.__setattr__(
            self,
            "kafka_bootstrap_servers",
            _normalize_text_tuple(self.kafka_bootstrap_servers, "ADAPTER_KAFKA_BOOTSTRAP_SERVERS"),
        )
        object.__setattr__(
            self,
            "kafka_client_id",
            _require_text(self.kafka_client_id, "ADAPTER_KAFKA_CLIENT_ID"),
        )
        object.__setattr__(
            self,
            "wallet_signature_domain",
            _require_text(self.wallet_signature_domain, "ADAPTER_WALLET_SIGNATURE_DOMAIN"),
        )
        object.__setattr__(
            self,
            "wallet_signature_rpc_url",
            _require_text(
                self.wallet_signature_rpc_url,
                "ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL",
            ),
        )
        object.__setattr__(
            self,
            "wallet_signature_chain_id",
            _require_positive_int(
                self.wallet_signature_chain_id,
                "ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID",
            ),
        )
        object.__setattr__(
            self,
            "wallet_signature_timeout_seconds",
            _require_positive_number(
                self.wallet_signature_timeout_seconds,
                "ADAPTER_AUTH_WALLET_SIGNATURE_TIMEOUT_SECONDS",
            ),
        )
        object.__setattr__(
            self,
            "blockchain_rpc_url",
            _require_text(self.blockchain_rpc_url, "ADAPTER_BLOCKCHAIN_RPC_URL"),
        )
        object.__setattr__(
            self,
            "blockchain_chain_id",
            _require_positive_int(self.blockchain_chain_id, "ADAPTER_BLOCKCHAIN_CHAIN_ID"),
        )
        object.__setattr__(
            self,
            "blockchain_native_symbol",
            _require_text(self.blockchain_native_symbol, "ADAPTER_BLOCKCHAIN_NATIVE_SYMBOL"),
        )
        object.__setattr__(
            self,
            "blockchain_native_decimals",
            _require_positive_int(self.blockchain_native_decimals, "ADAPTER_BLOCKCHAIN_NATIVE_DECIMALS"),
        )
        object.__setattr__(
            self,
            "blockchain_token_address",
            _optional_text(self.blockchain_token_address, "ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS"),
        )
        object.__setattr__(
            self,
            "blockchain_gas_buffer_rate",
            _require_non_negative_decimal(
                self.blockchain_gas_buffer_rate,
                "ADAPTER_BLOCKCHAIN_GAS_BUFFER_RATE",
            ),
        )
        if self.session_key_ring is None:
            object.__setattr__(
                self,
                "session_key_ring",
                SessionKeyRing.from_env({}, runtime_environment=self.runtime_environment),
            )
        elif not isinstance(self.session_key_ring, SessionKeyRing):
            raise ValueError("LiveRuntimeConfig.session_key_ring must be a SessionKeyRing")
        else:
            self.session_key_ring.validate_for_environment(self.runtime_environment)
        object.__setattr__(
            self,
            "session_access_ttl_seconds",
            _require_positive_int(self.session_access_ttl_seconds, "SESSION_ACCESS_TTL_SECONDS"),
        )
        object.__setattr__(
            self,
            "session_refresh_ttl_seconds",
            _require_positive_int(self.session_refresh_ttl_seconds, "SESSION_REFRESH_TTL_SECONDS"),
        )
        cors_allowed_origins = _normalize_text_tuple(self.cors_allowed_origins, "CORS_ALLOWED_ORIGINS")
        object.__setattr__(self, "cors_allowed_origins", cors_allowed_origins)
        if not isinstance(self.cors_allow_credentials, bool):
            raise ValueError("CORS_ALLOW_CREDENTIALS must be a bool")
        CorsPolicy(allowed_origins=cors_allowed_origins, allow_credentials=self.cors_allow_credentials)
        CsrfTokenConfig(
            active_key_id=self.csrf_key_id,
            signing_key=self.csrf_signing_key,
            max_age_seconds=self.csrf_max_age_seconds,
        ).validate_for_environment(self.runtime_environment)
        object.__setattr__(self, "csrf_key_id", _require_text(self.csrf_key_id, "CSRF_ACTIVE_KEY_ID"))
        object.__setattr__(self, "csrf_signing_key", _require_text(self.csrf_signing_key, "CSRF_SIGNING_KEY"))
        object.__setattr__(
            self,
            "csrf_max_age_seconds",
            _require_positive_int(self.csrf_max_age_seconds, "CSRF_MAX_AGE_SECONDS"),
        )
        csrf_cookie_settings = CsrfCookieSettings(
            cookie_name=self.csrf_cookie_name,
            same_site=self.cookie_samesite,
            secure=self.cookie_secure,
            max_age_seconds=self.csrf_max_age_seconds,
        )
        session_cookie_settings = CookieSettings(
            same_site=self.cookie_samesite,
            secure=self.cookie_secure,
            access_max_age_seconds=self.session_access_ttl_seconds,
            refresh_max_age_seconds=self.session_refresh_ttl_seconds,
        )
        object.__setattr__(self, "csrf_cookie_name", csrf_cookie_settings.cookie_name)
        object.__setattr__(self, "csrf_header_name", _require_text(self.csrf_header_name, "CSRF_HEADER_NAME"))
        object.__setattr__(self, "cookie_secure", session_cookie_settings.secure)
        object.__setattr__(self, "cookie_samesite", session_cookie_settings.same_site)
        if is_live_environment(self.runtime_environment) and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in live/prod mode")
        object.__setattr__(
            self,
            "request_body_max_bytes",
            _require_positive_int(self.request_body_max_bytes, "REQUEST_BODY_MAX_BYTES"),
        )
        object.__setattr__(
            self,
            "kafka_request_timeout_seconds",
            _require_positive_number(self.kafka_request_timeout_seconds, "ADAPTER_KAFKA_REQUEST_TIMEOUT_SECONDS"),
        )
        object.__setattr__(
            self,
            "worker_batch_size",
            _require_positive_int(self.worker_batch_size, "RUNTIME_WORKER_BATCH_SIZE"),
        )
        object.__setattr__(
            self,
            "worker_poll_interval_seconds",
            _require_positive_number(self.worker_poll_interval_seconds, "RUNTIME_WORKER_POLL_INTERVAL_SECONDS"),
        )
        object.__setattr__(
            self,
            "receipt_poll_interval_seconds",
            _require_positive_number(self.receipt_poll_interval_seconds, "RUNTIME_RECEIPT_POLL_INTERVAL_SECONDS"),
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        source = os.environ if env is None else env
        runtime_environment = source.get("RUNTIME_ENVIRONMENT", "local")
        session_key_config = SessionKeyConfig.from_env(source, runtime_environment=runtime_environment)
        csrf_env = _csrf_env_with_session_fallback(source, session_key_config)
        csrf_config = CsrfTokenConfig.from_env(csrf_env, runtime_environment=runtime_environment)
        blockchain_rpc_url = _blockchain_rpc_url_from_env(source)
        blockchain_chain_id = _parse_int(
            source,
            "ADAPTER_BLOCKCHAIN_CHAIN_ID",
            DEFAULT_BLOCKCHAIN_CHAIN_ID,
        )
        return cls(
            api_host=source.get("RUNTIME_API_HOST", "0.0.0.0"),
            api_port=_parse_int(source, "RUNTIME_API_PORT", 8000),
            runtime_environment=runtime_environment,
            request_timeout_seconds=_parse_float(source, "RUNTIME_REQUEST_TIMEOUT_SECONDS", 30.0),
            postgres_dsn=source.get("ADAPTER_POSTGRES_DSN", DEFAULT_POSTGRES_DSN),
            kafka_bootstrap_servers=_parse_csv(
                source.get("ADAPTER_KAFKA_BOOTSTRAP_SERVERS"),
                DEFAULT_KAFKA_BOOTSTRAP_SERVERS,
            ),
            kafka_client_id=source.get("ADAPTER_KAFKA_CLIENT_ID", DEFAULT_KAFKA_CLIENT_ID),
            wallet_signature_domain=source.get(
                "ADAPTER_WALLET_SIGNATURE_DOMAIN",
                DEFAULT_WALLET_SIGNATURE_DOMAIN,
            ),
            wallet_signature_rpc_url=_wallet_signature_rpc_url_from_env(source, blockchain_rpc_url),
            wallet_signature_chain_id=_parse_int(
                source,
                "ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID",
                blockchain_chain_id,
            ),
            wallet_signature_timeout_seconds=_parse_float(
                source,
                "ADAPTER_AUTH_WALLET_SIGNATURE_TIMEOUT_SECONDS",
                DEFAULT_WALLET_SIGNATURE_TIMEOUT_SECONDS,
            ),
            blockchain_rpc_url=blockchain_rpc_url,
            blockchain_chain_id=blockchain_chain_id,
            blockchain_native_symbol=source.get(
                "ADAPTER_BLOCKCHAIN_NATIVE_SYMBOL",
                DEFAULT_BLOCKCHAIN_NATIVE_SYMBOL,
            ),
            blockchain_native_decimals=_parse_int(
                source,
                "ADAPTER_BLOCKCHAIN_NATIVE_DECIMALS",
                DEFAULT_BLOCKCHAIN_NATIVE_DECIMALS,
            ),
            blockchain_token_address=source.get(
                "ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS",
                DEFAULT_BLOCKCHAIN_TOKEN_ADDRESS,
            ),
            blockchain_gas_buffer_rate=_parse_decimal(
                source,
                "ADAPTER_BLOCKCHAIN_GAS_BUFFER_RATE",
                DEFAULT_BLOCKCHAIN_GAS_BUFFER_RATE,
            ),
            session_key_ring=session_key_config.key_ring,
            session_access_ttl_seconds=session_key_config.access_ttl_seconds,
            session_refresh_ttl_seconds=session_key_config.refresh_ttl_seconds,
            cors_allowed_origins=_parse_csv(
                source.get("CORS_ALLOWED_ORIGINS"),
                DEFAULT_CORS_ALLOWED_ORIGINS,
            ),
            cors_allow_credentials=_parse_bool(source, "CORS_ALLOW_CREDENTIALS", True),
            csrf_key_id=csrf_config.active_key_id,
            csrf_signing_key=csrf_config.signing_key,
            csrf_max_age_seconds=csrf_config.max_age_seconds,
            csrf_cookie_name=source.get("CSRF_COOKIE_NAME", DEFAULT_CSRF_COOKIE_NAME),
            csrf_header_name=source.get("CSRF_HEADER_NAME", DEFAULT_CSRF_HEADER_NAME),
            cookie_secure=_parse_bool(source, "COOKIE_SECURE", True),
            cookie_samesite=source.get("COOKIE_SAMESITE", "Lax"),
            request_body_max_bytes=_parse_int(
                source,
                "REQUEST_BODY_MAX_BYTES",
                DEFAULT_REQUEST_BODY_MAX_BYTES,
            ),
            kafka_request_timeout_seconds=_parse_float(
                source,
                "ADAPTER_KAFKA_REQUEST_TIMEOUT_SECONDS",
                3.0,
            ),
            worker_batch_size=_parse_int(source, "RUNTIME_WORKER_BATCH_SIZE", 100),
            worker_poll_interval_seconds=_parse_float(
                source,
                "RUNTIME_WORKER_POLL_INTERVAL_SECONDS",
                1.0,
            ),
            receipt_poll_interval_seconds=_parse_float(
                source,
                "RUNTIME_RECEIPT_POLL_INTERVAL_SECONDS",
                5.0,
            ),
        )

    def to_redacted_dict(self) -> dict[str, JsonValue]:
        """Return JSON-safe configuration metadata without secrets or placeholder token addresses."""

        return {
            "api": {
                "host": self.api_host,
                "port": self.api_port,
                "environment": self.runtime_environment,
                "requestTimeoutSeconds": self.request_timeout_seconds,
            },
            "session": {
                "transport": "HttpOnlyCookie",
                "accessCookieName": "access_token",
                "refreshCookieName": "refresh_token",
                "activeKeyId": self.session_key_ring.active_key_id,
                "signingKeyIds": list(self.session_key_ring.keys),
                "signingKeysConfigured": bool(self.session_key_ring.keys),
                "accessTtlSeconds": self.session_access_ttl_seconds,
                "refreshTtlSeconds": self.session_refresh_ttl_seconds,
                "cookieSecure": self.cookie_secure,
                "cookieSameSite": self.cookie_samesite,
                "cookieSecretsRedacted": True,
            },
            "security": {
                "csrf": {
                    "cookieName": self.csrf_cookie_name,
                    "headerName": self.csrf_header_name,
                    "activeKeyId": self.csrf_key_id,
                    "signingKeyConfigured": bool(self.csrf_signing_key),
                    "secretRedacted": True,
                    "maxAgeSeconds": self.csrf_max_age_seconds,
                    "cookieSecure": self.cookie_secure,
                    "cookieSameSite": self.cookie_samesite,
                },
                "cors": {
                    "allowedOrigins": list(self.cors_allowed_origins),
                    "allowCredentials": self.cors_allow_credentials,
                    "wildcardWithCredentials": False,
                },
                "requestBodyMaxBytes": self.request_body_max_bytes,
            },
            "adapters": {
                "postgres": {
                    "dsn": _redact_url_secret(self.postgres_dsn),
                    "configured": bool(self.postgres_dsn),
                    "sessionFactoryInjectedExternally": True,
                },
                "kafka": {
                    "bootstrapServers": list(self.kafka_bootstrap_servers),
                    "clientId": self.kafka_client_id,
                    "requestTimeoutSeconds": self.kafka_request_timeout_seconds,
                    "producerInjectedExternally": True,
                },
                "walletSignature": {
                    "domain": self.wallet_signature_domain,
                    "rpcUrl": _redact_url_secret(self.wallet_signature_rpc_url),
                    "supportedChainIds": [self.wallet_signature_chain_id],
                    "timeoutSeconds": self.wallet_signature_timeout_seconds,
                    "clientInjectedExternally": True,
                },
                "blockchain": {
                    "rpcUrl": _redact_url_secret(self.blockchain_rpc_url),
                    "chainId": self.blockchain_chain_id,
                    "nativeSymbol": self.blockchain_native_symbol,
                    "nativeDecimals": self.blockchain_native_decimals,
                    "tokenAddress": "<redacted>" if self.blockchain_token_address else None,
                    "gasBufferRate": str(self.blockchain_gas_buffer_rate),
                    "clientInjectedExternally": True,
                },
            },
        }

    def to_debug_payload(self) -> dict[str, JsonValue]:
        return self.to_redacted_dict()


class LiveRuntimeDependencyError(ValueError):
    """Bounded validation error for incomplete live runtime wiring."""

    def __init__(self, missing_dependencies: Sequence[str]) -> None:
        missing = tuple(sorted(_require_text(name, "missing dependency") for name in missing_dependencies))
        self.missing_dependencies = missing
        super().__init__(f"missing live runtime dependencies: {', '.join(missing)}")

    def to_error(self) -> dict[str, JsonValue]:
        return {
            "code": LIVE_RUNTIME_DEPENDENCY_MISSING,
            "message": str(self),
            "missingDependencies": list(self.missing_dependencies),
        }


@dataclass(frozen=True)
class LiveRuntimeDependencies:
    """External dependencies required by live API composition.

    The objects are supplied by outer wiring. This contract only records and
    validates them; it never opens a database, Kafka, wallet, or blockchain connection.
    """

    postgres_session_factory: PostgresSessionFactory | Callable[[], Any] | None = None
    kafka_producer: KafkaProducerClient | Any | None = None
    wallet_signature_client: WalletSignatureClient | Any | None = None
    blockchain_client: BlockchainClient | Any | None = None
    clock: Clock | Any | None = None
    id_generator: IdGenerator | Any | None = None

    @classmethod
    def required_dependency_names(cls) -> tuple[str, ...]:
        return REQUIRED_LIVE_DEPENDENCIES

    def missing_dependencies(self) -> tuple[str, ...]:
        return tuple(name for name in REQUIRED_LIVE_DEPENDENCIES if getattr(self, name) is None)

    def validate(self) -> None:
        missing = self.missing_dependencies()
        if missing:
            raise LiveRuntimeDependencyError(missing)

    def describe(self) -> dict[str, JsonValue]:
        missing = self.missing_dependencies()
        provided = {
            name: _type_name(getattr(self, name))
            for name in REQUIRED_LIVE_DEPENDENCIES
            if getattr(self, name) is not None
        }
        return {
            "required": list(REQUIRED_LIVE_DEPENDENCIES),
            "provided": provided,
            "missing": list(missing),
            "valid": not missing,
        }


@dataclass(frozen=True)
class SystemClock:
    """Runtime clock backed by the system UTC clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True)
class UuidIdGenerator:
    """Runtime ID generator backed by UUID4 strings."""

    def new_id(self) -> str:
        return str(uuid4())


@dataclass(frozen=True)
class PsycopgPostgresSessionFactory:
    """Lazy psycopg session factory.

    Importing this module and constructing the factory do not open a socket.
    The connection is created only when the application handles a request or a
    readiness probe invokes the factory.
    """

    dsn: str
    connect_timeout_seconds: float = 3.0
    _schema_compatibility_checked: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dsn", _require_text(self.dsn, "ADAPTER_POSTGRES_DSN"))
        object.__setattr__(
            self,
            "connect_timeout_seconds",
            _require_positive_number(self.connect_timeout_seconds, "ADAPTER_POSTGRES_CONNECT_TIMEOUT_SECONDS"),
        )

    def __call__(self) -> Any:
        psycopg = importlib.import_module("psycopg")
        psycopg_rows = importlib.import_module("psycopg.rows")
        session = psycopg.connect(
            self.dsn,
            connect_timeout=int(self.connect_timeout_seconds),
            row_factory=psycopg_rows.dict_row,
        )
        if not self._schema_compatibility_checked:
            try:
                ensure_postgres_schema_compatibility(session)
            except Exception:
                close = getattr(session, "close", None)
                if callable(close):
                    close()
                raise
            object.__setattr__(self, "_schema_compatibility_checked", True)
        return session


@dataclass
class LazyKafkaProducerClient:
    """Lazy kafka-python producer wrapper."""

    bootstrap_servers: tuple[str, ...]
    client_id: str
    request_timeout_ms: int = 3_000
    _producer: Any | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.bootstrap_servers = _normalize_text_tuple(self.bootstrap_servers, "ADAPTER_KAFKA_BOOTSTRAP_SERVERS")
        self.client_id = _require_text(self.client_id, "ADAPTER_KAFKA_CLIENT_ID")
        self.request_timeout_ms = _require_positive_int(self.request_timeout_ms, "ADAPTER_KAFKA_REQUEST_TIMEOUT_MS")

    def send(self, *args: Any, **kwargs: Any) -> Any:
        return self._client().send(*args, **kwargs)

    def produce(self, *args: Any, **kwargs: Any) -> Any:
        producer = self._client()
        produce = getattr(producer, "produce", None)
        if not callable(produce):
            return producer.send(*args, **kwargs)
        return produce(*args, **kwargs)

    def flush(self, *args: Any, **kwargs: Any) -> Any:
        flush = getattr(self._client(), "flush", None)
        if callable(flush):
            return flush(*args, **kwargs)
        return None

    def bootstrap_connected(self) -> bool:
        producer = self._client()
        connected = getattr(producer, "bootstrap_connected", None)
        if callable(connected):
            return bool(connected())
        partitions = getattr(producer, "partitions_for", None)
        if callable(partitions):
            return partitions("__consumer_offsets") is not None
        return True

    def _client(self) -> Any:
        if self._producer is None:
            kafka = importlib.import_module("kafka")
            self._producer = kafka.KafkaProducer(
                bootstrap_servers=list(self.bootstrap_servers),
                client_id=self.client_id,
                request_timeout_ms=self.request_timeout_ms,
                value_serializer=None,
                key_serializer=None,
            )
        return self._producer


@dataclass(frozen=True)
class EthAccountWalletSignatureClient:
    """Lazy eth-account recovery and JSON-RPC ERC-1271 auth client."""

    domain: str
    rpc_url: str | None = None
    chain_id: int | None = None
    timeout_seconds: float = DEFAULT_WALLET_SIGNATURE_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", _require_text(self.domain, "ADAPTER_WALLET_SIGNATURE_DOMAIN"))
        if self.rpc_url is not None:
            object.__setattr__(
                self,
                "rpc_url",
                _require_text(self.rpc_url, "ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL"),
            )
        if self.chain_id is not None:
            object.__setattr__(
                self,
                "chain_id",
                _require_positive_int(self.chain_id, "ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID"),
            )
        object.__setattr__(
            self,
            "timeout_seconds",
            _require_positive_number(
                self.timeout_seconds,
                "ADAPTER_AUTH_WALLET_SIGNATURE_TIMEOUT_SECONDS",
            ),
        )

    def recover_address(self, message: str, signature: str) -> str:
        account_module = importlib.import_module("eth_account")
        messages_module = importlib.import_module("eth_account.messages")
        encoded = messages_module.encode_defunct(text=_require_text(message, "message"))
        return account_module.Account.recover_message(encoded, signature=_require_text(signature, "signature"))

    def get_code(self, request: Mapping[str, object] | None = None, **kwargs: object) -> str:
        payload = dict(request or kwargs)
        self._ensure_request_chain(payload)
        address = _require_text(str(payload.get("address") or payload.get("wallet") or ""), "address")
        return str(self._rpc("eth_getCode", (address, "latest")))

    def call_contract(self, request: Mapping[str, object] | None = None, **kwargs: object) -> str:
        payload = dict(request or kwargs)
        self._ensure_request_chain(payload)
        to = _require_text(str(payload.get("to") or payload.get("address") or ""), "to")
        data = _require_text(str(payload.get("data") or ""), "data")
        return str(self._rpc("eth_call", ({"to": to, "data": data}, "latest")))

    def _ensure_request_chain(self, payload: Mapping[str, object]) -> None:
        if self.chain_id is None:
            return
        raw_chain_id = payload.get("chain_id") or payload.get("chainId")
        if raw_chain_id is None:
            return
        actual = (
            int(str(raw_chain_id), 16)
            if isinstance(raw_chain_id, str) and raw_chain_id.startswith("0x")
            else int(raw_chain_id)
        )
        if actual != self.chain_id:
            raise ValueError("ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID mismatch")

    def _rpc(self, method: str, params: Sequence[object]) -> Any:
        if self.rpc_url is None:
            raise ValueError("ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL is not configured")
        urllib_request = importlib.import_module("urllib.request")
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": list(params)},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib_request.Request(
            self.rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(request, timeout=self.timeout_seconds) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, Mapping):
            raise ValueError("JSON-RPC response must be an object")
        if "error" in decoded:
            raise ValueError(f"JSON-RPC {method} failed: {decoded['error']}")
        return decoded.get("result")


@dataclass(frozen=True)
class JsonRpcBlockchainClient:
    """Small JSON-RPC client for local Ethereum-compatible test networks."""

    rpc_url: str
    chain_id: int
    native_symbol: str
    native_decimals: int
    timeout_seconds: float = 3.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "rpc_url", _require_text(self.rpc_url, "ADAPTER_BLOCKCHAIN_RPC_URL"))
        object.__setattr__(self, "chain_id", _require_positive_int(self.chain_id, "ADAPTER_BLOCKCHAIN_CHAIN_ID"))
        object.__setattr__(
            self,
            "native_symbol",
            _require_text(self.native_symbol, "ADAPTER_BLOCKCHAIN_NATIVE_SYMBOL"),
        )
        object.__setattr__(
            self,
            "native_decimals",
            _require_positive_int(self.native_decimals, "ADAPTER_BLOCKCHAIN_NATIVE_DECIMALS"),
        )
        object.__setattr__(
            self,
            "timeout_seconds",
            _require_positive_number(self.timeout_seconds, "ADAPTER_BLOCKCHAIN_TIMEOUT_SECONDS"),
        )

    def get_chain_id(self) -> int:
        value = self._rpc("eth_chainId", ())
        return int(str(value), 16) if isinstance(value, str) and value.startswith("0x") else int(value)

    def estimate_gas(self, request: Mapping[str, object] | None = None, **kwargs: object) -> dict[str, object]:
        payload = dict(request or kwargs)
        wallet_from = str(payload.get("wallet_from") or payload.get("walletFrom") or "")
        wallet_to = str(payload.get("wallet_to") or payload.get("walletTo") or "")
        amount = _amount_payload(payload.get("amount"))
        rpc_payload = _gas_transaction_payload(amount=amount, wallet_from=wallet_from, wallet_to=wallet_to)
        raw_gas = self._rpc("eth_estimateGas", (rpc_payload,))
        gas_limit = int(str(raw_gas), 16) if isinstance(raw_gas, str) and raw_gas.startswith("0x") else int(raw_gas)
        raw_gas_price = self._rpc("eth_gasPrice", ())
        gas_price = (
            int(str(raw_gas_price), 16)
            if isinstance(raw_gas_price, str) and raw_gas_price.startswith("0x")
            else int(raw_gas_price)
        )
        return {
            "estimated_fee": {
                "amount": _native_fee_amount(gas_limit * gas_price, self.native_decimals),
                "symbol": self.native_symbol,
                "chain_id": self.chain_id,
                "token_address": None,
                "decimals": self.native_decimals,
            },
            "gas_limit": gas_limit,
        }

    def get_transaction_receipt(self, request: Mapping[str, object] | None = None, **kwargs: object) -> dict[str, object] | None:
        payload = dict(request or kwargs)
        tx_hash = str(payload.get("tx_hash") or payload.get("txHash") or "")
        result = self._rpc("eth_getTransactionReceipt", (tx_hash,))
        if result is None:
            return None
        if not isinstance(result, Mapping):
            raise ValueError("eth_getTransactionReceipt result must be an object or null")
        block_number = result.get("blockNumber", 0)
        gas_used = result.get("gasUsed", 0)
        return {
            "hash": str(result.get("transactionHash") or tx_hash),
            "block_number": int(str(block_number), 16) if isinstance(block_number, str) else int(block_number),
            "gas_used": int(str(gas_used), 16) if isinstance(gas_used, str) else int(gas_used),
        }

    def create_signature_request(self, request: Mapping[str, object] | None = None, **kwargs: object) -> dict[str, object]:
        payload = dict(request or kwargs)
        return {
            "request_id": str(payload.get("payment_id") or payload.get("paymentId")),
            "amount": payload.get("amount"),
            "to": str(payload.get("wallet_to") or payload.get("walletTo")),
            "expires_at": str(payload.get("expires_at") or payload.get("expiresAt")),
        }

    def refund_payment(self, request: Mapping[str, object] | None = None, **kwargs: object) -> dict[str, object]:
        payload = dict(request or kwargs)
        refund_private_key = (os.environ.get("ADAPTER_BLOCKCHAIN_REFUND_PRIVATE_KEY") or "").strip()
        if not refund_private_key:
            raise ValueError("ADAPTER_BLOCKCHAIN_REFUND_PRIVATE_KEY is required for refund_payment")
        refund_account = (
            os.environ.get("ADAPTER_BLOCKCHAIN_REFUND_ACCOUNT")
            or os.environ.get("TEST_NETWORK_ACCOUNT")
            or ""
        ).strip()
        if not refund_account:
            raise ValueError("ADAPTER_BLOCKCHAIN_REFUND_ACCOUNT or TEST_NETWORK_ACCOUNT is required for refund_payment")
        wallet_to = str(payload.get("wallet_to") or payload.get("walletTo") or "")
        if not wallet_to:
            raise ValueError("refund_payment requires wallet_to")
        amount = _amount_payload(payload.get("amount"))
        tx_hash = self._rpc("eth_sendTransaction", (_refund_transaction_payload(amount, refund_account, wallet_to),))
        receipt = self._rpc("eth_getTransactionReceipt", (tx_hash,))
        if not isinstance(receipt, Mapping):
            raise ValueError("refund transaction receipt was not available")
        block_number = receipt.get("blockNumber", 0)
        gas_used = receipt.get("gasUsed", 0)
        return {
            "hash": str(receipt.get("transactionHash") or tx_hash),
            "block_number": int(str(block_number), 16) if isinstance(block_number, str) else int(block_number),
            "gas_used": int(str(gas_used), 16) if isinstance(gas_used, str) else int(gas_used),
        }

    def _rpc(self, method: str, params: Sequence[object]) -> Any:
        urllib_request = importlib.import_module("urllib.request")
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": list(params)},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib_request.Request(
            self.rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(request, timeout=self.timeout_seconds) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, Mapping):
            raise ValueError("JSON-RPC response must be an object")
        if "error" in decoded:
            raise ValueError(f"JSON-RPC {method} failed: {decoded['error']}")
        return decoded.get("result")


def _amount_payload(value: object) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("blockchain gas estimate amount must be an object")
    return value


def _gas_transaction_payload(
    *,
    amount: Mapping[str, object] | None,
    wallet_from: str,
    wallet_to: str,
) -> dict[str, object]:
    token_address = None if amount is None else _optional_text_value(amount, "token_address", "tokenAddress")
    if token_address:
        return {
            key: value
            for key, value in {
                "from": wallet_from,
                "to": token_address,
                "value": "0x0",
                "data": _erc20_transfer_data(wallet_to, _amount_base_units(amount)),
            }.items()
            if value
        }
    return {
        key: value
        for key, value in {
            "from": wallet_from,
            "to": wallet_to,
            "value": hex(_amount_base_units(amount) if amount is not None else 0),
        }.items()
        if value
    }


def _refund_transaction_payload(
    amount: Mapping[str, object] | None,
    refund_account: str,
    wallet_to: str,
) -> dict[str, object]:
    token_address = None if amount is None else _optional_text_value(amount, "token_address", "tokenAddress")
    if token_address:
        return {
            "from": refund_account,
            "to": token_address,
            "value": "0x0",
            "data": _erc20_transfer_data(wallet_to, _amount_base_units(amount)),
        }
    return {
        "from": refund_account,
        "to": wallet_to,
        "value": hex(_amount_base_units(amount) if amount is not None else 0),
    }


def _erc20_transfer_data(wallet_to: str, amount_base_units: int) -> str:
    address = _address_hex(wallet_to)
    return "0xa9059cbb" + address.rjust(64, "0") + hex(amount_base_units)[2:].rjust(64, "0")


def _amount_base_units(amount: Mapping[str, object]) -> int:
    decimals = int(_required_mapping_value(amount, "decimals"))
    value = Decimal(str(_required_mapping_value(amount, "amount")))
    scale = Decimal(10) ** decimals
    scaled = value * scale
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError("amount has more decimal precision than the token decimals allow")
    if integral < 0:
        raise ValueError("amount must be non-negative")
    return int(integral)


def _native_fee_amount(base_units: int, decimals: int) -> str:
    amount = Decimal(base_units) / (Decimal(10) ** decimals)
    return format(amount, "f")


def _address_hex(value: str) -> str:
    normalized = _require_text(value, "wallet_to").removeprefix("0x").removeprefix("0X")
    if len(normalized) != 40 or any(char not in "0123456789abcdefABCDEF" for char in normalized):
        raise ValueError("wallet_to must be a 20-byte hex address")
    return normalized.lower()


def _optional_text_value(payload: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _required_mapping_value(payload: Mapping[str, object], key: str) -> object:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"amount.{key} is required")
    return value


@dataclass(frozen=True)
class PostgresReadinessProbe:
    component: str
    session_factory: Callable[[], Any]
    timeout_seconds: float = 3.0

    def check(self) -> ReadinessProbeResult:
        session: Any | None = None
        try:
            session = self.session_factory()
            execute = getattr(session, "execute", None)
            if not callable(execute):
                raise TypeError("postgres session must expose execute()")
            execute("SELECT 1")
            return ReadinessProbeResult(
                component=self.component,
                state=HealthState.OK,
                details={"query": "SELECT 1", "timeoutSeconds": self.timeout_seconds},
            )
        except Exception as exc:
            return ReadinessProbeResult(
                component=self.component,
                state=HealthState.UNAVAILABLE,
                details={"timeoutSeconds": self.timeout_seconds},
                error_code="POSTGRES_UNAVAILABLE",
                message=f"{type(exc).__name__}: {exc}",
            )
        finally:
            close = getattr(session, "close", None)
            if callable(close):
                close()


@dataclass(frozen=True)
class KafkaReadinessProbe:
    component: str
    producer: Any
    timeout_seconds: float = 3.0

    def check(self) -> ReadinessProbeResult:
        try:
            connected = _kafka_connected(self.producer)
            if not connected:
                raise RuntimeError("Kafka bootstrap connection is unavailable")
            return ReadinessProbeResult(
                component=self.component,
                state=HealthState.OK,
                details={"bootstrapConnected": True, "timeoutSeconds": self.timeout_seconds},
            )
        except Exception as exc:
            return ReadinessProbeResult(
                component=self.component,
                state=HealthState.UNAVAILABLE,
                details={"timeoutSeconds": self.timeout_seconds},
                error_code="KAFKA_UNAVAILABLE",
                message=f"{type(exc).__name__}: {exc}",
            )


@dataclass(frozen=True)
class BlockchainReadinessProbe:
    component: str
    client: Any
    expected_chain_id: int
    timeout_seconds: float = 3.0

    def check(self) -> ReadinessProbeResult:
        try:
            actual_chain_id = _blockchain_chain_id(self.client)
            if actual_chain_id != self.expected_chain_id:
                return ReadinessProbeResult(
                    component=self.component,
                    state=HealthState.UNAVAILABLE,
                    details={
                        "expectedChainId": self.expected_chain_id,
                        "actualChainId": actual_chain_id,
                        "timeoutSeconds": self.timeout_seconds,
                    },
                    error_code="BLOCKCHAIN_CHAIN_ID_MISMATCH",
                    message="Blockchain RPC returned an unexpected chain id.",
                )
            return ReadinessProbeResult(
                component=self.component,
                state=HealthState.OK,
                details={"chainId": actual_chain_id, "timeoutSeconds": self.timeout_seconds},
            )
        except Exception as exc:
            return ReadinessProbeResult(
                component=self.component,
                state=HealthState.UNAVAILABLE,
                details={"expectedChainId": self.expected_chain_id, "timeoutSeconds": self.timeout_seconds},
                error_code="BLOCKCHAIN_UNAVAILABLE",
                message=f"{type(exc).__name__}: {exc}",
            )


def build_live_runtime_dependencies_from_env(
    env: Mapping[str, str] | None = None,
    *,
    config: LiveRuntimeConfig | None = None,
) -> LiveRuntimeDependencies:
    """Build lazy live runtime driver wrappers from env without opening network connections."""

    source = os.environ if env is None else env
    try:
        live_config = config or LiveRuntimeConfig.from_env(source)
    except ValueError as exc:
        raise LiveRuntimeDriverConfigurationError(_field_from_error(str(exc)), str(exc)) from exc

    try:
        return LiveRuntimeDependencies(
            postgres_session_factory=PsycopgPostgresSessionFactory(live_config.postgres_dsn),
            kafka_producer=LazyKafkaProducerClient(
                bootstrap_servers=live_config.kafka_bootstrap_servers,
                client_id=live_config.kafka_client_id,
            ),
            wallet_signature_client=EthAccountWalletSignatureClient(
                live_config.wallet_signature_domain,
                rpc_url=live_config.wallet_signature_rpc_url,
                chain_id=live_config.wallet_signature_chain_id,
                timeout_seconds=live_config.wallet_signature_timeout_seconds,
            ),
            blockchain_client=JsonRpcBlockchainClient(
                rpc_url=live_config.blockchain_rpc_url,
                chain_id=live_config.blockchain_chain_id,
                native_symbol=live_config.blockchain_native_symbol,
                native_decimals=live_config.blockchain_native_decimals,
            ),
            clock=SystemClock(),
            id_generator=UuidIdGenerator(),
        )
    except ValueError as exc:
        raise LiveRuntimeDriverConfigurationError(_field_from_error(str(exc)), str(exc)) from exc


def build_live_readiness_probes(
    *,
    config: LiveRuntimeConfig,
    dependencies: LiveRuntimeDependencies,
) -> tuple[ReadinessProbe, ...]:
    dependencies.validate()
    return (
        PostgresReadinessProbe(
            component="postgres",
            session_factory=dependencies.postgres_session_factory,
            timeout_seconds=config.request_timeout_seconds,
        ),
        KafkaReadinessProbe(
            component="kafka",
            producer=dependencies.kafka_producer,
            timeout_seconds=config.request_timeout_seconds,
        ),
        BlockchainReadinessProbe(
            component="blockchain",
            client=dependencies.blockchain_client,
            expected_chain_id=config.blockchain_chain_id,
            timeout_seconds=config.request_timeout_seconds,
        ),
    )


@dataclass(frozen=True)
class LiveApiComposition:
    """Live API dependency graph contract for later server wiring."""

    config: LiveRuntimeConfig = field(default_factory=LiveRuntimeConfig)
    dependencies: LiveRuntimeDependencies = field(default_factory=LiveRuntimeDependencies)

    def __post_init__(self) -> None:
        if not isinstance(self.config, LiveRuntimeConfig):
            raise ValueError("LiveApiComposition.config must be a LiveRuntimeConfig")
        if not isinstance(self.dependencies, LiveRuntimeDependencies):
            raise ValueError("LiveApiComposition.dependencies must be LiveRuntimeDependencies")
        self.dependencies.validate()

    def describe(self) -> dict[str, JsonValue]:
        return describe_live_runtime_dependencies(config=self.config, dependencies=self.dependencies)


@dataclass(frozen=True)
class LiveWorkerDescriptor:
    """No-start worker registry entry for live runtime composition previews."""

    name: str
    topic: str
    listener: str
    message_names: tuple[str, ...]
    long_running: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_text(self.name, "LiveWorkerDescriptor.name"))
        object.__setattr__(self, "topic", _require_text(self.topic, "LiveWorkerDescriptor.topic"))
        object.__setattr__(self, "listener", _require_text(self.listener, "LiveWorkerDescriptor.listener"))
        names = tuple(_require_text(name, "LiveWorkerDescriptor.message_names") for name in self.message_names)
        if not names:
            raise ValueError("LiveWorkerDescriptor.message_names must not be empty")
        object.__setattr__(self, "message_names", names)
        if not isinstance(self.long_running, bool):
            raise ValueError("LiveWorkerDescriptor.long_running must be a bool")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "topic": self.topic,
            "listener": self.listener,
            "messageNames": list(self.message_names),
            "longRunning": self.long_running,
        }


def live_worker_registry() -> tuple[LiveWorkerDescriptor, ...]:
    """Return live worker listener entries without constructing broker clients."""

    return (
        LiveWorkerDescriptor(
            name="checkout-process-manager",
            topic="checkout.events",
            listener="token_payments.contexts.checkout.adapter.kafka.CheckoutKafkaEventListener",
            message_names=tuple(event.value for event in CheckoutEventName),
        ),
        LiveWorkerDescriptor(
            name="inventory-command-listener",
            topic="inventory.commands",
            listener="token_payments.contexts.inventory.adapter.kafka.InventoryKafkaCommandListener",
            message_names=(
                CheckoutCommandName.RESERVE_INVENTORY.value,
                CheckoutCommandName.RELEASE_INVENTORY.value,
                CheckoutCommandName.CONFIRM_INVENTORY.value,
            ),
        ),
        LiveWorkerDescriptor(
            name="payment-command-listener",
            topic="payment.commands",
            listener="token_payments.contexts.payment.adapter.kafka.PaymentKafkaCommandListener",
            message_names=(
                CheckoutCommandName.INITIATE_PAYMENT.value,
                CheckoutCommandName.REFUND_PAYMENT.value,
            ),
        ),
        LiveWorkerDescriptor(
            name="store-approval-command-listener",
            topic="store-approval.commands",
            listener="token_payments.contexts.store_approval.adapter.kafka.StoreApprovalKafkaCommandListener",
            message_names=(CheckoutCommandName.REQUEST_STORE_APPROVAL.value,),
        ),
        LiveWorkerDescriptor(
            name="order-command-listener",
            topic="order.commands",
            listener="token_payments.contexts.order.adapter.kafka.OrderKafkaCommandListener",
            message_names=(CheckoutCommandName.CANCEL_ORDER.value,),
        ),
        LiveWorkerDescriptor(
            name="order-status-listener",
            topic="payment.events",
            listener="token_payments.contexts.order.adapter.kafka.OrderStatusKafkaEventListener",
            message_names=(
                CheckoutEventName.PAYMENT_CONFIRMED.value,
                CheckoutEventName.ORDER_APPROVED.value,
                CheckoutEventName.PAYMENT_FAILED.value,
                CheckoutEventName.PAYMENT_EXPIRED.value,
                CheckoutEventName.ORDER_REJECTED.value,
                CheckoutEventName.ORDER_CANCELLED.value,
            ),
        ),
        LiveWorkerDescriptor(
            name="auth-rbac-projector",
            topic="auth.rbac.projections",
            listener="token_payments.contexts.auth.application.StoreMembershipProjectionConsumer",
            message_names=("StoreCatalogStoreMembershipChangedEvent",),
        ),
    )


def describe_live_worker_registry() -> dict[str, JsonValue]:
    registry = live_worker_registry()
    return {
        "runtime": "live-worker",
        "longRunning": False,
        "serverStarted": False,
        "externalConnectionsOpened": False,
        "workers": [worker.to_dict() for worker in registry],
    }


@dataclass(frozen=True)
class LiveApiFacades:
    """Framework-neutral facade instances wired to live application services."""

    auth: Any
    orders: Any
    checkout: Any
    payments: Any
    catalog: Any
    inventory: Any
    merchant: Any
    operator: Any
    operator_action: Any


def register_auth_routes(
    router: Any,
    auth_api: Any,
    *,
    session_transport: Any | None = None,
    csrf_token_service: Any | None = None,
) -> Any:
    from token_payments.api import register_auth_routes as _register_auth_routes

    return _register_auth_routes(
        router,
        auth_api,
        session_transport=session_transport,
        csrf_token_service=csrf_token_service,
    )


def register_order_routes(router: Any, orders_api: Any) -> Any:
    from token_payments.api import register_order_routes as _register_order_routes

    return _register_order_routes(router, orders_api)


def register_checkout_routes(router: Any, checkout_api: Any) -> Any:
    from token_payments.api import register_checkout_routes as _register_checkout_routes

    return _register_checkout_routes(router, checkout_api)


def register_payment_routes(router: Any, payments_api: Any) -> Any:
    from token_payments.api import register_payment_routes as _register_payment_routes

    return _register_payment_routes(router, payments_api)


def register_store_catalog_routes(router: Any, catalog_api: Any) -> Any:
    from token_payments.api import register_store_catalog_routes as _register_store_catalog_routes

    return _register_store_catalog_routes(router, catalog_api)


def register_store_owner_inventory_routes(router: Any, inventory_api: Any) -> Any:
    from token_payments.api import register_store_owner_inventory_routes as _register_store_owner_inventory_routes

    return _register_store_owner_inventory_routes(router, inventory_api)


def register_merchant_membership_routes(router: Any, merchant_api: Any) -> Any:
    from token_payments.api import register_merchant_membership_routes as _register_merchant_membership_routes

    return _register_merchant_membership_routes(router, merchant_api)


def register_operator_routes(router: Any, operator_api: Any) -> Any:
    from token_payments.api import register_operator_routes as _register_operator_routes

    return _register_operator_routes(router, operator_api)


def register_operator_action_routes(router: Any, operator_action_api: Any) -> Any:
    from token_payments.api import register_operator_action_routes as _register_operator_action_routes

    return _register_operator_action_routes(router, operator_action_api)


class _TransactionalMerchantMembershipUseCase:
    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
        self._dependencies = dependencies

    def role_catalog(self, actor: Any):
        return self._execute(lambda service: service.role_catalog(actor))

    def list_members(self, actor: Any, store_id: Any):
        return self._execute(lambda service: service.list_members(actor, store_id))

    def list_invitations(self, actor: Any, store_id: Any):
        return self._execute(lambda service: service.list_invitations(actor, store_id))

    def create_invitation(self, actor: Any, store_id: Any, **kwargs: Any):
        return self._execute(lambda service: service.create_invitation(actor, store_id, **kwargs))

    def accept_invitation(self, actor: Any, invitation_id: Any, **kwargs: Any):
        return self._execute(lambda service: service.accept_invitation(actor, invitation_id, **kwargs))

    def revoke_invitation(self, actor: Any, invitation_id: Any):
        return self._execute(lambda service: service.revoke_invitation(actor, invitation_id))

    def update_member_role(self, actor: Any, store_id: Any, user_id: Any, role_id: Any):
        return self._execute(lambda service: service.update_member_role(actor, store_id, user_id, role_id))

    def remove_member(self, actor: Any, store_id: Any, user_id: Any):
        return self._execute(lambda service: service.remove_member(actor, store_id, user_id))

    def _execute(self, callback: Callable[[MerchantMembershipService], Any]) -> Any:
        return _with_transaction(self._dependencies, lambda connection: callback(self._service(connection)))

    def _service(self, connection: Any) -> MerchantMembershipService:
        return MerchantMembershipService(
            PostgresMerchantMembershipRepository(connection),
            invitation_id_generator=self._dependencies.id_generator,
        )


def build_live_api_facades(
    *,
    config: LiveRuntimeConfig | None = None,
    dependencies: LiveRuntimeDependencies | None = None,
) -> LiveApiFacades:
    """Build request-scoped API facades without opening external connections."""

    from token_payments.api import (
        AuthApi,
        CheckoutApi,
        OperatorActionApi,
        OperatorApi,
        OperatorCancelOrderActionExecutor,
        OperatorOutboxActionExecutor,
        MerchantMembershipApi,
        OrdersApi,
        PaymentsApi,
        StoreCatalogApi,
        StoreOwnerInventoryApi,
    )
    live_config = config or LiveRuntimeConfig.from_env()
    live_dependencies = dependencies or LiveRuntimeDependencies()
    LiveApiComposition(config=live_config, dependencies=live_dependencies)

    payment_handler = _TransactionalPaymentCommandHandler(live_config, live_dependencies)
    order_command_handler = _TransactionalOrderCommandHandler(live_dependencies)
    outbox_action_port = _TransactionalOperatorOutboxActionPort(live_dependencies)

    return LiveApiFacades(
        auth=AuthApi(_TransactionalAuthUseCase(live_config, live_dependencies)),
        orders=OrdersApi(_TransactionalOrderUseCase(live_config, live_dependencies)),
        checkout=CheckoutApi(_TransactionalCheckoutTrackingQuery(live_dependencies)),
        payments=PaymentsApi(payment_handler, tracking_query=_TransactionalCheckoutTrackingQuery(live_dependencies)),
        catalog=StoreCatalogApi(
            _TransactionalStoreCatalogUseCase(live_dependencies),
            id_generator=live_dependencies.id_generator,
        ),
        inventory=StoreOwnerInventoryApi(
            query=_TransactionalInventoryQuery(live_dependencies),
            command_handler=_TransactionalStoreOwnerInventoryCommandHandler(live_dependencies),
        ),
        merchant=MerchantMembershipApi(
            _TransactionalMerchantMembershipUseCase(live_dependencies)
        ),
        operator=OperatorApi(_TransactionalOperatorObservabilityQuery(live_dependencies)),
        operator_action=OperatorActionApi(
            cancel_order_executor=OperatorCancelOrderActionExecutor(order_command_handler),
            outbox_action_executor=OperatorOutboxActionExecutor(
                retry_port=outbox_action_port,
                replay_port=outbox_action_port,
            ),
        ),
    )


def build_live_api_router(
    *,
    config: LiveRuntimeConfig | None = None,
    dependencies: LiveRuntimeDependencies | None = None,
) -> Any:
    """Build the live framework-neutral router using the public route registration helpers."""

    from token_payments.api import HttpRouter

    live_config = config or LiveRuntimeConfig.from_env()
    live_dependencies = dependencies or LiveRuntimeDependencies()
    session_transport = _session_transport(live_config, live_dependencies.clock)
    csrf_token_service = _csrf_token_service(live_config, live_dependencies.clock)
    facades = build_live_api_facades(config=live_config, dependencies=live_dependencies)
    router = HttpRouter(
        auth_context_factory=session_transport.auth_context_from_http_request,
        allow_dev_auth_headers=not is_live_environment(live_config.runtime_environment),
        request_guard=_request_guard(live_config, csrf_token_service, session_transport),
    )
    _register_auth_routes_with_session_transport(router, facades.auth, session_transport, csrf_token_service)
    register_order_routes(router, facades.orders)
    register_checkout_routes(router, facades.checkout)
    register_payment_routes(router, facades.payments)
    register_store_catalog_routes(router, facades.catalog)
    register_store_owner_inventory_routes(router, facades.inventory)
    register_merchant_membership_routes(router, facades.merchant)
    register_operator_routes(router, facades.operator)
    register_operator_action_routes(router, facades.operator_action)
    return router


def describe_live_runtime_dependencies(
    *,
    config: LiveRuntimeConfig | None = None,
    dependencies: LiveRuntimeDependencies | None = None,
) -> dict[str, JsonValue]:
    """Return a JSON-safe live composition preview without starting infrastructure."""

    live_config = config or LiveRuntimeConfig.from_env()
    live_dependencies = dependencies or LiveRuntimeDependencies()
    return {
        "runtime": "live-api",
        "longRunning": False,
        "serverStarted": False,
        "externalConnectionsOpened": False,
        "config": live_config.to_redacted_dict(),
        "dependencies": live_dependencies.describe(),
    }


class _TransactionalAuthUseCase:
    def __init__(self, config: LiveRuntimeConfig, dependencies: LiveRuntimeDependencies) -> None:
        self._config = config
        self._dependencies = dependencies

    def requestLoginChallenge(self, command: RequestLoginChallengeCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).requestLoginChallenge(command),
        )

    def requestWalletLinkChallenge(self, command: RequestWalletLinkChallengeCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).requestWalletLinkChallenge(command),
        )

    def loginWithMetaMask(self, command: LoginWithMetaMaskCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).loginWithMetaMask(command),
        )

    def requestOAuthAuthorization(self, command: RequestOAuthAuthorizationCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).requestOAuthAuthorization(command),
        )

    def completeOAuthSession(self, command: CompleteOAuthSessionCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).completeOAuthSession(command),
        )

    def linkOAuthIdentity(self, command: LinkOAuthIdentityCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).linkOAuthIdentity(command),
        )

    def listOAuthIdentities(self, query: ListOAuthIdentitiesQuery):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).listOAuthIdentities(query),
        )

    def revokeOAuthIdentity(self, command: RevokeOAuthIdentityCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).revokeOAuthIdentity(command),
        )

    def linkWallet(self, command: LinkWalletCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).linkWallet(command),
        )

    def listWallets(self, query: ListWalletsQuery):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).listWallets(query),
        )

    def setPrimaryWallet(self, command: SetPrimaryWalletCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).setPrimaryWallet(command),
        )

    def revokeWallet(self, command: RevokeWalletCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).revokeWallet(command),
        )

    def refreshSession(self, command: RefreshSessionCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).refreshSession(command),
        )

    def logout(self, command: LogoutCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).logout(command),
        )

    def getCurrentUser(self, query: CurrentUserQuery):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).getCurrentUser(query),
        )

    def getCurrentUserProfile(self, query: GetCurrentUserProfileQuery):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).getCurrentUserProfile(query),
        )

    def getUserProfile(self, query: GetUserProfileQuery):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).getUserProfile(query),
        )

    def updateUserProfile(self, command: UpdateUserProfileCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).updateUserProfile(command),
        )

    def _service(self, connection: Any) -> AuthApplicationService:
        return AuthApplicationService(
            clock=self._dependencies.clock,
            nonce_generator=self._dependencies.id_generator,
            user_id_generator=self._dependencies.id_generator,
            session_id_generator=self._dependencies.id_generator,
            users=PostgresUserRepository(connection),
            wallets=PostgresUserWalletRepository(connection),
            login_challenges=PostgresLoginChallengeRepository(connection),
            sessions=PostgresAuthSessionRepository(connection),
            rbac=PostgresAuthRbacRepository(connection),
            profiles=PostgresUserProfileRepository(connection),
            oauth_identities=PostgresOAuthIdentityRepository(connection),
            signature_verifier=ClientWalletSignatureVerifier(
                self._dependencies.wallet_signature_client,
                supported_chain_ids=(self._config.wallet_signature_chain_id,),
            ),
            token_issuer=_RuntimeTokenIssuer(
                self._dependencies.clock,
                signer=SessionTokenSigner(self._config.session_key_ring),
                access_ttl=timedelta(seconds=self._config.session_access_ttl_seconds),
                refresh_ttl=timedelta(seconds=self._config.session_refresh_ttl_seconds),
            ),
            event_publisher=_NoopAuthEventPublisher(),
            challenge_ttl=timedelta(minutes=5),
        )


class _TransactionalOrderUseCase:
    def __init__(self, config: LiveRuntimeConfig, dependencies: LiveRuntimeDependencies) -> None:
        self._config = config
        self._dependencies = dependencies

    def createOrder(self, command: CreateOrderCommand):
        command = CreateOrderCommand(
            authenticated_user_id=command.authenticated_user_id,
            store_id=command.store_id,
            delivery_address=command.delivery_address,
            items=command.items,
            order_id=OrderId(_new_id(self._dependencies.id_generator, "order_id")),
            tracking_id=TrackingId(_new_id(self._dependencies.id_generator, "tracking_id")),
            event_message_id=MessageId(_new_id(self._dependencies.id_generator, "event_message_id")),
            requested_at=command.requested_at,
            causation_id=command.causation_id,
            wallet_id=command.wallet_id,
            payment_asset_id=command.payment_asset_id,
        )
        return _with_transaction(
            self._dependencies,
            lambda connection: self._create_order_and_payment_request(connection, command),
        )

    def _create_order_and_payment_request(self, connection: Any, command: CreateOrderCommand):
        outbox = PostgresOutboxMessageRepository(connection)
        result = OrderApplicationService(
            customers=PostgresCustomerRepository(connection),
            stores=PostgresStoreRepository(connection),
            orders=PostgresOrderRepository(connection),
            outbox_messages=outbox,
            wallets=PostgresUserWalletRepository(connection),
            payment_assets=_runtime_payment_asset_registry(self._config),
        ).createOrder(command)
        self._start_payment_request(connection, command, result)
        return result

    def _start_payment_request(self, connection: Any, command: CreateOrderCommand, result: Any) -> None:
        payload = result.outbox_message.payload
        payment_handler = PaymentCommandHandler(
            payment_repository=PostgresPaymentRepository(connection),
            authorization_repository=PostgresPaymentAuthorizationRepository(connection),
            processed_commands=PostgresProcessedCommandRepository(connection),
            outbox_messages=PostgresOutboxMessageRepository(connection),
            blockchain_adapter=ClientBlockchainAdapter(
                self._dependencies.blockchain_client,
                default_buffer_rate=self._config.blockchain_gas_buffer_rate,
            ),
            timeout_scheduler=_NoopPaymentTimeoutScheduler(),
            transaction_service=ClientTransactionService(self._dependencies.blockchain_client),
        )
        payment_handler.initiate_payment(
            InitiatePaymentCommand(
                command_id=CommandId.for_order_action(result.order.order_id, CheckoutCommandName.INITIATE_PAYMENT),
                payment_id=PaymentId(_new_id(self._dependencies.id_generator, "payment_id")),
                order_id=result.order.order_id,
                customer_id=result.order.customer_id,
                user_id=UserId(_required_payload_text(payload, "userId")),
                amount=result.total_amount,
                wallet_from=WalletAddress(_required_payload_text(payload, "walletFrom")),
                wallet_to=WalletAddress(_required_payload_text(payload, "walletTo")),
                chain_network=_chain_network_from_checkout_payload(payload, result.total_amount.chain_id),
                expires_at=command.requested_at + timedelta(minutes=15),
                requested_at=command.requested_at,
                causation_id=str(result.outbox_message.identity),
                event_message_id=MessageId(_new_id(self._dependencies.id_generator, "payment_event_message_id")),
                payer_wallet_id=_optional_payload_text(payload, "payerWalletId"),
                payment_asset_id=_optional_payload_text(payload, "paymentAssetId"),
            )
        )


def _chain_network_from_checkout_payload(payload: Mapping[str, Any], default_chain_id: int) -> ChainNetwork:
    chain = payload.get("chain")
    if not isinstance(chain, Mapping):
        return ChainNetwork(chain_id=default_chain_id, name=f"chain-{default_chain_id}")
    chain_id = chain.get("chainId") or chain.get("chain_id") or default_chain_id
    name = chain.get("name") or f"chain-{chain_id}"
    return ChainNetwork(chain_id=int(chain_id), name=str(name))


def _required_payload_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"checkout payload missing {key}")
    return value.strip()


def _optional_payload_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _runtime_payment_asset_registry(config: LiveRuntimeConfig) -> PaymentAssetRegistry:
    token_assets = list(_deployed_stablecoin_assets(config))
    if not token_assets and config.blockchain_token_address:
        token_assets.append(
            PaymentAsset.erc20("local-usdc", config.blockchain_chain_id, "USDC", 6, config.blockchain_token_address)
        )
    return PaymentAssetRegistry(
        chains=(
            PaymentChain(
                chain_id=config.blockchain_chain_id,
                display_name=f"chain-{config.blockchain_chain_id}",
                native_symbol=config.blockchain_native_symbol,
                enabled=True,
            ),
        ),
        assets=(
            PaymentAsset.native(
                "native",
                config.blockchain_chain_id,
                config.blockchain_native_symbol,
                config.blockchain_native_decimals,
            ),
            *token_assets,
        ),
    )


def _deployed_stablecoin_assets(config: LiveRuntimeConfig) -> tuple[PaymentAsset, ...]:
    path = os.environ.get("ADAPTER_BLOCKCHAIN_DEPLOYED_CONTRACTS_PATH", "/var/chainDB/deployed_contracts.json")
    try:
        with open(path, encoding="utf-8") as file:
            payload = json.load(file)
    except FileNotFoundError:
        return ()
    if not isinstance(payload, Mapping):
        return ()
    assets = payload.get("assets")
    if not isinstance(assets, Mapping):
        return ()
    result: list[PaymentAsset] = []
    for symbol in ("USDC", "USDT"):
        entry = assets.get(symbol)
        if not isinstance(entry, Mapping):
            continue
        address = entry.get("address")
        if address:
            result.append(
                PaymentAsset.erc20(
                    f"local-{symbol.lower()}",
                    config.blockchain_chain_id,
                    symbol,
                    int(entry.get("decimals") or 6),
                    str(address),
                )
            )
    return tuple(result)


class _TransactionalCheckoutTrackingQuery:
    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
        self._dependencies = dependencies

    def get_by_tracking_id(self, tracking_id: TrackingId):
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresCheckoutTrackingQuery(connection).get_by_tracking_id(tracking_id),
        )

    def get_by_order_id(self, order_id: OrderId):
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresCheckoutTrackingQuery(connection).get_by_order_id(order_id),
        )

    def resolve_and_verify(self, tracking_id: TrackingId, user_id: UserId) -> tuple[OrderId, PaymentId]:
        def _execute(connection):
            snapshot = PostgresCheckoutTrackingQuery(connection).get_by_tracking_id(tracking_id)
            if snapshot is None:
                raise ValueError(f"trackingId {tracking_id} not found")
            order = PostgresOrderRepository(connection).get(snapshot.order_id)
            if order is None:
                raise ValueError(f"order for trackingId {tracking_id} not found")
            customer = PostgresCustomerRepository(connection).get_by_user_id(user_id)
            if customer is None or customer.customer_id != order.customer_id:
                raise ValueError("authenticated user does not own the order")
            if snapshot.payment is None:
                raise ValueError("payment not found for this order")
            return snapshot.order_id, snapshot.payment.payment_id

        return _with_transaction(self._dependencies, _execute)


class _TransactionalPaymentCommandHandler:
    def __init__(self, config: LiveRuntimeConfig, dependencies: LiveRuntimeDependencies) -> None:
        self._config = config
        self._dependencies = dependencies

    def initiate_payment(self, command: InitiatePaymentCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._handler(connection).initiate_payment(command),
        )

    def submit_transaction_hash(self, command: SubmitTransactionHashCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._handler(connection).submit_transaction_hash(command),
        )

    def confirm_payment_receipt(self, command: ConfirmPaymentReceiptCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._handler(connection).confirm_payment_receipt(command),
        )

    def expire_awaiting_signature(self, command: ExpireAwaitingSignatureCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._handler(connection).expire_awaiting_signature(command),
        )

    def refund_payment(self, command: RefundPaymentCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._handler(connection).refund_payment(command),
        )

    def _handler(self, connection: Any) -> PaymentCommandHandler:
        blockchain = ClientBlockchainAdapter(
            self._dependencies.blockchain_client,
            default_buffer_rate=self._config.blockchain_gas_buffer_rate,
        )
        return PaymentCommandHandler(
            payment_repository=PostgresPaymentRepository(connection),
            authorization_repository=PostgresPaymentAuthorizationRepository(connection),
            processed_commands=PostgresProcessedCommandRepository(connection),
            outbox_messages=PostgresOutboxMessageRepository(connection),
            blockchain_adapter=blockchain,
            timeout_scheduler=_NoopPaymentTimeoutScheduler(),
            transaction_service=ClientTransactionService(self._dependencies.blockchain_client),
        )


class _TransactionalReceiptPollingRepository:
    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
        self._dependencies = dependencies

    def list_receipt_polling_candidates(self, *, limit: int):
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresPaymentRepository(connection).list_receipt_polling_candidates(limit=limit),
        )


class _TransactionalInventoryQuery:
    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
        self._dependencies = dependencies

    def list_inventory(self, store_id=None):
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresInventoryQueryRepository(connection).list_inventory(store_id),
        )

    def list_inventory_for_owner(self, owner_user_id, store_id=None):
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresInventoryQueryRepository(connection).list_inventory_for_owner(owner_user_id, store_id),
        )

    def owner_for_store(self, store_id):
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresInventoryQueryRepository(connection).owner_for_store(store_id),
        )


class _TransactionalStoreCatalogUseCase:
    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
        self._dependencies = dependencies

    def create_or_reuse_store_user(self, command):
        return self._execute(lambda service: service.create_or_reuse_store_user(command))

    def create_store(self, command):
        return self._execute(lambda service: service.create_store(command))

    def get_store_profile(self, query):
        return self._execute(lambda service: service.get_store_profile(query))

    def list_merchant_stores(self, query):
        return self._execute(lambda service: service.list_merchant_stores(query))

    def list_public_stores(self, *, limit: int, offset: int):
        return self._execute(lambda service: service.list_public_stores(limit=limit, offset=offset))

    def list_public_products(self, *, public_store_id, filters):
        return self._execute(
            lambda service: service.list_public_products(
                public_store_id=public_store_id,
                filters=filters,
            )
        )

    def get_public_product(self, *, public_store_id, public_product_id):
        return self._execute(
            lambda service: service.get_public_product(
                public_store_id=public_store_id,
                public_product_id=public_product_id,
            )
        )

    def list_merchant_products(self, *, actor_user_id, public_store_id, filters, platform_override=False):
        return self._execute(
            lambda service: service.list_merchant_products(
                actor_user_id=actor_user_id,
                public_store_id=public_store_id,
                filters=filters,
                platform_override=platform_override,
            )
        )

    def get_merchant_product(self, *, actor_user_id, public_store_id, public_product_id, platform_override=False):
        return self._execute(
            lambda service: service.get_merchant_product(
                actor_user_id=actor_user_id,
                public_store_id=public_store_id,
                public_product_id=public_product_id,
                platform_override=platform_override,
            )
        )

    def update_store_profile(self, command):
        return self._execute(lambda service: service.update_store_profile(command))

    def grant_store_membership(self, command):
        return self._execute(lambda service: service.grant_store_membership(command))

    def register_store_product(self, command):
        return self._execute(lambda service: service.register_store_product(command))

    def update_store_product(self, command):
        return self._execute(lambda service: service.update_store_product(command))

    def _execute(self, callback: Callable[[StoreCatalogApplicationService], Any]) -> Any:
        return _with_transaction(
            self._dependencies,
            lambda connection: callback(
                StoreCatalogApplicationService(
                    repository=PostgresStoreCatalogRepository(connection),
                    user_id_generator=self._dependencies.id_generator,
                )
            ),
        )



class _TransactionalStoreOwnerInventoryCommandHandler:
    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
        self._dependencies = dependencies

    def increase_stock(self, command):
        return self._execute(lambda handler: handler.increase_stock(command))

    def correct_stock(self, command):
        return self._execute(lambda handler: handler.correct_stock(command))

    def pause_sales(self, command):
        return self._execute(lambda handler: handler.pause_sales(command))

    def resume_sales(self, command):
        return self._execute(lambda handler: handler.resume_sales(command))

    def _execute(self, callback: Callable[[StoreOwnerInventoryCommandHandler], Any]) -> Any:
        return _with_transaction(
            self._dependencies,
            lambda connection: callback(
                StoreOwnerInventoryCommandHandler(
                    inventory_repository=PostgresInventoryRepository(connection),
                    processed_commands=PostgresProcessedCommandRepository(connection),
                    audit_repository=PostgresInventoryAuditRepository(connection),
                )
            ),
        )


class _TransactionalOperatorObservabilityQuery:
    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
        self._dependencies = dependencies

    def list_dashboard(self, query):
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresOperatorObservabilityQuery(connection).list_dashboard(query),
        )

    def get_order_detail(self, order_id: OrderId):
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresOperatorObservabilityQuery(connection).get_order_detail(order_id),
        )

    def get_payment_detail(self, payment_id: PaymentId):
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresOperatorObservabilityQuery(connection).get_payment_detail(payment_id),
        )

    def get_outbox_detail(self, kind: OutboxMessageKind, identity: str):
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresOperatorObservabilityQuery(connection).get_outbox_detail(kind, identity),
        )


class _TransactionalOrderCommandHandler:
    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
        self._dependencies = dependencies

    def cancel_order(self, command: CancelOrderCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: OrderCommandHandler(
                orders=PostgresOrderRepository(connection),
                processed_commands=PostgresProcessedCommandRepository(connection),
                outbox_messages=PostgresOutboxMessageRepository(connection),
            ).cancel_order(command),
        )


class _TransactionalOperatorOutboxActionPort:
    HANDLER_NAME = "operator-outbox-action"

    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
        self._dependencies = dependencies

    def request_retry(self, request):
        from token_payments.api import OperatorOutboxActionStatus

        return self._record_action(
            request,
            status=OperatorOutboxActionStatus.RETRYABLE,
            command_name="RetryOutboxMessageCommand",
            summary="Outbox message retry request recorded and message is retryable.",
        )

    def request_replay(self, request):
        from token_payments.api import OperatorOutboxActionStatus

        return self._record_action(
            request,
            status=OperatorOutboxActionStatus.RECORDED,
            command_name="ReplayMessageCommand",
            summary="Message replay request recorded.",
        )

    def _record_action(
        self,
        request: Any,
        *,
        status: Any,
        command_name: str,
        summary: str,
    ) -> Any:
        return _with_transaction(
            self._dependencies,
            lambda connection: self._record_action_in_connection(
                connection,
                request,
                status=status,
                command_name=command_name,
                summary=summary,
            ),
        )

    def _record_action_in_connection(
        self,
        connection: Any,
        request: Any,
        *,
        status: Any,
        command_name: str,
        summary: str,
    ) -> Any:
        from token_payments.api import OperatorOutboxActionPortResult, OperatorOutboxActionStatus

        command_id = CommandId(request.idempotency_key)
        processed = PostgresProcessedCommandRepository(connection)
        if processed.was_processed(command_id, self.HANDLER_NAME):
            return OperatorOutboxActionPortResult(
                status=OperatorOutboxActionStatus.DUPLICATE_IGNORED,
                message_kind=request.message_kind,
                message_identity=request.message_identity,
                request_id=request.request_id,
                idempotency_key=request.idempotency_key,
                summary="Duplicate operator outbox action ignored for idempotency key.",
            )

        outbox = PostgresOutboxMessageRepository(connection)
        outbox.save(
            OutboxMessage.record_command(
                metadata=CommandMetadata(
                    command_id=command_id,
                    name=command_name,
                    aggregate_id=request.message_identity,
                    issued_at=request.requested_at,
                    correlation_id=request.message_identity,
                    causation_id=request.request_id,
                ),
                topic="operator.commands",
                key=request.message_identity,
                payload={
                    "action": command_name,
                    "messageKind": request.message_kind.value,
                    "messageIdentity": request.message_identity,
                    "reason": request.reason,
                    "requestId": request.request_id,
                    "actorUserId": request.actor.user_id,
                },
                headers={
                    "correlationId": request.message_identity,
                    "causationId": request.request_id,
                },
            )
        )
        processed.record(
            ProcessedCommand.record(
                command_id=command_id,
                handler=self.HANDLER_NAME,
                processed_at=request.requested_at,
                order_id=None,
            )
        )
        return OperatorOutboxActionPortResult(
            status=status,
            message_kind=request.message_kind,
            message_identity=request.message_identity,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            summary=summary,
        )


def _session_transport(config: LiveRuntimeConfig, clock: Clock | Any | None = None) -> CookieSessionTransport:
    return CookieSessionTransport.from_key_config(
        SessionKeyConfig(
            key_ring=config.session_key_ring,
            access_ttl_seconds=config.session_access_ttl_seconds,
            refresh_ttl_seconds=config.session_refresh_ttl_seconds,
        ),
        settings=CookieSettings(
            same_site=config.cookie_samesite,
            secure=config.cookie_secure,
            access_max_age_seconds=config.session_access_ttl_seconds,
            refresh_max_age_seconds=config.session_refresh_ttl_seconds,
        ),
        clock=clock,
    )


def _csrf_token_service(config: LiveRuntimeConfig, clock: Clock | Any | None = None) -> CsrfTokenService:
    return CsrfTokenService(
        signer=HmacCsrfTokenSigner(
            key_id=config.csrf_key_id,
            secret_provider=lambda: config.csrf_signing_key,
        ),
        cookie_settings=CsrfCookieSettings(
            cookie_name=config.csrf_cookie_name,
            same_site=config.cookie_samesite,
            secure=config.cookie_secure,
            max_age_seconds=config.csrf_max_age_seconds,
        ),
        header_name=config.csrf_header_name,
        clock=clock,
    )


def _request_guard(
    config: LiveRuntimeConfig,
    csrf_token_service: CsrfTokenService,
    session_transport: CookieSessionTransport,
) -> RequestGuard:
    return RequestGuard(
        csrf_token_service=csrf_token_service,
        cors_policy=CorsPolicy(
            allowed_origins=config.cors_allowed_origins,
            allow_credentials=config.cors_allow_credentials,
        ),
        body_limit=RequestBodyLimit(max_bytes=config.request_body_max_bytes),
        auth_cookie_names=(
            session_transport.settings.access_cookie_name,
            session_transport.settings.refresh_cookie_name,
        ),
    )


def _register_auth_routes_with_session_transport(
    router: Any,
    auth_api: Any,
    session_transport: CookieSessionTransport,
    csrf_token_service: CsrfTokenService | None = None,
) -> Any:
    signature = inspect.signature(register_auth_routes)
    kwargs: dict[str, Any] = {}
    if "session_transport" in signature.parameters:
        kwargs["session_transport"] = session_transport
    if "csrf_token_service" in signature.parameters:
        kwargs["csrf_token_service"] = csrf_token_service
    if kwargs:
        return register_auth_routes(router, auth_api, **kwargs)
    return register_auth_routes(router, auth_api)


class _RuntimeTokenIssuer:
    def __init__(
        self,
        clock: Clock | Any,
        *,
        signer: SessionTokenSigner,
        access_ttl: timedelta,
        refresh_ttl: timedelta,
    ) -> None:
        self._clock = clock
        self._signer = signer
        self._access_ttl = _require_positive_timedelta(access_ttl, "SESSION_ACCESS_TTL_SECONDS")
        self._refresh_ttl = _require_positive_timedelta(refresh_ttl, "SESSION_REFRESH_TTL_SECONDS")

    def issue_tokens(self, user: User, session: AuthSession) -> IssuedToken:
        return self._token(user=user, session=session, rotation_version=0)

    def refresh_tokens(self, session: AuthSession) -> IssuedToken:
        return self._token(user=None, session=session, rotation_version=session.refresh_token_hash.rotation_version + 1)

    def refresh_tokens_for_user(self, user: User, session: AuthSession) -> IssuedToken:
        return self._token(user=user, session=session, rotation_version=session.refresh_token_hash.rotation_version + 1)

    def issue_tokens_with_claims(self, user: User, session: AuthSession, claims: dict[str, Any]) -> IssuedToken:
        return self._token(user=user, session=session, rotation_version=0, claims=claims)

    def refresh_tokens_with_claims(self, user: User, session: AuthSession, claims: dict[str, Any]) -> IssuedToken:
        return self._token(user=user, session=session, rotation_version=session.refresh_token_hash.rotation_version + 1, claims=claims)

    def _token(
        self,
        *,
        user: User | None,
        session: AuthSession,
        rotation_version: int,
        claims: dict[str, Any] | None = None,
    ) -> IssuedToken:
        now = self._clock.now()
        user_id = user.user_id if user is not None else session.user_id
        access_expires_at = now + self._access_ttl
        refresh_expires_at = now + self._refresh_ttl
        scopes = ()
        group_memberships = ()
        active_group_id = None
        if claims is not None:
            scopes = tuple(claims.get("scopes", ()))
            group_memberships = tuple(claims.get("groupMemberships", ()))
            active_group_id = claims.get("activeGroupId")
        base_claims = {
            "user_id": str(user_id),
            "session_id": str(session.session_id),
            "wallet_address": str(session.wallet),
            "issued_at": now,
            "jti": "pending",
            "rotation_version": rotation_version,
            "scopes": scopes,
            "group_memberships": group_memberships,
            "active_group_id": active_group_id,
        }
        return IssuedToken(
            access_token=self._signer.sign(
                SessionClaims(
                    **base_claims,
                    expires_at=access_expires_at,
                    token_type="access",
                )
            ),
            refresh_token=self._signer.sign(
                SessionClaims(
                    **base_claims,
                    expires_at=refresh_expires_at,
                    token_type="refresh",
                )
            ),
            expires_at=access_expires_at,
        )


class _NoopAuthEventPublisher:
    def publish(self, event: AuthEvent) -> None:
        return None


class _NoopPaymentTimeoutScheduler:
    def schedule_expiration(self, payment_id: PaymentId, expires_at: Any) -> None:
        return None

    def cancel_expiration(self, payment_id: PaymentId) -> None:
        return None


def _with_transaction(dependencies: LiveRuntimeDependencies, callback: Callable[[Any], Any]) -> Any:
    session = dependencies.postgres_session_factory()
    try:
        transaction_factory = _transaction_factory(session)
        if transaction_factory is not None:
            with transaction_factory() as transaction:
                connection = transaction if callable(getattr(transaction, "execute", None)) else session
                try:
                    result = callback(connection)
                except Exception:
                    rollback = getattr(transaction, "rollback", None)
                    if callable(rollback):
                        rollback()
                    raise
                commit = getattr(transaction, "commit", None)
                if callable(commit):
                    commit()
                return result

        try:
            result = callback(session)
        except Exception:
            rollback = getattr(session, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        commit = getattr(session, "commit", None)
        if callable(commit):
            commit()
        return result
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()


def _transaction_factory(session: Any) -> Callable[[], Any] | None:
    begin = getattr(session, "begin", None)
    if callable(begin):
        return begin
    transaction = getattr(session, "transaction", None)
    if callable(transaction):
        return transaction
    return None


def _new_id(generator: IdGenerator | Any, field_name: str) -> str:
    new_id = getattr(generator, "new_id", None)
    if callable(new_id):
        value = new_id()
    elif callable(generator):
        value = generator()
    else:
        raise ValueError(f"{field_name} generator must expose new_id()")
    return _require_text(str(value), field_name)


def _parse_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _parse_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number") from exc


def _parse_decimal(env: Mapping[str, str], key: str, default: Decimal) -> Decimal:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{key} must be a decimal number") from exc


def _blockchain_rpc_url_from_env(env: Mapping[str, str]) -> str:
    override = env.get("ADAPTER_BLOCKCHAIN_RPC_URL")
    if override is not None and override.strip():
        return override.strip()

    scheme = _require_text(
        env.get("ADAPTER_BLOCKCHAIN_RPC_SCHEME", DEFAULT_BLOCKCHAIN_RPC_SCHEME),
        "ADAPTER_BLOCKCHAIN_RPC_SCHEME",
    )
    host = _require_text(
        env.get("ADAPTER_BLOCKCHAIN_RPC_HOST", DEFAULT_BLOCKCHAIN_RPC_HOST),
        "ADAPTER_BLOCKCHAIN_RPC_HOST",
    )
    port = _parse_int(env, "ADAPTER_BLOCKCHAIN_RPC_PORT", DEFAULT_BLOCKCHAIN_RPC_PORT)
    path = (env.get("ADAPTER_BLOCKCHAIN_RPC_PATH", DEFAULT_BLOCKCHAIN_RPC_PATH) or "").strip()
    if path and not path.startswith("/"):
        path = f"/{path}"
    return f"{scheme}://{host}:{port}{path}"


def _wallet_signature_rpc_url_from_env(env: Mapping[str, str], default_rpc_url: str) -> str:
    override = env.get("ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL")
    if override is not None and override.strip():
        return override.strip()
    return _require_text(default_rpc_url, "ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL")


def _csrf_env_with_session_fallback(env: Mapping[str, str], session_key_config: SessionKeyConfig) -> Mapping[str, str]:
    if env.get("CSRF_SIGNING_KEY"):
        return env
    output = dict(env)
    active_key_id = session_key_config.key_ring.active_key_id
    output.setdefault("CSRF_ACTIVE_KEY_ID", active_key_id)
    output["CSRF_SIGNING_KEY"] = session_key_config.key_ring.secret_for(active_key_id)
    return output


def _parse_csv(raw: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _parse_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean")


def _normalize_text_tuple(value: tuple[str, ...] | str, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        values = _parse_csv(value, ())
    elif isinstance(value, Sequence):
        values = tuple(str(item).strip() for item in value if str(item).strip())
    else:
        raise ValueError(f"{field_name} must be a comma-separated string or sequence")
    if not values:
        raise ValueError(f"{field_name} must include at least one value")
    return tuple(_require_text(item, field_name) for item in values)


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = _require_text(value, field_name)
    return normalized or None


def _require_port(value: int, field_name: str) -> int:
    port = _require_positive_int(value, field_name)
    if port > 65535:
        raise ValueError(f"{field_name} must be between 1 and 65535")
    return port


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_positive_number(value: float | int, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or float(value) <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return float(value)


def _require_positive_timedelta(value: timedelta, field_name: str) -> timedelta:
    if not isinstance(value, timedelta) or value.total_seconds() <= 0:
        raise ValueError(f"{field_name} must be a positive timedelta")
    return value


def _require_non_negative_decimal(value: Decimal | str | int | float, field_name: str) -> Decimal:
    try:
        normalized = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a decimal number") from exc
    if not normalized.is_finite() or normalized < 0:
        raise ValueError(f"{field_name} must be a non-negative decimal number")
    return normalized


def _redact_url_secret(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "<redacted>"

    if not parsed.scheme or not parsed.netloc:
        return "<redacted>" if _looks_sensitive(value) else value

    netloc = parsed.netloc
    if "@" in netloc:
        netloc = _redacted_netloc(parsed)

    query = "<redacted>" if parsed.query else ""
    fragment = ""
    return urlunsplit(SplitResult(parsed.scheme, netloc, parsed.path, query, fragment))


def _redacted_netloc(parsed: SplitResult) -> str:
    host = parsed.hostname or ""
    try:
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError:
        port = ""
    user = parsed.username or ""
    userinfo = f"{user}:<redacted>@" if user else "<redacted>@"
    return f"{userinfo}{host}{port}"


def _looks_sensitive(value: str) -> bool:
    lower = value.lower()
    return any(marker in lower for marker in ("password", "private", "secret", "token", "seed"))


def _kafka_connected(producer: Any) -> bool:
    check_readiness = getattr(producer, "check_readiness", None)
    if callable(check_readiness):
        return bool(check_readiness())
    bootstrap_connected = getattr(producer, "bootstrap_connected", None)
    if callable(bootstrap_connected):
        return bool(bootstrap_connected())
    partitions_for = getattr(producer, "partitions_for", None)
    if callable(partitions_for):
        return partitions_for("__consumer_offsets") is not None
    raise TypeError("kafka producer must expose bootstrap_connected(), check_readiness(), or partitions_for()")


def _blockchain_chain_id(client: Any) -> int:
    for method_name in ("get_chain_id", "chain_id", "eth_chain_id"):
        method = getattr(client, method_name, None)
        if callable(method):
            value = method()
            return int(str(value), 16) if isinstance(value, str) and value.startswith("0x") else int(value)
    raise TypeError("blockchain client must expose get_chain_id(), chain_id(), or eth_chain_id()")


def _field_from_error(message: str) -> str:
    normalized = _require_text(message, "error message")
    first = normalized.split(maxsplit=1)[0].rstrip(":")
    if first.isupper() and "_" in first:
        return first
    return "runtime"


def _type_name(value: Any) -> str:
    return type(value).__name__


class _TransactionalOutboxRelayRepository:
    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
        self._dependencies = dependencies

    def claim_ready_batch(self, *, limit: int) -> tuple[OutboxMessage, ...]:
        return _with_transaction(
            self._dependencies,
            lambda connection: PostgresOutboxMessageRepository(connection).claim_ready_batch(limit=limit)
        )

    def mark_published(
        self,
        kind: OutboxMessageKind | str,
        identity: str,
        *,
        published_at: datetime | None = None,
    ) -> None:
        _with_transaction(
            self._dependencies,
            lambda connection: PostgresOutboxMessageRepository(connection).mark_published(
                kind, identity, published_at=published_at
            )
        )

    def mark_failed(self, kind: OutboxMessageKind | str, identity: str, error_message: str) -> None:
        _with_transaction(
            self._dependencies,
            lambda connection: PostgresOutboxMessageRepository(connection).mark_failed(
                kind, identity, error_message
            )
        )


class _TransactionalListener:
    def __init__(self, dependencies: LiveRuntimeDependencies, listener_factory: Callable[[Any], Any]) -> None:
        self._dependencies = dependencies
        self._listener_factory = listener_factory

    def handle(self, message: Any) -> Any:
        return _with_transaction(
            self._dependencies,
            lambda connection: self._listener_factory(connection).handle(message)
        )


def build_live_worker_runtime_from_env(
    env: Mapping[str, str] | None = None,
    *,
    config: LiveRuntimeConfig | None = None,
    dependencies: LiveRuntimeDependencies | None = None,
) -> WorkerRuntime:
    """Build live worker runtime with outbox relay, kafka consumer, and polling workers."""

    from token_payments.runtime.workers import (
        KafkaConsumerWorker,
        OutboxRelayWorker,
        PaymentReceiptPollingWorker,
        WorkerRuntime,
    )
    from token_payments.shared.adapter.kafka import KafkaProducerPublisher, LazyKafkaConsumerClient
    from token_payments.shared.adapter.outbox_relay import OutboxRelay

    live_config = config or LiveRuntimeConfig.from_env(env)
    live_dependencies = dependencies or build_live_runtime_dependencies_from_env(env, config=live_config)

    live_dependencies.validate()

    outbox_repo = _TransactionalOutboxRelayRepository(live_dependencies)
    kafka_publisher = KafkaProducerPublisher(
        live_dependencies.kafka_producer,
        send_timeout_seconds=live_config.kafka_request_timeout_seconds,
    )

    relay = OutboxRelay(outbox_repo, kafka_publisher)
    outbox_worker = OutboxRelayWorker(
        relay,
        options=live_config.worker_loop_options(),
    )

    # 1. Checkout Event Listener
    from token_payments.contexts.checkout.adapter.kafka import CheckoutKafkaEventListener
    from token_payments.contexts.checkout.application import CheckoutProcessManager

    checkout_listener = _TransactionalListener(
        live_dependencies,
        lambda connection: CheckoutKafkaEventListener(
            process_manager=CheckoutProcessManager(),
            processed_messages=PostgresProcessedMessageRepository(connection),
            outbox_messages=PostgresOutboxMessageRepository(connection),
        )
    )
    checkout_consumer = LazyKafkaConsumerClient(
        bootstrap_servers=live_config.kafka_bootstrap_servers,
        client_id=live_config.kafka_client_id,
        group_id="checkout-process-manager",
        topics=("checkout.events", "order.events", "inventory.events", "payment.events", "store-approval.events"),
        request_timeout_ms=int(live_config.kafka_request_timeout_seconds * 1000),
    )
    checkout_worker = KafkaConsumerWorker(
        consumer=checkout_consumer,
        listener=checkout_listener,
        options=live_config.worker_loop_options(),
        name="checkout-process-manager",
    )

    # 2. Inventory Command Listener
    from token_payments.contexts.inventory.adapter.kafka import InventoryKafkaCommandListener
    from token_payments.contexts.inventory.application import InventoryCommandHandler

    inventory_listener = _TransactionalListener(
        live_dependencies,
        lambda connection: InventoryKafkaCommandListener(
            command_handler=InventoryCommandHandler(
                inventory_repository=PostgresInventoryRepository(connection),
                processed_commands=PostgresProcessedCommandRepository(connection),
                outbox_messages=PostgresOutboxMessageRepository(connection),
            ),
            processed_commands=PostgresProcessedCommandRepository(connection),
        )
    )
    inventory_consumer = LazyKafkaConsumerClient(
        bootstrap_servers=live_config.kafka_bootstrap_servers,
        client_id=live_config.kafka_client_id,
        group_id="inventory-command-listener",
        topics=("inventory.commands",),
        request_timeout_ms=int(live_config.kafka_request_timeout_seconds * 1000),
    )
    inventory_worker = KafkaConsumerWorker(
        consumer=inventory_consumer,
        listener=inventory_listener,
        options=live_config.worker_loop_options(),
        name="inventory-command-listener",
    )

    # 3. Payment Command Listener
    from token_payments.contexts.payment.adapter.kafka import PaymentKafkaCommandListener
    from token_payments.contexts.payment.application import PaymentCommandHandler
    from token_payments.contexts.payment.adapter.blockchain import ClientBlockchainAdapter
    from token_payments.contexts.payment.adapter.transaction_service import ClientTransactionService

    def payment_listener_factory(connection: Any) -> Any:
        blockchain = ClientBlockchainAdapter(
            live_dependencies.blockchain_client,
            default_buffer_rate=live_config.blockchain_gas_buffer_rate,
        )
        handler = PaymentCommandHandler(
            payment_repository=PostgresPaymentRepository(connection),
            authorization_repository=PostgresPaymentAuthorizationRepository(connection),
            processed_commands=PostgresProcessedCommandRepository(connection),
            outbox_messages=PostgresOutboxMessageRepository(connection),
            blockchain_adapter=blockchain,
            timeout_scheduler=_NoopPaymentTimeoutScheduler(),
            transaction_service=ClientTransactionService(live_dependencies.blockchain_client),
        )
        return PaymentKafkaCommandListener(
            command_handler=handler,
            processed_commands=PostgresProcessedCommandRepository(connection),
        )

    payment_listener = _TransactionalListener(live_dependencies, payment_listener_factory)
    payment_consumer = LazyKafkaConsumerClient(
        bootstrap_servers=live_config.kafka_bootstrap_servers,
        client_id=live_config.kafka_client_id,
        group_id="payment-command-listener",
        topics=("payment.commands",),
        request_timeout_ms=int(live_config.kafka_request_timeout_seconds * 1000),
    )
    payment_worker = KafkaConsumerWorker(
        consumer=payment_consumer,
        listener=payment_listener,
        options=live_config.worker_loop_options(),
        name="payment-command-listener",
    )

    # 4. Store Approval Command Listener
    from token_payments.contexts.store_approval.adapter.kafka import StoreApprovalKafkaCommandListener
    from token_payments.contexts.store_approval.application import StoreApprovalService

    store_approval_listener = _TransactionalListener(
        live_dependencies,
        lambda connection: StoreApprovalKafkaCommandListener(
            service=StoreApprovalService(
                store_repository=PostgresStoreRepository(connection),
                order_detail_repository=PostgresOrderRepository(connection),
                processed_commands=PostgresProcessedCommandRepository(connection),
                outbox_messages=PostgresOutboxMessageRepository(connection),
            ),
            processed_commands=PostgresProcessedCommandRepository(connection),
        )
    )
    store_approval_consumer = LazyKafkaConsumerClient(
        bootstrap_servers=live_config.kafka_bootstrap_servers,
        client_id=live_config.kafka_client_id,
        group_id="store-approval-command-listener",
        topics=("store-approval.commands",),
        request_timeout_ms=int(live_config.kafka_request_timeout_seconds * 1000),
    )
    store_approval_worker = KafkaConsumerWorker(
        consumer=store_approval_consumer,
        listener=store_approval_listener,
        options=live_config.worker_loop_options(),
        name="store-approval-command-listener",
    )

    # 5. Order Command Listener
    from token_payments.contexts.order.adapter.kafka import OrderKafkaCommandListener
    from token_payments.contexts.order.application import OrderCommandHandler

    order_command_listener = _TransactionalListener(
        live_dependencies,
        lambda connection: OrderKafkaCommandListener(
            command_handler=OrderCommandHandler(
                orders=PostgresOrderRepository(connection),
                processed_commands=PostgresProcessedCommandRepository(connection),
                outbox_messages=PostgresOutboxMessageRepository(connection),
            ),
            processed_commands=PostgresProcessedCommandRepository(connection),
        ),
    )
    order_command_consumer = LazyKafkaConsumerClient(
        bootstrap_servers=live_config.kafka_bootstrap_servers,
        client_id=live_config.kafka_client_id,
        group_id="order-command-listener",
        topics=("order.commands",),
        request_timeout_ms=int(live_config.kafka_request_timeout_seconds * 1000),
    )
    order_command_worker = KafkaConsumerWorker(
        consumer=order_command_consumer,
        listener=order_command_listener,
        options=live_config.worker_loop_options(),
        name="order-command-listener",
    )

    # 6. Order Status Event Listener
    from token_payments.contexts.order.adapter.kafka import OrderStatusKafkaEventListener
    from token_payments.contexts.order.application import OrderStatusEventProjector

    order_status_listener = _TransactionalListener(
        live_dependencies,
        lambda connection: OrderStatusKafkaEventListener(
            projector=OrderStatusEventProjector(
                orders=PostgresOrderRepository(connection),
                processed_messages=PostgresProcessedMessageRepository(connection),
            )
        ),
    )
    order_status_consumer = LazyKafkaConsumerClient(
        bootstrap_servers=live_config.kafka_bootstrap_servers,
        client_id=live_config.kafka_client_id,
        group_id="order-status-listener",
        topics=("payment.events", "store-approval.events"),
        request_timeout_ms=int(live_config.kafka_request_timeout_seconds * 1000),
    )
    order_status_worker = KafkaConsumerWorker(
        consumer=order_status_consumer,
        listener=order_status_listener,
        options=live_config.worker_loop_options(),
        name="order-status-listener",
    )

    # 7. Auth RBAC Listener
    from token_payments.contexts.auth.adapter import StoreMembershipProjectionKafkaListener
    from token_payments.contexts.auth.application import StoreMembershipProjectionConsumer

    auth_rbac_listener = _TransactionalListener(
        live_dependencies,
        lambda connection: StoreMembershipProjectionKafkaListener(
            StoreMembershipProjectionConsumer(
                repository=PostgresAuthRbacRepository(connection)
            )
        ),
    )
    auth_rbac_consumer = LazyKafkaConsumerClient(
        bootstrap_servers=live_config.kafka_bootstrap_servers,
        client_id=live_config.kafka_client_id,
        group_id="auth-rbac-projector",
        topics=("auth.rbac.projections",),
        request_timeout_ms=int(live_config.kafka_request_timeout_seconds * 1000),
    )
    auth_rbac_worker = KafkaConsumerWorker(
        consumer=auth_rbac_consumer,
        listener=auth_rbac_listener,
        options=live_config.worker_loop_options(),
        name="auth-rbac-projector",
    )

    receipt_polling_worker = PaymentReceiptPollingWorker(
        payment_repository=_TransactionalReceiptPollingRepository(live_dependencies),
        command_handler=_TransactionalPaymentCommandHandler(live_config, live_dependencies),
        clock=live_dependencies.clock,
        options=live_config.worker_loop_options(),
    )

    workers = [
        outbox_worker,
        checkout_worker,
        inventory_worker,
        payment_worker,
        store_approval_worker,
        order_command_worker,
        order_status_worker,
        auth_rbac_worker,
        receipt_polling_worker,
    ]
    return WorkerRuntime(workers)


__all__ = [
    "BlockchainClient",
    "BlockchainReadinessProbe",
    "EthAccountWalletSignatureClient",
    "KafkaProducerClient",
    "KafkaReadinessProbe",
    "LIVE_RUNTIME_DEPENDENCY_MISSING",
    "LIVE_RUNTIME_DRIVER_CONFIGURATION_INVALID",
    "JsonRpcBlockchainClient",
    "LazyKafkaProducerClient",
    "LiveApiComposition",
    "LiveApiFacades",
    "LiveRuntimeConfig",
    "LiveRuntimeDependencies",
    "LiveRuntimeDriverConfigurationError",
    "LiveRuntimeDependencyError",
    "LiveWorkerDescriptor",
    "PostgresReadinessProbe",
    "PostgresSessionFactory",
    "PsycopgPostgresSessionFactory",
    "REQUIRED_LIVE_DEPENDENCIES",
    "SystemClock",
    "UuidIdGenerator",
    "WalletSignatureClient",
    "build_live_api_facades",
    "build_live_api_router",
    "build_live_readiness_probes",
    "build_live_runtime_dependencies_from_env",
    "build_live_worker_runtime_from_env",
    "describe_live_worker_registry",
    "describe_live_runtime_dependencies",
    "live_worker_registry",
]

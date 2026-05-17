"""Live API runtime composition contracts without driver construction."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import inspect
import os
from typing import Any, Mapping, Protocol, Self
from urllib.parse import SplitResult, urlsplit, urlunsplit

from token_payments.contexts.auth.adapter import ClientWalletSignatureVerifier
from token_payments.contexts.auth.adapter import (
    PostgresAuthSessionRepository,
    PostgresLoginChallengeRepository,
    PostgresUserRepository,
)
from token_payments.contexts.auth.application import (
    AuthApplicationService,
    CurrentUserQuery,
    LoginWithMetaMaskCommand,
    LogoutCommand,
    RefreshSessionCommand,
    RequestLoginChallengeCommand,
)
from token_payments.contexts.auth.domain import AuthEvent, AuthSession, IssuedToken, User
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
from token_payments.shared.domain import (
    CommandId,
    CommandMetadata,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxMessageKind,
    PaymentId,
    ProcessedCommand,
)
from token_payments.shared.adapter.postgres import (
    PostgresOutboxMessageRepository,
    PostgresProcessedCommandRepository,
)

from .contracts import Clock, IdGenerator, JsonValue
from .observability import PostgresOperatorObservabilityQuery
from .security import (
    DEFAULT_CORS_ALLOWED_ORIGINS,
    DEFAULT_CSRF_ACTIVE_KEY_ID,
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
    request_body_max_bytes: int = DEFAULT_REQUEST_BODY_MAX_BYTES

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
        object.__setattr__(
            self,
            "request_body_max_bytes",
            _require_positive_int(self.request_body_max_bytes, "REQUEST_BODY_MAX_BYTES"),
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        source = os.environ if env is None else env
        runtime_environment = source.get("RUNTIME_ENVIRONMENT", "local")
        session_key_config = SessionKeyConfig.from_env(source, runtime_environment=runtime_environment)
        csrf_env = _csrf_env_with_session_fallback(source, session_key_config)
        csrf_config = CsrfTokenConfig.from_env(csrf_env, runtime_environment=runtime_environment)
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
            blockchain_rpc_url=source.get("ADAPTER_BLOCKCHAIN_RPC_URL", DEFAULT_BLOCKCHAIN_RPC_URL),
            blockchain_chain_id=_parse_int(
                source,
                "ADAPTER_BLOCKCHAIN_CHAIN_ID",
                DEFAULT_BLOCKCHAIN_CHAIN_ID,
            ),
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
            request_body_max_bytes=_parse_int(
                source,
                "REQUEST_BODY_MAX_BYTES",
                DEFAULT_REQUEST_BODY_MAX_BYTES,
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
                "cookieSecretsRedacted": True,
            },
            "security": {
                "csrf": {
                    "cookieName": "csrf_token",
                    "headerName": "X-CSRF-Token",
                    "activeKeyId": self.csrf_key_id,
                    "signingKeyConfigured": bool(self.csrf_signing_key),
                    "secretRedacted": True,
                    "maxAgeSeconds": self.csrf_max_age_seconds,
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
                    "producerInjectedExternally": True,
                },
                "walletSignature": {
                    "domain": self.wallet_signature_domain,
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
class LiveApiFacades:
    """Framework-neutral facade instances wired to live application services."""

    auth: Any
    orders: Any
    checkout: Any
    payments: Any
    operator: Any
    operator_action: Any


def register_auth_routes(router: Any, auth_api: Any, *, session_transport: Any | None = None) -> Any:
    from token_payments.api import register_auth_routes as _register_auth_routes

    return _register_auth_routes(router, auth_api, session_transport=session_transport)


def register_order_routes(router: Any, orders_api: Any) -> Any:
    from token_payments.api import register_order_routes as _register_order_routes

    return _register_order_routes(router, orders_api)


def register_checkout_routes(router: Any, checkout_api: Any) -> Any:
    from token_payments.api import register_checkout_routes as _register_checkout_routes

    return _register_checkout_routes(router, checkout_api)


def register_payment_routes(router: Any, payments_api: Any) -> Any:
    from token_payments.api import register_payment_routes as _register_payment_routes

    return _register_payment_routes(router, payments_api)


def register_operator_routes(router: Any, operator_api: Any) -> Any:
    from token_payments.api import register_operator_routes as _register_operator_routes

    return _register_operator_routes(router, operator_api)


def register_operator_action_routes(router: Any, operator_action_api: Any) -> Any:
    from token_payments.api import register_operator_action_routes as _register_operator_action_routes

    return _register_operator_action_routes(router, operator_action_api)


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
        OrdersApi,
        PaymentsApi,
    )

    live_config = config or LiveRuntimeConfig.from_env()
    live_dependencies = dependencies or LiveRuntimeDependencies()
    LiveApiComposition(config=live_config, dependencies=live_dependencies)

    payment_handler = _TransactionalPaymentCommandHandler(live_config, live_dependencies)
    order_command_handler = _TransactionalOrderCommandHandler(live_dependencies)
    outbox_action_port = _TransactionalOperatorOutboxActionPort(live_dependencies)

    return LiveApiFacades(
        auth=AuthApi(_TransactionalAuthUseCase(live_config, live_dependencies)),
        orders=OrdersApi(_TransactionalOrderUseCase(live_dependencies)),
        checkout=CheckoutApi(_TransactionalCheckoutTrackingQuery(live_dependencies)),
        payments=PaymentsApi(payment_handler),
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

    def loginWithMetaMask(self, command: LoginWithMetaMaskCommand):
        return _with_transaction(
            self._dependencies,
            lambda connection: self._service(connection).loginWithMetaMask(command),
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

    def _service(self, connection: Any) -> AuthApplicationService:
        return AuthApplicationService(
            clock=self._dependencies.clock,
            nonce_generator=self._dependencies.id_generator,
            user_id_generator=self._dependencies.id_generator,
            session_id_generator=self._dependencies.id_generator,
            users=PostgresUserRepository(connection),
            login_challenges=PostgresLoginChallengeRepository(connection),
            sessions=PostgresAuthSessionRepository(connection),
            signature_verifier=ClientWalletSignatureVerifier(self._dependencies.wallet_signature_client),
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
    def __init__(self, dependencies: LiveRuntimeDependencies) -> None:
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
        )
        return _with_transaction(
            self._dependencies,
            lambda connection: OrderApplicationService(
                customers=PostgresCustomerRepository(connection),
                stores=PostgresStoreRepository(connection),
                orders=PostgresOrderRepository(connection),
                outbox_messages=PostgresOutboxMessageRepository(connection),
            ).createOrder(command),
        )


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
        clock=clock,
    )


def _csrf_token_service(config: LiveRuntimeConfig, clock: Clock | Any | None = None) -> CsrfTokenService:
    return CsrfTokenService(
        signer=HmacCsrfTokenSigner(
            key_id=config.csrf_key_id,
            secret_provider=lambda: config.csrf_signing_key,
        ),
        cookie_settings=CsrfCookieSettings(max_age_seconds=config.csrf_max_age_seconds),
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

    def _token(self, *, user: User | None, session: AuthSession, rotation_version: int) -> IssuedToken:
        now = self._clock.now()
        user_id = user.user_id if user is not None else session.user_id
        role = user.role.value if user is not None else "CUSTOMER"
        access_expires_at = now + self._access_ttl
        refresh_expires_at = now + self._refresh_ttl
        base_claims = {
            "user_id": str(user_id),
            "session_id": str(session.session_id),
            "wallet_address": str(session.wallet),
            "role": role,
            "issued_at": now,
            "jti": "pending",
            "rotation_version": rotation_version,
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
    begin = getattr(session, "begin", None)
    if callable(begin):
        with begin() as transaction:
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
    return callback(session)


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


def _type_name(value: Any) -> str:
    return type(value).__name__


__all__ = [
    "BlockchainClient",
    "KafkaProducerClient",
    "LIVE_RUNTIME_DEPENDENCY_MISSING",
    "LiveApiComposition",
    "LiveApiFacades",
    "LiveRuntimeConfig",
    "LiveRuntimeDependencies",
    "LiveRuntimeDependencyError",
    "PostgresSessionFactory",
    "REQUIRED_LIVE_DEPENDENCIES",
    "WalletSignatureClient",
    "build_live_api_facades",
    "build_live_api_router",
    "describe_live_runtime_dependencies",
]

"""Live API runtime composition contracts without driver construction."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import os
from typing import Any, Mapping, Protocol, Self
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .contracts import Clock, IdGenerator, JsonValue


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "api_host", _require_text(self.api_host, "RUNTIME_API_HOST"))
        object.__setattr__(self, "api_port", _require_port(self.api_port, "RUNTIME_API_PORT"))
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

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        source = os.environ if env is None else env
        return cls(
            api_host=source.get("RUNTIME_API_HOST", "0.0.0.0"),
            api_port=_parse_int(source, "RUNTIME_API_PORT", 8000),
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
        )

    def to_redacted_dict(self) -> dict[str, JsonValue]:
        """Return JSON-safe configuration metadata without secrets or placeholder token addresses."""

        return {
            "api": {
                "host": self.api_host,
                "port": self.api_port,
                "requestTimeoutSeconds": self.request_timeout_seconds,
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


def _parse_csv(raw: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


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
    "LiveRuntimeConfig",
    "LiveRuntimeDependencies",
    "LiveRuntimeDependencyError",
    "PostgresSessionFactory",
    "REQUIRED_LIVE_DEPENDENCIES",
    "WalletSignatureClient",
    "describe_live_runtime_dependencies",
]

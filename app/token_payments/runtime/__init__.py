"""Runtime contracts for Token Payments API and worker entrypoints."""

from importlib import import_module as _import_module

from .composition import (
    LIVE_RUNTIME_DEPENDENCY_MISSING,
    REQUIRED_LIVE_DEPENDENCIES,
    BlockchainClient,
    KafkaProducerClient,
    LiveApiComposition,
    LiveApiFacades,
    LiveRuntimeConfig,
    LiveRuntimeDependencies,
    LiveRuntimeDependencyError,
    PostgresSessionFactory,
    WalletSignatureClient,
    build_live_api_facades,
    build_live_api_router,
    describe_live_runtime_dependencies,
)
from .config import RuntimeConfig
from .contracts import (
    Clock,
    CommandDispatchResult,
    CommandDispatchStatus,
    HealthState,
    HealthStatus,
    IdGenerator,
    JsonValue,
    RuntimeContainer,
    WorkerLoopOptions,
)
from .entrypoint import ContractRuntimeContainer, dispatch_runtime_command
from .observability import (
    OperatorDashboardQuery,
    OperatorErrorSnapshot,
    OperatorObservabilityQueryPort,
    OperatorObservabilitySnapshot,
    OperatorOrderSnapshot,
    OperatorOutboxSnapshot,
    OperatorPage,
    OperatorPaymentSnapshot,
    OperatorSortDirection,
    OperatorWorkerSnapshot,
    PostgresOperatorObservabilityQuery,
)
from .smoke import (
    AVAILABLE_SMOKE_SCENARIOS,
    SMOKE_CONTRACT,
    UNKNOWN_SMOKE_SCENARIO_ERROR,
    SmokeResult,
    SmokeScenarioResult,
    SmokeStatus,
    SmokeStep,
    UnknownSmokeScenario,
    describe_smoke_registry,
    run_smoke_scenario,
)
from .workers import (
    KafkaConsumerWorker,
    OutboxRelayWorker,
    PaymentReceiptPollingWorker,
    PaymentTimeoutCandidate,
    PaymentTimeoutWorker,
    WorkerBatchResult,
    WorkerRunSummary,
    WorkerRuntime,
)

__all__ = [
    "AVAILABLE_SMOKE_SCENARIOS",
    "BrowserPreviewHttpServer",
    "BrowserPreviewRequestHandler",
    "BlockchainClient",
    "Clock",
    "CommandDispatchResult",
    "CommandDispatchStatus",
    "ContractRuntimeContainer",
    "DEFAULT_BROWSER_PREVIEW_HOST",
    "DEFAULT_BROWSER_PREVIEW_PORT",
    "HealthState",
    "HealthStatus",
    "IdGenerator",
    "JsonValue",
    "KafkaConsumerWorker",
    "KafkaProducerClient",
    "LIVE_RUNTIME_DEPENDENCY_MISSING",
    "LiveApiComposition",
    "LiveApiFacades",
    "LiveRuntimeConfig",
    "LiveRuntimeDependencies",
    "LiveRuntimeDependencyError",
    "OperatorDashboardQuery",
    "OperatorErrorSnapshot",
    "OperatorObservabilityQueryPort",
    "OperatorObservabilitySnapshot",
    "OperatorOrderSnapshot",
    "OperatorOutboxSnapshot",
    "OperatorPage",
    "OperatorPaymentSnapshot",
    "OperatorSortDirection",
    "OperatorWorkerSnapshot",
    "OutboxRelayWorker",
    "PaymentReceiptPollingWorker",
    "PaymentTimeoutCandidate",
    "PaymentTimeoutWorker",
    "PostgresSessionFactory",
    "RuntimeConfig",
    "RuntimeContainer",
    "REQUIRED_LIVE_DEPENDENCIES",
    "SMOKE_CONTRACT",
    "SmokeResult",
    "SmokeScenarioResult",
    "SmokeStatus",
    "SmokeStep",
    "PostgresOperatorObservabilityQuery",
    "UNKNOWN_SMOKE_SCENARIO_ERROR",
    "UnknownSmokeScenario",
    "WalletSignatureClient",
    "WorkerBatchResult",
    "WorkerLoopOptions",
    "WorkerRunSummary",
    "WorkerRuntime",
    "build_browser_preview_server",
    "build_live_api_facades",
    "build_live_api_router",
    "describe_live_runtime_dependencies",
    "describe_smoke_registry",
    "dispatch_runtime_command",
    "render_browser_preview_document",
    "run_smoke_scenario",
    "serve_browser_preview",
]

_BROWSER_PREVIEW_EXPORTS = frozenset(
    {
        "DEFAULT_BROWSER_PREVIEW_HOST",
        "DEFAULT_BROWSER_PREVIEW_PORT",
        "BrowserPreviewHttpServer",
        "BrowserPreviewRequestHandler",
        "build_browser_preview_server",
        "render_browser_preview_document",
        "serve_browser_preview",
    }
)


def __getattr__(name: str):
    if name in _BROWSER_PREVIEW_EXPORTS:
        value = getattr(_import_module("token_payments.runtime.browser_preview"), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

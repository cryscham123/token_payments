from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.runtime import (  # noqa: E402
    HealthState,
    LiveRuntimeConfig,
    LiveRuntimeDependencies,
    ReadinessProbeResult,
    build_live_readiness_probes,
    build_live_system_router,
)


NOW = datetime(2026, 5, 17, 10, 0, tzinfo=UTC)


def test_healthz_reports_process_health_without_opening_dependency_probes() -> None:
    probe = FailingProbe("postgres")
    router = build_live_system_router(readiness_probes=(probe,))

    response = router.handle(
        "GET",
        "/healthz",
        headers={"X-Request-Id": "req-health", "Cookie": "access_token=secret-token"},
        received_at=NOW,
    )
    payload = _json(response.body)

    assert response.status_code == 200
    assert payload["state"] == "OK"
    assert payload["details"]["scope"] == "process"
    assert payload["details"]["externalConnectionsOpened"] is False
    assert probe.calls == 0
    assert "secret-token" not in json.dumps(payload, sort_keys=True)


def test_readyz_uses_postgres_kafka_and_blockchain_probe_wrappers() -> None:
    session = FakePostgresSession()
    kafka = FakeKafkaProducer(connected=True)
    blockchain = FakeBlockchainClient(chain_id=1337)
    dependencies = LiveRuntimeDependencies(
        postgres_session_factory=lambda: session,
        kafka_producer=kafka,
        wallet_signature_client=object(),
        blockchain_client=blockchain,
        clock=FakeClock(),
        id_generator=FakeIdGenerator(),
    )
    config = LiveRuntimeConfig(blockchain_chain_id=1337)
    probes = build_live_readiness_probes(config=config, dependencies=dependencies)
    router = build_live_system_router(readiness_probes=probes)

    response = router.handle("GET", "/readyz", headers={"X-Request-Id": "req-ready"}, received_at=NOW)
    payload = _json(response.body)

    assert response.status_code == 200
    assert payload["state"] == "OK"
    assert [component["component"] for component in payload["components"]] == ["postgres", "kafka", "blockchain"]
    assert session.statements == ["SELECT 1"]
    assert kafka.bootstrap_checks == 1
    assert blockchain.chain_id_calls == 1


def test_readyz_returns_503_with_bounded_redacted_component_errors() -> None:
    dependencies = LiveRuntimeDependencies(
        postgres_session_factory=lambda: ExplodingPostgresSession(),
        kafka_producer=FakeKafkaProducer(connected=False),
        wallet_signature_client=object(),
        blockchain_client=FakeBlockchainClient(chain_id=999),
        clock=FakeClock(),
        id_generator=FakeIdGenerator(),
    )
    config = LiveRuntimeConfig(blockchain_chain_id=1337)
    router = build_live_system_router(readiness_probes=build_live_readiness_probes(config=config, dependencies=dependencies))

    response = router.handle("GET", "/readyz", headers={"X-Request-Id": "req-ready-fail"}, received_at=NOW)
    payload = _json(response.body)
    encoded = json.dumps(payload, sort_keys=True)

    assert response.status_code == 503
    assert payload["state"] == "UNAVAILABLE"
    components = {component["component"]: component for component in payload["components"]}
    assert components["postgres"]["error"]["code"] == "POSTGRES_UNAVAILABLE"
    assert components["kafka"]["error"]["code"] == "KAFKA_UNAVAILABLE"
    assert components["blockchain"]["error"]["code"] == "BLOCKCHAIN_CHAIN_ID_MISMATCH"
    assert "super-secret-password" not in encoded
    assert "paid-rpc-token" not in encoded
    assert "<redacted>" in encoded


def test_access_log_and_direct_probe_results_redact_sensitive_payload_values() -> None:
    events: list[dict[str, Any]] = []
    router = build_live_system_router(access_log_sink=events.append)
    result = ReadinessProbeResult(
        component="postgres",
        state=HealthState.UNAVAILABLE,
        checked_at=NOW,
        details={"dsnPassword": "super-secret-password", "safe": "visible"},
        error_code="POSTGRES_UNAVAILABLE",
        message="password=super-secret-password token=paid-rpc-token",
    )

    response = router.handle(
        "GET",
        "/healthz",
        headers={
            "X-Request-Id": "req-log",
            "Cookie": "access_token=secret-token",
            "Authorization": "Bearer secret-token",
        },
        received_at=NOW,
    )
    encoded = json.dumps({"event": events[0], "result": result.to_dict()}, sort_keys=True)

    assert response.status_code == 200
    assert events[0]["pathTemplate"] == "/healthz"
    assert "secret-token" not in encoded
    assert "super-secret-password" not in encoded
    assert "paid-rpc-token" not in encoded
    assert result.to_dict()["details"]["dsnPassword"] == "<redacted>"
    assert result.to_dict()["error"]["message"].count("<redacted>") >= 2


def _json(body: bytes) -> dict[str, Any]:
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return decoded


class FakePostgresSession:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str, *_args: Any, **_kwargs: Any) -> list[tuple[int]]:
        self.statements.append(sql)
        return [(1,)]


class ExplodingPostgresSession:
    def execute(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("postgres password=super-secret-password is unavailable")


class FakeKafkaProducer:
    def __init__(self, *, connected: bool) -> None:
        self.connected = connected
        self.bootstrap_checks = 0

    def bootstrap_connected(self) -> bool:
        self.bootstrap_checks += 1
        return self.connected


class FakeBlockchainClient:
    def __init__(self, *, chain_id: int) -> None:
        self.chain_id = chain_id
        self.chain_id_calls = 0

    def get_chain_id(self) -> int:
        self.chain_id_calls += 1
        return self.chain_id


class FailingProbe:
    def __init__(self, component: str) -> None:
        self.component = component
        self.calls = 0

    def check(self) -> ReadinessProbeResult:
        self.calls += 1
        raise AssertionError(f"{self.component} probe must not be called")


class FakeClock:
    def now(self) -> datetime:
        return NOW


class FakeIdGenerator:
    def new_id(self) -> str:
        return "generated-id"

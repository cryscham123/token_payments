from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import pytest

from token_payments.runtime.composition import (
    LiveRuntimeConfig,
    LiveRuntimeDependencies,
    build_live_worker_runtime_from_env,
)
from token_payments.runtime.workers import OutboxRelayWorker, WorkerRuntime
from token_payments.shared.domain import (
    CheckoutEventName,
    EventMetadata,
    MessageId,
    OrderId,
    OutboxMessage,
    OutboxPublishStatus,
)


def test_build_live_worker_runtime_is_lazy_and_does_not_connect() -> None:
    with patch("importlib.import_module") as mock_import:
        config = LiveRuntimeConfig(
            postgres_dsn="postgresql://user:pass@host:5432/db",
            kafka_bootstrap_servers=("localhost:9092",),
            kafka_client_id="test-client",
        )
        # build_live_worker_runtime_from_env should construct the runtime without triggering connection imports
        runtime = build_live_worker_runtime_from_env(config=config)
        assert isinstance(runtime, WorkerRuntime)
        
        # OutboxRelayWorker should be wired
        outbox_workers = [w for w in runtime.workers if isinstance(w, OutboxRelayWorker)]
        assert len(outbox_workers) == 1
        
        # Verify that psycopg and kafka imports (which happen inside connection open paths) have not been called
        mock_import.assert_not_called()


def test_outbox_relay_failure_transitions_to_failed_with_error_summary() -> None:
    # Set up a mock database connection that fails or succeeds
    connection = MagicMock()
    # Mocking claim_ready_batch to return one outbox event message
    event_id = MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
    order_id = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
    message = OutboxMessage.record_event(
        metadata=EventMetadata(
            message_id=event_id,
            name=CheckoutEventName.ORDER_CREATED,
            aggregate_id=str(order_id),
            occurred_at=datetime.now(UTC),
            correlation_id=str(order_id),
            causation_id="api-req",
        ),
        topic="order.events",
        key=str(order_id),
        payload={"eventName": "OrderCreatedEvent", "orderId": str(order_id)},
    )
    from dataclasses import replace
    message = replace(message, status=OutboxPublishStatus.PUBLISHING)

    # Stub executing queries for claim, publish, mark
    # Let psycopg row factory return dict-like objects
    connection.execute.return_value.fetchall.return_value = []
    
    # We will verify that OutboxRelayWorker marks failed status if Kafka publish fails
    kafka_producer = MagicMock()
    kafka_producer.send.side_effect = Exception("Kafka connection timeout")

    postgres_factory = MagicMock(return_value=connection)

    dependencies = LiveRuntimeDependencies(
        postgres_session_factory=postgres_factory,
        kafka_producer=kafka_producer,
        wallet_signature_client=MagicMock(),
        blockchain_client=MagicMock(),
        clock=SystemClockStub(),
        id_generator=MagicMock(),
    )
    
    config = LiveRuntimeConfig(
        postgres_dsn="postgresql://user:pass@host:5432/db",
        kafka_bootstrap_servers=("localhost:9092",),
        kafka_client_id="test-client",
    )

    runtime = build_live_worker_runtime_from_env(config=config, dependencies=dependencies)
    outbox_worker = [w for w in runtime.workers if isinstance(w, OutboxRelayWorker)][0]

    # Directly run a batch with mocked repository return
    with patch.object(outbox_worker._relay._outbox_repository, "claim_ready_batch", return_value=(message,)):
        with patch.object(outbox_worker._relay._outbox_repository, "mark_failed") as mock_mark_failed:
            result = outbox_worker.run_once()
            assert result.processed == 1
            assert result.details["failed"] == 1
            mock_mark_failed.assert_called_once_with(
                message.kind, message.identity, "Kafka connection timeout"
            )


class SystemClockStub:
    def now(self) -> datetime:
        return datetime.now(UTC)

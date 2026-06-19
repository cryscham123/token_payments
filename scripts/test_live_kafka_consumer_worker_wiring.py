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
from token_payments.runtime.workers import KafkaConsumerWorker, PaymentReceiptPollingWorker, WorkerRuntime
from token_payments.shared.adapter.kafka import KafkaInboundMessage, MalformedKafkaMessage
from token_payments.shared.domain import (
    CheckoutCommandName,
    CheckoutEventName,
    CommandId,
    MessageId,
    OrderId,
)


def test_build_live_worker_runtime_wires_consumers_lazily() -> None:
    with patch("importlib.import_module") as mock_import:
        config = LiveRuntimeConfig(
            postgres_dsn="postgresql://user:pass@host:5432/db",
            kafka_bootstrap_servers=("localhost:9092",),
            kafka_client_id="test-client",
        )
        runtime = build_live_worker_runtime_from_env(config=config)
        assert isinstance(runtime, WorkerRuntime)

        # There should be 7 KafkaConsumerWorkers plus a receipt polling worker.
        consumers = [w for w in runtime.workers if isinstance(w, KafkaConsumerWorker)]
        assert len(consumers) == 7
        pollers = [w for w in runtime.workers if isinstance(w, PaymentReceiptPollingWorker)]
        assert len(pollers) == 1
        assert pollers[0].name == "payment-receipt-polling"

        # Verify names
        names = {w.name for w in consumers}
        expected_names = {
            "checkout-process-manager",
            "inventory-command-listener",
            "payment-command-listener",
            "store-approval-command-listener",
            "order-command-listener",
            "order-status-listener",
            "auth-rbac-projector",
        }
        assert names == expected_names

        # Verify no socket/import triggered
        mock_import.assert_not_called()


class KafkaRecordStub:
    def __init__(self, topic: str, key: bytes, value: bytes, headers: list = None) -> None:
        self.topic = topic
        self.key = key
        self.value = value
        self.headers = headers or []


def test_consumer_loop_commits_offset_only_on_success() -> None:
    # We will mock the underlying kafka-python consumer to return some records
    # and verify that commit() is called after listener successfully processes them,
    # but NOT if listener raises an exception.
    connection = MagicMock()
    postgres_factory = MagicMock(return_value=connection)
    
    mock_record = KafkaRecordStub(
        topic="checkout.events",
        key=b"order-123",
        value=b"invalid-json-payload",
        headers=[]
    )

    # Mock kafka-python imported inside the lazy client
    with patch("importlib.import_module") as mock_import:
        mock_kafka = MagicMock()
        mock_import.return_value = mock_kafka
        mock_consumer = MagicMock()
        mock_kafka.KafkaConsumer.return_value = mock_consumer
        
        # When next(mock_consumer) is called, return mock_record
        mock_consumer.__next__.side_effect = [mock_record]

        dependencies = LiveRuntimeDependencies(
            postgres_session_factory=postgres_factory,
            kafka_producer=MagicMock(),
            wallet_signature_client=MagicMock(),
            blockchain_client=MagicMock(),
            clock=SystemClockStub(),
            id_generator=MagicMock(),
        )
        
        config = LiveRuntimeConfig(
            postgres_dsn="postgresql://user:pass@host:5432/db",
            kafka_bootstrap_servers=("localhost:9092",),
            kafka_client_id="test-client",
            worker_batch_size=1,
        )

        runtime = build_live_worker_runtime_from_env(config=config, dependencies=dependencies)
        checkout_worker = [w for w in runtime.workers if w.name == "checkout-process-manager"][0]

        # Running once with corrupt payload should raise MalformedKafkaMessage
        with pytest.raises(MalformedKafkaMessage):
            checkout_worker.run_once()

        # Under the hood, commit should NOT be called on mock_consumer
        mock_consumer.commit.assert_not_called()


def test_consumer_loop_commits_offset_on_successful_message() -> None:
    connection = MagicMock()
    postgres_factory = MagicMock(return_value=connection)
    
    # Correct JSON payload
    payload = {
        "message_id": "msg-123",
        "command_id": "cmd-123",
        "name": "checkout.commands.create",
        "payload": {
            "order_id": "order-123",
            "merchant_id": "merchant-123",
            "amount": "100.00",
            "currency": "USDT",
        },
        "timestamp": "2026-05-22T00:00:00Z"
    }
    
    # We must support checkout-process-manager which processes checkout events/commands.
    # Wait, what are the headers for the message? Or is payload in value?
    mock_record = KafkaRecordStub(
        topic="checkout.commands",
        key=b"order-123",
        value=json.dumps(payload).encode("utf-8"),
        headers=[("message-id", b"msg-123")]
    )

    with patch("importlib.import_module") as mock_import:
        mock_kafka = MagicMock()
        mock_import.return_value = mock_kafka
        mock_consumer = MagicMock()
        mock_kafka.KafkaConsumer.return_value = mock_consumer
        
        mock_consumer.__next__.side_effect = [mock_record]

        # We also mock the listener's handle method because the real checkout-process-manager
        # requires actual db operations and domain objects setup.
        # But wait! We want to test the wrapping / composition behavior, i.e.,
        # that commit is called when the listener handles it successfully.
        # So we can patch the listener's handle method or mock the db transaction and handle.
        # Let's check how the listener is wired. In composition.py, it constructs the listener.
        # Can we patch the actual command handler or the listener?
        # Let's inspect composition.py or mock the db transaction to do nothing.
        # Let's check if we can run it with mocked dependencies so it succeeds without patching handler.
        # If the handler is called, it might need to query orders, write tables etc.
        # Alternatively, we can patch the handler/listener.
        
        dependencies = LiveRuntimeDependencies(
            postgres_session_factory=postgres_factory,
            kafka_producer=MagicMock(),
            wallet_signature_client=MagicMock(),
            blockchain_client=MagicMock(),
            clock=SystemClockStub(),
            id_generator=MagicMock(),
        )
        
        config = LiveRuntimeConfig(
            postgres_dsn="postgresql://user:pass@host:5432/db",
            kafka_bootstrap_servers=("localhost:9092",),
            kafka_client_id="test-client",
            worker_batch_size=1,
        )

        runtime = build_live_worker_runtime_from_env(config=config, dependencies=dependencies)
        checkout_worker = [w for w in runtime.workers if w.name == "checkout-process-manager"][0]
        
        # Let's mock the listener's handle to do nothing
        with patch.object(checkout_worker._loop._listener, "handle") as mock_handle:
            result = checkout_worker.run_once()
            assert result.processed == 1
            mock_handle.assert_called_once()
            
        mock_consumer.commit.assert_called_once()


class SystemClockStub:
    def now(self) -> datetime:
        return datetime.now(UTC)


def test_checkout_listener_filters_unsupported_events_without_db_interaction() -> None:
    postgres_factory = MagicMock()
    dependencies = LiveRuntimeDependencies(
        postgres_session_factory=postgres_factory,
        kafka_producer=MagicMock(),
        wallet_signature_client=MagicMock(),
        blockchain_client=MagicMock(),
        clock=SystemClockStub(),
        id_generator=MagicMock(),
    )
    
    config = LiveRuntimeConfig(
        postgres_dsn="postgresql://user:pass@host:5432/db",
        kafka_bootstrap_servers=("localhost:9092",),
        kafka_client_id="test-client",
        worker_batch_size=1,
    )

    runtime = build_live_worker_runtime_from_env(config=config, dependencies=dependencies)
    checkout_worker = [w for w in runtime.workers if w.name == "checkout-process-manager"][0]
    
    unsupported_payload = {
        "eventName": "PaymentProcessingStartedEvent",
        "orderId": "order-123",
        "paymentId": "payment-123",
    }
    mock_record = KafkaRecordStub(
        topic="payment.events",
        key=b"order-123",
        value=json.dumps(unsupported_payload).encode("utf-8"),
        headers=[("message-id", b"msg-123")]
    )

    with patch("importlib.import_module") as mock_import:
        mock_kafka = MagicMock()
        mock_import.return_value = mock_kafka
        mock_consumer = MagicMock()
        mock_kafka.KafkaConsumer.return_value = mock_consumer
        mock_consumer.__next__.side_effect = [mock_record]

        result = checkout_worker.run_once()
        assert result.processed == 1
        
        postgres_factory.assert_not_called()
        mock_consumer.commit.assert_called_once()


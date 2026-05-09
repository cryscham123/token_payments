from __future__ import annotations

import ast
import contextlib
import importlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.shared.domain import (  # noqa: E402
    CheckoutCommandName,
    CheckoutEventName,
    Crypto,
    EventMetadata,
    MessageId,
    OrderId,
    OutboxMessage,
    WalletAddress,
)


EXPECTED_ADAPTER_EXPORTS = {
    "DEFAULT_COMMAND_TOPICS",
    "DEFAULT_EVENT_TOPICS",
    "JsonMessageSerializer",
    "MessageTopicResolver",
    "RetryBackoffConfig",
    "TransactionBoundary",
    "TransactionalSession",
}

FORBIDDEN_ADAPTER_IMPORT_ROOTS = {
    "aiokafka",
    "blockchain",
    "confluent_kafka",
    "kafka",
    "metamask",
    "psycopg",
    "psycopg2",
    "requests",
    "sqlalchemy",
    "web3",
}


def test_shared_adapter_public_contracts_are_exported() -> None:
    shared_adapter = importlib.import_module("token_payments.shared.adapter")
    exported = set(getattr(shared_adapter, "__all__", ()))

    assert EXPECTED_ADAPTER_EXPORTS <= exported
    for name in EXPECTED_ADAPTER_EXPORTS:
        assert hasattr(shared_adapter, name), f"token_payments.shared.adapter must export {name}"


def test_json_message_serializer_produces_json_safe_outbox_envelope() -> None:
    from token_payments.shared.adapter import JsonMessageSerializer

    now = datetime(2026, 5, 10, 0, 12, tzinfo=UTC)
    order_id = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
    event = EventMetadata(
        message_id=MessageId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22"),
        name=CheckoutEventName.ORDER_CREATED,
        aggregate_id=str(order_id),
        occurred_at=now,
        correlation_id=str(order_id),
        causation_id="api-request-123",
    )
    outbox = OutboxMessage.record_event(
        metadata=event,
        topic="order.events",
        key=str(order_id),
        payload={
            "orderId": order_id,
            "total": Crypto(
                amount=Decimal("1.25"),
                symbol="eth",
                chain_id=1337,
                token_address=WalletAddress("0x0000000000000000000000000000000000000001"),
                decimals=18,
            ),
            "submittedAt": now,
            "attempt": 1,
        },
    )

    serializer = JsonMessageSerializer()
    raw = serializer.dumps(outbox)
    decoded = json.loads(raw)

    assert decoded == serializer.to_dict(outbox)
    assert decoded["kind"] == "EVENT"
    assert decoded["identity"] == str(event.message_id)
    assert decoded["name"] == "OrderCreatedEvent"
    assert decoded["payload"]["orderId"] == str(order_id)
    assert decoded["payload"]["total"] == {
        "amount": "1.25",
        "symbol": "ETH",
        "chain_id": 1337,
        "token_address": "0x0000000000000000000000000000000000000001",
        "decimals": 18,
    }
    assert decoded["payload"]["submittedAt"] == now.isoformat()
    assert serializer.loads(raw) == decoded


def test_topic_resolver_maps_checkout_events_and_commands() -> None:
    from token_payments.shared.adapter import MessageTopicResolver

    resolver = MessageTopicResolver.default()

    assert resolver.topic_for(CheckoutEventName.ORDER_CREATED) == "order.events"
    assert resolver.topic_for(CheckoutEventName.INVENTORY_RESERVED) == "inventory.events"
    assert resolver.topic_for(CheckoutEventName.PAYMENT_CONFIRMED) == "payment.events"
    assert resolver.topic_for(CheckoutEventName.PAYMENT_EXPIRED) == "payment.events"
    assert resolver.topic_for(CheckoutEventName.ORDER_REJECTED) == "store-approval.events"
    assert resolver.topic_for(CheckoutCommandName.RESERVE_INVENTORY) == "inventory.commands"
    assert resolver.topic_for(CheckoutCommandName.REFUND_PAYMENT) == "payment.commands"
    assert resolver.topic_for(CheckoutCommandName.CANCEL_ORDER) == "order.commands"
    assert resolver.topic_for("RequestStoreApprovalCommand") == "store-approval.commands"

    with pytest.raises(ValueError):
        resolver.topic_for("UnknownCheckoutMessage")


def test_transaction_boundary_contracts_are_protocols() -> None:
    from token_payments.shared.adapter import TransactionBoundary, TransactionalSession

    assert getattr(TransactionBoundary, "_is_protocol", False)
    assert getattr(TransactionalSession, "_is_protocol", False)

    @dataclass
    class FakeTransaction:
        committed: bool = False
        rolled_back: bool = False

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

    class FakeSession:
        def __init__(self) -> None:
            self.transaction = FakeTransaction()

        @contextlib.contextmanager
        def begin(self):
            yield self.transaction

    session = FakeSession()
    assert isinstance(session.transaction, TransactionBoundary)
    assert isinstance(session, TransactionalSession)

    with session.begin() as transaction:
        transaction.commit()

    assert session.transaction.committed is True
    assert session.transaction.rolled_back is False


def test_retry_backoff_configuration_is_bounded_and_validated() -> None:
    from token_payments.shared.adapter import RetryBackoffConfig

    config = RetryBackoffConfig(
        max_attempts=5,
        initial_delay_seconds=0.5,
        multiplier=2,
        max_delay_seconds=2,
    )

    assert [config.delay_for_attempt(attempt) for attempt in range(1, 6)] == [0.5, 1.0, 2.0, 2.0, 2.0]
    assert config.should_retry(failure_count=0) is True
    assert config.should_retry(failure_count=4) is True
    assert config.should_retry(failure_count=5) is False

    with pytest.raises(ValueError):
        RetryBackoffConfig(max_attempts=0)
    with pytest.raises(ValueError):
        config.delay_for_attempt(0)


def test_postgres_schema_declares_minimum_adapter_tables_and_indexes() -> None:
    schema_path = ROOT / "app/postgres/init.d/001-token-payments-schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    normalized = sql.lower()

    assert schema_path.name.startswith("001-")
    assert "\\connect" not in normalized
    assert "\\i" not in normalized

    for table_name in (
        "outbox_messages",
        "processed_messages",
        "processed_commands",
        "product_inventory",
        "inventory_reservations",
        "payments",
        "payment_authorizations",
        "store_approval_order_details",
    ):
        assert f"create table if not exists {table_name}" in normalized

    for phrase in (
        "jsonb",
        "timestamptz",
        "create index if not exists",
        "unique",
        "check (status in",
    ):
        assert phrase in normalized


def test_adapter_env_keys_are_documented_without_secrets() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    for key in (
        "ADAPTER_POSTGRES_DSN=",
        "ADAPTER_KAFKA_BOOTSTRAP_SERVERS=",
        "ADAPTER_OUTBOX_BATCH_SIZE=",
        "ADAPTER_OUTBOX_RETRY_MAX_ATTEMPTS=",
        "ADAPTER_OUTBOX_RETRY_INITIAL_DELAY_SECONDS=",
        "ADAPTER_OUTBOX_RETRY_MAX_DELAY_SECONDS=",
    ):
        assert key in env_example

    assert (
        "ADAPTER_POSTGRES_DSN=postgresql://token_payments:"
        "replace_with_local_dev_only_password@postgres:5432/token_payments"
    ) in env_example


def test_domain_and_application_layers_do_not_import_external_adapter_dependencies() -> None:
    violations: dict[str, list[str]] = {}
    for path in sorted((ROOT / "app/token_payments").rglob("*.py")):
        if not _is_domain_or_application_path(path):
            continue

        illegal = sorted(module for module in _imported_modules(path) if _is_forbidden_dependency(module))
        if illegal:
            violations[str(path.relative_to(ROOT))] = illegal

    assert violations == {}


def _is_domain_or_application_path(path: Path) -> bool:
    return any(parent.name in {"domain", "application"} for parent in path.parents)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _is_forbidden_dependency(module_name: str) -> bool:
    parts = module_name.split(".")
    return parts[0] in FORBIDDEN_ADAPTER_IMPORT_ROOTS or "adapter" in parts

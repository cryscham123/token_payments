from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.adapter import ClientWalletSignatureVerifier  # noqa: E402
from token_payments.contexts.payment.adapter.blockchain import ClientBlockchainAdapter  # noqa: E402
from token_payments.contexts.payment.adapter.transaction_service import (  # noqa: E402
    ClientTransactionService,
)
from token_payments.shared.adapter import OutboxRelay, RetryBackoffConfig  # noqa: E402
from token_payments.shared.adapter.kafka import (  # noqa: E402
    KafkaConsumerLoop,
    KafkaOutboundMessage,
    KafkaProducerPublisher,
    KafkaRecordListener,
)
from token_payments.shared.adapter.postgres import (  # noqa: E402
    PostgresConnection,
    PostgresOutboxMessageRepository,
    PostgresProcessedCommandRepository,
    PostgresProcessedMessageRepository,
)


def test_adapter_infrastructure_public_exports_are_importable() -> None:
    import token_payments.contexts.auth.adapter as auth_adapter
    import token_payments.shared.adapter as shared_adapter
    import token_payments.shared.adapter.kafka as kafka_adapter
    import token_payments.shared.adapter.postgres as postgres_adapter

    assert {
        "JsonMessageSerializer",
        "MessageTopicResolver",
        "OutboxRelay",
        "RetryBackoffConfig",
        "TransactionBoundary",
        "TransactionalSession",
    } <= set(shared_adapter.__all__)
    assert {
        "KafkaConsumerLoop",
        "KafkaOutboundMessage",
        "KafkaProducerPublisher",
        "KafkaRecordListener",
    } <= set(kafka_adapter.__all__)
    assert {
        "PostgresConnection",
        "PostgresOutboxMessageRepository",
        "PostgresProcessedCommandRepository",
        "PostgresProcessedMessageRepository",
    } <= set(postgres_adapter.__all__)
    assert "ClientWalletSignatureVerifier" in auth_adapter.__all__

    for contract in (
        ClientWalletSignatureVerifier,
        ClientBlockchainAdapter,
        ClientTransactionService,
        KafkaConsumerLoop,
        KafkaOutboundMessage,
        KafkaProducerPublisher,
        OutboxRelay,
        RetryBackoffConfig,
    ):
        assert callable(contract)
    assert getattr(KafkaRecordListener, "_is_protocol", False)
    assert getattr(PostgresConnection, "_is_protocol", False)


def test_repository_and_message_adapters_expose_expected_contract_methods() -> None:
    for method_name in ("save", "claim_ready_batch", "mark_published", "mark_failed"):
        assert hasattr(PostgresOutboxMessageRepository, method_name)

    for repository in (PostgresProcessedCommandRepository, PostgresProcessedMessageRepository):
        assert hasattr(repository, "was_processed")
        assert hasattr(repository, "record")

    assert hasattr(ClientBlockchainAdapter, "estimate_gas")
    assert hasattr(ClientBlockchainAdapter, "get_transaction_receipt")
    assert hasattr(ClientTransactionService, "create_signature_request")
    assert hasattr(ClientTransactionService, "refund_payment")
    assert hasattr(ClientWalletSignatureVerifier, "recover_address")


def test_domain_and_application_layers_do_not_import_adapter_infrastructure() -> None:
    forbidden_external_roots = {
        "confluent_kafka",
        "kafka",
        "psycopg",
        "requests",
        "sqlalchemy",
        "web3",
    }
    scanned_roots = [
        ROOT / "app/token_payments/shared/domain",
        *sorted((ROOT / "app/token_payments/contexts").glob("*/domain")),
        *sorted((ROOT / "app/token_payments/contexts").glob("*/application")),
    ]

    for root in scanned_roots:
        for path in root.glob("**/*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots = {alias.name.split(".")[0] for alias in node.names}
                    assert imported_roots.isdisjoint(forbidden_external_roots), path
                elif isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                    assert module.split(".")[0] not in forbidden_external_roots, path
                    assert not module.startswith("token_payments.shared.adapter"), path
                    assert ".adapter" not in module, path


def test_env_compose_and_postgres_schema_cover_adapter_infrastructure() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    schema = (ROOT / "app/postgres/init.d/001-token-payments-schema.sql").read_text(encoding="utf-8")

    for key in (
        "ADAPTER_POSTGRES_DSN=",
        "ADAPTER_KAFKA_BOOTSTRAP_SERVERS=kafka:9092",
        "ADAPTER_KAFKA_CLIENT_ID=",
        "ADAPTER_OUTBOX_BATCH_SIZE=",
        "ADAPTER_WALLET_SIGNATURE_DOMAIN=",
        "ADAPTER_BLOCKCHAIN_RPC_URL=http://localhost:8545",
        "ADAPTER_BLOCKCHAIN_CHAIN_ID=1337",
    ):
        assert key in env_example

    for service in ("postgres:", "kafka:", "kafka-ui:", "test_network:"):
        assert service in compose

    for table in (
        "outbox_messages",
        "processed_messages",
        "processed_commands",
        "product_inventory",
        "inventory_reservations",
        "payments",
        "payment_authorizations",
        "store_approval_order_details",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema

    assert "ADAPTER_BLOCKCHAIN_PRIVATE_KEY" not in env_example
    assert "ADAPTER_BLOCKCHAIN_SEED_PHRASE" not in env_example

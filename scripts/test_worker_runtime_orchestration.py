from __future__ import annotations

import ast
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.payment.application import (  # noqa: E402
    ConfirmPaymentReceiptCommand,
    ExpireAwaitingSignatureCommand,
)
from token_payments.contexts.payment.domain import (  # noqa: E402
    GasEstimate,
    Payment,
    PaymentAuthorization,
    PaymentStatus,
    TransactionReceipt,
    TransactionSignatureRequest,
)
from token_payments.runtime import (  # noqa: E402
    CommandDispatchStatus,
    ContractRuntimeContainer,
    WorkerLoopOptions,
)
from token_payments.runtime.workers import (  # noqa: E402
    KafkaConsumerWorker,
    OutboxRelayWorker,
    PaymentReceiptPollingWorker,
    PaymentTimeoutCandidate,
    PaymentTimeoutWorker,
    WorkerBatchResult,
    WorkerRuntime,
)
from token_payments.shared.adapter.outbox_relay import OutboxRelayResult  # noqa: E402
from token_payments.shared.domain import (  # noqa: E402
    ChainNetwork,
    CommandId,
    Crypto,
    CustomerId,
    OrderId,
    PaymentId,
    TransactionHash,
    UserId,
    WalletAddress,
)


NOW = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
CHECKED_AT = NOW + timedelta(minutes=3)
EXPIRES_AT = NOW + timedelta(minutes=15)
EXPIRED_AT = EXPIRES_AT + timedelta(seconds=1)
ORDER_ID = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c21")
ORDER_ID_2 = OrderId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c22")
PAYMENT_ID = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c23")
PAYMENT_ID_2 = PaymentId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c24")
CUSTOMER_ID = CustomerId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c25")
USER_ID = UserId("018f33aa-9e6d-73d8-9dc3-47d6cdcc6c26")
WALLET_FROM = WalletAddress("0x1111111111111111111111111111111111111111")
WALLET_TO = WalletAddress("0x2222222222222222222222222222222222222222")
TOKEN_ADDRESS = WalletAddress("0x3333333333333333333333333333333333333333")
CHAIN = ChainNetwork(chain_id=11155111, name="Sepolia")
TX_HASH = TransactionHash("0x" + "ab" * 32)
TX_HASH_2 = TransactionHash("0x" + "cd" * 32)


def test_outbox_relay_worker_runs_bounded_batches_until_idle() -> None:
    relay = FakeOutboxRelay(
        results=[
            OutboxRelayResult(claimed=2, published=2, failed=0),
            OutboxRelayResult(claimed=1, published=0, failed=1),
            OutboxRelayResult(claimed=0, published=0, failed=0),
        ]
    )
    worker = OutboxRelayWorker(
        relay,
        options=WorkerLoopOptions(batch_size=2, poll_interval_seconds=0.1, receipt_poll_interval_seconds=1),
    )

    result = worker.run_until_idle(max_batches=5)

    assert relay.limits == [2, 2, 2]
    assert result.batches == 3
    assert result.processed == 3
    assert [batch.processed for batch in result.results] == [2, 1, 0]
    assert result.results[1].details["failed"] == 1
    assert result.idle is True


def test_kafka_consumer_worker_dispatches_records_and_commits_bounded_batch() -> None:
    records = [
        FakeKafkaRecord(topic="payment.events", key=str(ORDER_ID), value={"eventName": "PaymentConfirmedEvent"}),
        FakeKafkaRecord(topic="inventory.commands", key=str(ORDER_ID), value={"commandName": "ReserveInventoryCommand"}),
        FakeKafkaRecord(topic="store-approval.commands", key=str(ORDER_ID), value={"commandName": "RequestStoreApprovalCommand"}),
    ]
    consumer = FakeKafkaConsumer(records)
    listener = FakeKafkaListener()
    worker = KafkaConsumerWorker(
        consumer,
        listener,
        options=WorkerLoopOptions(batch_size=2, poll_interval_seconds=0.1, receipt_poll_interval_seconds=1),
    )

    first = worker.run_once()
    second = worker.run_once()

    assert first.processed == 2
    assert second.processed == 1
    assert [message.topic for message in listener.messages] == [
        "payment.events",
        "inventory.commands",
        "store-approval.commands",
    ]
    assert consumer.commit_count == 3


def test_payment_receipt_polling_worker_dispatches_confirm_commands_for_submitted_and_confirming_only() -> None:
    submitted = _awaiting_payment(payment_id=PAYMENT_ID, order_id=ORDER_ID).submit_tx_hash(TX_HASH)
    confirming = replace(
        _awaiting_payment(payment_id=PAYMENT_ID_2, order_id=ORDER_ID_2).submit_tx_hash(TX_HASH_2),
        status=PaymentStatus.CONFIRMING,
    )
    repository = FakeReceiptPollingRepository(
        [
            submitted,
            confirming,
            _awaiting_payment(),
            _confirmed_payment(),
        ]
    )
    handler = FakePaymentCommandHandler()
    worker = PaymentReceiptPollingWorker(
        payment_repository=repository,
        command_handler=handler,
        clock=FakeClock(CHECKED_AT),
        options=WorkerLoopOptions(batch_size=10, poll_interval_seconds=0.1, receipt_poll_interval_seconds=1),
    )

    result = worker.run_once()

    assert repository.limits == [10]
    assert result.processed == 2
    assert result.details["candidates"] == 4
    assert result.details["skipped"] == 2
    assert [command.payment_id for command in handler.confirm_calls] == [PAYMENT_ID, PAYMENT_ID_2]
    assert [command.order_id for command in handler.confirm_calls] == [ORDER_ID, ORDER_ID_2]
    assert [command.command_id for command in handler.confirm_calls] == [
        CommandId(f"{ORDER_ID}:ConfirmPaymentReceiptCommand:{PAYMENT_ID}:{TX_HASH}:{CHECKED_AT.isoformat()}"),
        CommandId(f"{ORDER_ID_2}:ConfirmPaymentReceiptCommand:{PAYMENT_ID_2}:{TX_HASH_2}:{CHECKED_AT.isoformat()}"),
    ]
    assert all(command.checked_at == CHECKED_AT for command in handler.confirm_calls)
    assert all(command.failure_reason == "receipt not confirmed" for command in handler.confirm_calls)


def test_payment_receipt_polling_worker_uses_attempt_specific_command_ids_for_retries() -> None:
    submitted = _awaiting_payment(payment_id=PAYMENT_ID, order_id=ORDER_ID).submit_tx_hash(TX_HASH)
    repository = FakeReceiptPollingRepository([submitted])
    handler = FakePaymentCommandHandler()
    first_checked_at = CHECKED_AT
    second_checked_at = CHECKED_AT + timedelta(seconds=5)
    worker = PaymentReceiptPollingWorker(
        payment_repository=repository,
        command_handler=handler,
        clock=SequenceClock([first_checked_at, second_checked_at]),
        options=WorkerLoopOptions(batch_size=10, poll_interval_seconds=0.1, receipt_poll_interval_seconds=1),
    )

    first = worker.run_once()
    second = worker.run_once()

    assert first.processed == 1
    assert second.processed == 1
    assert [command.command_id for command in handler.confirm_calls] == [
        CommandId(f"{ORDER_ID}:ConfirmPaymentReceiptCommand:{PAYMENT_ID}:{TX_HASH}:{first_checked_at.isoformat()}"),
        CommandId(f"{ORDER_ID}:ConfirmPaymentReceiptCommand:{PAYMENT_ID}:{TX_HASH}:{second_checked_at.isoformat()}"),
    ]


def test_payment_timeout_worker_dispatches_expire_only_for_expired_awaiting_signature_authorizations() -> None:
    expired_payment = _awaiting_payment(payment_id=PAYMENT_ID, order_id=ORDER_ID, expires_at=EXPIRES_AT)
    not_yet_expired = _awaiting_payment(
        payment_id=PAYMENT_ID_2,
        order_id=ORDER_ID_2,
        expires_at=EXPIRED_AT + timedelta(minutes=1),
    )
    submitted = expired_payment.submit_tx_hash(TX_HASH)
    requested_auth = _requested_authorization(payment_id=PAYMENT_ID, expires_at=EXPIRES_AT)
    authorized_auth = requested_auth.authorize_tx_hash(TX_HASH, authorized_at=NOW)
    repository = FakeTimeoutRepository(
        [
            PaymentTimeoutCandidate(payment=expired_payment, authorization=requested_auth),
            PaymentTimeoutCandidate(payment=not_yet_expired, authorization=_requested_authorization(PAYMENT_ID_2)),
            PaymentTimeoutCandidate(payment=submitted, authorization=requested_auth),
            PaymentTimeoutCandidate(payment=expired_payment, authorization=authorized_auth),
        ]
    )
    handler = FakePaymentCommandHandler()
    worker = PaymentTimeoutWorker(
        timeout_repository=repository,
        command_handler=handler,
        clock=FakeClock(EXPIRED_AT),
        options=WorkerLoopOptions(batch_size=20, poll_interval_seconds=0.1, receipt_poll_interval_seconds=1),
    )

    result = worker.run_once()

    assert repository.calls == [{"now": EXPIRED_AT, "limit": 20}]
    assert result.processed == 1
    assert result.details["candidates"] == 4
    assert result.details["skipped"] == 3
    assert len(handler.expire_calls) == 1
    command = handler.expire_calls[0]
    assert isinstance(command, ExpireAwaitingSignatureCommand)
    assert command.command_id == CommandId(f"{ORDER_ID}:ExpireAwaitingSignatureCommand")
    assert command.payment_id == PAYMENT_ID
    assert command.order_id == ORDER_ID
    assert command.expired_at == EXPIRED_AT
    assert command.reason == "signature expired"


def test_worker_runtime_runs_workers_until_idle_and_honors_graceful_stop() -> None:
    first = FakeRuntimeWorker("first", processed=[1, 0])
    second = FakeRuntimeWorker("second", processed=[0, 0])
    runtime = WorkerRuntime([first, second])

    result = runtime.run_until_idle(max_batches=3)

    assert result.batches == 2
    assert result.processed == 1
    assert [batch.worker for batch in result.results] == ["first", "second", "first", "second"]
    assert first.run_count == 2
    assert second.run_count == 2

    runtime.request_stop()
    stopped = runtime.run_once()

    assert stopped.stopped is True
    assert stopped.processed == 0
    assert first.stop_requested is True
    assert second.stop_requested is True
    assert first.run_count == 2
    assert second.run_count == 2


def test_worker_command_entrypoint_builds_runtime_without_live_infrastructure() -> None:
    runtime = WorkerRuntime([FakeRuntimeWorker("relay", processed=[2])])
    captured_options: list[WorkerLoopOptions] = []

    def build_worker_runtime(options: WorkerLoopOptions) -> WorkerRuntime:
        captured_options.append(options)
        return runtime

    container = ContractRuntimeContainer(worker_runtime_factory=build_worker_runtime)

    result = container.dispatch_command("worker")

    assert result.status is CommandDispatchStatus.SUCCEEDED
    assert result.command == "worker"
    assert result.details["worker"]["processed"] == 2
    assert captured_options == [container.config.worker_loop_options()]


def test_worker_runtime_does_not_import_harness_or_phase_runner() -> None:
    tree = ast.parse((ROOT / "app/token_payments/runtime/workers.py").read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert "scripts.execute" not in imported_modules
    assert all(not module.startswith("phases") for module in imported_modules)


def _amount() -> Crypto:
    return Crypto(
        amount=Decimal("1.25"),
        symbol="USDC",
        chain_id=CHAIN.chain_id,
        token_address=TOKEN_ADDRESS,
        decimals=6,
    )


def _gas_estimate() -> GasEstimate:
    return GasEstimate(
        estimated_fee=Crypto(
            amount=Decimal("0.01"),
            symbol="ETH",
            chain_id=CHAIN.chain_id,
            token_address=None,
            decimals=18,
        ),
        gas_limit=21_000,
        buffer_rate=Decimal("0.1"),
    )


def _awaiting_payment(
    payment_id: PaymentId = PAYMENT_ID,
    order_id: OrderId = ORDER_ID,
    expires_at: datetime = EXPIRES_AT,
) -> Payment:
    return Payment.initialize_payment(
        payment_id=payment_id,
        order_id=order_id,
        customer_id=CUSTOMER_ID,
        amount=_amount(),
        wallet_from=WALLET_FROM,
        wallet_to=WALLET_TO,
        chain_network=CHAIN,
        gas_estimate=_gas_estimate(),
        expires_at=expires_at,
        status=PaymentStatus.AWAITING_SIGNATURE,
    )


def _confirmed_payment() -> Payment:
    return _awaiting_payment().submit_tx_hash(TX_HASH).confirm_payment(
        TransactionReceipt(hash=TX_HASH, block_number=12345, gas_used=21_000)
    )


def _requested_authorization(
    payment_id: PaymentId = PAYMENT_ID,
    expires_at: datetime = EXPIRES_AT,
) -> PaymentAuthorization:
    return PaymentAuthorization.request_transaction_signature(
        payment_id=payment_id,
        user_id=USER_ID,
        wallet=WALLET_FROM,
        chain_network=CHAIN,
        signature_request=TransactionSignatureRequest(
            request_id=f"request-{payment_id}",
            amount=_amount(),
            to=WALLET_TO,
            expires_at=expires_at,
        ),
    )


class FakeOutboxRelay:
    def __init__(self, results: list[OutboxRelayResult]) -> None:
        self._results = list(results)
        self.limits: list[int] = []

    def publish_batch(self, *, limit: int) -> OutboxRelayResult:
        self.limits.append(limit)
        if self._results:
            return self._results.pop(0)
        return OutboxRelayResult(claimed=0, published=0, failed=0)


class FakeKafkaRecord:
    def __init__(self, *, topic: str, key: str, value: dict[str, Any]) -> None:
        self.topic = topic
        self.key = key
        self.value = json.dumps(value)
        self.headers = {"message_id": "018f33aa-9e6d-73d8-9dc3-47d6cdcc6c27"}


class FakeKafkaConsumer:
    def __init__(self, records: list[FakeKafkaRecord]) -> None:
        self._records = records
        self._offset = 0
        self.commit_count = 0

    def __iter__(self) -> FakeKafkaConsumer:
        return self

    def __next__(self) -> FakeKafkaRecord:
        if self._offset >= len(self._records):
            raise StopIteration
        record = self._records[self._offset]
        self._offset += 1
        return record

    def commit(self) -> None:
        self.commit_count += 1


class FakeKafkaListener:
    def __init__(self) -> None:
        self.messages: list[Any] = []

    def handle(self, message: Any) -> object:
        self.messages.append(message)
        return None


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class SequenceClock:
    def __init__(self, values: list[datetime]) -> None:
        self._values = list(values)

    def now(self) -> datetime:
        if not self._values:
            raise AssertionError("SequenceClock exhausted")
        return self._values.pop(0)


class FakeReceiptPollingRepository:
    def __init__(self, payments: list[Payment]) -> None:
        self._payments = payments
        self.limits: list[int] = []

    def list_receipt_polling_candidates(self, *, limit: int) -> tuple[Payment, ...]:
        self.limits.append(limit)
        return tuple(self._payments[:limit])


class FakeTimeoutRepository:
    def __init__(self, candidates: list[PaymentTimeoutCandidate]) -> None:
        self._candidates = candidates
        self.calls: list[dict[str, object]] = []

    def list_expired_awaiting_signature(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> tuple[PaymentTimeoutCandidate, ...]:
        self.calls.append({"now": now, "limit": limit})
        return tuple(self._candidates[:limit])


class FakePaymentCommandHandler:
    def __init__(self) -> None:
        self.confirm_calls: list[ConfirmPaymentReceiptCommand] = []
        self.expire_calls: list[ExpireAwaitingSignatureCommand] = []

    def confirm_payment_receipt(self, command: ConfirmPaymentReceiptCommand) -> object:
        self.confirm_calls.append(command)
        return object()

    def expire_awaiting_signature(self, command: ExpireAwaitingSignatureCommand) -> object:
        self.expire_calls.append(command)
        return object()


class FakeRuntimeWorker:
    def __init__(self, name: str, processed: list[int]) -> None:
        self.name = name
        self._processed = list(processed)
        self.run_count = 0
        self.stop_requested = False

    def run_once(self) -> WorkerBatchResult:
        processed = self._processed.pop(0) if self._processed else 0
        self.run_count += 1
        return WorkerBatchResult(worker=self.name, processed=processed)

    def request_stop(self) -> None:
        self.stop_requested = True

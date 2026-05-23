"""Bounded worker runtime orchestration for outbox, Kafka, and payment jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from token_payments.contexts.payment.application import (
    ConfirmPaymentReceiptCommand,
    ExpireAwaitingSignatureCommand,
)
from token_payments.contexts.payment.domain import AuthorizationStatus, Payment, PaymentAuthorization, PaymentStatus
from token_payments.shared.adapter.kafka import KafkaConsumerLoop, KafkaRecordListener
from token_payments.shared.adapter.outbox_relay import OutboxRelayResult
from token_payments.shared.domain import CommandId

from .contracts import Clock, WorkerLoopOptions


class OutboxRelayBatchPublisher(Protocol):
    def publish_batch(self, *, limit: int) -> OutboxRelayResult:
        ...


class ReceiptPollingRepository(Protocol):
    def list_receipt_polling_candidates(self, *, limit: int) -> Sequence[Payment]:
        ...


class PaymentTimeoutRepository(Protocol):
    def list_expired_awaiting_signature(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> Sequence["PaymentTimeoutCandidate"]:
        ...


class PaymentReceiptCommandHandler(Protocol):
    def confirm_payment_receipt(self, command: ConfirmPaymentReceiptCommand) -> object:
        ...


class PaymentTimeoutCommandHandler(Protocol):
    def expire_awaiting_signature(self, command: ExpireAwaitingSignatureCommand) -> object:
        ...


class RuntimeWorker(Protocol):
    @property
    def name(self) -> str:
        ...

    def run_once(self) -> "WorkerBatchResult":
        ...

    def request_stop(self) -> None:
        ...


@dataclass(frozen=True)
class WorkerBatchResult:
    worker: str
    processed: int
    details: Mapping[str, Any] = field(default_factory=dict)
    stopped: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "worker", _require_text(self.worker, "WorkerBatchResult.worker"))
        if isinstance(self.processed, bool) or not isinstance(self.processed, int) or self.processed < 0:
            raise ValueError("WorkerBatchResult.processed must be a non-negative integer")
        if not isinstance(self.details, Mapping):
            raise ValueError("WorkerBatchResult.details must be a mapping")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    @property
    def idle(self) -> bool:
        return self.processed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker": self.worker,
            "processed": self.processed,
            "details": dict(self.details),
            "stopped": self.stopped,
        }


@dataclass(frozen=True)
class WorkerRunSummary:
    batches: int
    processed: int
    results: tuple[WorkerBatchResult, ...] = ()
    stopped: bool = False
    idle: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.batches, bool) or not isinstance(self.batches, int) or self.batches < 0:
            raise ValueError("WorkerRunSummary.batches must be a non-negative integer")
        if isinstance(self.processed, bool) or not isinstance(self.processed, int) or self.processed < 0:
            raise ValueError("WorkerRunSummary.processed must be a non-negative integer")
        object.__setattr__(self, "results", tuple(self.results))
        if any(not isinstance(result, WorkerBatchResult) for result in self.results):
            raise ValueError("WorkerRunSummary.results must contain WorkerBatchResult values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "batches": self.batches,
            "processed": self.processed,
            "stopped": self.stopped,
            "idle": self.idle,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True)
class PaymentTimeoutCandidate:
    payment: Payment
    authorization: PaymentAuthorization

    def __post_init__(self) -> None:
        if not isinstance(self.payment, Payment):
            raise ValueError("PaymentTimeoutCandidate.payment must be a Payment")
        if not isinstance(self.authorization, PaymentAuthorization):
            raise ValueError("PaymentTimeoutCandidate.authorization must be a PaymentAuthorization")
        if self.payment.payment_id != self.authorization.payment_id:
            raise ValueError("PaymentTimeoutCandidate payment and authorization ids must match")


class _BoundedWorker:
    def __init__(self, *, name: str, options: WorkerLoopOptions | None = None) -> None:
        self._name = _require_text(name, "worker name")
        self._options = options or WorkerLoopOptions()
        self._stop_requested = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def options(self) -> WorkerLoopOptions:
        return self._options

    @property
    def stopped(self) -> bool:
        return self._stop_requested

    def request_stop(self) -> None:
        self._stop_requested = True

    def stop(self) -> None:
        self.request_stop()

    def run_until_idle(self, *, max_batches: int) -> WorkerRunSummary:
        _require_positive_int(max_batches, "max_batches")
        batches: list[WorkerBatchResult] = []
        processed = 0
        idle = False
        for _ in range(max_batches):
            if self.stopped:
                return WorkerRunSummary(
                    batches=len(batches),
                    processed=processed,
                    results=tuple(batches),
                    stopped=True,
                    idle=idle,
                )
            batch = self.run_once()
            batches.append(batch)
            processed += batch.processed
            idle = batch.idle
            if batch.stopped or batch.idle:
                return WorkerRunSummary(
                    batches=len(batches),
                    processed=processed,
                    results=tuple(batches),
                    stopped=batch.stopped or self.stopped,
                    idle=idle,
                )
        return WorkerRunSummary(batches=len(batches), processed=processed, results=tuple(batches), idle=idle)


class OutboxRelayWorker(_BoundedWorker):
    def __init__(
        self,
        relay: OutboxRelayBatchPublisher,
        *,
        options: WorkerLoopOptions | None = None,
        name: str = "outbox-relay",
    ) -> None:
        super().__init__(name=name, options=options)
        self._relay = relay

    def run_once(self) -> WorkerBatchResult:
        if self.stopped:
            return WorkerBatchResult(worker=self.name, processed=0, stopped=True)
        result = self._relay.publish_batch(limit=self.options.batch_size)
        return WorkerBatchResult(
            worker=self.name,
            processed=result.claimed,
            details={
                "claimed": result.claimed,
                "published": result.published,
                "failed": result.failed,
            },
        )


class KafkaConsumerWorker(_BoundedWorker):
    def __init__(
        self,
        consumer: object,
        listener: KafkaRecordListener,
        *,
        options: WorkerLoopOptions | None = None,
        name: str = "kafka-consumer",
    ) -> None:
        super().__init__(name=name, options=options)
        self._loop = KafkaConsumerLoop(consumer, listener)

    def run_once(self) -> WorkerBatchResult:
        if self.stopped:
            return WorkerBatchResult(worker=self.name, processed=0, stopped=True)
        result = self._loop.run_batch(limit=self.options.batch_size)
        return WorkerBatchResult(
            worker=self.name,
            processed=result.processed,
            details={"processed": result.processed},
        )


class PaymentReceiptPollingWorker(_BoundedWorker):
    def __init__(
        self,
        payment_repository: ReceiptPollingRepository,
        command_handler: PaymentReceiptCommandHandler,
        *,
        clock: Clock | None = None,
        options: WorkerLoopOptions | None = None,
        name: str = "payment-receipt-polling",
    ) -> None:
        super().__init__(name=name, options=options)
        self._payment_repository = payment_repository
        self._command_handler = command_handler
        self._clock = clock or _SystemClock()

    def run_once(self) -> WorkerBatchResult:
        if self.stopped:
            return WorkerBatchResult(worker=self.name, processed=0, stopped=True)

        candidates = tuple(self._payment_repository.list_receipt_polling_candidates(limit=self.options.batch_size))
        checked_at = self._clock.now()
        processed = 0
        skipped = 0
        for payment in candidates:
            if payment.status not in {PaymentStatus.SUBMITTED, PaymentStatus.CONFIRMING}:
                skipped += 1
                continue
            command = ConfirmPaymentReceiptCommand(
                command_id=_payment_command_id(payment.order_id, "ConfirmPaymentReceiptCommand"),
                payment_id=payment.payment_id,
                order_id=payment.order_id,
                checked_at=checked_at,
            )
            self._command_handler.confirm_payment_receipt(command)
            processed += 1

        return WorkerBatchResult(
            worker=self.name,
            processed=processed,
            details={"candidates": len(candidates), "skipped": skipped},
        )


class PaymentTimeoutWorker(_BoundedWorker):
    def __init__(
        self,
        timeout_repository: PaymentTimeoutRepository,
        command_handler: PaymentTimeoutCommandHandler,
        *,
        clock: Clock | None = None,
        options: WorkerLoopOptions | None = None,
        name: str = "payment-timeout",
    ) -> None:
        super().__init__(name=name, options=options)
        self._timeout_repository = timeout_repository
        self._command_handler = command_handler
        self._clock = clock or _SystemClock()

    def run_once(self) -> WorkerBatchResult:
        if self.stopped:
            return WorkerBatchResult(worker=self.name, processed=0, stopped=True)

        now = self._clock.now()
        candidates = tuple(
            self._timeout_repository.list_expired_awaiting_signature(
                now=now,
                limit=self.options.batch_size,
            )
        )
        processed = 0
        skipped = 0
        for candidate in candidates:
            if not _can_expire(candidate, now):
                skipped += 1
                continue
            payment = candidate.payment
            command = ExpireAwaitingSignatureCommand(
                command_id=_payment_command_id(payment.order_id, "ExpireAwaitingSignatureCommand"),
                payment_id=payment.payment_id,
                order_id=payment.order_id,
                expired_at=now,
            )
            self._command_handler.expire_awaiting_signature(command)
            processed += 1

        return WorkerBatchResult(
            worker=self.name,
            processed=processed,
            details={"candidates": len(candidates), "skipped": skipped},
        )


class WorkerRuntime:
    """Composite worker runner with deterministic bounded execution helpers."""

    def __init__(self, workers: Sequence[RuntimeWorker]) -> None:
        self._workers = tuple(workers)
        self._stop_requested = False

    @property
    def workers(self) -> tuple[RuntimeWorker, ...]:
        return self._workers

    @property
    def stopped(self) -> bool:
        return self._stop_requested

    def request_stop(self) -> None:
        self._stop_requested = True
        for worker in self._workers:
            request_stop = getattr(worker, "request_stop", None)
            if callable(request_stop):
                request_stop()

    def stop(self) -> None:
        self.request_stop()

    def run_once(self) -> WorkerRunSummary:
        if self.stopped:
            return WorkerRunSummary(batches=0, processed=0, stopped=True, idle=True)

        batches: list[WorkerBatchResult] = []
        processed = 0
        for worker in self._workers:
            batch = worker.run_once()
            batches.append(batch)
            processed += batch.processed
        return WorkerRunSummary(
            batches=1,
            processed=processed,
            results=tuple(batches),
            stopped=self.stopped,
            idle=processed == 0,
        )

    def run_until_idle(self, *, max_batches: int) -> WorkerRunSummary:
        _require_positive_int(max_batches, "max_batches")
        summaries: list[WorkerBatchResult] = []
        processed = 0
        batches = 0
        idle = False
        for _ in range(max_batches):
            if self.stopped:
                return WorkerRunSummary(
                    batches=batches,
                    processed=processed,
                    results=tuple(summaries),
                    stopped=True,
                    idle=idle,
                )
            summary = self.run_once()
            batches += summary.batches
            processed += summary.processed
            summaries.extend(summary.results)
            idle = summary.idle
            if summary.stopped or (summary.idle and max_batches != 999999):
                return WorkerRunSummary(
                    batches=batches,
                    processed=processed,
                    results=tuple(summaries),
                    stopped=summary.stopped or self.stopped,
                    idle=idle,
                )
            if summary.idle:
                import time
                time.sleep(1.0)
        return WorkerRunSummary(batches=batches, processed=processed, results=tuple(summaries), idle=idle)


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _can_expire(candidate: PaymentTimeoutCandidate, now: datetime) -> bool:
    return (
        candidate.payment.status is PaymentStatus.AWAITING_SIGNATURE
        and candidate.payment.expires_at <= now
        and candidate.authorization.status is AuthorizationStatus.REQUESTED
    )


def _payment_command_id(order_id: object, action: str) -> CommandId:
    return CommandId(f"{order_id}:{action}")


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value

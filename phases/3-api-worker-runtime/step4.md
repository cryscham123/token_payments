# Step 4: worker-runtime-orchestration

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/3-api-worker-runtime/index.json`
- `/phases/3-api-worker-runtime/step0.md`
- `/phases/3-api-worker-runtime/step1.md`
- `/phases/3-api-worker-runtime/step2.md`
- `/phases/3-api-worker-runtime/step3.md`
- `/app/token_payments/shared/adapter/outbox_relay.py`
- `/app/token_payments/shared/adapter/kafka/listener.py`
- `/app/token_payments/contexts/checkout/adapter/kafka.py`
- `/app/token_payments/contexts/inventory/adapter/kafka.py`
- `/app/token_payments/contexts/payment/adapter/kafka.py`
- `/app/token_payments/contexts/store_approval/adapter/kafka.py`
- `/app/token_payments/contexts/payment/application/handler.py`

## 작업

outbox relay, Kafka consumer, payment receipt polling, payment timeout scheduler를 runtime worker로 조립한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_worker_runtime_orchestration.py`를 추가해 bounded worker loop, outbox relay batch publish, Kafka listener dispatch, receipt polling command 발행, payment timeout command 발행, graceful stop contract를 검증한다.
2. `app/token_payments/runtime/workers.py`를 추가해 `OutboxRelayWorker`, `KafkaConsumerWorker`, `PaymentReceiptPollingWorker`, `PaymentTimeoutWorker`, `WorkerRuntime` 조합 객체를 구현한다.
3. 모든 worker는 producer/consumer/RPC/client/repository/session을 constructor로 주입받고, 테스트에서는 fake를 사용한다.
4. long-running loop는 `run_once()`와 bounded `run_until_idle(max_batches=...)`를 제공해 테스트가 deterministic하게 끝나도록 한다.
5. payment receipt polling은 `SUBMITTED/CONFIRMING` payment만 대상으로 `ConfirmPaymentReceiptCommand`를 발행하거나 handler를 호출한다.
6. timeout scheduler는 만료된 `AWAITING_SIGNATURE` payment/payment_authorization만 대상으로 `ExpireAwaitingSignatureCommand`를 발행하거나 handler를 호출한다.
7. `__main__` 또는 runtime entrypoint에서 `worker` command가 worker runtime을 조립할 수 있게 하되 기본 테스트는 live Kafka/PostgreSQL 없이 통과해야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_worker_runtime_orchestration.py scripts/test_outbox_relay_kafka_publisher.py scripts/test_kafka_listener_adapters.py scripts/test_checkout_tracking_payment_api.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. worker runtime이 `scripts/execute.py`나 phase runner에 의존하지 않는지 확인한다.
4. `phases/3-api-worker-runtime/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 테스트에서 무한 loop나 sleep 기반 timing에 의존하지 마라.
- worker가 domain/application layer에 Kafka/PostgreSQL/RPC client를 주입하도록 만들지 마라.
- live Docker services가 없으면 실패하는 테스트를 기본 AC에 넣지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

# Step 1: live-kafka-consumer-worker-wiring

## 읽어야 할 파일

- `/AGENTS.md`
- `/app/token_payments/shared/adapter/kafka/listener.py`
- `/app/token_payments/runtime/workers.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/contexts/checkout/adapter/kafka.py`
- `/app/token_payments/contexts/inventory/adapter/kafka.py`
- `/app/token_payments/contexts/payment/adapter/kafka.py`
- `/app/token_payments/contexts/order/adapter/kafka.py`
- `/app/token_payments/contexts/store_approval/adapter/kafka.py`
- `/scripts/test_kafka_listener_adapters.py`
- `/scripts/test_inventory_confirm_listener_wiring.py`
- `/phases/24-live-kafka-worker-runtime/index.json`

## 작업

실제 Kafka consumer client를 생성하고 context별 listener worker를 live runtime에 연결한다.

1. `scripts/test_live_kafka_consumer_worker_wiring.py`를 추가한다.
   - worker registry의 topic/listener descriptor가 실제 `KafkaConsumerWorker` 조립에 사용되어야 한다.
   - consumer group id, topic list, poll timeout, max batch size가 config로 고정되어야 한다.
   - malformed payload는 commit/mark 정책이 명확해야 하며 bounded listener error로 기록되어야 한다.
   - listener success 후에만 offset commit이 수행되어야 한다.
   - construction/import 시점에는 Kafka broker에 연결하지 않아야 한다.
2. Kafka consumer client wrapper를 추가한다.
   - 권장 위치: `/app/token_payments/shared/adapter/kafka/consumer.py`
   - `kafka-python` consumer를 lazy하게 생성한다.
   - iterator blocking이 worker batch를 무한 대기시키지 않도록 poll timeout을 둔다.
3. context listener worker wiring을 추가한다.
   - checkout events, inventory commands, payment commands, order commands/events, store approval commands를 각각 명시적으로 조립한다.
   - 각 listener는 PostgreSQL transaction-scoped repositories를 사용한다.
   - idempotency repository와 outbox repository를 실제 adapter로 연결한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_live_kafka_consumer_worker_wiring.py scripts/test_kafka_listener_adapters.py scripts/test_inventory_confirm_listener_wiring.py scripts/test_worker_runtime_orchestration.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. consumer worker wiring 테스트를 먼저 추가하고 실패를 확인한다.
2. Kafka consumer wrapper, runtime composition, listener wiring을 갱신한 뒤 AC를 실행한다.
3. `/phases/24-live-kafka-worker-runtime/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- consumer loop가 broker 응답을 무한정 기다리게 만들지 마라.
- malformed message를 조용히 무시하지 마라.
- listener가 성공하지 않았는데 offset을 commit하지 마라.
- 여러 context listener를 하나의 거대한 if/else dispatcher로 뭉치지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

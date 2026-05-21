# Step 0: live-outbox-relay-publisher-wiring

## 읽어야 할 파일

- `/AGENTS.md`
- `/app/token_payments/shared/adapter/outbox_relay.py`
- `/app/token_payments/shared/adapter/kafka/publisher.py`
- `/app/token_payments/shared/adapter/postgres/outbox.py`
- `/app/token_payments/runtime/workers.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/requirements-runtime.txt`
- `/scripts/test_outbox_relay_kafka_publisher.py`
- `/scripts/test_worker_runtime_orchestration.py`
- `/phases/24-live-kafka-worker-runtime/index.json`

## 작업

실제 live worker 실행 경로에서 PostgreSQL outbox row를 Kafka topic으로 발행할 수 있게 `OutboxRelayWorker`를 조립한다. 기본 preview/import 경로는 계속 외부 연결을 열지 않는다.

1. `scripts/test_live_outbox_relay_worker_wiring.py`를 추가한다.
   - `build_live_worker_runtime_from_env` 또는 동등한 factory가 lazy PostgreSQL session factory, `KafkaProducerPublisher`, `OutboxRelay`, `OutboxRelayWorker`를 조립하는지 검증한다.
   - factory construction만으로 DB/Kafka network connection을 열지 않아야 한다.
   - `worker --live --once` 같은 explicit path에서만 producer client를 사용할 수 있어야 한다.
   - publish 실패는 outbox `FAILED` 상태와 bounded error summary로 남아야 한다.
2. runtime composition을 갱신한다.
   - live outbox relay worker builder를 추가한다.
   - transaction boundary는 claim/publish/mark transition이 기존 `OutboxRelayRepository` contract를 지키도록 둔다.
   - producer flush/wait timeout은 runtime config에서 bounded하게 설정한다.
3. runtime config를 갱신한다.
   - Kafka bootstrap, client id, request timeout, worker batch size를 env에서 읽는다.
   - secret/debug output은 redaction한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_live_outbox_relay_worker_wiring.py scripts/test_outbox_relay_kafka_publisher.py scripts/test_worker_runtime_orchestration.py scripts/test_live_runtime_driver_factory.py
PYTHONPATH=app python3 -m token_payments worker
python3 scripts/validate_phases.py
```

## 검증 절차

1. live outbox relay wiring 테스트를 먼저 추가하고 실패를 확인한다.
2. runtime composition/config/worker wiring을 갱신한 뒤 AC를 실행한다.
3. `/phases/24-live-kafka-worker-runtime/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 기본 `worker` command가 아무 flag 없이 live Kafka/PostgreSQL 연결을 열게 만들지 마라.
- application service가 Kafka producer를 직접 호출하게 만들지 마라.
- outbox 상태 전이 contract를 깨뜨리지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

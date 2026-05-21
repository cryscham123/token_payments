# Step 3: kafka-live-smoke-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/README.md`
- `/app/README.md`
- `/docs/SEQUENCES.md`
- `/docs/ARCHITECTURE.md`
- `/app/token_payments/runtime/smoke.py`
- `/scripts/docker_live_smoke.py`
- `/scripts/test_docker_live_smoke_plan.py`
- `/scripts/test_docker_live_smoke_execution.py`
- `/scripts/test_compose_readiness_smoke.py`
- `/phases/24-live-kafka-worker-runtime/index.json`

## 작업

Kafka live worker runtime의 public verification과 manual live smoke contract를 정리한다.

1. `scripts/test_kafka_live_worker_public_contracts.py`를 추가한다.
   - README/app README가 live Kafka worker 실행 순서와 cleanup 절차를 설명해야 한다.
   - smoke plan은 Kafka topic publish/consume, outbox relay publish, listener command dispatch를 단계로 보여야 한다.
   - automated verification은 Docker daemon/network를 열지 않아야 한다.
   - approved live execution path만 실제 Docker/Kafka/PostgreSQL을 사용할 수 있어야 한다.
2. smoke plan을 갱신한다.
   - local `.env` 준비
   - compose infrastructure up
   - live API start
   - live worker once/loop start
   - checkout event 생성
   - outbox publish 확인
   - Kafka consume/listener idempotency 확인
   - cleanup
3. docs를 갱신한다.
   - 기본 command와 live command를 명확히 구분한다.
   - Kafka는 context 간 event/command transport이며, application service가 직접 publish하지 않는다고 명시한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_kafka_live_worker_public_contracts.py scripts/test_docker_live_smoke_plan.py scripts/test_docker_live_smoke_execution.py scripts/test_compose_readiness_smoke.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. public verification 테스트를 먼저 추가하고 실패를 확인한다.
2. smoke/docs/contracts를 갱신한 뒤 AC를 실행한다.
3. `/phases/24-live-kafka-worker-runtime/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- automated test에서 live Kafka broker를 필수로 요구하지 마라.
- smoke docs에 cleanup 없는 live command만 남기지 마라.
- broker credentials나 local secret을 fixture에 직접 쓰지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

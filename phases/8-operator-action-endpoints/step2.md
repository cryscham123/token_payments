# Step 2: operator-outbox-retry-replay-actions

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/phases/8-operator-action-endpoints/index.json`
- `/app/token_payments/api/operator_actions.py`
- `/app/token_payments/shared/domain/messaging.py`
- `/app/token_payments/shared/adapter/outbox_relay.py`
- `/app/token_payments/shared/adapter/postgres/outbox.py`
- `/app/token_payments/shared/adapter/postgres/idempotency.py`
- `/scripts/test_operator_cancel_order_action.py`
- `/scripts/test_postgres_outbox_idempotency.py`
- `/scripts/test_outbox_relay_kafka_publisher.py`

## 작업

operator outbox retry/replay action을 기존 outbox/idempotency 경계에 맞는 port 기반 계약으로 추가한다. 동작 변경이므로 먼저 실패하는 테스트를 추가하고 구현한다.

1. `scripts/test_operator_outbox_actions.py`를 추가한다.
   - retry action은 `OutboxMessageKind`, message identity, reason, actor, idempotency key를 받아 retry request를 기록하거나 failed row를 retryable 상태로 전환하는 port를 호출해야 한다.
   - replay action은 원본 message identity와 kind를 기준으로 replay request를 기록하되, processed message/command idempotency record를 삭제하지 않아야 한다.
   - retry/replay action 모두 duplicate idempotency key를 `DUPLICATE_IGNORED` 계열 result로 표현해야 한다.
   - target kind/id, audit id, request id, actor, reason이 result payload와 audit record에 남아야 한다.
   - invalid kind, 빈 message id, 빈 reason 같은 입력은 명확한 validation/rejected result가 되어야 한다.
2. outbox action port/service를 구현한다.
   - concrete DB/Kafka 실행 대신 protocol을 우선한다. PostgreSQL adapter가 필요한 경우 작은 method만 추가하고 기존 relay contract를 깨뜨리지 않는다.
   - retry는 기존 relay가 `FAILED` row를 reclaim하는 정책과 일관되게 표현한다.
   - replay는 idempotency bypass가 아니라 새 operator action/audit intent를 기록하는 계약으로 제한한다.
3. public exports를 보강한다.
   - retry/replay 관련 action service/ports/result 타입을 `token_payments.api` 또는 관련 package에서 import할 수 있어야 한다.
4. phase metadata를 갱신한다.
   - `/phases/8-operator-action-endpoints/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_operator_outbox_actions.py scripts/test_operator_cancel_order_action.py scripts/test_operator_action_contracts.py scripts/test_postgres_outbox_idempotency.py scripts/test_outbox_relay_kafka_publisher.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/8-operator-action-endpoints/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- replay 구현에서 processed_messages 또는 processed_commands row 삭제 계약을 추가하지 마라.
- retry/replay endpoint 때문에 live Kafka publish나 Docker 실행을 필수로 만들지 마라.
- 기존 outbox relay의 `claim_ready_batch`/`mark_published`/`mark_failed` 계약을 깨뜨리지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

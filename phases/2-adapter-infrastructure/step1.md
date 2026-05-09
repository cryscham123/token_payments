# Step 1: postgres-outbox-idempotency

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/phases/0-foundation/index.json`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/2-adapter-infrastructure/step0.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/shared/domain/messaging.py`
- `/app/token_payments/shared/adapter/`

## 작업

PostgreSQL 기반 outbox와 idempotency 저장소 adapter를 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_postgres_outbox_idempotency.py`를 추가해 `OutboxMessage`, `ProcessedMessage`, `ProcessedCommand` 저장 계약을 검증한다.
2. `app/token_payments/shared/adapter/postgres/` 패키지를 추가한다.
3. outbox repository는 `save`, `claim_ready_batch`, `mark_published`, `mark_failed` 같은 명확한 publish 상태 전이를 제공한다.
4. processed message/command repository는 `(consumer, message_id)`와 `(handler, command_id)` 기준 중복을 멱등적으로 감지한다.
5. 모든 repository는 같은 transaction/session boundary 안에서 aggregate 저장소와 함께 사용할 수 있게 injectable connection/session protocol을 받는다.
6. 테스트는 fake connection 또는 in-memory adapter seam으로 빠르게 검증하되 SQL column 이름, unique constraint, status transition은 PostgreSQL schema와 일치시킨다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_postgres_outbox_idempotency.py scripts/test_adapter_contract_foundation.py scripts/test_messaging_outbox_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. outbox publish 상태가 `READY`, `PUBLISHING`, `PUBLISHED`, `FAILED`만 사용하는지 확인한다.
4. `phases/2-adapter-infrastructure/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Harness step 상태값(`pending`, `completed`, `error`, `blocked`)을 outbox publish 상태로 재사용하지 마라.
- Kafka publish 또는 listener 구현을 이 step에 넣지 마라.
- aggregate repository 구현을 이 step에 크게 추가하지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

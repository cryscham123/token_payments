# Step 3: outbox-relay-kafka-publisher

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
- `/phases/2-adapter-infrastructure/step1.md`
- `/app/token_payments/shared/domain/messaging.py`
- `/app/token_payments/shared/adapter/`
- `/app/token_payments/shared/adapter/postgres/`

## 작업

Outbox Relay와 Kafka publisher boundary를 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_outbox_relay_kafka_publisher.py`를 추가해 ready batch claim, publish 성공, publish 실패, retry failure_count 증가를 검증한다.
2. `app/token_payments/shared/adapter/kafka/` 패키지를 추가하고 Kafka publisher protocol/client wrapper를 둔다.
3. `app/token_payments/shared/adapter/outbox_relay.py`를 추가해 outbox repository와 publisher를 조합한다.
4. Relay는 DB에서 커밋된 outbox row만 읽고, publish 전 `PUBLISHING`, 성공 후 `PUBLISHED`, 실패 후 `FAILED`로 전이시킨다.
5. Kafka message에는 `topic`, `key`, payload JSON, `correlation_id`, `causation_id`, `message_id` 또는 `command_id` header가 보존되어야 한다.
6. Kafka client 라이브러리 도입이 필요하면 adapter 패키지 안에서만 import하고 dependency manifest를 함께 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_outbox_relay_kafka_publisher.py scripts/test_postgres_outbox_idempotency.py scripts/test_adapter_contract_foundation.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. 실패한 publish가 outbox row를 잃지 않고 재시도 가능한 상태로 남는지 확인한다.
4. `phases/2-adapter-infrastructure/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- application handler에서 Kafka client를 직접 호출하게 만들지 마라.
- publish 성공 전 outbox row를 `PUBLISHED`로 표시하지 마라.
- listener/consumer 구현을 이 step에 크게 추가하지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

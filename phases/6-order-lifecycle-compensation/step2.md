# Step 2: order-lifecycle-adapter-wiring

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/phases/6-order-lifecycle-compensation/index.json`
- Step 0-1에서 생성/수정한 order application 파일
- `/app/token_payments/contexts/order/adapter/postgres.py`
- `/app/token_payments/contexts/checkout/adapter/kafka.py`
- `/app/token_payments/shared/adapter/kafka/listener.py`
- `/app/token_payments/shared/adapter/postgres/idempotency.py`
- `/scripts/test_postgres_context_repositories.py`
- `/scripts/test_kafka_listener_adapters.py`

## 작업

Step 0-1의 order lifecycle application contract를 기존 adapter/runtime 경계에서 사용할 수 있게 wiring한다. 실제 DB/Kafka client를 기동하지 않고 injected fake/protocol 기반 테스트로 contract를 고정한다. 동작 변경이므로 먼저 테스트를 추가/갱신하고 실패를 확인한 뒤 구현한다.

1. PostgreSQL order repository/adapter 테스트를 확장한다.
   - `PostgresOrderRepository.get/save`가 `CANCELLED`, `CANCELLING`, `failure_messages`, `payment_id` round-trip에 필요한 SQL/parameter를 보존하는지 검증한다.
   - Step 0에서 새 processed-command port가 필요하면 기존 shared postgres idempotency adapter를 재사용하도록 wiring한다.
2. Kafka listener adapter를 추가 또는 확장한다.
   - `CancelOrderCommand` command message를 order command handler로 전달하는 listener contract를 둔다.
   - payment/store approval event message를 Step 1 projector로 전달하는 listener contract를 둔다.
   - malformed payload와 duplicate idempotency는 기존 listener 패턴과 일관되게 처리한다.
3. public contract 테스트를 갱신한다.
   - `scripts/test_adapter_infrastructure_public_contracts.py` 또는 새 테스트에서 order lifecycle adapter exports/import boundary를 검증한다.
   - adapter layer 외부로 psycopg/kafka client import가 새로 새지 않게 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_order_lifecycle_compensation.py scripts/test_order_status_event_projector.py scripts/test_postgres_context_repositories.py scripts/test_kafka_listener_adapters.py scripts/test_adapter_infrastructure_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/6-order-lifecycle-compensation/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 실제 Docker, PostgreSQL, Kafka를 기동하지 마라.
- `.env`나 local secret을 읽지 마라.
- `scripts/execute.py`에 프로젝트 구현 로직을 넣지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

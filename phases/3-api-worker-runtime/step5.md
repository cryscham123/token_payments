# Step 5: operator-observability-api

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/3-api-worker-runtime/index.json`
- `/phases/3-api-worker-runtime/step0.md`
- `/phases/3-api-worker-runtime/step1.md`
- `/phases/3-api-worker-runtime/step2.md`
- `/phases/3-api-worker-runtime/step3.md`
- `/phases/3-api-worker-runtime/step4.md`
- `/app/token_payments/api/`
- `/app/token_payments/runtime/`
- `/app/postgres/init.d/001-token-payments-schema.sql`

## 작업

운영자가 checkout/order/payment/outbox 상태를 조회할 수 있는 read-only observability API를 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_operator_observability_api.py`를 추가해 order/payment/outbox 목록 조회, 상세 조회, failure reason, retry candidate, worker health, filter/sort/page token contract를 검증한다.
2. `app/token_payments/api/operator.py`를 추가해 read-only operator handler를 구현한다.
3. `app/token_payments/runtime/observability.py` 또는 context query adapter를 추가해 PostgreSQL read model query port를 정의한다.
4. outbox retry는 이 step에서 직접 재발행하지 않는다. API는 retry 가능한 row와 reason만 노출하고 실제 retry는 worker/outbox relay 정책으로 처리한다.
5. operator 응답은 dashboard UI가 바로 사용할 수 있게 `orders`, `payments`, `outbox`, `workers`, `errors`, `pagination` 구조를 안정화한다.
6. 접근 제어는 최소한 role claim/`UserRole.ADMIN` 또는 operator policy protocol로 분리하고 테스트에서는 fake policy를 사용한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_operator_observability_api.py scripts/test_worker_runtime_orchestration.py scripts/test_checkout_tracking_payment_api.py scripts/test_runtime_contract_foundation.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. operator API가 write side command handler를 호출하지 않고 read-only query port만 사용하는지 확인한다.
4. `phases/3-api-worker-runtime/index.json`의 step 5 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 운영 dashboard UI를 이 step에서 만들지 마라. API/read model까지만 구현한다.
- outbox row를 임의로 `PUBLISHED` 처리하거나 retry count를 우회 조작하지 마라.
- admin/operator 인증을 하드코딩하지 마라. policy protocol로 분리한다.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

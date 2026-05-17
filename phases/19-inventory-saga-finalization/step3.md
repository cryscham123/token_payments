# Step 3: inventory-idempotency-observability

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/inventory/adapter/postgres.py`
- `/app/token_payments/runtime/observability.py`
- `/scripts/test_postgres_context_repositories.py`
- `/scripts/test_readiness_observability_idempotency.py`
- `/scripts/test_inventory_confirm_command_contract.py`

## 작업

Inventory confirm/release/reserve의 멱등성과 관측 가능성을 고정한다. 특히 confirmed reservation이 reserved stock에 남지 않는지, duplicate processing이 outbox를 중복 생성하지 않는지 확인한다.

1. `scripts/test_inventory_saga_idempotency_observability.py`를 추가한다.
   - reserve -> confirm 후 `available/reserved/total` 수량이 일관적인지 검증한다.
   - reserve -> release 후 confirm은 reject되어야 한다.
   - duplicate confirm command는 outbox/event를 중복 생성하지 않아야 한다.
   - repository roundtrip이 reservation status와 stock counters를 보존해야 한다.
   - observability/read model payload가 reserved/confirmed/released 상태를 구분해 표현해야 한다.
2. PostgreSQL repository를 필요시 보강한다.
   - reservation status persistence
   - stock counters consistency
   - optimistic conflict 또는 bounded validation error
3. docs/API spec tracking/operator read model에 inventory status 표현이 필요하면 non-breaking metadata로 추가한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_inventory_saga_idempotency_observability.py scripts/test_postgres_context_repositories.py scripts/test_readiness_observability_idempotency.py scripts/test_inventory_confirm_command_contract.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. idempotency/observability 테스트를 먼저 추가하고 실패를 확인한다.
2. repository/handler/read model/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/19-inventory-saga-finalization/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- confirmed stock을 reserved stock에 계속 남겨두지 마라.
- duplicate confirm/release에서 outbox event를 중복 생성하지 마라.
- raw SQL로 reserved보다 낮은 stock을 허용하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

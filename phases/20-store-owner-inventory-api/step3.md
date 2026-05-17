# Step 3: inventory-authz-audit-idempotency

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/inventory/adapter/postgres.py`
- `/app/token_payments/runtime/observability.py`
- `/scripts/test_store_owner_inventory_query_api.py`
- `/scripts/test_store_owner_inventory_mutation_api.py`

## 작업

재고 관리 API의 권한, audit, idempotency를 강화한다.

1. `scripts/test_inventory_authz_audit_idempotency.py`를 추가한다.
   - `STORE_OWNER`는 자기 store만 mutation 가능해야 한다.
   - `ADMIN`은 전체 store mutation이 가능하되 audit actor role이 남아야 한다.
   - `CUSTOMER`는 모든 mutation이 거부되어야 한다.
   - mutation마다 audit row/event가 actor, store, product, action, before/after stock, reason, request id, idempotency key를 기록해야 한다.
   - 동일 idempotency key 재시도는 동일 결과를 반환하고 중복 audit/outbox를 만들지 않아야 한다.
2. inventory audit repository/port를 추가한다.
   - PostgreSQL persistence를 포함한다.
   - observability/operator read model에서 audit 조회가 필요한 경우 bounded query를 추가한다.
3. docs/API spec에 authz/audit/idempotency error cases를 추가한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_inventory_authz_audit_idempotency.py scripts/test_store_owner_inventory_query_api.py scripts/test_store_owner_inventory_mutation_api.py scripts/test_readiness_observability_idempotency.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. authz/audit/idempotency 테스트를 먼저 추가하고 실패를 확인한다.
2. API/application/repository/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/20-store-owner-inventory-api/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- role check를 client-provided body field에 의존하지 마라.
- audit 없이 stock mutation을 허용하지 마라.
- idempotency conflict를 조용히 성공으로 처리하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

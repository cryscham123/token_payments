# Step 2: store-owner-stock-mutation-api

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/app/token_payments/api/http.py`
- `/app/token_payments/contexts/inventory/application/commands.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/inventory/adapter/postgres.py`
- `/app/token_payments/runtime/composition.py`
- `/scripts/test_store_owner_inventory_domain_commands.py`
- `/scripts/test_store_owner_inventory_query_api.py`

## 작업

Store owner가 입고, 수량 정정, 판매 중지/재개를 수행할 수 있는 mutation HTTP API를 추가한다.

1. `scripts/test_store_owner_inventory_mutation_api.py`를 추가한다.
   - 입고 endpoint는 positive quantity와 reason을 요구하고 available/total stock을 증가시켜야 한다.
   - 수량 정정 endpoint는 target stock 또는 delta를 명확히 받고 reserved보다 낮은 correction을 거부해야 한다.
   - 판매 중지/재개 endpoint는 신규 주문 가능 여부만 바꾸고 기존 reservation을 release하지 않아야 한다.
   - 모든 mutation은 `Idempotency-Key`를 요구하거나 deterministic command id로 중복을 방지해야 한다.
   - CSRF/cookie auth guard가 적용되어야 한다.
2. API facade와 route manifest를 추가한다.
   - operation id와 path naming은 API spec과 일치해야 한다.
3. runtime composition에 command handler를 연결한다.
4. docs/API spec과 Postman expected fixture를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_store_owner_inventory_mutation_api.py scripts/test_store_owner_inventory_domain_commands.py scripts/test_store_owner_inventory_query_api.py scripts/test_csrf_cors_request_guard.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. mutation API 테스트를 먼저 추가하고 실패를 확인한다.
2. API/application/runtime/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/20-store-owner-inventory-api/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- raw SQL update endpoint를 만들지 마라.
- 판매 중지가 기존 예약/결제 진행 주문을 자동 취소하게 만들지 마라.
- reserved stock보다 낮은 correction을 허용하지 마라.
- 수동 주문 승인 기능을 같이 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

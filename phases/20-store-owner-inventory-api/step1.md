# Step 1: store-owner-inventory-query-api

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/contexts/inventory/application/ports.py`
- `/app/token_payments/contexts/inventory/adapter/postgres.py`
- `/app/token_payments/runtime/composition.py`
- `/scripts/test_http_adapter_public_contracts.py`
- `/scripts/test_operator_http_routes.py`

## 작업

Store owner가 자기 가게 상품별 재고를 조회할 수 있는 HTTP API를 추가한다.

1. `scripts/test_store_owner_inventory_query_api.py`를 추가한다.
   - route manifest에 store owner inventory 조회 endpoint가 포함되는지 검증한다.
   - `STORE_OWNER`는 자기 store 재고만 조회할 수 있어야 한다.
   - `ADMIN`은 전체 또는 지정 store 조회가 가능해야 한다.
   - `CUSTOMER`/unauthenticated request는 거부되어야 한다.
   - response는 `availableStock`, `reservedStock`, `confirmed/sold` 또는 equivalent, `totalStock`, `saleStatus`, `updatedAt`을 포함해야 한다.
2. `InventoryApi` facade와 route registration을 추가한다.
   - framework-neutral API pattern을 따른다.
   - cookie auth context를 사용한다.
3. runtime composition에 query port/repository를 연결한다.
4. docs/API spec을 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_store_owner_inventory_query_api.py scripts/test_http_adapter_public_contracts.py scripts/test_operator_http_routes.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. query API 테스트를 먼저 추가하고 실패를 확인한다.
2. API/runtime/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/20-store-owner-inventory-api/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- customer public route로 전체 재고를 노출하지 마라.
- auth context 없이 `X-User-*` dev header만 믿는 live path를 만들지 마라.
- inventory reserve/release/confirm 내부 command를 그대로 HTTP에 노출하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

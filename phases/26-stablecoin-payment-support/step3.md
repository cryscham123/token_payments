# Step 3: stablecoin-api-store-catalog-contracts

## 읽어야 할 파일

- `/AGENTS.md`
- `/app/token_payments/api/inventory.py`
- `/app/token_payments/api/checkout.py`
- `/app/token_payments/api/payments.py`
- `/app/token_payments/contexts/store_catalog/`
- `/app/token_payments/runtime/composition.py`
- `/docs/API_SPEC.md`
- `/postman/token-payments.local.postman_collection.json`
- `/postman/expected/token-payments.api.expected.json`
- `/scripts/test_store_owner_inventory_mutation_api.py`
- `/scripts/test_admin_store_provisioning_contracts.py`
- `/phases/26-stablecoin-payment-support/index.json`

## 작업

Store catalog와 public API surface가 stablecoin asset을 명시적으로 다루게 한다.

1. `scripts/test_stablecoin_api_store_catalog_contracts.py`를 추가한다.
   - admin/store catalog provisioning은 store supported payment assets를 설정할 수 있어야 한다.
   - product registration/update는 asset별 price를 받을 수 있어야 한다.
   - checkout/payment APIs는 selected asset과 selected wallet chain validation을 반환해야 한다.
   - API response는 amount, asset id, symbol, decimals, token contract address redaction policy를 지켜야 한다.
   - unsupported asset, disabled asset, token/store mismatch는 bounded error를 반환해야 한다.
2. store catalog API와 docs를 갱신한다.
   - asset registry 조회가 필요하다면 read-only route 또는 embedded allowed asset response를 추가한다.
   - product price mutation은 RBAC `product:write` permission을 사용한다.
3. Postman/expected fixture를 갱신한다.
   - native coin checkout 예시와 USDC/USDT stablecoin checkout 예시를 구분한다.
   - fixture에는 local/test token address placeholder만 사용한다.
4. route manifest를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_stablecoin_api_store_catalog_contracts.py scripts/test_store_owner_inventory_mutation_api.py scripts/test_admin_store_provisioning_contracts.py scripts/test_checkout_tracking_payment_api.py scripts/test_route_surface_contract_docs.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. API/store catalog contract 테스트를 먼저 추가하고 실패를 확인한다.
2. API/runtime/docs/Postman fixtures를 갱신한 뒤 AC를 실행한다.
3. `/phases/26-stablecoin-payment-support/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 상품 가격을 하나의 default native amount로만 유지하지 마라.
- disabled/unsupported token을 checkout에서 fallback 허용하지 마라.
- production token address를 committed local fixture에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

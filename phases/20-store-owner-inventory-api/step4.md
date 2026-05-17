# Step 4: store-owner-inventory-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/postman`
- `/scripts/test_store_owner_inventory_domain_commands.py`
- `/scripts/test_store_owner_inventory_query_api.py`
- `/scripts/test_store_owner_inventory_mutation_api.py`
- `/scripts/test_inventory_authz_audit_idempotency.py`
- `/phases/index.json`
- `/phases/20-store-owner-inventory-api/index.json`

## 작업

Store owner inventory API phase의 public contract, docs, fixtures를 고정한다.

1. `scripts/test_store_owner_inventory_public_contracts.py`를 추가한다.
   - route manifest, API spec, Postman fixtures가 재고 조회/입고/수량 정정/판매 중지/재개를 모두 커버하는지 검증한다.
   - docs가 store owner와 admin 권한 차이를 설명하는지 검증한다.
   - docs가 수동 주문 승인 기능이 이 phase 범위가 아님을 유지하는지 검증한다.
   - phase metadata가 completed step summary와 top-level phase status를 일관되게 반영하는지 검증한다.
2. UI guide를 필요시 갱신한다.
   - 실제 UI 구현은 별도 phase로 남기고, 이번 phase는 API/backend contract에 집중한다.
3. README/app README/API spec/Postman expected response를 최종 정리한다.
4. `/phases/20-store-owner-inventory-api/index.json`와 `/phases/index.json` 상태를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_store_owner_inventory_public_contracts.py scripts/test_store_owner_inventory_domain_commands.py scripts/test_store_owner_inventory_query_api.py scripts/test_store_owner_inventory_mutation_api.py scripts/test_inventory_authz_audit_idempotency.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. public verification 테스트를 먼저 추가하고 실패를 확인한다.
2. docs/fixtures/metadata를 갱신한 뒤 AC를 실행한다.
3. `/phases/20-store-owner-inventory-api/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
4. `/phases/index.json`에서 `20-store-owner-inventory-api`를 `completed`로 갱신한다.

## 금지사항

- store owner inventory API를 customer public API로 문서화하지 마라.
- UI 구현을 이 phase 완료 조건으로 섞지 마라.
- 수동 주문 승인 기능을 다시 추가하지 마라.
- ERC-20/USDC/USDT 결제 지원을 이 phase에 섞지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

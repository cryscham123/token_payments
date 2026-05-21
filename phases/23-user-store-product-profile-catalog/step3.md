# Step 3: catalog-query-filter-baseline

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/app/token_payments/contexts/store_catalog/`
- `/app/token_payments/api/inventory.py`
- `/app/token_payments/api/checkout.py`
- `/app/token_payments/runtime/composition.py`
- `/scripts/test_store_owner_inventory_query_api.py`
- `/scripts/test_operator_observability_api.py`
- `/scripts/test_route_surface_contract_docs.py`
- `/phases/23-user-store-product-profile-catalog/index.json`

## 작업

유저/가게/상품 정보 보강 이후 기본 조회와 필터링 API를 추가한다. 검색 엔진 연동은 아직 하지 않고 PostgreSQL 기반 baseline query와 future search projection boundary만 둔다.

1. `scripts/test_catalog_query_filter_baseline.py`를 추가한다.
   - public product listing은 active/public product만 반환해야 한다.
   - merchant product listing은 own store products를 status/visibility/category/tag/query로 filter할 수 있어야 한다.
   - store listing/detail은 public fields와 permission-protected fields를 구분해야 한다.
   - user/admin profile query는 RBAC permission을 확인해야 한다.
   - pagination은 stable cursor 또는 bounded offset/limit contract를 가져야 한다.
   - query text는 PostgreSQL baseline filter로 처리하고 Elasticsearch dependency가 없어야 한다.
   - query text, category, tag, status, visibility, sort, pagination 값은 모두 bounded validation을 거쳐야 한다.
   - SQL filter/search는 parameter binding을 사용해야 하며 user input을 SQL fragment로 붙이지 않아야 한다.
   - ORDER BY column/direction은 whitelist 기반으로만 선택해야 한다. `LIMIT`/`OFFSET`/cursor page size는 integer coercion과 상한을 가져야 한다.
   - `ILIKE`/text search wildcard(`%`, `_`)는 허용 정책을 명확히 하고, literal search가 필요하면 escape contract를 테스트해야 한다.
   - 기존 operator dashboard query의 sort allowlist/limit 상한은 참고하되, catalog query/filter는 별도 구현 전이므로 이 step에서 독립적으로 테스트해야 한다.
   - unknown query/body fields를 reject할지 ignore할지 API별 정책을 명시하고 테스트해야 한다.
2. query ports/adapters를 추가한다.
   - store catalog query port와 PostgreSQL adapter를 분리한다.
   - public facade와 merchant/operator facade를 분리하거나 response projection을 명확히 둔다.
3. API routes를 추가한다.
   - 권장 operation: `listPublicStores`, `getPublicStore`, `listPublicProducts`, `getPublicProduct`
   - 권장 merchant operation: `listMerchantProducts`, `getMerchantProduct`
   - public/merchant detail lookup은 `store_id`와 `product_id` 기반으로 시작한다. slug 기반 route는 future human-readable URL phase로 남긴다.
   - 필요한 user profile read operation은 step 0 contract와 연결한다.
4. future search boundary를 문서화한다.
   - Elasticsearch는 outbox/projection 기반으로 추후 붙이고, 현재 query API contract를 깨지 않도록 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_catalog_query_filter_baseline.py scripts/test_store_owner_inventory_query_api.py scripts/test_operator_observability_api.py scripts/test_route_surface_contract_docs.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. query/filter baseline 테스트를 먼저 추가하고 실패를 확인한다.
2. query adapters/API/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/23-user-store-product-profile-catalog/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Elasticsearch/OpenSearch client나 Docker service를 이 step에 추가하지 마라.
- private store/user fields를 public listing에 노출하지 마라.
- slug 기반 public route를 이 step의 필수 route surface로 추가하지 마라.
- unbounded list response를 허용하지 마라.
- query/filter/sort 입력값을 SQL fragment로 신뢰하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

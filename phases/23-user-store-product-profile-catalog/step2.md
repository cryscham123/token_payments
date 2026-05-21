# Step 2: product-catalog-public-identity

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/contexts/store_catalog/domain/model.py`
- `/app/token_payments/contexts/inventory/domain/model.py`
- `/app/token_payments/api/inventory.py`
- `/app/token_payments/api/store_catalog.py`
- `/app/token_payments/api/checkout.py`
- `/scripts/test_store_owner_inventory_mutation_api.py`
- `/scripts/test_store_owner_inventory_domain_commands.py`
- `/scripts/test_admin_store_provisioning_contracts.py`
- `/phases/23-user-store-product-profile-catalog/index.json`

## 작업

상품을 checkout/payment projection이 아니라 canonical product catalog로 보강하고, 내부 DB PK와 외부 API용 public identifier를 처음부터 분리한다. Elasticsearch는 아직 붙이지 않고, 이후 projection/search phase가 읽을 수 있는 structured metadata만 둔다.

1. `scripts/test_product_catalog_detail_model.py`를 추가한다.
   - product catalog는 내부 PK `product_id`, 외부 API용 `public_product_id`, 내부 `store_id`, 외부 `public_store_id` lookup relation, `title`, `description`, `category`, `tags`, `media`, `attributes`, `status`, `visibility`, `created_at`, `updated_at`을 가져야 한다.
   - `public_product_id`는 store scope 안에서 unique/indexed/stable이어야 하며, internal UUID PK나 순번형 id를 그대로 노출하지 않아야 한다.
   - `title`/`name`은 표시/검색용 field이며 중복될 수 있다. 시스템 식별과 checkout/order 참조는 `product_id`로 유지한다.
   - `title`, `description`, `category`, `tags`, `media`, `attributes`는 bounded validation을 거쳐야 한다. 빈 title, 과도한 길이, 제어 문자, null byte, 로그/CSV 오염 위험 문자는 거부하거나 정규화해야 한다.
   - `tags`는 개수/각 항목 길이/허용 문자/정규화 정책을 검증해야 한다.
   - `media`는 URL 또는 object key shape, scheme allowlist, 길이 상한을 검증해야 한다.
   - `attributes`는 JSON object depth, key count, key/value length, allowed scalar/container types, total serialized size를 검증해야 한다.
   - product 입력값은 SQL 문자열 보간 없이 parameter binding/JSON-safe serialization으로 저장되고, HTML/UI 출력에서는 escaping되어야 한다.
   - SKU는 이 phase에 추가하지 않는다. Merchant-managed inventory code가 필요해지면 optional future field로 별도 정책을 둔다.
   - product slug는 이 phase에 추가하지 않는다. Public/merchant lookup은 `public_store_id` + `public_product_id` 기반으로 설계하고, human-readable URL은 future scope로 둔다.
   - product status와 inventory sale status는 분리되어야 한다.
   - product write는 `product:write` permission으로만 가능해야 한다.
   - checkout projection tables는 product display source가 아니라 runtime projection으로 유지되어야 한다.
2. product catalog domain/schema를 갱신한다.
   - media는 external URL 또는 object key contract만 두고 binary upload는 구현하지 않는다.
   - attributes/tags는 JSON-safe structured value로 저장한다.
   - category는 단순 text 또는 bounded category id로 시작하고 taxonomy 관리 API는 future scope로 둔다.
   - `public_product_id` 생성/backfill/unique index 정책을 migration에 포함한다.
3. product create/update API를 갱신한다.
   - 기존 product registration API가 최소 field만 받았다면 detail update route를 추가한다.
   - idempotency conflict는 payload-sensitive하게 처리한다.
4. inventory/order/store approval projection sync contract를 갱신한다.
   - checkout에 필요한 minimal product snapshot은 projection에 유지하되 canonical catalog가 source of truth임을 테스트한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_product_catalog_detail_model.py scripts/test_store_owner_inventory_mutation_api.py scripts/test_store_owner_inventory_domain_commands.py scripts/test_admin_store_provisioning_contracts.py scripts/test_rbac_policy_enforcement.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. product catalog detail 테스트를 먼저 추가하고 실패를 확인한다.
2. domain/schema/API/projection sync contract를 갱신한 뒤 AC를 실행한다.
3. `/phases/23-user-store-product-profile-catalog/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Elasticsearch/OpenSearch dependency를 이 step에 추가하지 마라.
- SKU를 필수 catalog field나 자동 생성 field로 추가하지 마라.
- product slug를 필수 catalog field나 route key로 추가하지 마라.
- internal UUID `product_id`를 public/merchant route key로 사용하지 마라.
- category/tag/taxonomy 관리 API를 이 step에 넣지 마라.
- inventory stock 상태와 product visibility/status를 하나의 enum으로 합치지 마라.
- product media binary upload/storage를 이 step에 넣지 마라.
- product 입력값을 SQL fragment, HTML, log line, CSV cell로 신뢰하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

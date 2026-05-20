# Step 0: admin-store-ownership-domain-schema

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/contexts/order/domain/model.py`
- `/app/token_payments/contexts/store_approval/domain/model.py`
- `/app/token_payments/contexts/inventory/domain/model.py`
- `/app/token_payments/contexts/order/adapter/postgres.py`
- `/app/token_payments/contexts/store_approval/adapter/postgres.py`
- `/app/token_payments/contexts/inventory/adapter/postgres.py`
- `/app/token_payments/shared/adapter/postgres/schema.py`

## 작업

관리자가 가게 ownership과 최소 catalog를 생성할 수 있는 domain/schema contract를 추가한다. 이 phase부터 가게 관리는 전역 `STORE_OWNER` 계정 타입이 아니라 store ownership/membership으로 판단한다. 상품 설명, 카테고리, 이미지, 검색 기능은 구현하지 않는다.

1. `scripts/test_admin_store_provisioning_contracts.py`를 추가한다.
   - 가게 관리 권한은 `auth_users.role = STORE_OWNER`가 아니라 store ownership/membership에서 결정되어야 한다.
   - public login request body나 관리자 provisioning command가 전역 `STORE_OWNER` role을 부여하지 않아야 한다.
   - 이미 `CUSTOMER`로 가입된 wallet도 새 계정이나 role 변경 없이 store owner가 될 수 있어야 한다.
   - 같은 wallet로 두 번째 `auth_users` row를 만들면 안 된다.
   - 같은 사용자가 고객 checkout과 가게 관리를 함께 할 수 있어야 한다.
   - 가게 설정은 owner 계정이 아니라 store 단위에 `storeWallet`, `supportedChainIds`로 저장되어야 한다.
   - 상품 등록 contract는 `storeId`, `productId`, `name`, crypto price, `initialTotalStock`, availability만 요구한다.
   - product description/category/tags/search metadata는 future scope로 문서화하고 현재 required field로 만들지 않는다.
2. canonical store catalog contract를 추가한다.
   - 권장 위치: `/app/token_payments/contexts/store_catalog/domain/model.py`
   - `StoreProfile`은 `store_id`, `owner_user_id`, `active`, `store_wallet`, `supported_chain_ids`를 가진다.
   - 여러 관리자/직원 권한 확장을 고려한다면 `StoreMembership` 또는 `store_catalog_store_memberships`를 추가하고 `OWNER`/`MANAGER` 같은 store-scoped role을 둔다.
   - `StoreProduct`는 `store_id`, `product_id`, `name`, `price`, `active`를 가진다.
   - 같은 store 안에서 product id 중복을 허용하지 않는다.
3. PostgreSQL schema에 최소 canonical table을 추가한다.
   - 권장 테이블: `store_catalog_stores`, `store_catalog_products`
   - 권장 확장 테이블: `store_catalog_store_memberships` (`store_id`, `user_id`, `role`, `active`)
   - 기존 `order_stores`, `order_store_products`, `store_approval_stores`, `store_approval_products`, `product_inventory`는 checkout/runtime projection으로 유지한다.
   - 기존 projection table/column을 rename/drop하지 말고 additive schema change로 유지한다.
   - `owner_user_id` FK를 추가한다면 기존 seed/backfill에서 owner `auth_users` row가 먼저 존재하도록 보장한다.
   - live local DB compatibility가 필요한 column/table은 `POSTGRES_SCHEMA_COMPATIBILITY_SQL`에도 bounded additive update를 추가한다.
   - `inventory_audit_log`는 store owner/member actor가 전역 `STORE_OWNER` role을 갖는다고 가정하면 안 된다.
4. auth user role, store ownership, projection table의 관계를 문서화한다.
   - 현재 `auth_users.wallet_address` unique 제약 때문에 같은 wallet은 한 user identity에만 연결된다.
   - 고객으로 쓰던 wallet을 owner로 쓰는 경우 기존 user id를 재사용하고 store ownership/membership을 추가한다.
   - 고객 profile/order history는 보존한다.
   - `ADMIN`은 플랫폼 운영 권한이고, store owner는 전역 계정 role이 아니라 특정 store와 user의 관계다.
5. 기존 `STORE_OWNER` 사용 지점을 전환 계획에 포함한다.
   - 기존 enum/value는 backward compatibility를 위해 당장 삭제하지 않아도 되지만, 새 실행 경로와 새 테스트는 store ownership 기반이어야 한다.
   - `/store-owner/*` API는 `ADMIN` 또는 해당 store owner/member 여부로 판단해야 한다.
   - audit command/schema도 `CUSTOMER` role owner가 mutation할 때 CHECK constraint나 `UserRole.STORE_OWNER` coercion 때문에 실패하지 않아야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_admin_store_provisioning_contracts.py scripts/test_auth_api_session_runtime.py scripts/test_postgres_context_repositories.py scripts/test_store_owner_inventory_query_api.py scripts/test_inventory_authz_audit_idempotency.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. schema/domain contract 테스트를 먼저 추가하고 실패를 확인한다.
2. domain/schema/adapter contract를 구현한 뒤 AC를 실행한다.
3. `/phases/21-admin-store-catalog-provisioning/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- `/auth/sessions` 또는 public login flow에 `role=STORE_OWNER` 선택 기능을 추가하지 마라.
- 관리자 provisioning에서도 전역 `STORE_OWNER` role을 새 권한 모델의 필수 조건으로 만들지 마라.
- 기존 customer wallet을 owner로 만들 때 customer identity/order history를 잃게 하지 마라.
- 상품 설명, 카테고리, 태그, 검색 API를 이 step에 넣지 마라.
- checkout projection table을 유일한 상품 원장처럼 계속 확장하지 마라.
- 기존 checkout/payment/store approval runtime이 읽는 projection table을 제거하거나 read path를 한 번에 갈아엎지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 1: admin-store-ownership-provisioning-api

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/api/auth.py`
- `/app/token_payments/api/idempotency.py`
- `/app/token_payments/contexts/auth/application/service.py`
- `/app/token_payments/contexts/auth/adapter/postgres.py`
- `/app/token_payments/runtime/session_transport.py`
- `/app/token_payments/runtime/composition.py`
- `/phases/21-admin-store-catalog-provisioning/index.json`

## 작업

관리자가 기존 또는 신규 사용자에게 store ownership을 연결하고 가게를 생성하는 HTTP API를 추가한다. 이 step은 전역 `STORE_OWNER` 계정 타입을 만들지 않는다.

1. `scripts/test_admin_store_provisioning_api.py`를 추가한다.
   - `ADMIN` session만 사용자 생성/조회와 가게 생성/ownership 연결이 가능해야 한다.
   - `CUSTOMER`, store owner/member, unauthenticated request는 admin provisioning route에서 거부되어야 한다.
   - 신규 wallet은 일반 user identity로 생성되어야 하며, 전역 `STORE_OWNER` role을 부여하지 않아야 한다.
   - 이미 존재하는 wallet은 새 계정을 만들지 않고 기존 user id를 ownership target으로 사용해야 한다.
   - 이미 해당 store ownership/membership이 있으면 같은 request에 대해 idempotent result를 반환해야 한다.
   - 기존 wallet 처리 결과는 `userCreated`, `userReused`, `ownershipCreated`, `alreadyProvisioned`, `conflict`처럼 구분 가능해야 한다.
   - 가게 생성은 `ownerUserId`, `storeWalletAddress`, `supportedChainIds`, `active`를 저장해야 한다.
   - 가게 생성은 canonical `store_catalog_stores`와 runtime projection인 `order_stores`, `store_approval_stores`를 한 transaction에서 맞춰야 한다.
   - checkout은 `order_stores.store_wallet_address`와 `supported_chain_ids`를 직접 읽으므로 projection 누락이 checkout 실패로 이어져야 한다.
2. route manifest에 관리자 provisioning endpoint를 추가한다.
   - 권장 route: `POST /admin/store-users` (`createOrReuseStoreUser`)
   - 권장 route: `POST /admin/stores` (`createStore`)
   - 권장 route: `POST /admin/stores/{storeId}/memberships` (`grantStoreMembership`) if membership table is added.
3. framework-neutral API facade를 추가한다.
   - cookie auth context의 server-side role만 신뢰한다.
   - request body의 actor role이나 platform role 값을 신뢰하지 않는다.
4. runtime composition에 새 facade와 routes를 연결한다.
   - live path에서는 dev `X-User-*` header fallback을 사용하지 않는다.
   - CSRF/cookie guard 적용 방식을 기존 mutating routes와 맞춘다.
5. 최초 `ADMIN` 계정 bootstrap 방식은 local seed/DB bootstrap으로 명확히 문서화한다.
   - FK나 ownership constraint를 추가하는 경우 Postman seed에도 owner `auth_users` row를 추가한다.
6. 기존 store-owner inventory route의 권한 모델을 전환한다.
   - `role == STORE_OWNER`가 아니라 authenticated `user_id`가 store owner/member인지 확인한다.
   - `ADMIN`은 전체 store 조회/변경 override를 유지한다.
   - own-store list는 owner/member 관계로 필터링한다.
   - inventory audit에 기록되는 actor 정보는 store-scoped permission과 platform role을 혼동하지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_admin_store_provisioning_api.py scripts/test_store_owner_inventory_query_api.py scripts/test_inventory_authz_audit_idempotency.py scripts/test_fastapi_asgi_public_contracts.py scripts/test_live_api_facade_wiring.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. admin provisioning API 테스트를 먼저 추가하고 실패를 확인한다.
2. API facade, route manifest, runtime composition을 구현한 뒤 AC를 실행한다.
3. `/phases/21-admin-store-catalog-provisioning/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 가게 주인이 public self-signup으로 자기 platform role을 올릴 수 있게 하지 마라.
- `ADMIN` 권한 검사를 request body field에 의존하지 마라.
- 신규 또는 기존 user에 전역 `STORE_OWNER` role을 필수로 부여하지 마라.
- 기존 customer wallet을 owner로 provision할 때 동일 wallet의 두 번째 `auth_users` row를 만들지 마라.
- owner로 승격된 사용자가 기존 customer checkout profile/order history를 잃게 하지 마라.
- 가게 wallet/chain 설정을 owner 계정 전역 설정으로 저장하지 마라.
- `store_catalog_stores`만 쓰고 `order_stores` 또는 `store_approval_stores` projection 생성을 누락하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

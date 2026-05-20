# Step 3: ownership-authz-audit-idempotency

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/app/token_payments/api/idempotency.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/runtime/security.py`
- `/app/token_payments/runtime/session_transport.py`
- `/app/token_payments/shared/adapter/postgres/idempotency.py`
- `/app/token_payments/shared/adapter/transactions.py`
- `/app/token_payments/contexts/inventory/adapter/postgres.py`
- `/scripts/test_inventory_authz_audit_idempotency.py`
- `/scripts/test_csrf_cors_request_guard.py`
- `/phases/21-admin-store-catalog-provisioning/index.json`

## 작업

관리자 provisioning mutation과 store-owner API의 ownership 기반 권한, 감사, 멱등성, rollback 경계를 고정한다.

1. `scripts/test_admin_catalog_projection_consistency.py`를 추가한다.
   - 모든 관리자 mutation은 `ADMIN` role을 server-side session claim에서만 읽어야 한다.
   - `Idempotency-Key`가 없으면 거부되어야 한다.
   - 같은 key 재시도는 owner/store/product/projection/audit row를 중복 생성하지 않아야 한다.
   - 같은 key로 다른 payload를 보내면 conflict로 거부해야 한다.
   - 기존 `CUSTOMER` wallet에 store ownership을 부여해도 같은 user id를 유지해야 한다.
   - 전역 `STORE_OWNER` role 없이도 owning/member store inventory 조회와 mutation이 가능해야 한다.
   - `CUSTOMER` role owner/member가 inventory mutation을 수행해도 command validation과 audit insert가 실패하지 않아야 한다.
   - customer profile이 이미 있으면 보존하고, 없으면 필요한 경우 별도 customer profile 생성을 강제하지 않는다.
   - projection write 중 하나가 실패하면 canonical/product/inventory/projection이 부분 생성 상태로 남지 않아야 한다.
2. 감사 기록을 추가한다.
   - actor admin user id, target owner/store/product, action, request id, idempotency key, before/after 핵심 값을 기록한다.
   - customer wallet에 store ownership/membership을 부여한 경우 previous ownership state와 resulting ownership state를 기록한다.
   - inventory mutation audit은 platform role(`CUSTOMER`/`ADMIN`)만으로 권한을 설명하지 말고 store-scoped role(`OWNER`/`MANAGER`) 또는 equivalent permission context를 기록한다.
   - 기존 `inventory_audit_log.actor_role` CHECK가 `STORE_OWNER`/`ADMIN`만 허용해 CUSTOMER owner를 막지 않도록 schema/adapter를 조정한다.
   - 민감한 cookie/token/signature 값은 감사 row나 로그에 남기지 않는다.
3. 기존 request guard와 일관되게 CSRF를 적용한다.
   - cookie auth mutating request는 CSRF token이 필요하다.
   - local/dev fallback header는 live path에서 허용하지 않는다.
4. transaction boundary를 명확히 한다.
   - project-specific orchestration은 application service/adapter에 두고 `scripts/execute.py`에 넣지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_admin_catalog_projection_consistency.py scripts/test_admin_store_provisioning_api.py scripts/test_store_owner_product_registration_api.py scripts/test_store_owner_inventory_query_api.py scripts/test_store_owner_inventory_mutation_api.py scripts/test_csrf_cors_request_guard.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. authz/audit/idempotency/rollback 테스트를 먼저 추가하고 실패를 확인한다.
2. handler/adapter/security/docs를 구현한 뒤 AC를 실행한다.
3. `/phases/21-admin-store-catalog-provisioning/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 관리자 권한을 client-provided body field나 query parameter에 의존하지 마라.
- wallet unique 제약을 우회하려고 동일 wallet의 duplicate user를 만들지 마라.
- store ownership 검사를 전역 `STORE_OWNER` role 검사로 대체하지 마라.
- audit schema나 command validation에서 전역 `STORE_OWNER` role을 store owner/member mutation의 필수 조건으로 만들지 마라.
- audit row에 access token, refresh token, SIWE message, signature, private key를 저장하지 마라.
- duplicate idempotency retry에서 projection이나 inventory row를 추가로 만들지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

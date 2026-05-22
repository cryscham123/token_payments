# Step 0: security-refactor-audit-invariants

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/PRD.md`
- `/docs/API_SPEC.md`
- `/docs/HARNESS.md`
- `/docs/ADR.md`
- `/docs/SEQUENCES.md`
- `/docs/DOMAIN_MODEL.md`
- `/app/token_payments/api/`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/runtime/session_transport.py`
- `/app/token_payments/runtime/security.py`
- `/app/token_payments/contexts/auth/`
- `/app/token_payments/contexts/inventory/`
- `/app/token_payments/contexts/order/`
- `/app/token_payments/contexts/payment/`
- `/app/token_payments/contexts/store_catalog/`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/postman/token-payments.local.postman_collection.json`
- `/postman/expected/token-payments.api.expected.json`
- `/phases/23-user-store-product-profile-catalog/index.json`
- `/phases/25-multi-wallet-accounts/index.json`

## 작업

API 보안 계약, write authorization, bounded context boundary, runtime composition, membership projection을 한 번에 정리하기 위한 audit와 완료 후 불변조건을 명시한다.

1. `scripts/test_security_refactor_audit.py`를 추가한다.
   - `orderId`, `customerId`, `storeId`, `sessionId`, `refreshTokenHash`, `refreshTokenHash.hash`, `refreshTokenHash.salt`, `refreshTokenHash.rotationVersion`의 API response 노출 위치를 전수 확인해야 한다.
   - payment tx hash submission request/response와 idempotency fallback에서 internal order id가 외부 계약으로 남아 있는지 확인해야 한다.
   - inventory mutation에서 `inventory:write` scope 없이 role/ownership fallback으로 통과하는 경로를 확인해야 한다.
   - product registration은 API layer scope check와 service layer store ownership/membership check가 분리되어 있는지 확인해야 한다.
   - `inventory/application/commands.py`, `store_catalog/application/service.py`, `order/adapter/postgres.py`의 cross-context domain import를 확인해야 한다.
   - `runtime/composition.py`의 단일 파일 조립 책임และ 크기를 확인해야 한다.
   - `store_catalog_store_memberships`와 `auth_group_memberships`의 source-of-truth/projection 역할과 직접 write API를 확인해야 한다.
   - **(추가)** `POST /merchant/stores` 및 `POST /merchant/stores/{publicStoreId}/products` 요청 본문에 클라이언트가 식별자(`storeId`, `publicStoreId`, `productId`, `publicProductId`)를 제공할 시 `400 Bad Request`로 거부하는지 확인해야 한다.
   - **(추가)** `POST /merchant/stores/{publicStoreId}/products` 요청이 기존 제품 데이터에 대해 덮어쓰기(upsert) 동작을 유발하지 않고 신규 등록 역할만 수행하는지 확인해야 한다.
2. architecture invariant를 문서화한다.
   - 외부 API request/response는 internal `orderId`, `customerId`, `sessionId`, `refreshTokenHash`를 노출하지 않는다.
   - payment submit의 외부 식별자는 `trackingId`이고, server 내부에서만 order/payment id로 resolve한다.
   - idempotency fallback key는 raw internal id가 아니라 `trackingId` 기반 namespace 또는 hash를 사용한다.
   - write authorization은 scope + canonical store membership을 fail-closed로 검증한다.
   - **(추가)** 리소스 생성 POST API는 클라이언트 측 식별자 지정을 허용하지 않으며, POST는 중복 업데이트(Upsert) 동작을 지원하지 않는다.
   - read projection lag는 read model에만 허용된다. inventory/product write 같은 보안 쓰기 작업은 auth RBAC projection만으로 권한을 확정하지 않는다.
   - bounded context 간에는 domain object 직접 import 대신 port, DTO, ACL, snapshot/query model을 사용한다.
   - auth RBAC membership projection은 write authority가 아니다.
3. 기존 public contract 테스트를 실패하도록 갱신한다.
   - 금지 필드가 response payload에 있으면 실패해야 한다.
   - legacy fallback이 inventory write를 통과시키면 실패해야 한다.
   - legacy auth group membership 직접 write API가 canonical write path처럼 남아 있으면 실패해야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_security_refactor_audit.py scripts/test_auth_api_session_runtime.py scripts/test_checkout_tracking_payment_api.py scripts/test_store_owner_inventory_mutation_api.py scripts/test_store_owner_product_registration_api.py scripts/test_architecture_contract_alignment.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. audit/invariant 테스트를 먼저 추가하고 실패를 확인한다.
2. audit 결과를 근거로 step 1~5의 수정 대상을 확정한다.
3. `/phases/26-security-hardening-architecture-refactoring/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- internal id 노출을 snapshot fixture 편의 목적으로 allowlist에 넣지 마라.
- session hash/salt/rotation metadata를 redaction 없이 테스트 fixture에 남기지 마라.
- projection lag를 쓰기 권한 허용 근거로 문서화하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

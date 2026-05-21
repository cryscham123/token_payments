# Step 4: rbac-seed-audit-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/README.md`
- `/app/README.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/postman/fixtures/token-payments.local.seed-plan.json`
- `/postman/token-payments.local.postman_collection.json`
- `/postman/expected/token-payments.api.expected.json`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/scripts/test_route_surface_contract_docs.py`
- `/scripts/test_local_env_seed_contract.py`
- `/phases/22-resource-scoped-rbac/index.json`

## 작업

RBAC seed, audit, public contract를 정리하고 legacy global role 의존을 phase 범위에서 제거한다.

1. `scripts/test_rbac_public_contracts.py`를 추가한다.
   - docs/API spec이 global `User.role`이 아니라 group membership/permission model을 설명해야 한다.
   - local seed plan은 platform group, merchant group, personal customer group, 기본 roles/permissions를 포함해야 한다.
   - seed role templates는 최소 `PERSONAL_CUSTOMER`, `MERCHANT_OWNER`, `MERCHANT_MANAGER`, `MERCHANT_STAFF`, `PLATFORM_OPERATOR`, `PLATFORM_ADMIN`을 포함해야 한다.
   - merchant-facing role catalog는 non-owner merchant staff templates만 반환하고 raw permission mutation capability를 노출하지 않아야 한다.
   - audit payload는 `actorUserId`, optional `groupId`, `permission`, `resourceType`, `resourceId`를 보존해야 한다.
   - Postman expected fixtures가 `X-User-Role` 또는 request body role escalation에 의존하지 않아야 한다.
2. seed와 fixtures를 갱신한다.
   - platform admin user는 platform group membership으로 표현한다.
   - merchant owner/store manager는 merchant group membership으로 표현한다.
   - customer checkout user는 personal group membership으로 표현한다.
   - role/permission catalog는 local seed/static fixture로 제공한다. Runtime full CRUD role/permission 관리 API는 이 phase에서 열지 않는다.
   - store provisioning은 merchant group 생성/연결과 initial owner membership을 함께 seed/provisioning contract로 남긴다.
3. docs를 갱신한다.
   - 권한 판단 흐름과 forbidden error를 명시한다.
   - group/role/permission 관리 API는 admin seed/provisioning 범위, merchant member/invitation 범위, future full CRUD API 범위를 구분한다.
   - 기존 admin membership provisioning route는 merchant group membership 생성/수정으로 연결하되, role/permission CRUD route를 함께 추가하지 않는다.
   - platform/personal group CRUD, platform role assignment, owner transfer는 merchant/customer API가 아님을 명시한다.
   - 검색, DID, 이메일 복구는 future scope로 유지한다.
4. phase metadata를 검증한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_rbac_public_contracts.py scripts/test_route_surface_contract_docs.py scripts/test_local_env_seed_contract.py scripts/test_api_seed_expected_responses.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. public contract 테스트를 먼저 추가하고 실패를 확인한다.
2. docs/fixtures/seed/audit contract를 갱신한 뒤 AC를 실행한다.
3. `/phases/22-resource-scoped-rbac/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- docs에 global `ADMIN`/`STORE_OWNER` role을 새 권한 source로 남기지 마라.
- role/permission full CRUD API를 이 phase의 필수 route surface로 만들지 마라.
- merchant role catalog를 raw permission editor처럼 만들지 마라.
- seed fixture에 production secret, private key, seed phrase, real token을 넣지 마라.
- 검색, DID, 이메일 계정 복구 API를 이 phase에 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

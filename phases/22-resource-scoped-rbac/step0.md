# Step 0: rbac-domain-schema-reset

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/contexts/auth/adapter/postgres.py`
- `/app/token_payments/shared/adapter/postgres/schema.py`
- `/app/token_payments/contexts/inventory/application/commands.py`
- `/app/token_payments/contexts/inventory/application/ports.py`
- `/phases/21-admin-store-catalog-provisioning/index.json`

## 작업

전역 `User.role` 중심 권한 모델을 제거하고, user identity와 group-scoped RBAC를 분리하는 domain/schema contract를 추가한다. 이 phase는 production compatibility를 고려하지 않는다. 이상한 legacy role 분기와 전역 `STORE_OWNER` 전제를 제거하는 방향으로 진행한다.

1. `scripts/test_rbac_domain_schema_contracts.py`를 추가한다.
   - `User`는 identity, login state, wallet/account reference만 갖고 전역 role을 갖지 않아야 한다.
   - 신규 RBAC 모델은 `Group`, `GroupMembership`, `Role`, `Permission`, `RolePermission`을 포함해야 한다.
   - group type은 최소 `PLATFORM`, `MERCHANT`, `PERSONAL`을 지원해야 한다.
   - `Group`은 user처럼 직접 행동하는 actor가 아니라 permission scope/resource boundary다. Audit actor는 계속 `actorUserId`를 기준으로 남긴다.
   - nested group은 이 phase 범위가 아니다. `GroupMembership`의 member는 user이며, group 안에 group을 넣는 hierarchy를 만들지 않는다.
   - `PERSONAL` group은 customer 기본 self-scope를 전역 `User.role` 없이 표현하기 위한 얇은 scope로 유지한다.
   - role은 permission 묶음이고, 권한 판단은 role 이름 직접 비교가 아니라 permission lookup으로 가능해야 한다.
   - 같은 user가 personal customer group과 merchant group, platform group에 동시에 속할 수 있어야 한다.
   - inactive membership이나 inactive role은 permission을 부여하지 않아야 한다.
   - schema compatibility SQL은 신규 RBAC table을 additive하게 만들고, `auth_users.role` 의존을 새 실행 경로에서 제거해야 한다.
2. auth domain 모델을 갱신한다.
   - `UserRole` enum과 `User.role`은 새 실행 경로에서 제거한다.
   - 필요한 경우 migration 중 import 정리를 위해 작은 compatibility alias를 임시로 둘 수 있지만, application/API policy 판단에는 사용하지 않는다.
   - `GroupId`, `RoleId`, `PermissionName` 같은 value object를 추가한다.
   - `GroupMembership`은 `user_id`, `group_id`, `role_id`, `active`, `joined_at`을 가져야 한다.
3. PostgreSQL schema를 갱신한다.
   - 권장 테이블: `auth_groups`, `auth_roles`, `auth_permissions`, `auth_role_permissions`, `auth_group_memberships`
   - `auth_groups`는 `group_type`, optional `resource_type`, optional `resource_id`를 가진다.
   - merchant store와 group을 연결할 수 있도록 store catalog schema에 `group_id` 참조를 추가한다.
   - `auth_users.role` column을 새 code path에서 읽지 않도록 adapter contract를 바꾼다. 실제 drop은 테스트/fixture 정리 후 별도 migration으로 처리해도 된다.
4. docs에 권한 모델을 정리한다.
   - `User`는 계정 identity이고 권한 holder가 아니다.
   - `GroupMembership`이 user와 resource scope를 연결한다.
   - `Role`은 permission bundle이며, permission이 API authorization의 source of truth다.
   - role/permission catalog는 우선 seed/static contract로 시작하고, full CRUD 관리 API는 별도 future surface로 구분한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_rbac_domain_schema_contracts.py scripts/test_auth_context_skeleton.py scripts/test_postgres_context_repositories.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. RBAC domain/schema 테스트를 먼저 추가하고 실패를 확인한다.
2. auth domain/schema/postgres compatibility code를 갱신한 뒤 AC를 실행한다.
3. `/phases/22-resource-scoped-rbac/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 새 권한 판단을 `User.role`, `X-User-Role`, `STORE_OWNER`, `ADMIN` 직접 비교에 의존하게 만들지 마라.
- group을 user substitute나 nested organization tree로 모델링하지 마라.
- group/role 모델을 store catalog projection table에만 묻어두지 마라.
- 검색, DID, 이메일 복구, stablecoin 결제를 이 step에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

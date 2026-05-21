# Step 3: merchant-group-membership-api

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/contexts/auth/`
- `/app/token_payments/contexts/store_catalog/`
- `/app/token_payments/api/`
- `/app/token_payments/runtime/composition.py`
- `/scripts/test_rbac_policy_enforcement.py`
- `/scripts/test_admin_store_provisioning_contracts.py`
- `/phases/22-resource-scoped-rbac/index.json`

## 작업

Merchant store team 관리에 필요한 group membership API를 추가한다. 이 step은 별도 phase를 만들지 않고 phase 22 RBAC 안에서 처리한다. Role/permission catalog 자체는 seed/static으로 유지하고, merchant-facing API는 server-defined merchant role template 선택만 허용한다.

1. `scripts/test_merchant_group_membership_api.py`를 추가한다.
   - store provisioning은 merchant group을 생성하거나 연결하고 initial `MERCHANT_OWNER` membership을 부여해야 한다.
   - admin/provisioning surface는 `admin:provision` 또는 `rbac:manage`로 initial owner assignment를 수행할 수 있어야 한다.
   - merchant-facing APIs는 `MERCHANT_OWNER` grant/revoke/transfer를 허용하지 않아야 한다.
   - merchant member list/invitation list는 scoped merchant group 안의 사용자와 초대만 반환해야 한다.
   - invitation create는 `merchant_member:invite` permission과 scoped store/group을 확인해야 한다.
   - invitation accept는 authenticated target user만 수행하고, 만료/취소/중복 초대를 거부해야 한다.
   - invitation revoke는 scoped `merchant_member:invite` 또는 `merchant_member:manage` permission이 필요해야 한다.
   - member role update는 server-defined non-owner merchant staff role template만 허용하고 raw permission array, platform role, personal role을 거부해야 한다.
   - member removal은 non-owner staff만 허용하고 마지막 owner 제거를 방지해야 한다.
   - 같은 user가 여러 merchant group에 속해도 요청 `storeId`의 merchant group에 대해서만 동작해야 한다.
2. merchant membership domain/application contract를 추가한다.
   - 권장 모델: `GroupInvitation`, `InvitationStatus`, `MerchantRoleTemplate`.
   - 권장 service: `MerchantMembershipService` 또는 auth context 내 명확한 group membership application service.
   - role template catalog는 repository/seed에서 읽되 API request가 permission list를 직접 제출하지 못하게 한다.
3. API routes를 추가한다.
   - `GET /merchant/stores/{storeId}/members`
   - `GET /merchant/stores/{storeId}/invitations`
   - `POST /merchant/stores/{storeId}/invitations`
   - `POST /merchant/invitations/{invitationId}/accept`
   - `POST /merchant/invitations/{invitationId}/revoke`
   - `PATCH /merchant/stores/{storeId}/members/{userId}`
   - `DELETE /merchant/stores/{storeId}/members/{userId}`
   - `GET /merchant/role-catalog`
4. PostgreSQL schema/adapter를 갱신한다.
   - 권장 테이블: `auth_group_invitations`
   - invitation target은 wallet/email/user id 중 지원하는 값을 명확히 구분하고 bounded validation을 거친다.
   - uniqueness/idempotency는 active invitation과 accepted membership 중복 생성을 막아야 한다.
5. docs와 Postman contract 후보를 갱신한다.
   - platform group creation, platform role assignment, personal group management, role/permission CRUD, owner transfer는 merchant/customer API가 아님을 명시한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_merchant_group_membership_api.py scripts/test_rbac_policy_enforcement.py scripts/test_admin_store_provisioning_contracts.py scripts/test_route_surface_contract_docs.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. merchant membership API 테스트를 먼저 추가하고 실패를 확인한다.
2. domain/schema/application/API/runtime wiring을 갱신한 뒤 AC를 실행한다.
3. `/phases/22-resource-scoped-rbac/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- merchant API에서 `MERCHANT_OWNER`, `PLATFORM_OPERATOR`, `PLATFORM_ADMIN`, `PERSONAL_CUSTOMER`를 assign할 수 있게 만들지 마라.
- request body의 role/permission 문자열을 그대로 권한으로 신뢰하지 마라.
- owner transfer를 invitation/member update API에 넣지 마라.
- group nesting, organization hierarchy, team hierarchy를 이 step에 넣지 마라.
- role/permission full CRUD API를 merchant surface로 열지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

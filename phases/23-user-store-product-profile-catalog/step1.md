# Step 1: store-profile-business-details

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/contexts/store_catalog/domain/model.py`
- `/app/token_payments/contexts/store_catalog/`
- `/app/token_payments/api/inventory.py`
- `/app/token_payments/runtime/composition.py`
- `/scripts/test_admin_store_provisioning_contracts.py`
- `/scripts/test_rbac_policy_enforcement.py`
- `/phases/23-user-store-product-profile-catalog/index.json`

## 작업

가게를 결제 projection이 아니라 canonical business profile로 보강한다.

1. `scripts/test_store_profile_business_details.py`를 추가한다.
   - store profile은 `store_id`, `group_id`, `display_name`, `description`, `status`, `support_email`, `business_registration_label`, `created_at`, `updated_at`을 가져야 한다.
   - public store detail은 공개 가능한 field만 반환해야 한다.
   - `store:write`는 `display_name`, `description`, 공개/비공개 support contact 같은 business profile field만 수정할 수 있어야 한다.
   - `display_name`은 중복 가능하지만 bounded text validation을 거쳐야 한다. `description`과 `business_registration_label`도 길이 상한, 제어 문자, null byte, 로그/CSV 오염 위험 문자를 검증해야 한다.
   - store profile 입력값은 SQL 문자열 보간 없이 parameter binding으로 저장되고, HTML/UI 출력에서는 escaping되어야 한다.
   - `store:manage` 또는 platform approval은 store status 같은 민감 운영 설정에만 사용한다.
   - slug는 이 phase에 추가하지 않는다. Public/merchant lookup은 안정적인 `store_id` 기반으로 유지하고, human-readable URL은 future scope로 둔다.
   - checkout projection table을 store canonical source로 계속 확장하지 않아야 한다.
2. store catalog domain/schema를 갱신한다.
   - 기존 `StoreProfile`이 있다면 payment wallet/chain settings와 business profile field를 명확히 분리한다.
   - settlement wallet/supported chains 변경은 store business profile update가 아니라 별도 policy-gated payment settings flow로 남긴다.
   - 권장 테이블: `store_catalog_store_profiles` 또는 기존 `store_catalog_stores` 확장.
   - group-scoped RBAC의 merchant group과 store를 연결한다.
3. store profile API를 추가한다.
   - 권장 operation: `getStoreProfile`, `updateStoreProfile`, `listMerchantStores`
   - update는 RBAC policy `store:write`를 사용한다.
   - public response와 owner/operator response를 구분한다.
   - owner transfer, member invite/remove, role/permission 변경은 store profile API가 아니라 RBAC/membership provisioning surface의 책임이다.
4. docs와 seed를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_store_profile_business_details.py scripts/test_admin_store_provisioning_contracts.py scripts/test_rbac_policy_enforcement.py scripts/test_route_surface_contract_docs.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. store profile 테스트를 먼저 추가하고 실패를 확인한다.
2. domain/schema/API/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/23-user-store-product-profile-catalog/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- store owner 권한을 user global role로 되돌리지 마라.
- slug를 필수 profile field나 route key로 추가하지 마라.
- private business/contact fields를 public store listing에 무조건 노출하지 마라.
- payment settlement wallet 설정과 public store profile을 한 DTO에 섞어 노출하지 마라.
- owner transfer/group membership 변경을 `updateStoreProfile`에 넣지 마라.
- store profile 입력값을 SQL fragment, HTML, log line, CSV cell로 신뢰하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

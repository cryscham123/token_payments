# Step 0: user-profile-domain-schema

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/contexts/auth/application/service.py`
- `/app/token_payments/contexts/auth/adapter/postgres.py`
- `/app/token_payments/api/auth.py`
- `/app/token_payments/shared/adapter/postgres/schema.py`
- `/phases/22-resource-scoped-rbac/index.json`

## 작업

Auth identity와 표시/연락용 user profile을 분리한다. 이메일 계정 복구와 DID는 future scope로 유지하고, 이 step은 사용자 정보 보완과 redaction/audit contract만 다룬다.

1. `scripts/test_user_profile_contracts.py`를 추가한다.
   - `User` identity는 login/session/wallet/group membership의 주체이고, profile display fields와 분리되어야 한다.
   - `UserProfile`은 `user_id`, `display_name`, optional `email`, `email_verified_at`, `locale`, `timezone`, `status`, `created_at`, `updated_at`을 가져야 한다.
   - email field가 존재하더라도 email/password login 또는 email account recovery를 활성화하지 않아야 한다.
   - public response는 민감한 contact field를 기본 노출하지 않고, owner/self 또는 permission 있는 operator만 상세 조회할 수 있어야 한다.
   - profile update는 authenticated self 또는 `user:manage` permission으로만 가능해야 한다.
   - `display_name`은 중복 가능하지만 bounded text validation을 거쳐야 한다. 빈 문자열, 제어 문자, 과도한 길이, null byte, 로그/CSV 오염 위험 문자는 거부하거나 정규화해야 한다.
   - `display_name`, `email`, `locale`, `timezone` 같은 사용자 입력값은 SQL 문자열 보간 없이 parameter binding으로 저장되고, HTML/UI 출력에서는 escaping되어야 한다.
2. auth/profile domain을 추가한다.
   - 권장 위치: `/app/token_payments/contexts/auth/domain/profile.py` 또는 auth domain 내 명확한 profile model.
   - `UserProfileStatus`는 최소 `ACTIVE`, `SUSPENDED`, `DELETED`를 둔다.
   - `DELETED`는 profile tombstone 상태다. 원래 `display_name`, `email` 같은 PII/contact fields는 redacted/null 처리하고, auth identity/order/audit reference 보존과 혼동하지 않는다.
   - account login disable/revoke는 auth identity/session policy에서 다루며, profile `DELETED`만으로 인증 정책을 대체하지 않는다.
   - profile validation은 display name length, email shape, locale/timezone text bounds, control character rejection, Unicode normalization policy를 포함한다.
3. PostgreSQL schema와 adapter를 갱신한다.
   - 권장 테이블: `auth_user_profiles`
   - `auth_users`와 1:1로 연결하되 auth identity table에 display/contact fields를 계속 추가하지 않는다.
   - schema compatibility SQL을 additive하게 갱신한다.
4. API contract를 추가 또는 갱신한다.
   - 권장 operation: `getCurrentUserProfile`, `updateCurrentUserProfile`, optional admin `getUserProfile`
   - `ApiAuthContext`와 RBAC policy를 사용하고 legacy role fallback을 사용하지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_user_profile_contracts.py scripts/test_auth_api_session_runtime.py scripts/test_rbac_policy_enforcement.py scripts/test_postgres_context_repositories.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. user profile contract 테스트를 먼저 추가하고 실패를 확인한다.
2. domain/schema/API/runtime wiring을 갱신한 뒤 AC를 실행한다.
3. `/phases/23-user-store-product-profile-catalog/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- email/password login, email account recovery, DID를 이 step에 넣지 마라.
- email을 verified identity source처럼 사용하지 마라.
- profile 정보를 session cookie에 과도하게 싣지 마라.
- `DELETED` profile에 원래 contact/display PII가 그대로 남는 계약을 만들지 마라.
- profile 입력값을 SQL fragment, HTML, log line, CSV cell로 신뢰하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

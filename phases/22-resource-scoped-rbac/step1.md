# Step 1: auth-session-claims-without-global-role

## 읽어야 할 파일

- `/AGENTS.md`
- `/app/token_payments/contexts/auth/application/service.py`
- `/app/token_payments/contexts/auth/application/ports.py`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/contexts/auth/adapter/postgres.py`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/runtime/session_transport.py`
- `/app/token_payments/runtime/api_server.py`
- `/scripts/test_auth_api_session_runtime.py`
- `/scripts/test_cookie_session_transport.py`
- `/phases/22-resource-scoped-rbac/index.json`

## 작업

로그인/session claim에서 전역 role을 제거하고, authenticated user identity와 active group/scopes snapshot을 분리한다.

1. `scripts/test_rbac_auth_session_claims.py`를 추가한다.
   - SIWE login으로 생성되는 `User`와 session은 전역 role을 저장하지 않아야 한다.
   - 신규 가입 사용자는 personal group과 seed/static `PERSONAL_CUSTOMER` role membership을 얻어야 한다.
   - session payload와 cookie transport는 `role` 대신 `activeGroupId`, `groupMemberships` 또는 bounded `scopes` snapshot을 사용해야 한다.
   - `X-User-Role` fallback은 제거하거나 테스트 전용 local fallback에서도 권한 source로 사용하지 않아야 한다.
   - refresh session은 role claim을 재발급하지 않고 user/membership state를 기준으로 안전한 claim을 만든다.
2. auth application service를 갱신한다.
   - user registration 시 personal group/membership을 생성한다.
   - token issuer가 role 대신 scopes 또는 membership summary를 받을 수 있게 contract를 바꾼다.
   - current user query는 user identity와 필요한 membership summary를 조회할 수 있어야 한다.
3. API auth context를 갱신한다.
   - `ApiAuthContext.role`을 제거한다.
   - 필요한 필드는 `active_group_id`, `scopes`, `memberships` 등으로 명확히 둔다.
   - 중요한 mutation은 claim snapshot만 믿지 않고 policy/repository를 재조회한다는 문서/테스트를 남긴다.
4. runtime request context extraction을 갱신한다.
   - live API에서 legacy role header를 권한 source로 받아들이지 않는다.
   - local-only fixture가 필요하면 user id/session id 중심으로 유지한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_rbac_auth_session_claims.py scripts/test_auth_api_session_runtime.py scripts/test_cookie_session_transport.py scripts/test_siwe_erc1271_auth_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. auth/session claim 테스트를 먼저 추가하고 실패를 확인한다.
2. auth service, ports, session transport, API contracts를 갱신한 뒤 AC를 실행한다.
3. `/phases/22-resource-scoped-rbac/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- session cookie에 모든 permission을 무제한으로 싣지 마라. snapshot은 bounded하고 재검증 가능해야 한다.
- `role=ADMIN` 같은 client-provided claim으로 운영자 권한을 부여하지 마라.
- wallet ownership과 group authorization을 같은 개념으로 섞지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

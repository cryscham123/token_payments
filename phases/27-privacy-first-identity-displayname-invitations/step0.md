# Step 0: privacy-first-identity-contract

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/app/token_payments/api/auth.py`
- `/app/token_payments/api/merchant.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/contexts/auth/domain/`
- `/app/token_payments/contexts/auth/application/`
- `/app/token_payments/contexts/auth/adapter/postgres.py`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/shared/adapter/postgres/schema.py`
- `/postman/token-payments.local.postman_collection.json`

## 작업

사용자 개인정보를 서버 프로필 데이터로 저장하지 않는 identity 구조로 정리한다. 이 phase는 하나의 phase 안에서 user profile, merchant invitation, OAuth identity, unlink safety, 문서/Postman 계약을 함께 맞춘다.

## 결정사항

1. User profile은 `displayName`만 저장한다.
   - `displayName`은 optional이다.
   - `displayName` 미설정 상태에서도 서비스 사용이 가능하다.
   - `email`, `emailVerifiedAt`, `locale`, `timezone`은 user profile/domain/API/schema에서 제거한다.
   - email hash도 저장하지 않는다.
2. Display name은 설정된 경우에만 active profile 사이에서 case-insensitive unique이다.
   - Korean/Unicode display name을 허용한다.
   - control character, null, log/CSV injection prefix는 거부한다.
3. Merchant-facing invitation 기본 타겟은 `targetDisplayName`이다.
   - 서버는 초대 생성 시점에 `targetDisplayName`을 active profile의 `userId`로 resolve한다.
   - 저장되는 권한 타겟은 `targetUserId`이다.
   - `targetWallet`은 advanced/fallback으로 유지한다.
   - `targetUserId`는 내부/admin/debug/Postman 계약으로 유지할 수 있다.
   - `targetEmail`은 제거한다.
4. OAuth identity는 email이 아니라 `provider + providerSubject`를 권한 식별자로 쓴다.
   - Google `email` claim은 저장하지 않는다.
   - 이메일 일치 기반 자동 병합은 금지한다.
   - 기존 EOA 계정 연동은 로그인된 세션 또는 EOA 서명으로만 허용한다.
5. Unlink는 soft revoke이다.
   - `revoked_at`을 남기고 hard delete하지 않는다.
   - 마지막 로그인 수단 unlink는 금지한다.
   - 진행 중 payment/refund/reservation에 연결된 wallet/social identity unlink는 금지한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_user_profile_contracts.py scripts/test_merchant_group_membership_api.py scripts/test_auth_order_http_routes.py scripts/test_route_surface_contract_docs.py
python3 scripts/validate_phases.py
```

## 금지사항

- email, email hash, locale, timezone을 user profile 저장 모델로 되살리지 않는다.
- Google email claim으로 기존 계정을 자동 병합하지 않는다.
- OAuth identity를 hard delete하지 않는다.
- Claude 전용 파일이나 명령을 추가하지 않는다.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 않는다.

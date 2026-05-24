# Step 1: profile-and-invitation-contract-tests

## 작업

Privacy-first profile과 displayName invitation 계약을 테스트로 먼저 고정한다.

1. `scripts/test_user_profile_contracts.py`
   - `UserProfile` dataclass에 `email`, `email_verified_at`, `locale`, `timezone` 필드가 없음을 확인한다.
   - `displayName`이 `None`이어도 active profile 생성이 가능해야 한다.
   - public/self profile payload 모두 contact/locale/timezone 필드를 반환하지 않아야 한다.
   - profile update body에서 `email`, `locale`, `timezone`을 받지 않아야 한다.
   - Postgres profile SQL과 schema compatibility가 제거된 필드를 참조하지 않아야 한다.
2. `scripts/test_merchant_group_membership_api.py`
   - `targetDisplayName` invitation이 active user profile을 `targetUserId`로 resolve해야 한다.
   - `targetEmail` 요청은 거부되어야 한다.
   - response payload에서 `targetEmail`이 없어야 한다.
3. route manifest 테스트
   - `GET /auth/me/profile`, `PATCH /auth/me/profile`가 auth route surface에 등록되어야 한다.
   - route manifest count와 docs 문구를 새 surface에 맞춘다.

## Acceptance Criteria

테스트 갱신 직후에는 기존 구현 때문에 실패해야 한다.

```bash
python3 -m pytest scripts/test_user_profile_contracts.py scripts/test_merchant_group_membership_api.py scripts/test_auth_order_http_routes.py scripts/test_route_surface_contract_docs.py
```

# Step 3: oauth-identity-unlink-contract

## 작업

OAuth identity 저장 계약과 unlink safety를 현재 phase에 문서/스키마 레벨로 고정한다.

1. `auth_oauth_identities` 스키마를 추가한다.
   - `provider`
   - `provider_subject`
   - `user_id`
   - optional linked `wallet_id`
   - `linked_at`
   - `revoked_at`
   - active `(provider, provider_subject)` unique index
2. 테스트는 email/email hash 컬럼이 존재하지 않음을 확인한다.
3. 문서에는 email 자동 병합 금지, provider subject 기반 link/login/recovery, soft unlink와 active payment safety를 명시한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_user_profile_contracts.py
```

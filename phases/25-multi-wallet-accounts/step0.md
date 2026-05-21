# Step 0: multi-wallet-domain-schema

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/contexts/auth/application/service.py`
- `/app/token_payments/contexts/auth/adapter/postgres.py`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/shared/adapter/postgres/schema.py`
- `/phases/22-resource-scoped-rbac/index.json`

## 작업

하나의 user identity가 여러 wallet을 검증/연결/해제할 수 있는 canonical wallet model을 추가한다.

1. `scripts/test_multi_wallet_domain_schema.py`를 추가한다.
   - `User`는 단일 `primary_wallet` 필드에 identity를 묶지 않아야 한다.
   - `UserWallet`은 `wallet_id`, `user_id`, `address`, `chain_id`, `wallet_type`, `verification_status`, `primary`, `linked_at`, optional `revoked_at`을 가진다.
   - 같은 `(chain_id, address)` wallet은 한 active user에게만 연결될 수 있어야 한다.
   - user는 chain별 primary wallet을 가질 수 있어야 한다.
   - revoked wallet은 login/payment selection에 사용될 수 없어야 한다.
   - EOA와 deployed smart wallet type을 구분하되 ERC-6492/counterfactual은 future scope로 남긴다.
2. auth domain/schema를 갱신한다.
   - `auth_user_wallets` table을 추가한다.
   - 기존 `auth_users.wallet_address` 의존을 새 wallet table lookup으로 전환한다.
   - login 시 wallet lookup은 `(chain_id, address)` 기준으로 수행한다.
3. PostgreSQL adapter를 갱신한다.
   - wallet repository port를 추가한다.
   - user repository는 wallet address unique lookup을 직접 소유하지 않는다.
   - schema compatibility SQL도 additive하게 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_multi_wallet_domain_schema.py scripts/test_auth_api_session_runtime.py scripts/test_siwe_erc1271_auth_public_contracts.py scripts/test_postgres_context_repositories.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. multi-wallet domain/schema 테스트를 먼저 추가하고 실패를 확인한다.
2. auth domain/schema/repository를 갱신한 뒤 AC를 실행한다.
3. `/phases/25-multi-wallet-accounts/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 같은 wallet address를 chain id 없이 unique 처리하지 마라.
- wallet link를 group/role 권한 부여와 같은 동작으로 만들지 마라.
- 이메일 복구, DID, ERC-6492를 이 step에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 0: multi-wallet-domain-schema

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/contexts/auth/application/service.py`
- `/app/token_payments/contexts/auth/adapter/postgres.py`
- `/app/token_payments/contexts/order/domain/model.py`
- `/app/token_payments/contexts/order/adapter/postgres.py`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/contexts/store_catalog/domain/model.py`
- `/app/token_payments/contexts/store_catalog/adapter/postgres.py`
- `/app/token_payments/shared/adapter/postgres/schema.py`
- `/phases/22-resource-scoped-rbac/index.json`

## 작업

하나의 user identity가 여러 wallet을 검증/연결/해제할 수 있는 canonical wallet model을 추가한다.

0. schema audit와 완료 후 불변조건을 먼저 명시한다.
   - `auth_users.wallet_address`, `auth_sessions.wallet_address`, `order_customers.wallet_address`, `store_catalog_stores.store_wallet_address`, `order_stores.store_wallet_address`의 사용 위치를 전수 확인한다.
   - `payments`, `payment_authorizations`의 wallet/asset/chain 관련 column 변경은 이 phase의 stablecoin steps와 함께 한 번의 정규화 방향으로 계획한다.
   - phase 완료 후 user/customer/session/store settlement의 source of truth는 raw wallet address 컬럼이 아니라 verified wallet model 또는 검증된 settlement wallet model이어야 한다.
   - raw wallet address snapshot이 필요한 경우에는 canonical 참조에서 파생된 immutable audit/receipt snapshot임을 컬럼명/테스트/문서에 명확히 남기고, client 입력 문자열을 source of truth로 저장하지 않는다.
1. `scripts/test_multi_wallet_domain_schema.py`를 추가한다.
   - `User`는 단일 `primary_wallet` 필드에 identity를 묶지 않아야 한다.
   - `UserWallet`은 `wallet_id`, `user_id`, `address`, `chain_id`, `wallet_type`, `verification_status`, `primary`, `linked_at`, optional `revoked_at`을 가진다.
   - 같은 `(chain_id, address)` wallet은 한 active user에게만 연결될 수 있어야 한다.
   - user는 chain별 primary wallet을 가질 수 있어야 한다.
   - revoked wallet은 login/payment selection에 사용될 수 없어야 한다.
   - EOA와 deployed smart wallet type을 구분하되 ERC-6492/counterfactual은 future scope로 남긴다.
   - `auth_sessions`는 raw `wallet_address`를 보관하지 않아야 하며, 로그인 지갑 보존이 필요하면 `login_wallet_id` 같은 canonical wallet FK를 사용해야 한다.
   - `order_customers`는 raw `wallet_address`를 보관하지 않아야 한다. 결제에 쓰는 지갑은 customer row가 아니라 payment authorization/checkout selection에 연결해야 한다.
   - store settlement wallet은 임의 text address가 아니라 verified wallet 참조 또는 별도 `store_wallets`/`store_settlement_wallets` 모델의 검증된 row를 통해 지정되어야 한다.
2. auth domain/schema를 갱신한다.
   - `auth_user_wallets` table을 추가한다.
   - 기존 `auth_users.wallet_address` 의존을 새 wallet table lookup으로 전환한다.
   - login 시 wallet lookup은 `(chain_id, address)` 기준으로 수행한다.
   - `auth_sessions.wallet_address`를 제거하거나 `login_wallet_id` FK로 전환한다. 세션 refresh/lookup은 `user_id`와 session token metadata를 기준으로 동작하고, wallet address text에 의존하지 않는다.
   - 기존 단일 wallet data는 backfill로 `auth_user_wallets`에 이동하고, `(chain_id, normalized_address)` active uniqueness와 `login_wallet_id` FK/nullability 정책을 함께 정의한다.
3. order/store settlement schema를 정규화한다.
   - `order_customers.wallet_address`를 제거하고 customer identity는 `user_id`/customer profile 정보로만 유지한다.
   - 결제 지갑 선택값은 `payment_authorizations.payer_wallet_id` 또는 동등한 payment authorization field에 둔다.
   - `store_catalog_stores.store_wallet_address`와 `order_stores.store_wallet_address`는 검증된 settlement wallet 참조로 전환한다. order snapshot에 address가 필요하면 verified settlement wallet에서 파생된 immutable snapshot으로만 남긴다.
   - migration/backfill은 기존 store owner의 verified wallet과 정산 주소를 매칭하고, 매칭 실패 row는 명시적 `blocked`/manual remediation 대상으로 남긴다.
4. PostgreSQL adapter를 갱신한다.
   - wallet repository port를 추가한다.
   - user repository는 wallet address unique lookup을 직접 소유하지 않는다.
   - schema compatibility SQL도 목표 schema와 같은 정규화 규칙을 따른다. legacy raw wallet column은 canonical write path로 유지하지 않는다.
   - payment authorization schema에 들어갈 `payer_wallet_id`, asset, chain 정규화는 step 4~6과 충돌하지 않도록 같은 migration plan으로 묶는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_multi_wallet_domain_schema.py scripts/test_auth_api_session_runtime.py scripts/test_siwe_erc1271_auth_public_contracts.py scripts/test_postgres_context_repositories.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. multi-wallet domain/schema 테스트를 먼저 추가하고 실패를 확인한다.
2. auth/order/store settlement schema와 repository를 갱신한 뒤 AC를 실행한다.
3. `/phases/25-multi-wallet-accounts/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 같은 wallet address를 chain id 없이 unique 처리하지 마라.
- wallet link를 group/role 권한 부여와 같은 동작으로 만들지 마라.
- `auth_sessions`, `order_customers`, store settlement row에 client-provided raw wallet address를 canonical data로 남기지 마라.
- settlement wallet backfill 실패를 임의 primary wallet fallback으로 조용히 처리하지 마라.
- 이메일 복구, DID, ERC-6492를 이 step에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

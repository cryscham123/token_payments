# Step 3: multi-wallet-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/README.md`
- `/app/README.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/postman/token-payments.local.postman_collection.json`
- `/postman/expected/token-payments.api.expected.json`
- `/postman/fixtures/token-payments.local.seed-plan.json`
- `/scripts/test_postman_cookie_auth_flow.py`
- `/scripts/test_route_surface_contract_docs.py`
- `/phases/25-multi-wallet-accounts/index.json`

## 작업

Multi-wallet public contract, docs, Postman fixture, seed plan을 정리한다.

1. `scripts/test_multi_wallet_public_contracts.py`를 추가한다.
   - API spec이 login wallet과 linked wallet, payment selected wallet을 구분해야 한다.
   - Postman collection은 wallet link/list/primary/revoke flow를 포함해야 한다.
   - seed plan은 한 user의 여러 wallet과 chain별 primary wallet 예시를 포함해야 한다.
   - docs는 wallet revocation이 asset recovery를 의미하지 않는다고 명시해야 한다.
   - docs/API examples는 `auth_sessions.wallet_address`, `order_customers.wallet_address`, unchecked `store_wallet_address`를 multi-wallet 이후 canonical field처럼 설명하지 않아야 한다.
   - public contract는 session login wallet, selected payer wallet, store settlement wallet을 각각 다른 개념으로 설명해야 한다.
2. docs/fixtures를 갱신한다.
   - DID, email recovery, linked external identity provider는 future scope로 유지한다.
   - ERC-1271 deployed smart wallet 지원과 ERC-6492 future scope를 구분한다.
   - store settlement wallet은 verified wallet reference 또는 검증된 store settlement wallet model로 지정된다는 점을 명시한다.
3. route manifest와 expected JSON을 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_multi_wallet_public_contracts.py scripts/test_route_surface_contract_docs.py scripts/test_postman_cookie_auth_flow.py scripts/test_api_seed_expected_responses.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. public contract 테스트를 먼저 추가하고 실패를 확인한다.
2. docs/Postman/seed/route expected files를 갱신한 뒤 AC를 실행한다.
3. `/phases/25-multi-wallet-accounts/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- email recovery나 DID를 이번 phase route로 추가하지 마라.
- wallet revoke를 blockchain asset transfer/recovery처럼 설명하지 마라.
- session/customer/store settlement 계약에 raw wallet address를 canonical identity처럼 다시 노출하지 마라.
- fixture에 real private key, seed phrase, production wallet signature를 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

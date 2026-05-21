# Step 4: profile-catalog-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/README.md`
- `/app/README.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/postman/token-payments.local.postman_collection.json`
- `/postman/expected/token-payments.api.expected.json`
- `/postman/fixtures/token-payments.local.seed-plan.json`
- `/scripts/test_api_seed_expected_responses.py`
- `/scripts/test_local_env_seed_contract.py`
- `/phases/23-user-store-product-profile-catalog/index.json`

## 작업

유저/가게/상품 정보 보강 phase의 public docs, seed, Postman contract를 정리한다.

1. `scripts/test_profile_catalog_public_contracts.py`를 추가한다.
   - docs가 user identity, user profile, group membership을 구분해야 한다.
   - docs가 store business profile, store payment settings, product catalog, inventory를 구분해야 한다.
   - docs는 store/product slug를 phase 23 필수 field나 route key로 설명하지 않아야 한다.
   - Postman collection/expected fixture는 user profile, store profile, product detail, catalog query examples를 포함해야 한다.
   - local seed plan은 platform admin, merchant group, store profile, product details, public product listing fixture를 포함해야 한다.
   - docs는 Elasticsearch, DID, email account recovery를 future scope로 남겨야 한다.
2. README/app README를 갱신한다.
   - phase 23 산출물과 다음 phase 후보를 정리한다.
   - Kafka live worker, multi-wallet, stablecoin이 이후 phase임을 명시한다.
3. API spec/Postman/seed expected files를 갱신한다.
4. phase metadata를 검증한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_profile_catalog_public_contracts.py scripts/test_api_seed_expected_responses.py scripts/test_local_env_seed_contract.py scripts/test_route_surface_contract_docs.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. public contract 테스트를 먼저 추가하고 실패를 확인한다.
2. docs/Postman/seed fixtures를 갱신한 뒤 AC를 실행한다.
3. `/phases/23-user-store-product-profile-catalog/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 검색 엔진, DID, 이메일 복구 구현을 이 phase에 추가하지 마라.
- local seed에 real secret, private key, seed phrase, production token을 넣지 마라.
- profile/catalog docs에서 auth identity와 public profile을 혼동하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

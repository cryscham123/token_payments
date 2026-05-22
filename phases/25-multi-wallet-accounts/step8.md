# Step 8: multi-wallet-stablecoin-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/README.md`
- `/app/README.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/docs/SEQUENCES.md`
- `/postman/fixtures/token-payments.local.seed-plan.json`
- `/scripts/test_happy_path_checkout_e2e.py`
- `/scripts/test_docker_live_smoke_plan.py`
- `/phases/25-multi-wallet-accounts/index.json`

## 작업

Multi-wallet + stablecoin 결제 지원 범위를 public verification으로 잠그고, 이후 검색/DID/email recovery/permit/gas sponsorship/swap은 다음 roadmap으로 남긴다.

1. `scripts/test_multi_wallet_stablecoin_public_contracts.py`를 추가한다.
   - docs가 login wallet, linked wallet, selected payer wallet, store settlement wallet을 구분해야 한다.
   - docs가 supported payment assets, native coin, ERC-20 stablecoin의 차이를 설명해야 한다.
   - sequence가 selected wallet + stablecoin authorization과 ERC-20 receipt verification을 포함해야 한다.
   - local seed plan은 한 user의 여러 wallet, chain별 primary wallet, enabled stablecoin asset, disabled/unsupported asset negative case를 포함해야 한다.
   - smoke plan은 stablecoin checkout을 optional approved live scenario로 표시하되 automated test에서 live chain/Kafka를 열지 않아야 한다.
   - docs는 `chain_id`가 canonical network key이고 `chain_name`은 registry/display metadata임을 명시해야 한다.
   - docs는 `payment_authorizations`가 expected payer wallet/payment terms를 소유하고 `payments`가 observed transaction/receipt result를 소유한다는 역할 분리를 설명해야 한다.
2. e2e/smoke contract를 갱신한다.
   - happy path checkout e2e는 native asset과 stablecoin fixture 중 최소 하나를 명확히 검증한다.
   - compensation path는 stablecoin payment failed/expired/rejected event payload가 asset metadata와 selected wallet reference를 보존하는지 검증한다.
   - public contract tests는 payment write model에 `chain_name` canonical column이 다시 생기지 않는지 확인해야 한다.
3. README/app README를 갱신한다.
   - roadmap completed scope: RBAC, live Kafka worker, catalog public read API, multi-wallet, stablecoin payment.
   - future scope: search/Elasticsearch projection, DID, email account recovery, permit/gas sponsorship/swap.
4. phase metadata를 검증한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_multi_wallet_stablecoin_public_contracts.py scripts/test_happy_path_checkout_e2e.py scripts/test_compensation_checkout_e2e.py scripts/test_docker_live_smoke_plan.py scripts/test_api_seed_expected_responses.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. multi-wallet/stablecoin public contract 테스트를 먼저 추가하고 실패를 확인한다.
2. docs/e2e/smoke/seed fixtures를 갱신한 뒤 AC를 실행한다.
3. `/phases/25-multi-wallet-accounts/index.json`의 step 8 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Elasticsearch, DID, email recovery를 이 phase에 구현하지 마라.
- stablecoin support를 arbitrary token marketplace처럼 문서화하지 마라.
- authorization/payment expected asset duplication을 정상 write model처럼 문서화하지 마라.
- live Docker/Kafka/blockchain 실행을 automated verification의 필수 조건으로 만들지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

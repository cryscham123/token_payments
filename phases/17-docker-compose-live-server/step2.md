# Step 2: local-env-seed-contract

## 읽어야 할 파일

- `/AGENTS.md`
- `/.env.example`
- `/README.md`
- `/app/README.md`
- `/docs/API_SPEC.md`
- `/postman/fixtures/token-payments.local.seed-plan.json`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/docker-compose.yml`
- `/scripts/docker_live_smoke.py`
- `/scripts/test_api_seed_expected_responses.py`
- `/scripts/test_postman_cookie_auth_flow.py`

## 작업

로컬 실행자가 `.env.example`을 복사했을 때 가능한 한 바로 동작하는 dev 값을 제공한다. 진짜 secret은 커밋하지 않되, placeholder 때문에 local live server가 불필요하게 죽는 문제를 줄인다.

1. `scripts/test_local_env_seed_contract.py`를 추가한다.
   - `.env.example`에 local dev용 session/CSRF signing key 값이 있거나, live/prod와 local/dev validation policy가 명확히 분리되어 있어야 한다.
   - PostgreSQL/Kafka/API/CORS/CSRF/session/readiness/Postman seed env key가 같은 naming으로 연결되는지 검증한다.
   - `.env.example`이 private key, seed phrase, production credential, real paid RPC key를 포함하지 않는지 검증한다.
   - seed plan이 schema table/column과 drift 없이 맞는지 검증한다.
2. `.env.example`을 갱신한다.
   - local dev에서 실제 검증을 통과할 수 있는 non-secret signing material을 제공한다.
   - chain/RPC/test-network 값은 local test network 기준으로 둔다.
   - 값이 운영용이 아님을 명확히 주석으로 표시한다.
3. seed 문서와 fixture를 정리한다.
   - `docker compose up` 후 seed 적용 순서가 README에 있어야 한다.
   - seed는 고객, 가게, 상품, 재고, payment destination, test network ids를 포함해야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_local_env_seed_contract.py scripts/test_api_seed_expected_responses.py scripts/test_postman_cookie_auth_flow.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. local env/seed contract 테스트를 먼저 추가하고 실패를 확인한다.
2. `.env.example`, seed fixture, docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/17-docker-compose-live-server/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- `.env.example`에 운영 secret, real private key, seed phrase, 상용 RPC key를 넣지 마라.
- local dev 편의를 위해 live/prod secret validation을 약화하지 마라.
- seed data에 실제 사용자 wallet이나 실제 결제 주소를 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

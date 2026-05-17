# Step 2: api-seed-and-expected-responses

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/API_SPEC.md`
- `/README.md`
- `/app/README.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/runtime/smoke.py`
- `/scripts/test_happy_path_checkout_e2e.py`
- `/scripts/test_compensation_checkout_e2e.py`
- `/scripts/test_postman_cookie_auth_flow.py`
- `/phases/15-postman-docker-api-readiness/index.json`

## 작업

Postman collection이 deterministic local data로 실행될 수 있도록 seed flow와 expected response fixtures를 추가한다. 이 step도 live DB를 직접 열지 않고 committed SQL/JSON/CLI contract를 검증한다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_api_seed_expected_responses.py`를 추가한다.
   - seed fixture 또는 SQL script가 demo user/store/product/inventory/payment destination/test network ids를 포함하는지 검증한다.
   - fixture는 existing schema table names와 column names를 사용해야 한다.
   - expected response JSON fixtures가 `docs/API_SPEC.md`의 route summary와 Postman collection request names에 대응해야 한다.
   - expected responses는 cookie/CSRF headers, idempotency header, request id, happy-path checkout, compensation/operator action examples를 포함해야 한다.
   - fixtures에는 secret, private key, seed phrase, real production token, raw refresh token이 없어야 한다.
2. `app/postgres/init.d` 아래에 seed script를 추가할지, 별도 `postman/fixtures` JSON seed plan을 추가할지 선택한다.
   - 자동 DB mutation을 피하려면 default init schema와 분리된 explicit seed script/plan으로 둔다.
   - Docker compose API readiness에서 explicit seed command를 실행할 수 있도록 command metadata를 남긴다.
3. `postman/expected` 또는 동등한 fixture 디렉터리를 추가한다.
   - auth, order, checkout, payment, operator dashboard/action response examples를 route별로 둔다.
   - dynamic ids/timestamps는 placeholder convention을 사용한다.
4. README/app README와 `docs/API_SPEC.md`에 seed flow를 문서화한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_api_seed_expected_responses.py scripts/test_postman_cookie_auth_flow.py scripts/test_happy_path_checkout_e2e.py scripts/test_compensation_checkout_e2e.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 seed/expected response 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/15-postman-docker-api-readiness/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- default schema init에 destructive seed reset을 섞지 마라.
- fixture에 real secret/token/signature/private key를 넣지 마라.
- expected response fixture가 implementation internals, refresh token hash/salt를 public API처럼 노출하게 만들지 마라.
- live Docker/DB/Kafka/Blockchain을 자동 검증으로 시작하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

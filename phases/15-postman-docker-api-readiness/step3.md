# Step 3: docker-api-readiness-security-smoke

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/API_SPEC.md`
- `/README.md`
- `/app/README.md`
- `/.env.example`
- `/docker-compose.yml`
- `/scripts/docker_live_smoke.py`
- `/app/token_payments/runtime/smoke.py`
- `/scripts/test_postman_docker_api_service.py`
- `/scripts/test_postman_cookie_auth_flow.py`
- `/scripts/test_api_seed_expected_responses.py`
- `/phases/15-postman-docker-api-readiness/index.json`

## 작업

Docker API service가 실제로 준비되었을 때 수행할 bounded live readiness/security smoke plan을 추가한다. 기본 automated path는 dry-run/static verification만 수행하고 Docker/API server를 시작하지 않는다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_docker_api_readiness_security_smoke.py`를 추가한다.
   - dry-run plan이 API service start, session signing key validation, invalid/expired signature rejection, `/healthz`, `/readyz`, auth cookie flow, CSRF failure/success, CORS preflight, oversized body, malformed JSON, idempotency duplicate, checkout happy path, operator action smoke 순서를 포함하는지 검증한다.
   - plan은 command argv와 display string을 함께 제공하고 `shell=True` 전제가 없어야 한다.
   - `--execute` without explicit confirmation은 bounded refusal JSON을 반환해야 한다.
   - live execution path는 injectable fake runner/client로 테스트하고 real Docker/API/network를 열지 않아야 한다.
   - smoke output은 session signing key, signed token, cookie/token/CSRF secret/header raw values를 redaction해야 한다.
2. `scripts/docker_live_smoke.py` 또는 새 `scripts/api_live_smoke.py`를 확장/추가한다.
   - 기존 Docker live smoke guardrail을 재사용한다.
   - API readiness/security smoke는 `--plan` 기본, explicit confirmation required 원칙을 따른다.
   - cleanup은 실패/성공 모두에서 시도되어야 한다.
3. `app/token_payments/runtime/smoke.py` registry에 `postman-docker-api-readiness` 또는 동등한 scenario metadata를 추가한다.
   - scenario는 automated path에서 live server를 시작하지 않고 plan/contract를 반환해야 한다.
4. README/app README에 manual live API smoke 순서를 문서화한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_docker_api_readiness_security_smoke.py scripts/test_postman_docker_api_service.py scripts/test_postman_cookie_auth_flow.py scripts/test_api_seed_expected_responses.py scripts/test_docker_live_smoke_public_contracts.py
PYTHONPATH=app python3 -m token_payments smoke postman-docker-api-readiness
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 Docker API readiness/security smoke 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/15-postman-docker-api-readiness/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- confirmation 없는 smoke execution이 Docker/API server/network를 시작하게 만들지 마라.
- smoke output에 session signing key, signed token, cookie/token/CSRF secret/private key/seed phrase를 노출하지 마라.
- 기존 docker live smoke refusal/cleanup guardrail을 약화하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 4: postman-docker-api-public-verification

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
- `/Dockerfile`
- `/docker-compose.yml`
- `/postman`
- `/scripts/docker_live_smoke.py`
- `/app/token_payments/runtime/smoke.py`
- `/scripts/test_postman_docker_api_service.py`
- `/scripts/test_postman_cookie_auth_flow.py`
- `/scripts/test_api_seed_expected_responses.py`
- `/scripts/test_docker_api_readiness_security_smoke.py`
- `/phases/index.json`
- `/phases/15-postman-docker-api-readiness/index.json`

## 작업

Postman/Docker API readiness phase의 public contract, 문서, phase metadata를 고정한다. 동작 변경이 있으면 먼저 테스트를 갱신하고, 문서 변경도 테스트로 검증한다.

1. `scripts/test_postman_docker_api_public_contracts.py`를 추가한다.
   - README/app README/API spec이 compose API service, env-backed session signing keys, active/previous key rotation expectation, Postman collection/environment, cookie auth, CSRF token, CORS credentials, seed flow, expected responses, Docker API readiness/security smoke를 문서화하는지 검증한다.
   - Postman collection request list가 route manifest와 API spec route summary를 커버하는지 검증한다.
   - expected response fixtures가 route별 status/error/security cases를 포함하는지 검증한다.
   - smoke registry와 Docker live smoke plan이 API readiness/security scenario를 포함하는지 검증한다.
   - phase metadata가 completed step summary와 top-level phase status를 일관되게 반영하는지 검증한다.
2. README/app README를 정리한다.
   - 최종 local backend 실행 순서를 `cp .env.example .env`, compose config, build/up, seed, Postman import, smoke, cleanup 순서로 적는다.
   - automated harness는 Docker/API server를 시작하지 않는다는 경계를 유지한다.
3. `docs/API_SPEC.md`를 최종 갱신한다.
   - cookie-first browser auth, signed session token, env-backed key rotation, CSRF, CORS, idempotency, health/readiness, Postman flow를 명확히 정리한다.
4. 모든 phase metadata를 정리한다.
   - `/phases/15-postman-docker-api-readiness/index.json`의 모든 완료 step에는 구체적인 `summary`가 있어야 한다.
   - `/phases/index.json`에서 `15-postman-docker-api-readiness`를 `completed`로 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_postman_docker_api_public_contracts.py scripts/test_docker_api_readiness_security_smoke.py scripts/test_api_seed_expected_responses.py scripts/test_postman_cookie_auth_flow.py scripts/test_postman_docker_api_service.py
PYTHONPATH=app python3 -m token_payments smoke postman-docker-api-readiness
python3 scripts/validate_phases.py
```

## 검증 절차

1. public contract/README/API spec 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/15-postman-docker-api-readiness/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
4. `/phases/index.json`에서 `15-postman-docker-api-readiness`를 `completed`로 갱신한다.

## 금지사항

- final docs가 Bearer/localStorage를 browser 기본 auth transport로 권장하게 만들지 마라.
- automated verification에서 Docker daemon, real API server, real DB/Kafka/Blockchain/local `.env` 접근을 수행하지 마라.
- fixture/docs에 session signing key, signed token 원문, secret, private key, seed phrase, real access/refresh token을 넣지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

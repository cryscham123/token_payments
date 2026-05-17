# Step 6: live-api-runtime-public-verification

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
- `/app/token_payments/runtime/config.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/runtime/session_transport.py`
- `/app/token_payments/runtime/security.py`
- `/app/token_payments/runtime/api_server.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/asgi.py`
- `/app/token_payments/api/fastapi.py`
- `/scripts/test_live_api_runtime_composition.py`
- `/scripts/test_live_api_facade_wiring.py`
- `/scripts/test_cookie_session_transport.py`
- `/scripts/test_csrf_cors_request_guard.py`
- `/scripts/test_live_api_server_entrypoint.py`
- `/scripts/test_readiness_observability_idempotency.py`
- `/scripts/test_fastapi_asgi_public_contracts.py`
- `/scripts/test_docker_runtime_smoke.py`
- `/phases/index.json`
- `/phases/14-live-api-runtime-composition/index.json`

## 작업

live API runtime composition phase의 public contract, 문서, phase metadata를 고정한다. 이 step은 다음 `15-postman-docker-api-readiness` phase가 Docker compose API service와 Postman cookie/CSRF examples를 추가할 수 있도록 경계를 명확히 남긴다. 동작 변경이 있으면 먼저 테스트를 갱신하고, 문서 변경도 테스트로 검증한다.

1. `scripts/test_live_api_runtime_public_contracts.py`를 추가한다.
   - `token_payments.runtime` public exports가 live runtime config/composition/cookie/security/server/readiness surface를 포함하는지 검증한다.
   - `api`, `serve-api`, `serve-api --live --dry-run`, `serve-api --live` command의 bounded JSON contract를 검증한다.
   - dry-run/refusal payload가 route count, ASGI/FastAPI factory metadata, live dependency groups, env-backed session signing enabled, active key id redacted summary, signing key placeholder rejection, cookie session transport enabled, CSRF guard enabled, CORS allowlist, readiness probes, idempotency header support, required confirmation, redacted config, no-server-start status를 포함하는지 검증한다.
   - source import boundary를 검증한다: domain/application은 API/runtime/adapter를 import하지 않고, runtime preview modules는 real driver/framework/server import를 lazy 또는 optional boundary 밖으로 퍼뜨리지 않아야 한다.
   - README, app README, `docs/API_SPEC.md`가 `Live API Runtime Composition`, cookie auth, CSRF/CORS, health/readiness, idempotency header, explicit live confirmation boundary, no-default-server-start boundary, 다음 phase 후보 `15-postman-docker-api-readiness`를 문서화하는지 검증한다.
   - `phases/14-live-api-runtime-composition/index.json` step summary/status와 `phases/index.json` top-level phase 상태가 `validate_phases`와 일관되어야 한다.
2. README와 app README를 갱신한다.
   - phase 14 산출물과 기본 preview/live dry-run/refusal command를 문서화한다.
   - 실제 long-running API server는 explicit confirmation과 준비된 live dependency environment에서만 실행한다는 점을 명시한다.
   - Docker compose service, seed flow, Postman collection/examples는 phase 15 범위로 남긴다.
3. 필요하면 `app/token_payments/runtime/smoke.py`의 readiness metadata를 확장한다.
   - 자동 smoke가 live server를 시작하지 않도록 유지한다.
   - 다음 phase가 compose API service, cookie/CSRF flow, `/healthz`, `/readyz`를 검증할 수 있는 command hint만 추가한다.
4. 모든 phase metadata를 정리한다.
   - `/phases/14-live-api-runtime-composition/index.json`의 모든 완료 step에는 구체적인 `summary`가 있어야 한다.
   - `/phases/index.json`에서 `14-live-api-runtime-composition`을 `completed`로 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_live_api_runtime_public_contracts.py scripts/test_readiness_observability_idempotency.py scripts/test_live_api_server_entrypoint.py scripts/test_csrf_cors_request_guard.py scripts/test_cookie_session_transport.py scripts/test_live_api_facade_wiring.py scripts/test_live_api_runtime_composition.py scripts/test_fastapi_asgi_public_contracts.py scripts/test_docker_runtime_smoke.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run
PYTHONPATH=app python3 -m token_payments serve-api --live
python3 scripts/validate_phases.py
```

## 검증 절차

1. public contract/README/API spec 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/14-live-api-runtime-composition/index.json`의 step 6 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
4. `/phases/index.json`에서 `14-live-api-runtime-composition`을 `completed`로 갱신한다.

## 금지사항

- Docker compose API service, Postman collection, seed script, expected response fixture를 이 phase에 추가하지 마라. 그것은 phase 15 범위다.
- 자동 검증에서 server start, socket bind, Docker daemon, real PostgreSQL/Kafka/Blockchain/local `.env` 접근을 수행하지 마라.
- session signing key, signed token 원문, secret 또는 `.env` 값을 README, JSON preview, test fixture에 노출하지 마라.
- route manifest, operation id, existing API/ASGI/FastAPI/WSGI contracts를 깨뜨리지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

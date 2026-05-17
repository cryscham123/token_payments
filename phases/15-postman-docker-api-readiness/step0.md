# Step 0: compose-api-service-contract

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
- `/app/token_payments/runtime/api_server.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/scripts/test_docker_compose_runtime_services.py`
- `/scripts/test_docker_runtime_smoke.py`
- `/scripts/test_live_api_runtime_public_contracts.py`
- `/phases/14-live-api-runtime-composition/index.json`

## 작업

Postman에서 호출할 수 있는 local API service를 Docker compose contract로 추가한다. 이 step은 compose service/config를 고정하지만 automated harness에서 Docker daemon을 시작하지 않는다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_postman_docker_api_service.py`를 추가한다.
   - `docker-compose.yml`에 `token_payments_api` service가 있어야 한다.
   - service는 root `Dockerfile` image를 사용하고 `PYTHONPATH=/workspace/app`를 설정해야 한다.
   - command는 explicit live confirmation이 있는 API server command여야 한다. 예: `python -m token_payments serve-api --live --confirm-live-api`.
   - service는 `RUNTIME_API_HOST=0.0.0.0`, `RUNTIME_API_PORT=8000`을 사용하고 host port는 local Postman용으로 명확히 노출해야 한다.
   - service는 postgres healthy, kafka started, test_network started 이후 시작되어야 한다.
   - service에는 session signing key id/key ring, access/refresh TTL, cookie/CSRF/CORS/readiness 관련 env keys가 연결되어야 하며 secret raw value를 compose file에 직접 쓰면 안 된다.
   - daemon-less config validation은 `SESSION_ACTIVE_KEY_ID`, `SESSION_SIGNING_KEYS`, `SESSION_ACCESS_TTL_SECONDS`, `SESSION_REFRESH_TTL_SECONDS` 또는 동등한 env key가 service로 전달되는지 검증해야 한다.
   - `docker compose --env-file .env.example --profile api config --services` 또는 daemon-less config validation이 `token_payments_api`를 포함해야 한다.
2. `.env.example`을 갱신한다.
   - local API origin, CORS allowed origins, cookie secure/samesite policy, CSRF settings, session active key id, session signing key placeholder, access/refresh TTL, API public base URL을 민감정보 없이 추가한다.
   - `.env.example`의 session signing key는 live/prod start에서 반드시 거부되는 placeholder여야 하며, README에는 로컬 개발자가 `.env`에서 교체해야 한다고 명시한다.
3. `app/token_payments/runtime/smoke.py` 또는 Docker runtime metadata를 갱신한다.
   - manual live command sequence에 API service config/build/up/readiness check 순서를 추가한다.
   - 자동 smoke는 Docker daemon을 시작하지 않고 committed config만 검증해야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_postman_docker_api_service.py scripts/test_docker_compose_runtime_services.py scripts/test_docker_runtime_smoke.py scripts/test_live_api_runtime_public_contracts.py
docker compose --env-file .env.example --profile api config --services
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 compose API service 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다. Docker config validation이 sandbox에서 불가능하면 실패 원인을 `summary` 또는 `error_message`에 구체적으로 남긴다.
3. `/phases/15-postman-docker-api-readiness/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- automated harness에서 `docker compose up`, `docker compose run`, `docker build`, Docker socket 접근을 수행하지 마라.
- compose file이나 `.env.example`에 real session signing key, secret, private key, seed phrase, real token을 직접 쓰지 마라.
- API service가 `api`/`serve-api` 기본 preview command를 long-running으로 바꾸게 만들지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

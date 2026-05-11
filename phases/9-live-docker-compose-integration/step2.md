# Step 2: docker-runtime-smoke-scenario

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/README.md`
- `/app/README.md`
- `/Dockerfile`
- `/.dockerignore`
- `/docker-compose.yml`
- `/.env.example`
- `/app/token_payments/runtime/smoke.py`
- `/app/token_payments/runtime/__init__.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/scripts/test_e2e_integration_public_contracts.py`
- `/scripts/test_compose_readiness_smoke.py`
- `/scripts/test_docker_compose_runtime_services.py`
- `/phases/9-live-docker-compose-integration/index.json`

## 작업

Docker runtime/compose 계약을 bounded smoke scenario로 노출한다. 이 scenario는 committed Docker 파일과 compose one-shot service command chain을 검증하지만 기본 테스트에서 Docker daemon을 시작하지 않는다. 동작 변경이므로 먼저 테스트를 작성하거나 갱신하고 실패를 확인한 뒤 구현한다.

1. `scripts/test_docker_runtime_smoke.py`를 추가한다.
   - `token_payments.runtime.smoke.AVAILABLE_SMOKE_SCENARIOS`에 `docker-runtime-readiness`가 포함되어야 한다.
   - `run_smoke_scenario("docker-runtime-readiness")`가 `passed` 상태의 JSON primitive payload를 반환해야 한다.
   - details에는 `dockerStarted=false`, `networkCalls=false`, `image.contract`, `compose.runtimeServices`, `compose.runCommands`, `manualLiveCommands`가 포함되어야 한다.
   - `compose.runCommands`에는 다음 one-shot command가 순서대로 들어가야 한다.
     - `docker compose --env-file .env --profile runtime run --rm token_payments_health`
     - `docker compose --env-file .env --profile runtime run --rm token_payments_worker`
     - `docker compose --env-file .env --profile smoke run --rm token_payments_smoke`
   - `manualLiveCommands`에는 local cleanup command(`docker compose --env-file .env down`)가 포함되어야 한다.
   - CLI `PYTHONPATH=app python3 -m token_payments smoke docker-runtime-readiness`가 bounded JSON을 출력해야 한다.
   - 기존 smoke scenario registry tests를 새 scenario 수와 이름에 맞게 갱신한다.
2. `app/token_payments/runtime/smoke.py`를 갱신한다.
   - 기존 helper를 재사용해 Dockerfile, `.dockerignore`, compose runtime services, `.env.example` path를 검증한다.
   - Docker daemon, Docker socket, network, live database/Kafka connection을 열지 않는다.
   - 결과는 JSON primitive만 포함한다.
3. `app/token_payments/runtime/__init__.py` public exports가 scenario registry 변경으로 깨지지 않게 한다.
4. 기존 `compose-readiness`, happy-path, compensation smoke가 계속 통과해야 한다.

## Acceptance Criteria

```bash
python3 -m pytest \
  scripts/test_docker_runtime_smoke.py \
  scripts/test_e2e_integration_public_contracts.py \
  scripts/test_compose_readiness_smoke.py
PYTHONPATH=app python3 -m token_payments smoke docker-runtime-readiness
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/9-live-docker-compose-integration/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step에서 Docker daemon을 시작하거나 Docker socket을 여는 코드를 runtime smoke 기본 경로에 넣지 마라.
- `docker` Python SDK, requests, psycopg, Kafka client 같은 새 dependency/import를 추가하지 마라.
- 기존 smoke scenario payload를 비호환으로 바꾸지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

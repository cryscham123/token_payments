# Step 0: default-compose-api-entrypoint

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/API_SPEC.md`
- `/README.md`
- `/app/README.md`
- `/.env.example`
- `/Dockerfile`
- `/docker-compose.yml`
- `/app/token_payments/runtime/api_server.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/scripts/test_postman_docker_api_service.py`
- `/scripts/test_docker_compose_runtime_services.py`
- `/scripts/test_docker_runtime_smoke.py`
- `/phases/15-postman-docker-api-readiness/index.json`
- `/phases/16-architecture-contract-alignment/index.json`

## 작업

`docker compose up`만으로 local live API service가 기동 대상에 포함되도록 compose contract를 정리한다. Automated harness는 Docker daemon을 시작하지 않고 committed compose config만 검증한다.

1. `scripts/test_docker_compose_live_server_default.py`를 추가한다.
   - `docker compose --env-file .env.example config --services` 또는 daemon-less equivalent가 `token_payments_api`를 포함해야 한다.
   - API service command는 `python -m token_payments serve-api --live --confirm-live-api` 또는 동등한 explicit live command여야 한다.
   - API service는 `RUNTIME_API_HOST=0.0.0.0`, `RUNTIME_API_PORT=8000`, `PYTHONPATH=/workspace/app`를 받아야 한다.
   - `depends_on` health/start order가 PostgreSQL, Kafka, test network readiness를 반영해야 한다.
   - compose file이 secret raw value를 직접 포함하지 않고 env key를 참조해야 한다.
2. `docker-compose.yml`을 갱신한다.
   - plain `docker compose up` target에 API가 포함되게 한다. profile을 유지할 경우 `.env.example`의 `COMPOSE_PROFILES`와 docs가 실제 plain up 동작을 보장해야 한다.
   - API service restart policy와 readiness retry policy를 명확히 한다.
3. README/app README/API spec의 local live 실행 명령을 갱신한다.
   - 기본 경로는 `cp .env.example .env` 후 `docker compose up`이다.
   - profile을 별도 요구하지 않도록 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_docker_compose_live_server_default.py scripts/test_postman_docker_api_service.py scripts/test_docker_compose_runtime_services.py scripts/test_docker_runtime_smoke.py
docker compose --env-file .env.example config --services
python3 scripts/validate_phases.py
```

## 검증 절차

1. compose default contract 테스트를 먼저 추가하고 실패를 확인한다.
2. compose/docs/env를 갱신한 뒤 AC를 실행한다.
3. Docker config command가 sandbox나 로컬 Docker 미설치로 불가능하면 실패 원인을 `summary` 또는 `error_message`에 구체적으로 남긴다.
4. `/phases/17-docker-compose-live-server/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- automated harness에서 `docker compose up`, `docker compose run`, `docker build`, Docker socket 접근을 수행하지 마라.
- compose file이나 `.env.example`에 real secret, private key, seed phrase, 운영 credential을 직접 쓰지 마라.
- API default preview command를 long-running server로 바꾸지 마라. live server는 explicit live command에만 묶는다.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

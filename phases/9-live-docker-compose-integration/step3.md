# Step 3: docker-compose-config-validation

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/HARNESS.md`
- `/README.md`
- `/app/README.md`
- `/Dockerfile`
- `/.dockerignore`
- `/docker-compose.yml`
- `/.env.example`
- `/scripts/test_docker_runtime_image_contracts.py`
- `/scripts/test_docker_compose_runtime_services.py`
- `/scripts/test_docker_runtime_smoke.py`
- `/app/token_payments/runtime/smoke.py`
- `/phases/9-live-docker-compose-integration/index.json`

## 작업

Docker daemon 없이도 실행 가능한 Docker Compose config validation을 테스트와 문서 계약으로 고정한다. 동작 변경이므로 먼저 테스트를 작성하거나 갱신하고 실패를 확인한 뒤 구현한다.

1. `scripts/test_docker_compose_config_validation.py`를 추가한다.
   - `docker compose version`이 설치된 환경이면 `docker compose --env-file .env.example config --services`를 실행해 compose 파일이 해석 가능한지 검증한다.
   - Docker Compose CLI가 없는 환경에서는 명확한 skip reason으로 skip하고, static tests(`test_docker_compose_runtime_services.py`)가 계약을 대신 검증해야 한다.
   - config 결과에 `postgres`, `kafka`, `kafka-ui`, `pgweb`, `test_network`, `token_payments_health`, `token_payments_worker`, `token_payments_smoke`가 포함되어야 한다.
   - `docker compose --env-file .env.example --profile runtime config --services` 결과에 runtime one-shot services가 포함되어야 한다.
   - config validation은 Docker daemon/socket에 접속하지 않아야 하며 `up`, `run`, `build`를 호출하지 않아야 한다.
2. 필요하면 `.env.example` 또는 compose variable usage를 조정한다.
   - committed placeholder 값만 유지한다.
   - local `.env`는 수정하지 않는다.
3. 필요하면 Docker runtime smoke details에 `composeConfigValidationCommand`를 추가한다.
   - command는 daemon-less validation임을 명시한다.

## Acceptance Criteria

```bash
python3 -m pytest \
  scripts/test_docker_compose_config_validation.py \
  scripts/test_docker_compose_runtime_services.py \
  scripts/test_docker_runtime_smoke.py
PYTHONPATH=app python3 -m token_payments smoke docker-runtime-readiness
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/9-live-docker-compose-integration/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step의 automated tests에서 `docker compose up`, `docker compose run`, `docker build`를 실행하지 마라.
- local `.env`를 생성/수정/커밋하지 마라.
- Docker daemon 권한이 없다는 이유로 phase를 실패 처리하지 마라. daemon-less config validation과 static tests를 유지하라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

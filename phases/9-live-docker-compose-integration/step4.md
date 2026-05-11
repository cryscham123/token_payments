# Step 4: docker-phase-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/README.md`
- `/app/README.md`
- `/Dockerfile`
- `/.dockerignore`
- `/docker-compose.yml`
- `/.env.example`
- `/app/token_payments/runtime/smoke.py`
- `/app/token_payments/runtime/__init__.py`
- `/scripts/test_docker_runtime_image_contracts.py`
- `/scripts/test_docker_compose_runtime_services.py`
- `/scripts/test_docker_runtime_smoke.py`
- `/scripts/test_docker_compose_config_validation.py`
- `/phases/9-live-docker-compose-integration/index.json`
- `/phases/index.json`

## 작업

Docker phase 산출물을 public contract, README 문서, phase metadata 관점에서 마감한다. 누락된 동작이 있으면 먼저 실패하는 테스트를 추가하고 구현을 보완한다.

1. `scripts/test_docker_phase_public_contracts.py`를 추가한다.
   - Dockerfile, `.dockerignore`, compose runtime service, docker smoke scenario, daemon-less compose config validation 테스트 파일이 모두 존재해야 한다.
   - `token_payments.runtime.smoke` public registry에서 기존 smoke scenario와 `docker-runtime-readiness`를 모두 안정적으로 import/execute할 수 있어야 한다.
   - runtime smoke module이 Docker SDK, web framework, PostgreSQL/Kafka live client, network HTTP client를 직접 import하지 않아야 한다.
   - Dockerfile/compose/docs에 Claude 전용 명령이 없어야 한다.
   - phase 9 metadata의 모든 completed step summary는 Docker runtime image, compose runtime service, smoke scenario, compose config validation 중 해당 산출물을 구체적으로 언급해야 한다.
2. README와 app README를 갱신한다.
   - Docker runtime image, compose one-shot services, `docker-runtime-readiness` smoke command, daemon-less compose config validation command를 문서화한다.
   - live local 실행은 수동/승인 필요 작업으로 분리하고 다음 순서를 명시한다.
     - `cp .env.example .env`
     - `docker compose --env-file .env --profile runtime config --services`
     - `docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network`
     - `docker compose --env-file .env --profile runtime run --rm token_payments_health`
     - `docker compose --env-file .env --profile runtime run --rm token_payments_worker`
     - `docker compose --env-file .env --profile smoke run --rm token_payments_smoke`
     - `docker compose --env-file .env down`
   - Docker daemon/socket 권한이 없는 automated harness에서는 live container 실행이 아니라 static/config/smoke contract를 검증한다는 점을 명확히 쓴다.
   - 다음 phase 후보를 Docker 이후 자연스러운 방향으로 남긴다: ASGI/FastAPI thin adapter, live Docker e2e with approved daemon, operator action UI wiring.
3. 전체 관련 테스트를 실행한다.
4. phase metadata를 마감한다.
   - `/phases/9-live-docker-compose-integration/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
   - top-level `/phases/index.json`는 하네스가 phase 완료 시 갱신하므로 수동으로 완료 처리하지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest \
  scripts/test_docker_runtime_image_contracts.py \
  scripts/test_docker_compose_runtime_services.py \
  scripts/test_docker_runtime_smoke.py \
  scripts/test_docker_compose_config_validation.py \
  scripts/test_docker_phase_public_contracts.py \
  scripts/test_compose_readiness_smoke.py \
  scripts/test_e2e_integration_public_contracts.py \
  scripts/test_operator_action_public_contracts.py
PYTHONPATH=app python3 -m token_payments smoke docker-runtime-readiness
docker compose --env-file .env.example --profile runtime config --services
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/9-live-docker-compose-integration/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Automated AC에서 `docker compose up`, `docker compose run`, `docker build`를 실행하지 마라.
- local `.env`를 생성/수정/커밋하지 마라.
- live Docker/Kafka/PostgreSQL 연결을 runtime smoke 기본 경로에 넣지 마라.
- `scripts/execute.py`에 프로젝트별 Docker 구현 로직을 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

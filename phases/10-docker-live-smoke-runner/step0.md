# Step 0: docker-live-smoke-plan-contract

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
- `/scripts/test_docker_runtime_smoke.py`
- `/scripts/test_docker_compose_config_validation.py`
- `/phases/9-live-docker-compose-integration/index.json`

## 작업

Live Docker compose smoke를 실행하기 전에, 실행 순서와 안전 계약을 JSON으로 확인할 수 있는 dry-run planner를 추가한다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_docker_live_smoke_plan.py`를 추가한다.
   - `scripts/docker_live_smoke.py --plan`이 bounded JSON을 stdout으로 출력해야 한다.
   - 인자 없이 실행해도 기본은 dry-run plan이어야 하며 Docker daemon, Docker socket, network, filesystem write를 시작하지 않아야 한다.
   - payload는 `contract`, `mode`, `status`, `dockerStarted`, `networkCalls`, `envFile`, `requiredServices`, `commandSequence`, `cleanupCommand`를 포함해야 한다.
   - `commandSequence`는 다음 순서를 고정해야 한다.
     - `compose-config`: `docker compose --env-file .env --profile runtime config --services`
     - `start-infrastructure`: `docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network`
     - `runtime-health`: `docker compose --env-file .env --profile runtime run --rm token_payments_health`
     - `runtime-worker`: `docker compose --env-file .env --profile runtime run --rm token_payments_worker`
     - `runtime-smoke`: `docker compose --env-file .env --profile smoke run --rm token_payments_smoke`
   - cleanup command는 `docker compose --env-file .env down`이어야 한다.
   - 모든 command는 list argv와 display string을 함께 제공해야 하며 `shell=True` 전제가 없어야 한다.
   - plan payload에 `.env.example`의 민감 placeholder 값, private key, seed phrase, Claude 전용 명령/파일명이 노출되지 않아야 한다.
2. `scripts/docker_live_smoke.py`를 추가한다.
   - 표준 라이브러리만 사용한다.
   - 기본 실행과 `--plan`은 동일하게 live Docker를 시작하지 않는 JSON plan만 출력한다.
   - root 경로는 script 위치 기준으로 안정적으로 계산한다.
   - command argv는 중앙 상수/데이터 구조에서 만들고, 문자열 조합은 표시용으로만 사용한다.
   - 이 step에서는 live 실행 모드를 구현하지 않는다. `--execute`가 들어오면 JSON error로 거부한다.
3. 기존 Dockerfile, docker-compose, runtime smoke 계약을 깨뜨리지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_docker_live_smoke_plan.py scripts/test_docker_runtime_smoke.py
python3 scripts/docker_live_smoke.py --plan
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/10-docker-live-smoke-runner/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step에서 `docker compose up`, `docker compose run`, `docker build`, Docker socket 접근을 실행하지 마라.
- local `.env`를 생성/수정하지 마라.
- 새 third-party dependency를 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 Docker 구현 로직을 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

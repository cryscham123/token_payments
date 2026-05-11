# Step 1: docker-live-smoke-execution-guardrails

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/README.md`
- `/app/README.md`
- `/docker-compose.yml`
- `/.env.example`
- `/scripts/docker_live_smoke.py`
- `/scripts/test_docker_live_smoke_plan.py`
- `/scripts/test_docker_compose_config_validation.py`
- `/phases/10-docker-live-smoke-runner/index.json`

## 작업

`scripts/docker_live_smoke.py`에 명시 승인형 live execution 모드를 추가한다. automated harness에서는 실제 Docker를 시작하지 않고 mock/subprocess injection 테스트로 실행 가드만 검증한다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_docker_live_smoke_execution.py`를 추가한다.
   - `--execute`만 주면 Docker를 시작하지 않고 JSON error를 반환해야 한다.
   - live 실행은 `--execute --confirm-live-docker`가 모두 있을 때만 허용해야 한다.
   - live 실행은 `.env`를 기본 env file로 요구해야 하며 `.env.example`을 live env file로 사용하려 하면 거부해야 한다.
   - 테스트는 `subprocess.run`을 monkeypatch/mock 하여 Docker daemon이 없어도 command sequence, timeout, cwd, shell 미사용을 검증해야 한다.
   - command 실패 시 `docker compose --env-file .env down` cleanup을 시도하고 JSON failure payload에 실패 step name과 exit code를 남겨야 한다.
   - 성공 시 JSON success payload에 실행된 step 이름, command count, cleanup 실행 여부를 남겨야 한다.
   - stdout/stderr capture는 하되 payload에 민감 env 값을 노출하지 않아야 한다.
2. `scripts/docker_live_smoke.py`를 갱신한다.
   - `--execute`와 `--confirm-live-docker` 옵션을 추가한다.
   - `--env-file`은 기본 `.env`로 두되, live 실행에서 `.env.example`은 거부한다.
   - 각 Docker command는 bounded timeout을 가져야 한다.
   - `subprocess.run(..., shell=False, cwd=<repo root>, text=True, capture_output=True, timeout=<bounded>)` 형태를 유지한다.
   - infrastructure start 이후 어떤 command가 실패하더라도 cleanup command를 한 번 시도한다.
   - 실제 command stdout/stderr는 길이를 제한하고 secret-like 값을 redaction 한다.
3. plan mode payload는 step 0 테스트와 호환되어야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_docker_live_smoke_plan.py scripts/test_docker_live_smoke_execution.py scripts/test_docker_runtime_smoke.py
python3 scripts/docker_live_smoke.py --plan
python3 scripts/docker_live_smoke.py --execute
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다. `python3 scripts/docker_live_smoke.py --execute`는 Docker를 시작하지 않고 거부 JSON을 반환해야 한다.
2. `/phases/10-docker-live-smoke-runner/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Automated AC에서 `--confirm-live-docker`를 사용하지 마라.
- 테스트에서 실제 Docker daemon, Docker socket, network, PostgreSQL, Kafka에 접속하지 마라.
- local `.env`를 생성/수정/커밋하지 마라.
- `shell=True`를 사용하지 마라.
- `scripts/execute.py`에 프로젝트별 Docker 구현 로직을 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

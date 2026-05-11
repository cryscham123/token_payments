# Step 2: docker-live-smoke-public-verification

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
- `/scripts/docker_live_smoke.py`
- `/scripts/test_docker_live_smoke_plan.py`
- `/scripts/test_docker_live_smoke_execution.py`
- `/scripts/test_docker_phase_public_contracts.py`
- `/phases/9-live-docker-compose-integration/index.json`
- `/phases/10-docker-live-smoke-runner/index.json`
- `/phases/index.json`

## 작업

Docker live smoke runner 산출물을 public contract와 문서 관점에서 마감한다. 누락된 동작이 있으면 먼저 실패하는 테스트를 추가하고 구현을 보완한다.

1. `scripts/test_docker_live_smoke_public_contracts.py`를 추가한다.
   - `scripts/docker_live_smoke.py`, plan test, execution test가 모두 존재해야 한다.
   - `scripts/docker_live_smoke.py --plan` payload가 `docker-runtime-readiness`의 manual live command 순서와 호환되어야 한다.
   - script source가 `shell=True`, Docker SDK import, HTTP/network client import, Claude 전용 명령을 포함하지 않아야 한다.
   - README와 app README가 dry-run plan command, explicit live execution command, refusal behavior, cleanup behavior를 문서화해야 한다.
   - phase 10 metadata의 completed step summary가 plan contract, execution guardrail, public verification을 구체적으로 언급해야 한다.
2. README와 app README를 갱신한다.
   - automated harness에서 실행할 명령:
     - `python3 scripts/docker_live_smoke.py --plan`
     - `python3 scripts/docker_live_smoke.py --execute`
   - 실제 live Docker 실행은 명시 승인/수동 작업으로 분리하고 다음 명령을 문서화한다.
     - `cp .env.example .env`
     - `python3 scripts/docker_live_smoke.py --execute --confirm-live-docker`
   - `--execute` 단독은 Docker를 시작하지 않고 거부 JSON을 반환한다는 점을 명확히 쓴다.
   - failure 중에도 cleanup command가 시도된다는 점을 쓴다.
3. 관련 Docker 테스트와 phase 검증을 실행한다.
4. phase metadata를 마감한다.
   - `/phases/10-docker-live-smoke-runner/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
   - top-level `/phases/index.json`는 하네스가 phase 완료 시 갱신하므로 수동으로 완료 처리하지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest \
  scripts/test_docker_live_smoke_plan.py \
  scripts/test_docker_live_smoke_execution.py \
  scripts/test_docker_live_smoke_public_contracts.py \
  scripts/test_docker_runtime_smoke.py \
  scripts/test_docker_phase_public_contracts.py
python3 scripts/docker_live_smoke.py --plan
python3 scripts/docker_live_smoke.py --execute
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다. `python3 scripts/docker_live_smoke.py --execute`는 Docker를 시작하지 않고 거부 JSON을 반환해야 한다.
2. `/phases/10-docker-live-smoke-runner/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Automated AC에서 `--confirm-live-docker`를 사용하지 마라.
- local `.env`를 생성/수정/커밋하지 마라.
- live Docker/Kafka/PostgreSQL 연결을 runtime smoke 기본 경로에 넣지 마라.
- `scripts/execute.py`에 프로젝트별 Docker 구현 로직을 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

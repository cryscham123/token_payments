# Step 2: worker-cli-compose-live-boundary

## 읽어야 할 파일

- `/AGENTS.md`
- `/docker-compose.yml`
- `/Dockerfile`
- `/requirements-runtime.txt`
- `/app/token_payments/runtime/entrypoint.py`
- `/app/token_payments/runtime/config.py`
- `/app/token_payments/runtime/api_server.py`
- `/app/token_payments/runtime/smoke.py`
- `/scripts/test_docker_compose_runtime_services.py`
- `/scripts/test_compose_live_server_public_contracts.py`
- `/scripts/test_api_worker_runtime_public_contracts.py`
- `/phases/24-live-kafka-worker-runtime/index.json`

## 작업

live worker가 실제 DB/Kafka network를 여는 경로를 명시 flag와 compose service로 분리한다.

1. `scripts/test_live_worker_entrypoint_contracts.py`를 추가한다.
   - `worker` 기본 command는 bounded preview/no-live behavior를 유지해야 한다.
   - `worker --live --once`는 live worker runtime을 한 batch 실행할 계획을 만든다.
   - long-running mode가 있다면 `--confirm-live-worker` 같은 명시 confirmation 없이는 시작하지 않아야 한다.
   - dry-run은 DB/Kafka connection을 열지 않고 worker plan과 required env를 반환해야 한다.
2. CLI dispatch를 갱신한다.
   - `worker --live --dry-run`
   - `worker --live --once`
   - optional `worker --live --loop --confirm-live-worker`
   - exit code와 JSON summary는 기존 `CommandDispatchResult` contract를 따른다.
3. Docker compose를 갱신한다.
   - existing one-shot worker service는 명시적인 live once command를 사용할지, preview worker로 남길지 문서화한다.
   - 필요한 경우 `token_payments_live_worker` service를 별도로 추가한다.
   - live worker service는 postgres healthy, kafka started, test network started 이후 시작되어야 한다.
4. runtime docs를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_live_worker_entrypoint_contracts.py scripts/test_docker_compose_runtime_services.py scripts/test_compose_live_server_public_contracts.py scripts/test_api_worker_runtime_public_contracts.py
PYTHONPATH=app python3 -m token_payments worker --live --dry-run
python3 scripts/validate_phases.py
```

## 검증 절차

1. entrypoint/compose contract 테스트를 먼저 추가하고 실패를 확인한다.
2. CLI/config/compose/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/24-live-kafka-worker-runtime/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- CI/default test path에서 Docker daemon, PostgreSQL, Kafka, Blockchain RPC를 자동으로 시작하지 마라.
- live worker confirmation 없이 long-running process를 시작하지 마라.
- compose service 이름을 기존 smoke docs와 충돌하게 바꾸지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

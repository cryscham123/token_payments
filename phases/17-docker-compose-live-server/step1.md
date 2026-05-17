# Step 1: live-runtime-driver-factory

## 읽어야 할 파일

- `/AGENTS.md`
- `/Dockerfile`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/runtime/api_server.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/app/token_payments/contexts/auth/adapter/postgres.py`
- `/app/token_payments/shared/adapter/postgres/protocols.py`
- `/app/token_payments/contexts/auth/adapter/wallet_signature.py`
- `/app/token_payments/contexts/payment/adapter/blockchain.py`
- `/app/token_payments/contexts/payment/adapter/transaction_service.py`
- `/scripts/test_live_api_server_entrypoint.py`
- `/scripts/test_live_api_facade_wiring.py`
- `/scripts/test_docker_runtime_image_contracts.py`

## 작업

Live server가 `LiveRuntimeDependencies()` 누락으로 즉시 종료되지 않도록 runtime driver factory를 구현한다. 이 step은 production-grade driver wrapper를 추가하되, import 시점에는 외부 연결을 열지 않는다.

1. `scripts/test_live_runtime_driver_factory.py`를 추가한다.
   - env/config에서 PostgreSQL session factory, Kafka producer, wallet signature client, blockchain client, clock, id generator가 구성되는지 검증한다.
   - missing env/dependency는 bounded configuration error로 보고해야 한다.
   - module import만으로 network socket, Docker, DB, Kafka 연결을 열지 않아야 한다.
   - Docker image contract가 live API 실행에 필요한 Python dependency를 설치하는지 검증한다. 예: ASGI server, PostgreSQL driver, Kafka client, HTTP/RPC client가 project policy에 맞게 포함된다.
2. runtime composition을 갱신한다.
   - `build_live_runtime_dependencies_from_env()` 또는 동등한 factory를 추가한다.
   - 실제 driver import는 lazy boundary에 둔다.
   - dependency summary는 DSN password, token, private key, RPC credential을 redaction한다.
3. Dockerfile/runtime dependency metadata를 갱신한다.
   - live API container에서 `uvicorn` 또는 선택한 ASGI server가 사용 가능해야 한다.
   - dependency 설치 방식은 reproducible하고 root README에 설명되어야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_live_runtime_driver_factory.py scripts/test_live_api_server_entrypoint.py scripts/test_live_api_facade_wiring.py scripts/test_docker_runtime_image_contracts.py
PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run
python3 scripts/validate_phases.py
```

## 검증 절차

1. driver factory 테스트를 먼저 추가하고 실패를 확인한다.
2. runtime/Dockerfile/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/17-docker-compose-live-server/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- import 시점에 PostgreSQL/Kafka/Blockchain network 연결을 열지 마라.
- missing dependency를 `None`으로 조용히 무시하지 마라.
- `pip install`을 harness step 실행 중에 수행하지 마라. 필요한 dependency는 Docker/runtime contract로 고정한다.
- secret 원문을 readiness/debug JSON에 노출하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

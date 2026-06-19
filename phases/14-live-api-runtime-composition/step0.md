# Step 0: live-runtime-composition-contract

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/README.md`
- `/app/README.md`
- `/.env.example`
- `/app/token_payments/runtime/config.py`
- `/app/token_payments/runtime/contracts.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/asgi.py`
- `/app/token_payments/api/fastapi.py`
- `/app/token_payments/shared/adapter/postgres/protocols.py`
- `/app/token_payments/shared/adapter/kafka/publisher.py`
- `/app/token_payments/contexts/auth/adapter/wallet_signature.py`
- `/app/token_payments/contexts/payment/adapter/blockchain.py`
- `/scripts/test_api_worker_runtime_public_contracts.py`
- `/scripts/test_fastapi_asgi_public_contracts.py`
- `/scripts/test_adapter_infrastructure_public_contracts.py`
- `/phases/13-fastapi-asgi-adapter/index.json`

## 작업

실제 API runtime composition을 만들기 전에, live dependency와 runtime 설정을 명확한 public contract로 고정한다. 이 step은 서버를 시작하거나 DB/Kafka/Blockchain에 연결하지 않는다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_live_api_runtime_composition.py`를 추가한다.
   - `token_payments.runtime` public export에 live API composition surface가 포함되는지 검증한다. 이름은 구현에 맞게 정하되 `LiveRuntimeConfig`, `LiveRuntimeDependencies`, `LiveApiComposition`, `describe_live_runtime_dependencies` 또는 동등한 명시적 contract여야 한다.
   - `RuntimeConfig.from_env()` 또는 분리된 live config가 `.env.example`의 API/adapter 환경 변수를 파싱해야 한다: `RUNTIME_API_HOST`, `RUNTIME_API_PORT`, `RUNTIME_REQUEST_TIMEOUT_SECONDS`, `ADAPTER_POSTGRES_DSN`, `ADAPTER_KAFKA_BOOTSTRAP_SERVERS`, `ADAPTER_KAFKA_CLIENT_ID`, `ADAPTER_WALLET_SIGNATURE_DOMAIN`, `ADAPTER_BLOCKCHAIN_RPC_URL`, `ADAPTER_BLOCKCHAIN_CHAIN_ID`, `ADAPTER_BLOCKCHAIN_NATIVE_SYMBOL`, `ADAPTER_BLOCKCHAIN_NATIVE_DECIMALS`, `ADAPTER_BLOCKCHAIN_DEPLOYED_CONTRACTS_PATH`, `ADAPTER_BLOCKCHAIN_GAS_BUFFER_RATE`.
   - config의 JSON/debug payload는 DSN password, private key, token address placeholder 같은 민감 값을 그대로 노출하지 않고 redacted summary만 제공해야 한다.
   - live composition module import와 dependency description은 `psycopg`, `psycopg2`, `asyncpg`, `kafka`, `confluent_kafka`, `web3`, `requests`, `fastapi`, `starlette`, `uvicorn`, `docker`, `dotenv`, `socket`을 import하지 않아야 한다.
   - live dependencies는 PostgreSQL connection/session factory, Kafka producer/client, wallet signature client, blockchain client, clock, id generator를 constructor로 주입받아야 하며 module import나 object 생성 시 외부 연결을 열면 안 된다.
   - 기존 `ContractRuntimeContainer`, `api`, `serve-api`, `health`, `worker`, `smoke` command는 bounded JSON preview 계약과 no-server-start 경계를 유지해야 한다.
2. `app/token_payments/runtime/composition.py` 또는 동등한 module을 추가한다.
   - live API runtime dependency graph를 표현하는 dataclass/protocol을 둔다.
   - dependency validation은 누락된 필수 dependency를 명확한 bounded error로 보고해야 한다.
   - `describe_live_runtime_dependencies()`는 Postman/Docker readiness phase가 사용할 수 있는 JSON-safe metadata를 반환하되 secret 값을 redaction한다.
   - 실제 PostgreSQL/Kafka/Blockchain driver 생성은 이 step에서 구현하지 않는다. 필요한 외부 client는 모두 outer composition이 주입한다.
3. `app/token_payments/runtime/__init__.py` public export를 갱신한다.
4. README/app README는 필요 최소 범위에서 live API runtime composition이 다음 phase임을 유지하되, 실제 실행 방법은 Step 2/3에서 완성한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_live_api_runtime_composition.py scripts/test_api_worker_runtime_public_contracts.py scripts/test_fastapi_asgi_public_contracts.py scripts/test_adapter_infrastructure_public_contracts.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/14-live-api-runtime-composition/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 하네스 기본 실행 경로에서 PostgreSQL/Kafka/Blockchain/Docker/local `.env`에 접근하지 마라.
- 이 step에서 `pip install`, driver 추가, network socket 생성, FastAPI/Uvicorn server 실행을 하지 마라.
- secret, DSN password, private key, seed phrase, 실제 token address를 JSON preview나 README에 노출하지 마라.
- 기존 `ContractRuntimeContainer`의 bounded preview 계약을 깨뜨리지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

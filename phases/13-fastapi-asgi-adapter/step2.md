# Step 2: fastapi-runtime-public-contracts

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/api/asgi.py`
- `/app/token_payments/api/fastapi.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/__init__.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/app/token_payments/runtime/smoke.py`
- `/scripts/test_fastapi_thin_adapter.py`
- `/scripts/test_asgi_adapter_contract_foundation.py`
- `/scripts/test_wsgi_runtime_preview.py`
- `/scripts/test_api_worker_runtime_public_contracts.py`
- `/scripts/test_browser_preview_public_contracts.py`
- `/phases/index.json`
- `/phases/13-fastapi-asgi-adapter/index.json`

## 작업

ASGI/FastAPI adapter phase의 runtime preview, public contract, 문서를 고정한다. 실제 서버 기동은 자동화하지 않고, optional FastAPI adapter factory와 실행 경계를 명확히 드러낸다.

1. `scripts/test_fastapi_asgi_public_contracts.py`를 추가한다.
   - `token_payments.api` public exports가 ASGI/FastAPI adapter surface를 포함하는지 검증한다.
   - `PYTHONPATH=app python3 -m token_payments api`와 `serve-api` bounded JSON preview가 기존 route manifest와 함께 `asgiFactory`, `fastapiFactory`, `fastapiAvailable`, `longRunning=false`, `serverStarted=false` 같은 adapter metadata를 포함하는지 검증한다.
   - preview는 route count 16, operator action operation ids, UI intent endpoint metadata와 일치해야 한다.
   - runtime preview와 smoke registry가 server start, network bind, Docker/Kafka/PostgreSQL/Blockchain/local `.env` 접근을 수행하지 않는지 검증한다.
   - README와 app README가 ASGI/FastAPI thin adapter 사용 범위, optional dependency boundary, verification commands, no-server-start boundary, manual production serve 예시를 문서화하는지 검증한다.
   - `phases/13-fastapi-asgi-adapter/index.json` step summary/status와 `phases/index.json` top-level phase 상태가 `validate_phases`와 일관되어야 한다.
2. `app/token_payments/runtime/entrypoint.py`를 갱신한다.
   - `api`/`serve-api` preview는 여전히 bounded JSON만 반환하고 서버를 시작하지 않는다.
   - details에 기존 `framework-neutral-wsgi` metadata를 유지하면서 ASGI/FastAPI adapter factory metadata를 추가한다.
   - FastAPI가 미설치인 경우에도 preview command는 성공하고 `fastapiAvailable=false` 및 unavailable reason을 표시해야 한다.
3. README와 app README에 `ASGI/FastAPI Thin Adapter` 섹션을 추가한다.
   - 기존 route manifest와 facade contract를 유지한다는 점을 명시한다.
   - 하네스 검증 명령을 정확히 적는다.
   - 실제 production server 실행은 수동/명시적 환경에서만 수행하며 하네스 기본 경로에서는 실행하지 않는다고 명시한다.
   - 다음 후보를 갱신한다: live API runtime composition, Postman Docker API readiness, FastAPI optional dependency live smoke.
4. 필요하면 public contract/README 기대값 테스트를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_fastapi_asgi_public_contracts.py scripts/test_fastapi_thin_adapter.py scripts/test_asgi_adapter_contract_foundation.py scripts/test_wsgi_runtime_preview.py scripts/test_api_worker_runtime_public_contracts.py scripts/test_browser_preview_public_contracts.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/13-fastapi-asgi-adapter/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 하네스 기본 실행 경로에서 Uvicorn/FastAPI server를 시작하거나 network port를 bind하지 마라.
- FastAPI/Starlette/Uvicorn 설치를 자동화하지 마라.
- DB, Kafka, Blockchain RPC, Docker daemon, local `.env`에 접근하지 마라.
- route manifest, operation id, WSGI callable, browser preview route manifest 계약을 깨뜨리지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

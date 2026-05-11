# Step 4: wsgi-runtime-preview

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/phases/7-http-framework-adapter/index.json`
- `/app/token_payments/api/http.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/app/token_payments/runtime/contracts.py`
- `/app/token_payments/runtime/config.py`
- `/app/token_payments/__main__.py`
- `/scripts/test_runtime_contract_foundation.py`
- `/scripts/test_api_worker_runtime_public_contracts.py`

## 작업

HTTP adapter를 WSGI-compatible callable과 bounded runtime preview로 연결한다. 이 step은 production server를 띄우는 것이 아니라, framework가 붙을 수 있는 importable boundary와 CLI route manifest를 고정하는 작업이다.

1. `scripts/test_wsgi_runtime_preview.py`를 추가한다.
   - `build_wsgi_app(router)` 또는 동등한 factory가 WSGI `environ`/`start_response`를 받아 `HttpRouter`를 호출하는지 검증한다.
   - query string, request body bytes, headers, request id가 `ApiRequest`로 전달되는지 검증한다.
   - response status line, headers, body iterable이 WSGI contract에 맞는지 검증한다.
   - `OPTIONS` 또는 route manifest 조회가 필요한 경우 bounded JSON response로 유지한다.
2. runtime `api` command를 확장한다.
   - long-running server를 시작하지 않는다.
   - `PYTHONPATH=app python3 -m token_payments api`는 route manifest와 adapter summary를 bounded JSON으로 반환해야 한다.
   - `serve-api`도 기존처럼 command accepted 상태를 유지하되, 실제 서버 loop를 시작하지 않는다.
3. route manifest helper를 정리한다.
   - 모든 auth/order/checkout/payment/operator route가 method/path/operation id로 나열되어야 한다.
   - manifest는 docs와 테스트에서 재사용할 수 있게 deterministic ordering을 가져야 한다.
4. public export를 정리한다.
   - WSGI factory와 manifest helper가 `token_payments.api` 또는 명확한 하위 module에서 import 가능해야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_wsgi_runtime_preview.py scripts/test_runtime_contract_foundation.py scripts/test_api_worker_runtime_public_contracts.py scripts/test_http_adapter_contract_foundation.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/7-http-framework-adapter/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- gunicorn, uvicorn, waitress 같은 server dependency를 추가하지 마라.
- CLI command가 테스트 중 무기한 대기하는 long-running process가 되게 하지 마라.
- Codex CLI 옵션/하네스 실행 경로를 수정하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

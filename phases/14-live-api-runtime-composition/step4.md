# Step 4: explicit-live-api-server-entrypoint

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/API_SPEC.md`
- `/README.md`
- `/app/README.md`
- `/.env.example`
- `/app/token_payments/__main__.py`
- `/app/token_payments/runtime/config.py`
- `/app/token_payments/runtime/contracts.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/runtime/session_transport.py`
- `/app/token_payments/runtime/security.py`
- `/app/token_payments/api/asgi.py`
- `/app/token_payments/api/fastapi.py`
- `/scripts/test_live_api_runtime_composition.py`
- `/scripts/test_live_api_facade_wiring.py`
- `/scripts/test_cookie_session_transport.py`
- `/scripts/test_csrf_cors_request_guard.py`
- `/scripts/test_fastapi_asgi_public_contracts.py`
- `/scripts/test_docker_live_smoke_plan.py`
- `/phases/14-live-api-runtime-composition/index.json`

## 작업

live API router를 실제 long-running server로 넘길 수 있는 명시적 entrypoint를 추가한다. 기본 `api`/`serve-api` 명령은 계속 서버를 시작하지 않아야 하며, live server 실행은 explicit live flag와 confirmation 없이는 bounded refusal JSON으로 끝나야 한다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_live_api_server_entrypoint.py`를 추가한다.
   - `PYTHONPATH=app python3 -m token_payments serve-api`는 기존처럼 `serverStarted=false`, `longRunning=false` preview를 반환해야 한다.
   - `PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run` 또는 동등한 explicit dry-run command는 live API server plan을 JSON으로 반환하고 network port를 bind하지 않아야 한다.
   - `--live` 실행에 confirmation이 없으면 bounded refusal JSON을 반환해야 하며, exit code와 summary가 자동 실행에서 왜 서버를 시작하지 않았는지 명확해야 한다.
   - confirmed live 실행 경로는 injectable runner/fake runner로 테스트해야 하며, 테스트 중 `uvicorn.run`, socket bind, Docker, DB/Kafka/Blockchain/local `.env` 접근이 발생하지 않아야 한다.
   - live server plan payload는 host, port, app factory, route count, required dependency groups, env-backed session key validation status, active key id redacted summary, cookie/CSRF/CORS guard enabled status, redaction status, `requiresConfirmation=true`, `serverStarted=false`, `longRunning=true`를 포함해야 한다.
   - live server start validation은 missing/placeholder `SESSION_SIGNING_KEYS` 또는 missing `SESSION_ACTIVE_KEY_ID`를 bounded error로 거부해야 한다.
   - FastAPI/Uvicorn이 설치되지 않은 환경에서도 dry-run과 refusal path는 성공해야 하며 optional dependency unavailable reason을 포함해야 한다.
   - `__main__.py`는 여전히 thin dispatcher여야 하고 project-specific live logic을 직접 품지 않아야 한다.
2. `app/token_payments/runtime/api_server.py` 또는 동등한 module을 추가한다.
   - live API server plan/result DTO를 표준 라이브러리 기반으로 둔다.
   - `build_live_asgi_application(...)`은 Step 1의 live router와 Step 2/3의 cookie/CSRF/CORS guard를 `build_asgi_app` 또는 optional `build_fastapi_app`에 연결한다.
   - actual server runner는 injectable callable 또는 lazy optional import로 격리한다. module import 시 `uvicorn`을 필수 import하지 않는다.
   - confirmed live 실행이 필요한 경우에만 runner를 호출하고, host/port는 runtime config에서 가져온다.
3. `dispatch_runtime_command` parsing을 확장한다.
   - `serve-api --live --dry-run`, `serve-api --live`, `serve-api --live --confirm-live-api` 같은 explicit mode를 구분할 수 있어야 한다.
   - 기존 `api`, `serve-api`, `ui`, `smoke`, `worker`, `health` 동작과 출력 shape를 깨뜨리지 않는다.
4. README/app README에는 실행 경계만 최소 문서화하고, Docker compose service와 Postman examples는 phase 15에 남긴다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_live_api_server_entrypoint.py scripts/test_csrf_cors_request_guard.py scripts/test_cookie_session_transport.py scripts/test_live_api_facade_wiring.py scripts/test_live_api_runtime_composition.py scripts/test_fastapi_asgi_public_contracts.py scripts/test_docker_live_smoke_plan.py
PYTHONPATH=app python3 -m token_payments serve-api
PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run
PYTHONPATH=app python3 -m token_payments serve-api --live
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 entrypoint 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/14-live-api-runtime-composition/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 자동 하네스 검증에서 real server, socket bind, Docker, PostgreSQL, Kafka, Blockchain RPC, local `.env` 접근을 수행하지 마라.
- confirmation 없는 `--live`가 서버를 시작하게 만들지 마라.
- `api`/`serve-api` 기본 preview를 long-running command로 바꾸지 마라.
- FastAPI/Uvicorn 설치를 자동화하지 마라.
- Docker compose API service나 Postman collection을 이 step에 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

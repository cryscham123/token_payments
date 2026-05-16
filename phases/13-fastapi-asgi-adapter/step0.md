# Step 0: asgi-adapter-contract-foundation

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/__init__.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/scripts/test_http_adapter_contract_foundation.py`
- `/scripts/test_wsgi_runtime_preview.py`
- `/scripts/test_http_adapter_public_contracts.py`
- `/scripts/test_operator_action_http_routes.py`
- `/phases/7-http-framework-adapter/index.json`
- `/phases/8-operator-action-endpoints/index.json`
- `/phases/12-operator-action-ui-wiring/index.json`

## 작업

FastAPI adapter를 얇게 얹기 전에, 기존 `HttpRouter`/`ApiRequest`/`ApiResponse` contract를 깨뜨리지 않는 표준 ASGI adapter foundation을 추가한다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_asgi_adapter_contract_foundation.py`를 추가한다.
   - `token_payments.api` public export에 `AsgiApplication`, `AsgiReceive`, `AsgiScope`, `AsgiSend`, `build_asgi_app` 또는 동등한 ASGI boundary surface가 포함되는지 검증한다.
   - `build_asgi_app(HttpRouter)`가 ASGI `scope`, `receive`, `send`를 `HttpRequest`로 변환하고 `HttpResponse`를 `http.response.start`/`http.response.body` 이벤트로 직렬화하는지 검증한다.
   - `GET` query string, path params, `X-Request-Id`, JSON `POST` body, content type, response headers, deterministic body serialization을 검증한다.
   - unknown route는 404 JSON, method mismatch는 405 JSON과 `Allow` header, malformed JSON은 400 JSON으로 반환되어야 한다.
   - lifespan/websocket scope는 명확한 bounded error 또는 unsupported response로 처리하고 long-running loop를 시작하지 않아야 한다.
   - ASGI adapter foundation은 `fastapi`, `starlette`, `uvicorn`, `requests`, `httpx`, DB/Kafka/Blockchain/Docker client를 import하지 않아야 한다.
2. `app/token_payments/api/asgi.py`를 추가한다.
   - 표준 라이브러리만 사용해 ASGI callable을 만든다.
   - 기존 `HttpRouter`를 유일한 dispatch boundary로 사용하고 API facade를 직접 호출하지 않는다.
   - request body는 `receive()` 이벤트를 bounded 방식으로 모아 `HttpRouter.handle()`에 전달한다.
   - response는 기존 `HttpResponse` headers/body를 보존하고 `more_body=False`로 종료한다.
3. `app/token_payments/api/__init__.py` public export를 갱신한다.
4. 기존 WSGI adapter와 route manifest 테스트가 그대로 통과하도록 유지한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_asgi_adapter_contract_foundation.py scripts/test_http_adapter_contract_foundation.py scripts/test_wsgi_runtime_preview.py scripts/test_operator_action_http_routes.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/13-fastapi-asgi-adapter/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step에서 FastAPI, Starlette, Uvicorn 또는 새 third-party dependency를 import하거나 설치하지 마라.
- ASGI adapter가 network port를 bind하거나 long-running server를 시작하지 않게 하라.
- DB, Kafka, Blockchain RPC, Docker daemon, local `.env`에 접근하지 마라.
- 기존 `build_wsgi_app`, `HttpRouter`, `http_route_manifest` public contract를 깨뜨리지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 1: fastapi-thin-adapter

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/api/asgi.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/__init__.py`
- `/app/token_payments/runtime/config.py`
- `/scripts/test_asgi_adapter_contract_foundation.py`
- `/scripts/test_http_adapter_public_contracts.py`
- `/scripts/test_operator_action_public_contracts.py`
- `/scripts/test_docker_compose_runtime_services.py`
- `/phases/13-fastapi-asgi-adapter/index.json`

## 작업

표준 ASGI foundation 위에 optional FastAPI production adapter를 얇게 추가한다. 하네스 환경은 FastAPI 설치를 요구하지 않아야 하므로 import guard와 명확한 unavailable contract를 먼저 테스트로 고정한다.

1. `scripts/test_fastapi_thin_adapter.py`를 추가한다.
   - `token_payments.api` public export에 `FastApiAdapterUnavailable`, `build_fastapi_app`, `is_fastapi_available` 또는 동등한 FastAPI adapter surface가 포함되는지 검증한다.
   - FastAPI가 설치되어 있지 않아도 `import token_payments.api.fastapi`와 `import token_payments.api`가 실패하지 않아야 한다.
   - FastAPI가 없을 때 `build_fastapi_app(...)`는 `ImportError`가 아니라 명확한 domain-specific unavailable exception과 설치 힌트를 반환/raise해야 한다.
   - FastAPI가 있을 때 사용할 route metadata는 기존 `http_route_manifest()`와 같은 16개 route, 같은 method/path/operation id를 사용해야 한다.
   - adapter source는 API facade를 새로 구현하지 않고 `build_asgi_app` 또는 `HttpRouter`만 dispatch boundary로 사용해야 한다.
   - FastAPI adapter module 외부의 core API/domain/application/runtime modules는 `fastapi`, `starlette`, `uvicorn`에 의존하지 않아야 한다.
2. `app/token_payments/api/fastapi.py`를 추가한다.
   - module import 시점에는 FastAPI를 필수 import하지 말고 lazy import 또는 availability probe를 사용한다.
   - `build_fastapi_app(router: HttpRouter, *, title: str = ..., version: str = ...)` 같은 얇은 factory를 제공한다.
   - FastAPI app은 기존 route manifest의 operation id와 path template을 보존해야 한다.
   - request/response 변환은 Step 0의 ASGI adapter 또는 기존 `HttpRouter`를 통해 수행하고, endpoint별 business logic을 중복 구현하지 않는다.
   - optional dependency 설치/실행 안내는 문서에만 남기고 하네스에서 `pip install`, `uvicorn`, network bind를 실행하지 않는다.
3. `app/token_payments/api/__init__.py` public export를 갱신한다.
4. 기존 forbidden-import 테스트를 갱신해 `app/token_payments/api/fastapi.py`만 FastAPI import를 허용하고, domain/application/core API facade에는 금지 상태를 유지한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_fastapi_thin_adapter.py scripts/test_asgi_adapter_contract_foundation.py scripts/test_http_adapter_public_contracts.py scripts/test_operator_action_public_contracts.py scripts/test_docker_compose_runtime_services.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/13-fastapi-asgi-adapter/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 하네스 실행 중 FastAPI/Uvicorn 설치, package download, `uvicorn` 실행, network port bind를 수행하지 마라.
- FastAPI adapter 밖의 domain/application/API facade/runtime core에 FastAPI/Starlette/Uvicorn import를 퍼뜨리지 마라.
- route manifest, operation id, path template, WSGI callable contract를 바꾸지 마라.
- DB, Kafka, Blockchain RPC, Docker daemon, local `.env`에 접근하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

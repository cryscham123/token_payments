# Step 3: csrf-cors-request-guard

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
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/asgi.py`
- `/app/token_payments/runtime/config.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/runtime/session_transport.py`
- `/scripts/test_cookie_session_transport.py`
- `/scripts/test_asgi_adapter_contract_foundation.py`
- `/scripts/test_fastapi_asgi_public_contracts.py`
- `/phases/14-live-api-runtime-composition/index.json`

## 작업

Cookie auth를 안전하게 쓰기 위해 CSRF, CORS, request guard를 live API adapter 경계에 추가한다. 이 step은 보안 transport contract를 고정하지만 live server/network를 시작하지 않는다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_csrf_cors_request_guard.py`를 추가한다.
   - CSRF token 발급 surface를 검증한다. `GET /auth/csrf`를 route manifest에 추가하거나 login challenge response에 CSRF token/cookie를 포함하는 방식 중 하나를 선택하되, 최종 Postman/browser flow가 명확해야 한다.
   - mutating methods `POST`, `PUT`, `PATCH`, `DELETE`는 cookie-authenticated request일 때 `X-CSRF-Token` 또는 동등한 double-submit token 검증을 통과해야 한다.
   - CSRF 실패는 `403 CSRF_TOKEN_MISSING` 또는 `403 CSRF_TOKEN_INVALID` 형태의 bounded JSON error를 반환해야 한다.
   - safe methods `GET`, `HEAD`, `OPTIONS`는 CSRF token을 요구하지 않아야 한다.
   - credentialed CORS는 origin allowlist 기반이어야 하며 wildcard origin과 credentials 조합을 허용하면 안 된다.
   - preflight `OPTIONS`는 route handler business logic을 호출하지 않고 bounded CORS headers를 반환해야 한다.
   - request body max size를 초과하면 `413 REQUEST_BODY_TOO_LARGE`, malformed JSON은 기존 `400 MALFORMED_JSON` contract를 유지해야 한다.
   - guard source는 real DB/Kafka/Blockchain/Docker client, FastAPI/Starlette/Uvicorn에 직접 의존하지 않아야 한다.
2. `app/token_payments/runtime/security.py` 또는 동등한 module을 추가한다.
   - `CsrfTokenService`, `CorsPolicy`, `RequestGuard`, `RequestBodyLimit` 또는 동등한 표준 라이브러리 기반 contract를 제공한다.
   - origin allowlist는 `RuntimeConfig` 또는 live config에서 파싱한다. `.env.example`에는 local browser origin 예시를 민감정보 없이 추가한다.
   - CSRF token signing/verification은 주입 가능한 signer/secret provider 경계로 둔다. 하네스 테스트에서는 deterministic fake를 사용한다.
3. ASGI/HTTP adapter boundary에 guard를 적용한다.
   - guard는 `HttpRouter` dispatch 전에 실행되어야 한다.
   - guard가 차단한 request는 facade/application service를 호출하지 않아야 한다.
4. `docs/API_SPEC.md`와 README/app README를 갱신한다.
   - cookie auth request에는 CSRF token이 필요하다는 점을 명시한다.
   - CORS credentials와 allowed origin 정책을 문서화한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_csrf_cors_request_guard.py scripts/test_cookie_session_transport.py scripts/test_asgi_adapter_contract_foundation.py scripts/test_fastapi_asgi_public_contracts.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 security guard 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/14-live-api-runtime-composition/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- cookie auth와 credentialed CORS에서 wildcard origin을 허용하지 마라.
- mutating request의 CSRF 검증을 UI/클라이언트 책임으로만 남기지 마라.
- request guard가 domain/application layer에 침투하게 만들지 마라.
- live server, socket bind, Docker, real DB/Kafka/Blockchain/local `.env` 접근을 수행하지 마라.
- 새 third-party dependency를 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

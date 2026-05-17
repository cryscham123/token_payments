# Step 1: postman-cookie-auth-flow

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
- `/app/token_payments/runtime/session_transport.py`
- `/app/token_payments/runtime/security.py`
- `/scripts/test_cookie_session_transport.py`
- `/scripts/test_csrf_cors_request_guard.py`
- `/scripts/test_postman_docker_api_service.py`
- `/phases/15-postman-docker-api-readiness/index.json`

## 작업

Postman에서 cookie auth와 CSRF token flow를 그대로 검증할 수 있는 collection/examples를 추가한다. 이 step은 JSON fixture와 static contract를 만들며 live API server를 시작하지 않는다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_postman_cookie_auth_flow.py`를 추가한다.
   - committed Postman collection 또는 equivalent JSON examples가 존재해야 한다.
   - collection은 `POST /auth/challenges`, `POST /auth/sessions`, `POST /auth/sessions/refresh`, `DELETE /auth/sessions`, `GET /auth/me`를 포함해야 한다.
   - login response의 `Set-Cookie`를 Postman cookie jar가 저장하고 이후 request가 cookie를 전송하는 flow를 문서화해야 한다.
   - expected `Set-Cookie`는 signed session token 형태를 검증해야 한다. fixture에는 token 원문 대신 redacted placeholder와 signature/kid presence expectation만 둔다.
   - collection/examples는 active key id가 token metadata에 존재하고, expired/invalid signature token이 `401`로 거부되는 negative case를 포함해야 한다.
   - CSRF token extraction과 `X-CSRF-Token` header injection이 collection script 또는 examples에 명확히 들어가야 한다.
   - cookie 속성 기대값 `HttpOnly`, `Secure`, `SameSite`, `Path`, bounded expiration을 expected response fixture에 포함해야 한다.
   - collection/examples에는 real wallet private key, seed phrase, real signature, production token이 없어야 한다.
2. `postman/token-payments.local.postman_collection.json` 또는 동등한 경로를 추가한다.
   - local base URL variable은 `{{baseUrl}}`로 둔다.
   - wallet/signature 값은 placeholder와 설명만 둔다.
   - cookie jar와 CSRF token을 사용하는 request flow가 순서대로 배치되어야 한다.
3. `postman/token-payments.local.postman_environment.json` 또는 동등한 env fixture를 추가한다.
   - `baseUrl=http://localhost:8000`, demo wallet placeholders, order/product ids, CSRF variable을 포함한다.
   - secret/current value는 비워두거나 placeholder여야 한다.
4. README/app README와 `docs/API_SPEC.md`에 Postman cookie auth flow 실행 순서를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_postman_cookie_auth_flow.py scripts/test_cookie_session_transport.py scripts/test_csrf_cors_request_guard.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 Postman cookie flow 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/15-postman-docker-api-readiness/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Postman fixture에 real private key, seed phrase, API key, production token, real refresh/access token을 넣지 마라.
- Postman fixture에 real session signing key 또는 signed token 원문을 넣지 마라.
- Browser 최종 auth flow를 Bearer/localStorage 중심으로 문서화하지 마라.
- live API server, Docker daemon, Blockchain RPC를 자동 검증으로 시작하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

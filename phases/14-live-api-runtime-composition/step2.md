# Step 2: cookie-session-transport

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/API_SPEC.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/auth.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/contexts/auth/application/service.py`
- `/scripts/test_auth_api_session_runtime.py`
- `/scripts/test_http_adapter_public_contracts.py`
- `/scripts/test_live_api_facade_wiring.py`
- `/phases/14-live-api-runtime-composition/index.json`

## 작업

브라우저 checkout 기준의 최종 auth transport를 HttpOnly cookie 중심으로 고정한다. 기존 framework-neutral facade는 유지하되, live HTTP/ASGI adapter 경계에서 auth token/session을 cookie로 발급, 회전, 제거하고 cookie claim을 `ApiRequest`로 주입한다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_cookie_session_transport.py`를 추가한다.
   - login 성공 response가 `access_token`과 `refresh_token` 또는 동등한 session cookie를 `Set-Cookie`로 내려주는지 검증한다.
   - cookie 속성은 최소 `HttpOnly`, `Secure`, `SameSite=Lax` 또는 더 엄격한 정책, `Path=/`, bounded `Max-Age`/`Expires`를 포함해야 한다.
   - refresh 성공은 refresh token cookie rotation과 access token cookie 재발급을 수행해야 한다.
   - logout 성공은 auth cookie를 만료/삭제하는 `Set-Cookie`를 내려야 한다.
   - cookie parser는 request `Cookie` header에서 session/access claim을 추출해 `ApiRequest` 또는 auth context에 주입해야 하며, public API가 `X-User-Id`를 신뢰하는 최종 경로를 만들면 안 된다.
   - access/refresh cookie value는 실제 서명된 token이어야 한다. 테스트용 deterministic 문자열을 live/prod path에 그대로 쓰면 안 된다.
   - 표준 라이브러리 HMAC-SHA256 또는 더 강한 표준 서명 방식을 사용해 token header/payload/signature를 만들고 검증해야 한다. 이 step에서 JWT dependency를 추가하지 않는다.
   - token header 또는 envelope에는 `kid`가 포함되어야 하며, payload에는 최소 `sub`, `sessionId`, `walletAddress`, `role`, `iat`, `exp`, `typ`, `jti` 또는 동등한 claim이 있어야 한다.
   - access token TTL과 refresh token TTL은 분리되어야 하며, refresh token은 rotation/reuse detection을 위해 server-side session repository의 hash/salt/rotation model과 연결되어야 한다.
   - `SESSION_ACTIVE_KEY_ID`, `SESSION_SIGNING_KEYS`, `SESSION_ACCESS_TTL_SECONDS`, `SESSION_REFRESH_TTL_SECONDS` 또는 동등한 env-backed key/TTL config를 파싱해야 한다.
   - `SESSION_SIGNING_KEYS`는 active key와 previous key를 함께 표현할 수 있어야 한다. 새 token은 active key로 서명하고, 검증은 active+previous key를 token 만료 전까지 허용한다.
   - live/prod mode에서 session signing key가 누락되었거나 `.env.example` placeholder 값이면 server start를 bounded validation error로 거부해야 한다.
   - `X-User-Id`, `X-User-Role`, `X-User-Scopes` fallback은 local/dev/test mode에서만 명시적으로 허용되어야 하며 production/live mode에서는 거부 또는 무시되어야 한다.
   - cookie value, refresh token, access token, hash/salt가 logs, runtime preview, API spec fixture에 평문으로 노출되지 않아야 한다.
   - cookie transport module은 `fastapi`, `starlette`, `uvicorn`, real DB/Kafka/Blockchain driver를 import하지 않아야 한다.
2. `app/token_payments/runtime/session_transport.py` 또는 동등한 module을 추가한다.
   - 표준 라이브러리 기반 cookie serialization/parser를 제공한다.
   - `CookieSessionTransport`, `CookieSettings`, `AuthCookiePair`, `SessionClaims`, `SessionTokenSigner`, `SessionKeyRing`, `SessionKeyConfig` 또는 동등한 dataclass/protocol을 둔다.
   - token issuer/verifier는 constructor injection으로 받되, live 기본 구현은 env-backed key ring을 사용하는 실제 signer/verifier여야 한다.
   - token signing input은 canonical JSON/base64url 등 deterministic serialization을 사용해야 하며, verifier는 signature, `kid`, expiry, token type, session id를 검증해야 한다.
   - cookie claim extraction 결과는 framework-neutral `ApiRequest` headers/query/body 조작이 아니라 명확한 auth context 또는 request enrichment boundary로 전달한다.
3. `RuntimeConfig` 또는 live config를 갱신한다.
   - session key/TTL env 값을 파싱하고 redacted `to_dict()`/preview를 제공한다.
   - `.env.example`에는 placeholder key만 추가하고 실제 secret은 커밋하지 않는다.
   - preview/test mode는 deterministic fake signer를 주입할 수 있어야 하지만 live/prod mode에서는 fake signer를 사용할 수 없어야 한다.
4. `AuthApi` 또는 live route wrapper를 갱신한다.
   - facade response body의 token payload가 남더라도 live HTTP response에서는 cookie가 source of truth임을 문서화한다.
   - 민감한 refresh token hash 내부 모델이 public JSON response로 새로 노출되지 않게 한다.
5. `docs/API_SPEC.md`를 갱신한다.
   - final browser API는 `Authorization: Bearer`가 아니라 HttpOnly cookie를 기본 auth transport로 사용한다고 명시한다.
   - Bearer/header claim은 non-browser 또는 local/dev fallback으로만 설명한다.
   - session tokens are signed with env-backed active/previous keys and are never stored or logged in plaintext.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_cookie_session_transport.py scripts/test_live_api_facade_wiring.py scripts/test_auth_api_session_runtime.py scripts/test_http_adapter_public_contracts.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 cookie transport 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/14-live-api-runtime-composition/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- access/refresh token을 `localStorage` 전제로 설계하지 마라.
- production/live 경로에서 `X-User-Id`/`X-User-Role` header를 신뢰하지 마라.
- live/prod path에서 deterministic fake token issuer나 hardcoded signing key를 사용하지 마라.
- 새 third-party auth/JWT/cookie dependency를 추가하지 마라.
- session signing key, signed token, refresh token hash/salt, private key를 response/log/docs에 노출하지 마라.
- domain/application layer가 HTTP cookie, API adapter, runtime module을 import하게 만들지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

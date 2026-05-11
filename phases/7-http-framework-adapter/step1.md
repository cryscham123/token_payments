# Step 1: auth-order-http-routes

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
- `/app/token_payments/api/auth.py`
- `/app/token_payments/api/orders.py`
- `/app/token_payments/api/contracts.py`
- `/scripts/test_auth_api_session_runtime.py`
- `/scripts/test_order_api_checkout_start.py`
- `/scripts/test_http_adapter_contract_foundation.py`

## 작업

HTTP router에 auth/order facade route를 등록하는 contract를 추가한다. 이 step은 framework adapter와 기존 facade 사이의 route mapping만 다루며, 실제 인증 middleware나 DB-backed composition root는 만들지 않는다.

1. `scripts/test_auth_order_http_routes.py`를 추가한다.
   - fake `AuthUseCase`/`OrderUseCase`로 route가 올바른 facade method를 호출하는지 검증한다.
   - `POST /auth/challenges`는 `AuthApi.request_login_challenge`로 연결되어 `201` challenge payload를 반환해야 한다.
   - `POST /auth/sessions`는 MetaMask login route로 연결되어 token/session payload를 반환해야 한다.
   - `POST /auth/sessions/refresh`, `DELETE /auth/sessions`, `GET /auth/me` route를 검증한다.
   - `POST /orders`는 `OrdersApi.create_order`로 연결되고 `X-User-Id` header가 `ApiRequest`까지 보존되어야 한다.
2. route registration helper를 추가한다.
   - 예: `register_auth_routes(router, auth_api)`, `register_order_routes(router, orders_api)`.
   - helper는 기존 `HttpRouter`를 받아 route를 추가하거나 route sequence를 반환하는 형태로 구현한다.
   - route path/method는 테스트와 README에서 일관되게 사용할 수 있게 상수 또는 manifest로 조회 가능해야 한다.
3. auth/order facade의 validation/error mapping을 HTTP adapter가 덮어쓰지 않게 한다.
   - facade가 반환한 `ApiResponse.status_code`와 body를 그대로 직렬화한다.
   - adapter 레벨 400은 malformed JSON 같은 HTTP decoding 오류에만 사용한다.
4. public export를 정리한다.
   - `token_payments.api` 또는 `token_payments.api.http`에서 auth/order route registration helper를 import할 수 있어야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_auth_order_http_routes.py scripts/test_http_adapter_contract_foundation.py scripts/test_auth_api_session_runtime.py scripts/test_order_api_checkout_start.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/7-http-framework-adapter/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step에서 real session store, wallet signature recovery, PostgreSQL repository를 새로 wire하지 마라.
- 기존 auth/order facade method signature를 route 등록 편의를 위해 바꾸지 마라.
- auth 실패를 adapter에서 임의로 200으로 감싸지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

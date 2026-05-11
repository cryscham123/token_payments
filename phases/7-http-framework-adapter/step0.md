# Step 0: http-adapter-contract-foundation

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
- `/phases/0-foundation/index.json`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/3-api-worker-runtime/index.json`
- `/phases/4-customer-operator-ui/index.json`
- `/phases/5-e2e-integration-readiness/index.json`
- `/phases/6-order-lifecycle-compensation/index.json`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/api/__init__.py`
- `/scripts/test_api_worker_runtime_public_contracts.py`
- `/scripts/test_checkout_tracking_payment_api.py`

## 작업

기존 framework-neutral `ApiRequest`/`ApiResponse` facade를 실제 HTTP 경계에 연결할 수 있는 순수 adapter contract를 추가한다. 동작 변경이므로 먼저 테스트를 작성하거나 갱신하고 실패를 확인한 뒤 구현한다.

1. `scripts/test_http_adapter_contract_foundation.py`를 추가한다.
   - HTTP method/path/query/header/body bytes를 `ApiRequest`로 변환하는 contract를 검증한다.
   - JSON request body는 `application/json`일 때만 object/array/scalar를 decode하고, 빈 body는 `None`으로 유지한다.
   - malformed JSON은 facade handler까지 전달하지 않고 `400` JSON error response로 끝나야 한다.
   - `ApiResponse`를 status, headers, body bytes로 직렬화할 때 `Content-Type`, `Content-Length`, `X-Request-Id`가 안정적으로 보존되어야 한다.
   - route miss는 `404`, method mismatch는 `405` JSON response가 되어야 한다.
2. `app/token_payments/api/http.py` 또는 동등한 API package 내부 모듈을 추가한다.
   - `HttpRoute`/`HttpRouter`/`HttpResponse`처럼 외부 framework에 묶이지 않는 작은 contract를 둔다.
   - route path template은 고정 segment와 `{param}` segment를 지원한다.
   - path param은 기존 facade가 그대로 쓸 수 있도록 request query에 병합하되, 명시 query 값이 있으면 query 값을 우선한다.
   - request id는 `X-Request-Id` header가 있으면 사용하고 없으면 deterministic하게 생성 가능해야 한다.
3. 기존 `ApiRequest`, `ApiResponse`, `json_response` 계약을 깨뜨리지 않는다.
   - 기존 API facade test가 추가 수정 없이 통과해야 한다.
   - adapter는 auth/order/payment/operator application layer를 import하지 않는 foundation으로 유지한다.
4. public export를 정리한다.
   - `token_payments.api`에서 HTTP adapter foundation contract를 import할 수 있어야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_http_adapter_contract_foundation.py scripts/test_api_worker_runtime_public_contracts.py scripts/test_checkout_tracking_payment_api.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/7-http-framework-adapter/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- FastAPI, Flask, Django 같은 새 third-party web framework dependency를 추가하지 마라.
- 이 step에서 runtime command를 long-running server로 바꾸지 마라.
- 기존 `ApiRequest`/`ApiResponse` field 이름이나 JSON 직렬화 계약을 깨뜨리지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

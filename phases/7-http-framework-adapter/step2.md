# Step 2: checkout-payment-http-routes

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
- `/app/token_payments/api/checkout.py`
- `/app/token_payments/api/payments.py`
- `/app/token_payments/api/contracts.py`
- `/scripts/test_checkout_tracking_payment_api.py`
- `/scripts/test_happy_path_checkout_e2e.py`

## 작업

checkout tracking과 payment txHash 제출 facade를 HTTP route로 연결한다. Customer UI와 smoke가 동일 route manifest를 참조할 수 있도록 path/method contract를 명확히 고정한다.

1. `scripts/test_checkout_payment_http_routes.py`를 추가한다.
   - fake tracking query와 fake payment command handler를 사용한다.
   - `GET /checkouts/tracking/{trackingId}`는 `CheckoutApi.get_tracking`으로 연결되어 tracking snapshot을 반환해야 한다.
   - `GET /checkouts/orders/{orderId}`는 order id 기반 tracking 조회로 연결되어야 한다.
   - `POST /payments/transaction-hashes`는 `PaymentsApi.submit_transaction_hash`로 연결되어 `202` payment status payload를 반환해야 한다.
   - query string lookup(`trackingId`, `orderId`)과 path param lookup이 모두 기존 facade contract와 호환되어야 한다.
2. checkout/payment route registration helper를 추가한다.
   - 예: `register_checkout_routes(router, checkout_api)`, `register_payment_routes(router, payments_api)`.
   - route manifest에는 method, path template, operation id가 포함되어야 한다.
3. idempotency/correlation 정보를 보존한다.
   - request id가 `causation_id`로 이어질 수 있도록 `X-Request-Id`가 `ApiRequest.request_id`에 남아야 한다.
   - optional `commandId` body 값은 adapter가 제거하거나 변경하지 않는다.
4. 기존 smoke/public contract를 깨뜨리지 않는다.
   - smoke는 여전히 long-running HTTP server 없이 deterministic하게 실행되어야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_checkout_payment_http_routes.py scripts/test_checkout_tracking_payment_api.py scripts/test_happy_path_checkout_e2e.py scripts/test_http_adapter_contract_foundation.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/7-http-framework-adapter/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step에서 blockchain RPC, receipt polling worker, Kafka listener를 새로 실행 경로에 넣지 마라.
- payment command result를 route adapter에서 임의로 재해석하지 마라.
- UI preview HTML을 이 step에서 수정하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 1: api-sensitive-payload-tracking-id-hardening

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/docs/SEQUENCES.md`
- `/docs/DOMAIN_MODEL.md`
- `/app/token_payments/api/auth.py`
- `/app/token_payments/api/orders.py`
- `/app/token_payments/api/payments.py`
- `/app/token_payments/api/idempotency.py`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/runtime/session_transport.py`
- `/app/token_payments/contexts/auth/application/service.py`
- `/app/token_payments/contexts/order/application/service.py`
- `/app/token_payments/contexts/order/application/queries.py`
- `/app/token_payments/contexts/payment/application/commands.py`
- `/app/token_payments/contexts/payment/application/handler.py`
- `/scripts/test_auth_api_session_runtime.py`
- `/scripts/test_checkout_tracking_payment_api.py`
- `/scripts/test_order_api_checkout_start.py`
- `/scripts/test_payment_application_contracts.py`
- `/phases/26-security-hardening-architecture-refactoring/index.json`

## 작업

Payment submit을 `trackingId` 중심으로 전환하고 session/order/payment response의 민감 내부 정보를 제거한다.

1. `scripts/test_api_sensitive_payload_tracking_id_hardening.py`를 추가한다.
   - payment tx hash submission request body는 `trackingId`를 받아야 한다.
   - request body의 `orderId`는 허용하지 않거나 bounded validation error를 반환해야 한다.
   - response payload는 `trackingId`, payment status, transaction hash receipt metadata만 반환하고 internal `orderId`를 반환하지 않아야 한다.
   - tracking id는 소유권/세션 scope 검증 후 server 내부에서 order/payment id로 resolve되어야 한다.
   - idempotency key header가 없을 때 fallback은 `payment.submit_tx:{trackingId}` 또는 그 hash처럼 tracking id 기반이어야 한다.
   - `GET /auth/session` 또는 현재 session inspection route는 `sessionId`, `refreshTokenHash`, `hash`, `salt`, `rotationVersion`을 반환하지 않아야 한다.
   - `POST /orders` success response는 internal `customerId`와 internal store PK를 반환하지 않아야 한다.
2. payment API와 command boundary를 갱신한다.
   - `SubmitTransactionHashCommand` 또는 동등 command는 external DTO에서 `trackingId`를 받고 application layer에서 internal id를 resolve한다.
   - domain/application 내부에서 필요한 order id 사용은 허용하되 public DTO와 idempotency fallback에는 노출하지 않는다.
3. payload builder를 갱신한다.
   - `_session_payload`는 session persistence/debug object를 그대로 serialize하지 않는다.
   - `_order_creation_payload`는 browser/client가 필요로 하는 checkout tracking 정보만 반환한다.
   - public store 표시가 필요하면 `publicStoreId` 같은 Phase 23 public identifier를 사용한다.
4. docs/Postman expected fixture를 갱신한다.
   - cookie/token redaction shape와 session metadata shape를 명확히 분리한다.
   - public examples는 internal ids를 숨기고 공개 식별자 중심으로 설명한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_api_sensitive_payload_tracking_id_hardening.py scripts/test_auth_api_session_runtime.py scripts/test_auth_order_http_routes.py scripts/test_order_api_checkout_start.py scripts/test_checkout_tracking_payment_api.py scripts/test_payment_application_contracts.py scripts/test_api_seed_expected_responses.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. API security hardening 테스트를 먼저 추가하고 실패를 확인한다.
2. API/payment/order/idempotency/docs/fixtures를 갱신한 뒤 AC를 실행한다.
3. `/phases/26-security-hardening-architecture-refactoring/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- public request/response schema에 `orderId` fallback을 남기지 마라.
- tracking id만으로 조회하고 session/ownership 검증을 생략하지 마라.
- idempotency fallback에 raw internal order/payment id를 포함하지 마라.
- `refreshTokenHash` 내부 구조를 masked object로라도 public response에 남기지 마라.
- customer/browser convenience를 이유로 internal `customerId`를 반환하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

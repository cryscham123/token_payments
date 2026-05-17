# Step 1: live-api-facade-wiring

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/api/__init__.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/auth.py`
- `/app/token_payments/api/orders.py`
- `/app/token_payments/api/checkout.py`
- `/app/token_payments/api/payments.py`
- `/app/token_payments/api/operator.py`
- `/app/token_payments/api/operator_actions.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/contexts/auth/application/service.py`
- `/app/token_payments/contexts/order/application/service.py`
- `/app/token_payments/contexts/order/application/queries.py`
- `/app/token_payments/contexts/order/adapter/postgres.py`
- `/app/token_payments/contexts/payment/application/handler.py`
- `/app/token_payments/contexts/payment/adapter/postgres.py`
- `/app/token_payments/contexts/inventory/adapter/postgres.py`
- `/app/token_payments/contexts/store_approval/adapter/postgres.py`
- `/app/token_payments/shared/adapter/outbox_relay.py`
- `/app/token_payments/shared/adapter/postgres/outbox.py`
- `/scripts/test_live_api_runtime_composition.py`
- `/scripts/test_http_adapter_public_contracts.py`
- `/scripts/test_operator_action_public_contracts.py`
- `/phases/14-live-api-runtime-composition/index.json`

## 작업

Step 0의 live dependency contract 위에 실제 framework-neutral API facade와 `HttpRouter`를 조립한다. 이 step은 route/facade/application/repository wiring을 검증하지만 long-running server와 live network client는 시작하지 않는다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_live_api_facade_wiring.py`를 추가한다.
   - `build_live_api_router(...)` 또는 동등한 factory가 `HttpRouter`를 반환하고 `http_route_manifest()`와 동일한 method/path/operation id 16개 route를 등록하는지 검증한다.
   - router 등록은 기존 `register_auth_routes`, `register_order_routes`, `register_checkout_routes`, `register_payment_routes`, `register_operator_routes`, `register_operator_action_routes` helper를 사용해야 하며 route manifest를 복제 구현하지 않아야 한다.
   - factory는 `AuthApi`, `OrdersApi`, `CheckoutApi`, `PaymentsApi`, `OperatorApi`, `OperatorActionApi` facade를 실제 application service/handler/query/action executor와 연결해야 한다.
   - tests는 fake PostgreSQL connection/session, fake Kafka producer, fake wallet signature client, fake blockchain client, deterministic clock/id generator를 사용해 외부 연결 없이 create order, tracking lookup, txHash submit, operator dashboard, cancel/retry/replay action route가 facade까지 dispatch되는지 확인한다.
   - 주문 생성과 payment txHash 제출처럼 상태를 바꾸는 API는 injected transaction boundary 안에서 aggregate repository와 outbox repository를 함께 사용해야 한다.
   - operator action audit/idempotency 결과는 기존 phase 8/12 public contract와 같은 payload shape를 유지해야 한다.
   - live API facade wiring source는 `fastapi`, `starlette`, `uvicorn`, `socket`, `requests`, `docker`, real DB/Kafka/Blockchain driver를 import하지 않아야 한다.
2. Step 0에서 만든 composition module을 확장한다.
   - `build_live_api_facades(...)`와 `build_live_api_router(...)` 또는 동등한 좁은 factory를 추가한다.
   - transaction/session provider, repositories, outbox publisher, process manager, command handlers, query ports, operator action executors를 dependency injection으로 연결한다.
   - idempotency repository와 outbox repository는 기존 adapter contracts를 사용하고, 새 ad hoc storage abstraction을 만들지 않는다.
   - live dependency가 누락되면 server start 전에 bounded validation error를 반환해야 한다.
3. 기존 framework-neutral HTTP adapter, ASGI/FastAPI adapter, WSGI preview가 route manifest와 handler contract를 그대로 유지하도록 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_live_api_facade_wiring.py scripts/test_live_api_runtime_composition.py scripts/test_http_adapter_public_contracts.py scripts/test_operator_action_public_contracts.py scripts/test_happy_path_checkout_e2e.py scripts/test_compensation_checkout_e2e.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 wiring 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/14-live-api-runtime-composition/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- live API wiring 테스트에서 Docker daemon, real PostgreSQL, real Kafka, Blockchain RPC, local `.env`를 열지 마라.
- route manifest, operation id, public API facade DTO shape를 바꾸지 마라.
- HTTP adapter 밖에서 framework-specific request/response 타입에 의존하지 마라.
- domain/application layer가 API/runtime/adapter/framework를 import하게 만들지 마라.
- 새 third-party dependency를 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 2: order-api-checkout-start

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/phases/0-foundation/index.json`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/3-api-worker-runtime/index.json`
- `/phases/3-api-worker-runtime/step0.md`
- `/phases/3-api-worker-runtime/step1.md`
- `/app/token_payments/contexts/order/domain/model.py`
- `/app/token_payments/shared/domain/messaging.py`
- `/app/token_payments/shared/adapter/postgres/__init__.py`
- `/app/token_payments/api/`
- `/app/postgres/init.d/001-token-payments-schema.sql`

## 작업

고객 주문 생성 API와 checkout 시작 outbox 흐름을 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_order_api_checkout_start.py`를 추가해 authenticated user 기반 order creation, product snapshot, total amount, order repository save, `OrderCreatedEvent` outbox 저장, tracking id 응답, validation error mapping을 검증한다.
2. `contexts/order/application/commands.py`, `ports.py`, `service.py`를 추가해 `CreateOrderCommand`, `OrderUseCase`, customer/store/order repository, outbox repository port를 정의하고 구현한다.
3. `contexts/order/adapter/postgres.py`와 schema 변경을 추가해 orders/order_items/customer/store/product snapshot read/write에 필요한 최소 repository adapter를 만든다. 테스트는 fake connection 기반으로 작성한다.
4. `app/token_payments/api/orders.py`를 추가해 framework-independent order API handler를 구현한다.
5. 주문 생성과 outbox 저장은 같은 injected transaction/session boundary 안에서 일어나도록 composition contract를 둔다.
6. `OrderCreatedEvent` payload는 checkout process manager가 소비할 수 있는 `orderId`, `customerId`, `storeId`, item/product/quantity, amount, wallet/chain metadata, correlation/causation headers를 포함한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_order_api_checkout_start.py scripts/test_order_checkout_skeleton.py scripts/test_messaging_outbox_contracts.py scripts/test_runtime_contract_foundation.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. 주문 생성 API가 payment/inventory/store approval application service를 직접 호출하지 않고 outbox/event로 checkout을 시작하는지 확인한다.
4. `phases/3-api-worker-runtime/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Order API에서 inventory/payment/store approval command handler를 직접 호출하지 마라.
- DB 저장 없이 in-memory global state에 의존하는 production runtime 코드를 만들지 마라.
- 실제 결제 transaction을 이 step에 섞지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

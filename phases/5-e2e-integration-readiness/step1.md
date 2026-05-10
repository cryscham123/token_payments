# Step 1: happy-path-checkout-e2e

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
- `/phases/5-e2e-integration-readiness/index.json`
- Step 0에서 생성/수정한 smoke contract 파일
- `/app/token_payments/contexts/order/application/commands.py`
- `/app/token_payments/contexts/order/application/service.py`
- `/app/token_payments/contexts/checkout/application/process_manager.py`
- `/app/token_payments/contexts/inventory/application/commands.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/payment/application/commands.py`
- `/app/token_payments/contexts/payment/application/handler.py`
- `/app/token_payments/contexts/store_approval/application/commands.py`
- `/app/token_payments/contexts/store_approval/application/service.py`

## 작업

주문 생성부터 재고 예약, 결제 생성, txHash 제출, receipt 확인, 가게 승인까지 정상 checkout sequence를 deterministic in-memory smoke로 구현한다.

1. 먼저 실패하는 테스트를 추가한다.
   - `scripts/test_happy_path_checkout_e2e.py`
   - 테스트는 `run_smoke_scenario("happy-path-checkout")` 또는 동등한 public API를 통해 flow를 실행한다.
2. app runtime smoke 구현을 확장한다.
   - order/inventory/payment/store-approval application service와 `CheckoutProcessManager`를 실제로 호출한다.
   - repository, outbox, processed command/message, blockchain, timeout scheduler, transaction service는 in-memory fake로 둔다.
   - fakes는 smoke module 내부 또는 테스트 전용 helper에 둘 수 있지만 production 외부 client로 위장하지 않는다.
3. happy-path smoke는 다음을 step 결과로 기록한다.
   - `OrderCreatedEvent`
   - `ReserveInventoryCommand`
   - `InventoryReservedEvent`
   - `InitiatePaymentCommand`
   - payment signature request/gas estimate
   - txHash submit result
   - `PaymentConfirmedEvent`
   - `RequestStoreApprovalCommand`
   - `OrderApprovedEvent`
4. 최종 `SmokeScenarioResult.to_dict()`에는 최소 다음 details가 있어야 한다.
   - `orderId`, `trackingId`, `paymentId`
   - 최종 order/store approval 상태
   - saved outbox event names
   - deterministic process manager command ids
   - duplicate command이 아닌 정상 처리였다는 idempotency summary
5. CLI를 확장한다.
   - `PYTHONPATH=app python3 -m token_payments smoke happy-path-checkout`가 bounded JSON을 출력한다.
6. phase metadata를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_happy_path_checkout_e2e.py
python3 -m pytest scripts/test_e2e_smoke_contract_foundation.py scripts/test_checkout_core_public_contracts.py scripts/test_api_worker_runtime_public_contracts.py
PYTHONPATH=app python3 -m token_payments smoke happy-path-checkout
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 happy-path e2e 테스트를 먼저 추가하고 실패를 확인한다.
2. 구현 후 AC 커맨드를 실행한다.
3. CLI 출력에 정상 flow step, event, command id, 최종 승인 상태가 들어있는지 확인한다.
4. `/phases/5-e2e-integration-readiness/index.json`의 step 1 status를 `completed`로 바꾸고 `summary`에 정상 sequence와 검증된 경계를 구체적으로 적는다.

## 금지사항

- 실제 Docker, PostgreSQL, Kafka, Blockchain RPC, MetaMask client를 호출하지 마라.
- application service를 우회해 단순 문자열 배열만 만드는 fake e2e를 만들지 마라.
- checkout 정상 flow와 무관한 UI/HTML 변경을 하지 마라.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

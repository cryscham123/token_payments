# Step 2: compensation-checkout-e2e

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
- Step 0-1에서 생성/수정한 smoke contract와 happy-path smoke 파일
- `/app/token_payments/contexts/checkout/application/process_manager.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/payment/application/handler.py`
- `/app/token_payments/contexts/store_approval/application/service.py`

## 작업

결제 실패, 결제 만료, 가게 반려 상황에서 보상 command가 deterministic id로 발행되고 중복 메시지/중복 command를 멱등적으로 무시하는 e2e smoke를 추가한다.

1. 먼저 실패하는 테스트를 추가한다.
   - `scripts/test_compensation_checkout_e2e.py`
2. app runtime smoke 구현을 확장한다.
   - `run_smoke_scenario("compensation-checkout")` 또는 동등한 public API를 구현한다.
   - 최소 세 하위 scenario를 실행한다.
     - payment receipt failure: `PaymentFailedEvent` -> `ReleaseInventoryCommand`, `CancelOrderCommand`
     - payment signature expiration: `PaymentExpiredEvent` -> `ReleaseInventoryCommand`, `CancelOrderCommand`
     - store rejection after payment confirmation: `OrderRejectedEvent` -> `RefundPaymentCommand`, `ReleaseInventoryCommand`, `CancelOrderCommand`
   - 가능한 경우 inventory release와 payment refund handler를 실제 application service로 호출한다.
   - 현재 구현에 `CancelOrderCommand` handler가 없다면 process manager decision까지만 검증하고 result details에 `cancelOrderHandlerWired=false`처럼 명확히 남긴다. 이 경우 blocked가 아니라 다음 phase 후보로 문서화한다.
3. 멱등성 검증을 포함한다.
   - 같은 event를 process manager에 두 번 넣어도 command id가 동일함을 검증한다.
   - 같은 compensation command를 handler에 두 번 넣으면 두 번째 결과가 `DUPLICATE_IGNORED` 계열임을 검증한다.
   - result details에 command id 목록과 duplicate summary를 남긴다.
4. CLI를 확장한다.
   - `PYTHONPATH=app python3 -m token_payments smoke compensation-checkout`가 bounded JSON을 출력한다.
5. phase metadata를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_compensation_checkout_e2e.py
python3 -m pytest scripts/test_happy_path_checkout_e2e.py scripts/test_e2e_smoke_contract_foundation.py scripts/test_checkout_core_public_contracts.py
PYTHONPATH=app python3 -m token_payments smoke compensation-checkout
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 compensation e2e 테스트를 먼저 추가하고 실패를 확인한다.
2. 구현 후 AC 커맨드를 실행한다.
3. CLI 출력에 세 compensation sub-scenario와 deterministic command id, duplicate summary가 들어있는지 확인한다.
4. `/phases/5-e2e-integration-readiness/index.json`의 step 2 status를 `completed`로 바꾸고 `summary`에 보상 flow와 남은 handler wiring gap을 구체적으로 적는다.

## 금지사항

- 보상 command id를 랜덤하게 만들지 마라. `CommandId.for_order_action` 또는 기존 deterministic 규칙을 사용한다.
- 누락된 `CancelOrderCommand` handler를 큰 범위로 새로 구현하지 마라. 필요하면 gap으로 남기고 다음 phase 후보에 적는다.
- 실제 Docker, PostgreSQL, Kafka, Blockchain RPC, MetaMask client를 호출하지 마라.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

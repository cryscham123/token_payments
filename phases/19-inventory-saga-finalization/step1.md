# Step 1: approval-to-inventory-confirm-wiring

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/SEQUENCES.md`
- `/app/token_payments/contexts/checkout/application/process_manager.py`
- `/app/token_payments/contexts/checkout/adapter/kafka.py`
- `/app/token_payments/contexts/store_approval/application/service.py`
- `/app/token_payments/shared/domain/messaging.py`
- `/scripts/test_order_checkout_skeleton.py`
- `/scripts/test_kafka_listener_adapters.py`
- `/scripts/test_order_lifecycle_compensation.py`
- `/scripts/test_inventory_confirm_command_contract.py`

## 작업

결제 성공 후 자동 승인된 주문이 `reserved -> confirmed` 재고 전환을 수행하도록 checkout saga decision을 연결한다. 수동 주문 승인 기능은 추가하지 않는다.

1. `scripts/test_inventory_saga_confirm_flow.py`를 추가한다.
   - `OrderApprovedEvent`를 받은 `CheckoutProcessManager`가 `ConfirmInventoryCommand`를 결정해야 한다.
   - `OrderRejectedEvent`, `PaymentFailedEvent`, `PaymentExpiredEvent`는 기존처럼 `ReleaseInventoryCommand`를 결정해야 한다.
   - duplicate `OrderApprovedEvent`는 동일 deterministic command id로 멱등 처리되어야 한다.
   - 이미 terminal/cancelled order path에서는 confirm이 중복 발행되지 않아야 한다.
2. checkout process manager와 Kafka adapter를 갱신한다.
   - `CheckoutCommandName.CONFIRM_INVENTORY` 또는 동등한 command name을 사용한다.
   - command payload에는 inventory context가 reservation을 찾을 수 있는 최소 identity가 포함되어야 한다.
3. docs/sequence를 갱신한다.
   - 성공 흐름에 inventory confirm step을 추가한다.
   - 실패/거절 흐름의 release와 구분한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_inventory_saga_confirm_flow.py scripts/test_order_checkout_skeleton.py scripts/test_kafka_listener_adapters.py scripts/test_order_lifecycle_compensation.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. saga confirm flow 테스트를 먼저 추가하고 실패를 확인한다.
2. process manager/adapter/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/19-inventory-saga-finalization/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 수동 승인/거절 HTTP API를 추가하지 마라.
- `OrderApprovedEvent` 전에 inventory confirm을 실행하지 마라.
- reject/fail/expire compensation release 동작을 깨뜨리지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

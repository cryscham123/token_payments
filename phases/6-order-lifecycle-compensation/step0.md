# Step 0: cancel-order-command-handler

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
- `/app/token_payments/contexts/order/domain/model.py`
- `/app/token_payments/contexts/order/application/commands.py`
- `/app/token_payments/contexts/order/application/service.py`
- `/app/token_payments/contexts/order/application/ports.py`
- `/scripts/test_order_checkout_skeleton.py`
- `/scripts/test_compensation_checkout_e2e.py`

## 작업

보상 flow의 `CancelOrderCommand`가 더 이상 `HANDLER_NOT_WIRED`로 남지 않도록 order bounded context의 순수 application contract를 추가한다. 동작 변경이므로 먼저 테스트를 작성하거나 갱신하고 실패를 확인한 뒤 구현한다.

1. `scripts/test_order_lifecycle_compensation.py`를 추가한다.
   - `CancelOrderCommand` DTO가 `command_id`, `order_id`, `reason`, `requested_at`, `causation_id`, `event_message_id`를 검증한다.
   - handler가 기존 order를 취소하고 `OrderCancelledEvent` outbox message를 저장하는지 검증한다.
   - 동일 `command_id` 재실행은 저장소 mutation/outbox 중복 없이 `DUPLICATE_IGNORED` 계열 결과로 반환되어야 한다.
   - 이미 `CANCELLED`인 order에 대한 재시도는 멱등 성공으로 취급하되 failure message를 중복 누적하지 않는다.
2. order application에 command handler를 추가한다.
   - 기존 `OrderApplicationService.createOrder` 계약을 깨뜨리지 않는다.
   - 새 handler는 repository, outbox repository, processed-command repository port에만 의존한다.
   - `CancelOrderCommand`의 default reason은 두지 말고, 보상 source가 구체 reason을 전달하게 한다.
3. public exports를 정리한다.
   - `token_payments.contexts.order.application`에서 새 command, result, status, handler, port를 import할 수 있어야 한다.
   - domain layer가 adapter dependency를 import하지 않도록 기존 boundary를 유지한다.
4. outbox event payload는 기존 `OrderCreatedEvent`/checkout event naming 규칙과 일관되게 만든다.
   - event name은 shared `CheckoutEventName.ORDER_CANCELLED`가 없다면 이 step에서 shared enum에 추가하고 public contract 테스트를 갱신한다.
   - payload에는 최소 `eventName`, `orderId`, `status`, `reason`, `occurredAt`, `correlationId`, `causationId`가 포함되어야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_order_lifecycle_compensation.py scripts/test_order_checkout_skeleton.py scripts/test_checkout_core_public_contracts.py scripts/test_foundation_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/6-order-lifecycle-compensation/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step에서 Kafka listener, PostgreSQL repository, smoke runtime을 크게 수정하지 마라. 순수 order application contract 중심으로 끝낸다.
- 실패한 보상 테스트를 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

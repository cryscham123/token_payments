# Step 1: operator-cancel-order-action

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/phases/8-operator-action-endpoints/index.json`
- `/app/token_payments/api/operator.py`
- `/app/token_payments/api/operator_actions.py`
- `/app/token_payments/contexts/order/application/commands.py`
- `/app/token_payments/contexts/order/application/service.py`
- `/app/token_payments/contexts/order/application/ports.py`
- `/app/token_payments/contexts/order/adapter/kafka.py`
- `/scripts/test_operator_action_contracts.py`
- `/scripts/test_order_lifecycle_compensation.py`
- `/scripts/test_kafka_listener_adapters.py`

## 작업

operator cancel order action을 기존 `CancelOrderCommand`/`OrderCommandHandler` 계약에 연결한다. 동작 변경이므로 먼저 실패하는 테스트를 추가하고 구현한다.

1. `scripts/test_operator_cancel_order_action.py`를 추가한다.
   - ADMIN operator가 orderId, reason, optional idempotencyKey로 cancel action을 요청하면 deterministic `CancelOrderCommand`가 생성되어 handler로 전달되어야 한다.
   - idempotencyKey가 없으면 request id와 order id를 기준으로 안정적인 key를 만들어야 한다.
   - action result는 `CANCELLED`, `ALREADY_CANCELLED`, `DUPLICATE_IGNORED` 같은 handler 결과를 operator action status/payload로 보존해야 한다.
   - handler rejection(`ORDER_NOT_FOUND`, `INVALID_STATE`)은 action rejected result로 변환되어야 하며 exception을 HTTP layer까지 누수하지 않아야 한다.
   - audit repository가 주입된 경우 성공/중복/거절 outcome을 모두 기록해야 한다.
   - ADMIN이 아닌 claims는 handler를 호출하지 않고 forbidden/rejected 결과가 되어야 한다.
2. operator action executor/service를 구현한다.
   - 기존 order application handler를 직접 바꾸기보다 action layer에서 `CancelOrderCommand`를 구성한다.
   - `command_id`는 body idempotencyKey가 있으면 그 값을 CommandId로 사용하고, 없으면 `CommandId.for_order_action(order_id, CheckoutCommandName.CANCEL_ORDER)` 또는 동등하게 deterministic한 값을 사용한다.
   - `causation_id`는 request id를 전달한다.
   - `event_message_id`는 명시 값이 없으면 `MessageId.new()`를 사용한다.
3. public exports를 보강한다.
   - cancel action executor/service가 API package 또는 적절한 runtime-neutral 모듈에서 import 가능해야 한다.
   - order application layer에는 operator API imports를 추가하지 않는다.
4. phase metadata를 갱신한다.
   - `/phases/8-operator-action-endpoints/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_operator_cancel_order_action.py scripts/test_operator_action_contracts.py scripts/test_order_lifecycle_compensation.py scripts/test_kafka_listener_adapters.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/8-operator-action-endpoints/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- order domain/application에 operator HTTP나 web framework 의존성을 추가하지 마라.
- cancel action을 위해 `scripts/execute.py`를 수정하지 마라.
- 사용자 권한 검사를 우회하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

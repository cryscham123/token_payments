# Step 1: order-status-event-projector

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
- `/phases/6-order-lifecycle-compensation/index.json`
- Step 0에서 생성/수정한 order application 파일
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/contexts/store_approval/domain/model.py`
- `/app/token_payments/contexts/order/application/queries.py`
- `/scripts/test_checkout_tracking_payment_api.py`
- `/scripts/test_happy_path_checkout_e2e.py`
- `/scripts/test_compensation_checkout_e2e.py`

## 작업

payment/store approval event를 order 상태로 반영하는 application projector를 추가한다. 현재 smoke runtime의 수동 `order_repository.save(order.confirm_payment(...))`/`approve()` 호출을 대체할 수 있는 계약을 만든다. 동작 변경이므로 먼저 테스트를 추가/갱신하고 실패를 확인한 뒤 구현한다.

1. `scripts/test_order_status_event_projector.py`를 추가한다.
   - `PaymentConfirmedEvent` 수신 시 order가 `PENDING -> PAID`로 바뀌고 `payment_id`가 기록되는지 검증한다.
   - `OrderApprovedEvent` 수신 시 order가 `PAID -> APPROVED`로 바뀌는지 검증한다.
   - `PaymentFailedEvent`, `PaymentExpiredEvent`, `OrderRejectedEvent`는 order를 `CANCELLED` 또는 `CANCELLING`으로 projection하지 않는다. 최종 취소는 Step 0의 `CancelOrderCommand` handler가 담당한다.
   - 동일 event message id는 processed-message repository로 중복 무시되어야 한다.
   - 상태 전이가 이미 반영된 order에 대한 replay는 멱등 결과를 반환하고 outbox를 중복 저장하지 않는다.
2. projector와 port/result contract를 order application에 추가한다.
   - source event payload를 직접 dict로 받기보다 명시 DTO 또는 parser를 둔다.
   - event metadata의 `message_id`, `correlation_id`, `causation_id`, `occurred_at`을 유지한다.
   - 알 수 없는 event name은 구조화된 skipped/ignored 결과로 처리한다.
3. checkout tracking read model이 새 상태를 자연스럽게 해석하는지 확인하고 필요한 테스트를 보강한다.
   - `PAID`, `APPROVED`, `CANCELLED`, `CANCELLING`에 대한 `current_step`, `is_terminal`, `failure_reason` 계산을 깨뜨리지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_order_status_event_projector.py scripts/test_order_lifecycle_compensation.py scripts/test_checkout_tracking_payment_api.py scripts/test_happy_path_checkout_e2e.py scripts/test_checkout_core_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/6-order-lifecycle-compensation/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- projector에서 inventory/payment/store approval aggregate를 직접 수정하지 마라.
- event payload를 ad hoc string parsing만으로 처리하지 마라. 명시 DTO 또는 검증 함수를 둔다.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

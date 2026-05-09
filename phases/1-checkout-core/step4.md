# Step 4: store-approval-core

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/PRD.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/phases/1-checkout-core/index.json`
- `/app/token_payments/shared/domain/messaging.py`
- `/app/token_payments/contexts/store_approval/domain/__init__.py`
- `/app/token_payments/contexts/store_approval/application/__init__.py`
- `/scripts/test_order_checkout_skeleton.py`
- `/scripts/test_payment_application_contracts.py`

## 작업

가게 승인 context의 순수 domain model과 application approval service contract를 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_store_approval_core.py`를 추가해 승인 성공, owner 불일치, inactive store, 상품 불일치/비활성, 중복 approval command 멱등 처리를 검증한다.
2. `app/token_payments/contexts/store_approval/domain/model.py`를 추가해 `Store`, `OrderDetail`, `Product`, `ApprovalStatus`, `OrderApprovedEvent`, `OrderRejectedEvent`를 구현한다.
3. `Store.validate_owner`, `Store.validate_order`, `Store.construct_order_approval` 같은 domain 행위를 구현한다.
4. 승인 성공은 `OrderApprovedEvent`, 검증 실패 또는 명시적 반려는 `OrderRejectedEvent`와 구체적 rejection reason을 만든다.
5. `app/token_payments/contexts/store_approval/application/ports.py`, `commands.py`, `service.py`를 추가해 repository/outbox/processed-command port와 approval service를 정의한다.
6. application service는 `RequestStoreApprovalCommand`를 처리하고 outbox에 `CheckoutEventName.ORDER_APPROVED` 또는 `CheckoutEventName.ORDER_REJECTED` event를 저장한다.
7. command 중복은 `ProcessedCommandRepository`로 처리하고 중복이면 aggregate/outbox 저장을 반복하지 않는다.
8. `domain/__init__.py`와 `application/__init__.py`에서 public contract를 export한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_store_approval_core.py scripts/test_order_checkout_skeleton.py scripts/test_messaging_outbox_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. store approval domain/application layer가 adapter dependency를 import하지 않는지 테스트로 검증한다.
4. `phases/1-checkout-core/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- REST API, Kafka listener/publisher, DB repository 구현체를 추가하지 마라.
- 주문 context의 `Order` aggregate를 직접 변경하지 마라. 승인 결과는 event contract로 연결한다.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

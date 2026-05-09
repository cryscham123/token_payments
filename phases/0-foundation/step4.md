# Step 4: order-checkout-skeleton

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/docs/ARCHITECTURE.md`
- Step 1과 Step 2에서 생성/수정한 파일

## 작업

주문 생성 context와 `CheckoutProcessManager`의 최소 skeleton을 구현한다.

1. `Order`, `OrderItem`, `Customer`, `Store`, `Product` 모델을 만든다.
2. `OrderStatus`, `ProductSnapshot`, `TrackingId`, `Address`를 구현한다.
3. `OrderCreatedEvent`, `OrderPaidEvent`, `OrderCancelledEvent`를 정의한다.
4. `CheckoutProcessManager`가 다음 이벤트를 받아 다음 커맨드를 결정하는 순수 로직을 만든다.
   - `OrderCreated`
   - `InventoryReserved`
   - `PaymentConfirmed`
   - `PaymentFailed`
   - `PaymentExpired`
   - `OrderApproved`
   - `OrderRejected`
5. 성공 흐름과 실패/보상 흐름 테스트를 추가한다.

## Acceptance Criteria

```bash
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `PaymentFailedEvent`, `PaymentExpiredEvent`, `OrderRejectedEvent` 보상 커맨드가 문서와 일치하는지 확인한다.
3. `phases/0-foundation/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 재고, 결제, 가게 승인 context의 내부 aggregate를 이 step에서 구현하지 마라.
- 보상 커맨드 id를 랜덤으로 만들지 마라.
- Kafka나 DB adapter 구현을 process manager 순수 로직에 섞지 마라.

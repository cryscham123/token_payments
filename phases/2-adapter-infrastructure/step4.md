# Step 4: kafka-listener-adapters

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/phases/0-foundation/index.json`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/2-adapter-infrastructure/step0.md`
- `/phases/2-adapter-infrastructure/step1.md`
- `/phases/2-adapter-infrastructure/step2.md`
- `/phases/2-adapter-infrastructure/step3.md`
- `/app/token_payments/contexts/checkout/application/process_manager.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/payment/application/handler.py`
- `/app/token_payments/contexts/store_approval/application/service.py`
- `/app/token_payments/shared/adapter/kafka/`

## 작업

Kafka listener adapter를 구현해 외부 메시지를 application handler와 checkout process manager에 연결한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_kafka_listener_adapters.py`를 추가해 command/event deserialization, handler dispatch, duplicate message ignore, malformed payload rejection을 검증한다.
2. checkout listener는 `OrderCreatedEvent`, `InventoryReservedEvent`, `PaymentConfirmedEvent`, `PaymentFailedEvent`, `PaymentExpiredEvent`, `OrderApprovedEvent`, `OrderRejectedEvent`를 `CheckoutProcessManager`에 전달하고 결정된 command를 outbox에 저장한다.
3. inventory listener는 `ReserveInventoryCommand`, `ReleaseInventoryCommand`를 `InventoryCommandHandler`에 전달한다.
4. payment listener는 `InitiatePaymentCommand`, `RefundPaymentCommand`를 `PaymentCommandHandler`에 전달한다.
5. store approval listener는 `RequestStoreApprovalCommand`를 `StoreApprovalService`에 전달한다.
6. listener는 `ProcessedMessageRepository` 또는 `ProcessedCommandRepository`를 사용해 at-least-once delivery 중복을 부작용 없이 무시한다.
7. consumer loop는 얇은 adapter로 유지하고 테스트는 fake message와 fake handler/repository로 빠르게 검증한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_kafka_listener_adapters.py scripts/test_outbox_relay_kafka_publisher.py scripts/test_checkout_core_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. 중복 `MessageId` 또는 `CommandId` 처리 시 추가 outbox command, 결제 환불, 재고 해제가 발생하지 않는지 확인한다.
4. `phases/2-adapter-infrastructure/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- listener에서 domain aggregate 상태를 직접 변경하지 마라. application handler/process manager를 통해서만 처리한다.
- consumer offset commit, process manager 결정, outbox 저장 순서를 불명확하게 섞지 마라.
- Blockchain RPC 또는 MetaMask 구현을 이 step에 넣지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

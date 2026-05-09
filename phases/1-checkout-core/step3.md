# Step 3: payment-application-contracts

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/PRD.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/phases/1-checkout-core/index.json`
- `/app/token_payments/shared/domain/messaging.py`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/contexts/payment/application/__init__.py`
- `/scripts/test_payment_domain_model.py`

## 작업

결제 command 처리와 외부 의존성 port 계약을 만든다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_payment_application_contracts.py`를 추가해 결제 시작, txHash 제출/receipt 확인, 만료 처리, 환불 command의 outbox event 저장과 멱등 처리를 검증한다.
2. `app/token_payments/contexts/payment/application/ports.py`를 추가해 `PaymentRepository`, `PaymentAuthorizationRepository`, `ProcessedCommandRepository`, `OutboxMessageRepository`, `BlockchainAdapter`, `PaymentTimeoutScheduler`, `TransactionService` Protocol을 정의한다.
3. `app/token_payments/contexts/payment/application/commands.py`를 추가해 `InitiatePaymentCommand`, `SubmitTransactionHashCommand`, `ConfirmPaymentReceiptCommand`, `ExpireAwaitingSignatureCommand`, `RefundPaymentCommand` 같은 입력 DTO를 정의한다.
4. `app/token_payments/contexts/payment/application/handler.py`를 추가해 port만 의존하는 순수 application handler를 구현한다.
5. `InitiatePaymentCommand` 처리 시 `Payment(AWAITING_SIGNATURE, expiresAt)`, `PaymentAuthorization`, payment request/gas estimate 결과를 만들고 `PaymentProcessingStartedEvent` outbox를 저장한다.
6. receipt 확인 성공 시 `PaymentConfirmedEvent`, 실패 시 `PaymentFailedEvent`, 만료 시 `PaymentExpiredEvent`, 환불 성공 시 `PaymentRefundedEvent` outbox를 저장한다.
7. checkout process manager가 소비할 수 있도록 payment event outbox는 `CheckoutEventName.PAYMENT_CONFIRMED`, `PAYMENT_FAILED`, `PAYMENT_EXPIRED` 이름과 `OrderId` correlation/key를 사용한다.
8. command 중복은 `ProcessedCommandRepository`로 처리하고 중복이면 외부 port 호출과 outbox 저장을 반복하지 않는다.
9. `app/token_payments/contexts/payment/application/__init__.py`에서 public contract를 export한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_payment_domain_model.py scripts/test_payment_application_contracts.py scripts/test_messaging_outbox_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. application layer가 외부 시스템 호출을 port로만 표현하는지 확인한다.
4. `phases/1-checkout-core/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 실제 RPC 호출, HTTP client, web3, MetaMask client, Kafka publisher, DB adapter를 추가하지 마라.
- 결제 실패/만료 보상 로직을 CheckoutProcessManager가 아닌 payment handler에 섞지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- `scripts/execute.py`를 수정하지 마라.

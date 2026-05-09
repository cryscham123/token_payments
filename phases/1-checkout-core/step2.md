# Step 2: payment-domain-model

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/PRD.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/phases/1-checkout-core/index.json`
- `/app/token_payments/shared/domain/ids.py`
- `/app/token_payments/shared/domain/value_objects.py`
- `/app/token_payments/contexts/payment/domain/__init__.py`
- `/scripts/test_inventory_application_contracts.py`

## 작업

결제 context의 순수 domain model을 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_payment_domain_model.py`를 추가해 `Payment`, `PaymentAuthorization`, `GasEstimate`, `TransactionReceipt`, `PaymentStatus`, `AuthorizationStatus`의 핵심 계약을 검증한다.
2. `app/token_payments/contexts/payment/domain/model.py`를 추가한다.
3. `Payment.initialize_payment(...)`는 `INITIATED` 또는 `AWAITING_SIGNATURE` 상태와 만료 시각을 명확히 만들고, 만료 시각은 timezone-aware여야 한다.
4. `mark_awaiting_signature`, `submit_tx_hash`, `confirm_payment`, `fail_payment`, `expire_awaiting_signature`, `refund_payment` 상태 전이를 구현한다.
5. 유효하지 않은 상태 전이는 `ValueError`로 보호한다. 이미 최종 상태(`CONFIRMED`, `FAILED`, `EXPIRED`, `REFUNDED`)인 결제는 중복 부작용을 만들지 않아야 한다.
6. `GasEstimate.apply_buffer`는 buffer rate를 적용한 `max_fee`를 결정적으로 계산한다.
7. `PaymentAuthorization`은 서명 요청, txHash authorize, 만료 상태 전이를 지원한다.
8. `PaymentProcessingStartedEvent`, `PaymentConfirmedEvent`, `PaymentFailedEvent`, `PaymentRefundedEvent`, `PaymentExpiredEvent`를 domain event로 추가한다.
9. `app/token_payments/contexts/payment/domain/__init__.py`에서 public contract를 `__all__`로 export한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_payment_domain_model.py scripts/test_shared_domain_kernel.py scripts/test_messaging_outbox_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. forbidden adapter dependency(`kafka`, `psycopg`, `sqlalchemy`, `web3`, `requests`, `blockchain`, `metamask`)가 payment domain에 import되지 않았는지 테스트로 검증한다.
4. `phases/1-checkout-core/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 실제 Blockchain RPC, web3, MetaMask client 호출을 구현하지 마라.
- scheduler, repository, adapter 구현은 이 step에서 만들지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

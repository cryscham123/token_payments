# Step 3: checkout-tracking-payment-api

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/3-api-worker-runtime/index.json`
- `/phases/3-api-worker-runtime/step0.md`
- `/phases/3-api-worker-runtime/step1.md`
- `/phases/3-api-worker-runtime/step2.md`
- `/app/token_payments/contexts/payment/application/commands.py`
- `/app/token_payments/contexts/payment/application/handler.py`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/contexts/order/domain/model.py`
- `/app/token_payments/api/`

## 작업

고객 checkout tracking API와 txHash 제출 API를 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_checkout_tracking_payment_api.py`를 추가해 tracking response, pending action, payment request/gas estimate 노출, txHash 제출, receipt pending 상태, 실패/만료/승인 상태 mapping을 검증한다.
2. `contexts/order/application/queries.py` 또는 `checkout/application/queries.py`를 추가해 checkout tracking read model과 query port를 정의한다.
3. `app/token_payments/api/checkout.py`를 추가해 `GET trackingId/orderId` 형태의 framework-independent tracking handler를 구현한다.
4. `app/token_payments/api/payments.py`를 추가해 `SubmitTransactionHashCommand`를 payment application handler로 전달하는 API handler를 구현한다.
5. tracking read adapter는 orders, payments, payment_authorizations, outbox status를 조합하되 command side aggregate mutation과 분리한다.
6. API 응답은 UI가 바로 쓸 수 있게 `status`, `currentStep`, `pendingAction`, `paymentRequest`, `gasEstimate`, `txHash`, `failureReason`, `updatedAt`을 구조화한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_checkout_tracking_payment_api.py scripts/test_payment_application_contracts.py scripts/test_order_api_checkout_start.py scripts/test_runtime_contract_foundation.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. txHash 제출 API가 payment domain 상태 전이를 우회하지 않고 `PaymentCommandHandler`를 통해 처리되는지 확인한다.
4. `phases/3-api-worker-runtime/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- tracking API에서 Kafka publish나 blockchain receipt 조회를 직접 수행하지 마라.
- UI 구현을 이 step에 추가하지 마라.
- 실제 transaction hash가 아닌 fixture 값은 value object 검증을 통과하는 deterministic 값만 사용하라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

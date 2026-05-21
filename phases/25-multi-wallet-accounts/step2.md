# Step 2: checkout-wallet-selection

## 읽어야 할 파일

- `/AGENTS.md`
- `/app/token_payments/api/checkout.py`
- `/app/token_payments/api/payments.py`
- `/app/token_payments/contexts/order/application/service.py`
- `/app/token_payments/contexts/payment/application/commands.py`
- `/app/token_payments/contexts/payment/application/handler.py`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/contexts/payment/adapter/postgres.py`
- `/scripts/test_checkout_tracking_payment_api.py`
- `/scripts/test_payment_application_contracts.py`
- `/scripts/test_happy_path_checkout_e2e.py`
- `/phases/25-multi-wallet-accounts/index.json`

## 작업

Checkout/payment flow에서 결제 지갑을 명시적으로 선택할 수 있게 한다.

1. `scripts/test_checkout_wallet_selection.py`를 추가한다.
   - checkout 시작 또는 payment initiation은 verified active wallet id를 선택할 수 있어야 한다.
   - wallet id를 생략하면 chain별 primary wallet을 사용해야 한다.
   - 다른 user의 wallet, revoked wallet, chain mismatch wallet은 거부되어야 한다.
   - payment authorization은 `wallet_id`, `wallet_address`, `chain_id`를 보존해야 한다.
   - tracking response는 선택된 wallet을 redacted/bounded하게 반환해야 한다.
2. payment command/domain을 갱신한다.
   - `InitiatePaymentCommand`와 authorization model에 wallet id를 추가한다.
   - MetaMask/signature request는 selected wallet 기준으로 생성한다.
   - existing payment receipt confirmation은 wallet identity를 검증 가능한 형태로 보존한다.
3. checkout/payment API를 갱신한다.
   - request body에 optional `walletId`를 추가한다.
   - response/docs/Postman expected fixtures를 갱신한다.
4. PostgreSQL adapter를 갱신한다.
   - payment authorization table에 wallet id/chain id/address를 저장한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_checkout_wallet_selection.py scripts/test_checkout_tracking_payment_api.py scripts/test_payment_application_contracts.py scripts/test_happy_path_checkout_e2e.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. checkout wallet selection 테스트를 먼저 추가하고 실패를 확인한다.
2. payment/order/API/postgres adapter를 갱신한 뒤 AC를 실행한다.
3. `/phases/25-multi-wallet-accounts/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- wallet address만 request로 받아 결제 소유권을 판단하지 마라.
- revoked/unverified wallet을 fallback으로 사용하지 마라.
- stablecoin asset model을 이 step에 크게 추가하지 마라. asset-aware 결제는 다음 phase에서 다룬다.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

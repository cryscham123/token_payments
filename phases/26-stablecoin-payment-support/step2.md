# Step 2: erc20-payment-authorization-receipts

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/SEQUENCES.md`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/contexts/payment/application/handler.py`
- `/app/token_payments/contexts/payment/adapter/blockchain.py`
- `/app/token_payments/contexts/payment/adapter/transaction_service.py`
- `/app/token_payments/contexts/payment/adapter/postgres.py`
- `/app/token_payments/runtime/composition.py`
- `/scripts/test_wallet_blockchain_boundaries.py`
- `/scripts/test_payment_application_contracts.py`
- `/phases/26-stablecoin-payment-support/index.json`

## 작업

ERC-20 stablecoin 결제 요청과 receipt verification을 지원한다.

1. `scripts/test_erc20_payment_authorization_receipts.py`를 추가한다.
   - ERC-20 payment authorization은 token contract address, recipient, amount minor units, chain id를 포함해야 한다.
   - MetaMask transaction request는 native transfer와 ERC-20 transfer call을 구분해야 한다.
   - receipt verification은 tx success뿐 아니라 ERC-20 `Transfer` log의 token address, from, to, amount를 검증해야 한다.
   - wrong token, wrong recipient, insufficient amount, wrong chain, reverted tx는 payment failed event를 만들어야 한다.
   - native coin 결제 path는 기존 behavior를 유지해야 한다.
2. blockchain adapter를 갱신한다.
   - ERC-20 transfer calldata 생성 또는 transaction request factory를 추가한다.
   - receipt log decoder는 표준 library/structured parsing을 사용하고 ad hoc string parsing을 피한다.
   - bounded timeout/error handling을 유지한다.
3. payment application을 갱신한다.
   - payment status transition은 asset type에 따라 verification strategy를 선택한다.
   - outbox event payload는 asset metadata와 receipt verification result를 포함한다.
4. postgres adapter를 갱신한다.
   - payment/payment authorization row에 asset id/type/token address/amount minor units를 저장한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_erc20_payment_authorization_receipts.py scripts/test_wallet_blockchain_boundaries.py scripts/test_payment_application_contracts.py scripts/test_compensation_checkout_e2e.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. ERC-20 authorization/receipt 테스트를 먼저 추가하고 실패를 확인한다.
2. payment application/blockchain/postgres adapters를 갱신한 뒤 AC를 실행한다.
3. `/phases/26-stablecoin-payment-support/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- receipt status만 보고 ERC-20 결제를 성공 처리하지 마라.
- token decimals를 client-provided value로 신뢰하지 마라.
- permit, gas sponsorship, swap, exchange-rate conversion을 이 step에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

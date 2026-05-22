# Step 6: erc20-payment-authorization-receipts

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
- `/phases/25-multi-wallet-accounts/index.json`

## 작업

선택된 payer wallet 기준으로 ERC-20 stablecoin 결제 요청과 receipt verification을 지원한다.

1. `scripts/test_erc20_payment_authorization_receipts.py`를 추가한다.
   - ERC-20 payment authorization은 `payer_wallet_id`, token contract address, recipient, amount minor units, chain id를 포함해야 한다.
   - MetaMask transaction request는 native transfer와 ERC-20 transfer call을 구분해야 한다.
   - receipt verification은 tx success뿐 아니라 ERC-20 `Transfer` log의 token address, from, to, amount를 검증해야 한다.
   - wrong token, wrong recipient, wrong payer wallet, insufficient amount, wrong chain, reverted tx는 payment failed event를 만들어야 한다.
   - native coin 결제 path는 기존 behavior를 유지해야 한다.
   - persistence schema는 `payment_authorizations`에 expected payer wallet/asset/chain/amount/recipient terms를 두고, `payments`에는 authorization reference와 observed tx hash/status/receipt verification result를 둬야 한다.
   - `payments`가 asset fields를 보관한다면 expected value 중복이 아니라 immutable receipt snapshot 또는 denormalized read snapshot임을 컬럼명/테스트로 구분해야 한다.
   - `payment_authorizations.chain_name`과 `payments.chain_name`은 write model에서 제거되어야 한다.
2. blockchain adapter를 갱신한다.
   - ERC-20 transfer calldata 생성 또는 transaction request factory를 추가한다.
   - receipt log decoder는 표준 library/structured parsing을 사용하고 ad hoc string parsing을 피한다.
   - bounded timeout/error handling을 유지한다.
3. payment application을 갱신한다.
   - payment status transition은 asset type에 따라 verification strategy를 선택한다.
   - outbox event payload는 expected authorization terms와 observed receipt verification result를 분리해서 포함한다.
   - payment confirmation은 authorization의 expected payer wallet/asset/amount/recipient/chain을 기준으로 검증하고, request body의 asset fields를 신뢰하지 않는다.
4. postgres adapter를 갱신한다.
   - payment authorization row에는 expected `payer_wallet_id`, `asset_id`, `chain_id`, recipient, expected amount minor units를 저장한다.
   - payments row에는 `payment_authorization_id`/`payment_id` 참조, transaction hash, observed status, observed receipt fields를 저장한다.
   - duplicated expected asset columns를 `payments`에 추가하지 않는다. 읽기 성능 때문에 snapshot이 필요하면 `*_snapshot` 또는 `observed_*` 의미로 제한하고 immutable하게 다룬다.
   - `chain_name`은 두 테이블 모두에 canonical write column으로 추가하지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_erc20_payment_authorization_receipts.py scripts/test_wallet_blockchain_boundaries.py scripts/test_payment_application_contracts.py scripts/test_compensation_checkout_e2e.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. ERC-20 authorization/receipt 테스트를 먼저 추가하고 실패를 확인한다.
2. payment application/blockchain/postgres adapters를 갱신한 뒤 AC를 실행한다.
3. `/phases/25-multi-wallet-accounts/index.json`의 step 6 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- receipt status만 보고 ERC-20 결제를 성공 처리하지 마라.
- token decimals를 client-provided value로 신뢰하지 마라.
- authorization과 payment row에 같은 의미의 expected asset/amount/chain field를 중복 저장하지 마라.
- `chain_name`을 chain id의 종속 데이터로 payment tables에 다시 저장하지 마라.
- permit, gas sponsorship, swap, exchange-rate conversion을 이 step에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 5: wallet-asset-aware-pricing-checkout

## 읽어야 할 파일

- `/AGENTS.md`
- `/app/token_payments/contexts/order/domain/model.py`
- `/app/token_payments/contexts/order/application/service.py`
- `/app/token_payments/contexts/store_catalog/domain/model.py`
- `/app/token_payments/contexts/payment/application/commands.py`
- `/app/token_payments/contexts/payment/application/handler.py`
- `/app/token_payments/api/checkout.py`
- `/scripts/test_order_api_checkout_start.py`
- `/scripts/test_checkout_tracking_payment_api.py`
- `/scripts/test_payment_application_contracts.py`
- `/phases/25-multi-wallet-accounts/index.json`

## 작업

상품 가격, checkout total, payment initiation을 selected wallet과 selected asset 기준으로 정합하게 바꾼다.

1. `scripts/test_asset_aware_pricing_checkout.py`를 추가한다.
   - store product는 지원 asset별 price를 가질 수 있어야 한다.
   - checkout request는 `paymentAssetId`와 optional `walletId`를 선택할 수 있어야 한다.
   - wallet id를 생략하면 selected asset chain에 맞는 chain별 primary wallet을 사용해야 한다.
   - 선택한 asset이 store/product에서 지원되지 않거나 selected wallet chain과 asset chain이 다르면 bounded validation error가 나야 한다.
   - order total과 outbox event payload는 `assetId`, `chainId`, `amountMinorUnits` 또는 lossless decimal amount를 보존해야 한다.
   - `symbol`, `decimals`, token display metadata가 필요하면 registry에서 검증된 asset snapshot으로만 전달하고 client-provided value를 신뢰하지 않아야 한다.
   - idempotent checkout retry는 같은 wallet/asset/amount를 유지해야 하며 다른 wallet/asset으로 같은 key를 재사용하면 conflict가 나야 한다.
2. order/store catalog domain을 갱신한다.
   - product price를 단일 native `Crypto`에서 asset-aware price set으로 전환한다.
   - store supported payment assets와 settlement wallet chain compatibility를 명확히 둔다.
3. checkout API와 process manager payload를 갱신한다.
   - order created event, reserve inventory command, initiate payment command가 selected wallet reference와 asset metadata를 전달한다.
   - event payload에서 expected asset metadata와 observed payment receipt metadata를 구분할 수 있어야 한다.
   - 기존 native-only tests를 asset-aware expected data로 수정한다.
4. payment initiation command를 갱신한다.
   - selected wallet chain과 selected asset chain이 일치해야 한다.
   - payment initiation은 `chain_name`이 아니라 `chain_id`와 asset registry/mapping으로 network metadata를 resolve한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_asset_aware_pricing_checkout.py scripts/test_checkout_wallet_selection.py scripts/test_order_api_checkout_start.py scripts/test_checkout_tracking_payment_api.py scripts/test_payment_application_contracts.py scripts/test_happy_path_checkout_e2e.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. wallet/asset-aware checkout 테스트를 먼저 추가하고 실패를 확인한다.
2. order/store catalog/payment/API code를 갱신한 뒤 AC를 실행한다.
3. `/phases/25-multi-wallet-accounts/index.json`의 step 5 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 서로 다른 asset 금액을 단순 numeric amount만으로 비교하지 마라.
- selected wallet chain과 asset chain mismatch를 허용하지 마라.
- registry에 없는 symbol/decimals/token address를 checkout request나 client payload에서 받아 저장하지 마라.
- exchange-rate conversion을 이 step에 넣지 마라. stablecoin pricing은 explicit price 기준으로 둔다.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

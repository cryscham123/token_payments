# Step 0: payment-asset-registry-domain

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/shared/domain/value_objects.py`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/contexts/store_catalog/domain/model.py`
- `/app/token_payments/shared/adapter/postgres/schema.py`
- `/phases/25-multi-wallet-accounts/index.json`

## 작업

Native coin 전용 결제 모델을 asset-aware payment model로 확장하고, USDC/USDT 같은 stablecoin을 registry로 관리한다.

1. `scripts/test_payment_asset_registry_domain.py`를 추가한다.
   - `PaymentAsset` 또는 동등한 domain value가 `asset_id`, `asset_type`, `chain_id`, `symbol`, `decimals`, optional `contract_address`, `enabled`를 가져야 한다.
   - native asset과 ERC-20 stablecoin asset을 구분해야 한다.
   - ERC-20 asset은 contract address와 decimals가 필수여야 한다.
   - supported stablecoin은 registry에 의해 결정되고 request body 임의 token address를 신뢰하지 않아야 한다.
   - amount는 asset decimals 기준 integer minor unit 또는 정확한 decimal value로 loss 없이 표현되어야 한다.
2. domain/schema를 추가한다.
   - 권장 테이블: `payment_assets`
   - 권장 seed assets: local native token, local USDC, local USDT placeholder
   - production token address는 committed fixture에 넣지 않는다. local/test placeholder만 사용한다.
3. shared money/value object를 갱신한다.
   - 기존 `Crypto`가 native symbol만 가정한다면 asset id/decimals aware type으로 확장하거나 새 type을 추가한다.
   - rounding, decimal scale, serialization을 명시한다.
4. docs를 갱신한다.
   - stablecoin 지원은 registry-driven이고 arbitrary ERC-20 payment는 scope 밖임을 명시한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_payment_asset_registry_domain.py scripts/test_payment_domain_model.py scripts/test_store_owner_inventory_domain_commands.py scripts/test_postgres_context_repositories.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. payment asset registry 테스트를 먼저 추가하고 실패를 확인한다.
2. domain/schema/shared value object를 갱신한 뒤 AC를 실행한다.
3. `/phases/26-stablecoin-payment-support/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- arbitrary token address를 checkout request에서 받아 결제 asset으로 신뢰하지 마라.
- float 기반 금액 계산을 추가하지 마라.
- real mainnet token address나 production RPC key를 fixture에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 4: payment-asset-chain-registry-domain

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/shared/domain/value_objects.py`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/contexts/payment/adapter/postgres.py`
- `/app/token_payments/contexts/store_catalog/domain/model.py`
- `/app/token_payments/shared/adapter/postgres/schema.py`
- `/app/test_network/Dockerfile`
- `/docker-compose.yml`
- `/.env.example`
- `/phases/25-multi-wallet-accounts/index.json`

## 작업

Native coin 전용 결제 모델을 asset-aware payment model로 확장하고, USDC/USDT 같은 stablecoin과 chain metadata를 registry로 관리한다.

0. chain/asset audit와 완료 후 불변조건을 먼저 명시한다.
   - `payment_authorizations.chain_name`, `payments.chain_name`, duplicated `asset_id`/`asset_type`/`token_address`/`amount_numeric` 사용 위치를 전수 확인한다.
   - phase 완료 후 `chain_id`가 canonical chain key이고, chain display metadata는 `chains`/`networks` registry 또는 명시적 application mapping에서만 나온다.
   - `payment_authorizations`는 기대 결제 조건의 source of truth이고, `payments`는 authorization 참조와 실제 on-chain receipt/transaction 관측값을 기록한다.
   - expected asset/amount 필드를 두 테이블에 같은 의미로 중복 저장하지 않는다. 중복이 필요한 경우에는 immutable snapshot/observed value 의미가 컬럼명과 테스트에 드러나야 한다.
1. `scripts/test_payment_asset_registry_domain.py`를 추가한다.
   - `PaymentAsset` 또는 동등한 domain value가 `asset_id`, `asset_type`, `chain_id`, `symbol`, `decimals`, optional `contract_address`, `enabled`를 가져야 한다.
   - native asset과 ERC-20 stablecoin asset을 구분해야 한다.
   - ERC-20 asset은 contract address와 decimals가 필수여야 한다.
   - supported stablecoin은 registry에 의해 결정되고 request body 임의 token address를 신뢰하지 않아야 한다.
   - amount는 asset decimals 기준 integer minor unit 또는 정확한 decimal value로 loss 없이 표현되어야 한다.
   - `chain_name`은 payment/payment authorization persistence model의 write column으로 남지 않아야 한다.
   - `PaymentAsset.chain_id`는 canonical chain registry/mapping에 존재하는 chain만 참조해야 한다.
2. domain/schema를 추가한다.
   - 권장 테이블 또는 mapping: `chains`/`networks` with `chain_id`, display name, native symbol, explorer/RPC metadata policy, enabled status.
   - 권장 테이블: `payment_assets`
   - 권장 seed assets: local native token, local USDC, local USDT placeholder
   - production token address는 committed fixture에 넣지 않는다. local/test placeholder만 사용한다.
   - `payment_assets.chain_id`는 `chains.chain_id` FK 또는 application mapping validation으로 보호한다.
   - `payments.chain_name`과 `payment_authorizations.chain_name`은 제거하거나 compatibility read-only projection으로 격리한다.
3. shared money/value object를 갱신한다.
   - 기존 `Crypto`가 native symbol만 가정한다면 asset id/decimals aware type으로 확장하거나 새 type을 추가한다.
   - rounding, decimal scale, serialization을 명시한다.
4. docs를 갱신한다.
   - stablecoin 지원은 registry-driven이고 arbitrary ERC-20 payment는 scope 밖임을 명시한다.
   - API/docs는 backend 내부 chain display 설정이나 RPC 설정명을 response contract로 노출하지 않는다.
5. `app/test_network/` 아래 ERC-20 컨트랙트 자동 배포 스크립트를 추가한다.
   - Ganache 시작 직후 실행되는 `deploy.js` (Node.js) 스크립트를 작성한다. `ganache` npm 패키지가 이미 설치된 이미지에서 실행 가능해야 한다.
   - 최소 ERC-20 컨트랙트(USDC-like, symbol `USDC`, decimals 6)와 (USDT-like, symbol `USDT`, decimals 6) 두 개를 배포한다. Solidity 컴파일 없이 배포할 수 있도록 미리 컴파일된 ERC-20 bytecode를 사용한다.
   - 배포 계정은 `TEST_NETWORK_PRIVATE_KEY` 환경 변수로 주어진 Ganache 계정을 사용한다.
   - 배포된 USDC/USDT contract address를 `/var/chainDB/deployed_contracts.json` 파일에 저장한다. 이후 런타임에서 이 파일을 읽어 `ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS`를 동적으로 설정하거나, compose 환경에서 해당 주소를 확인할 수 있어야 한다.
   - `app/test_network/Dockerfile`을 수정해 Ganache와 함께 `deploy.js`가 실행되도록 entrypoint를 갱신한다.
   - `.env.example`의 `ADAPTER_BLOCKCHAIN_TOKEN_ADDRESS` 주석에 이 배포 파일 경로를 참조하도록 안내를 추가한다.
   - `payment_assets` registry seed는 placeholder `0x333...` 주소 대신 `deployed_contracts.json`에서 읽은 실제 배포 주소를 참조하거나, `.env`에 명시된 주소를 사용해야 한다. placeholder 주소를 source of truth로 사용하지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_payment_asset_registry_domain.py scripts/test_payment_domain_model.py scripts/test_store_owner_inventory_domain_commands.py scripts/test_postgres_context_repositories.py
python3 scripts/validate_phases.py
```

> **test_network 수동 검증**: `docker compose up test_network -d` 후 `cat $(docker inspect test_network --format '{{range .Mounts}}{{.Destination}}{{end}}')/deployed_contracts.json` 으로 USDC/USDT contract address가 출력되는지 확인한다.

## 검증 절차

1. payment asset registry 테스트를 먼저 추가하고 실패를 확인한다.
2. domain/schema/shared value object를 갱신한 뒤 AC를 실행한다.
3. test_network Dockerfile/deploy script를 추가하고 `docker compose build test_network`로 빌드가 성공하는지 확인한다.
4. `/phases/25-multi-wallet-accounts/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- arbitrary token address를 checkout request에서 받아 결제 asset으로 신뢰하지 마라.
- float 기반 금액 계산을 추가하지 마라.
- `chain_id`에 종속되는 `chain_name`을 payment/payment authorization row에 canonical data로 중복 저장하지 마라.
- real mainnet token address나 production RPC key를 fixture에 넣지 마라.
- Solidity 컴파일러(`solc`)를 test_network 이미지 빌드 단계에 추가하지 마라. 미리 컴파일된 ERC-20 bytecode만 사용한다.
- placeholder `0x333...` 같은 임의 주소를 `payment_assets` registry의 production-like seed로 커밋하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

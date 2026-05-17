# Step 2: erc1271-smart-wallet-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/.env.example`
- `/docs/API_SPEC.md`
- `/app/token_payments/contexts/auth/adapter/wallet_signature.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/contexts/payment/adapter/_chain_mapping.py`
- `/app/token_payments/contexts/payment/adapter/blockchain.py`
- `/scripts/test_wallet_signature_verifier_port.py`
- `/scripts/test_wallet_blockchain_boundaries.py`

## 작업

배포된 smart contract wallet 로그인 지원을 위해 ERC-1271 verification을 추가한다. 이 phase의 범위는 deployed contract account까지만이며, ERC-6492 counterfactual account는 제외한다.

1. `scripts/test_erc1271_smart_wallet_auth.py`를 추가한다.
   - verifier가 `eth_getCode` 또는 동등한 client call로 signer wallet이 contract인지 확인하는지 검증한다.
   - contract wallet이면 SIWE message digest와 signature로 `isValidSignature(bytes32,bytes)`를 호출해야 한다.
   - success magic value `0x1626ba7e`만 valid로 취급한다.
   - revert, wrong magic value, no code, chain mismatch, timeout은 bounded invalid signature/readiness error로 매핑해야 한다.
   - EOA wallet은 기존 EOA path를 계속 사용한다.
2. blockchain/auth client boundary를 추가한다.
   - provider client는 `get_code`, `call_contract` 또는 동등한 최소 method만 요구한다.
   - ABI encoding/decoding은 표준 라이브러리로 충분하지 않으면 명시적 dependency contract를 추가한다.
3. `.env.example`과 runtime config를 갱신한다.
   - auth verifier가 사용할 chain RPC URL, chain id, timeout key를 명확히 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_erc1271_smart_wallet_auth.py scripts/test_wallet_signature_verifier_port.py scripts/test_siwe_message_contract.py scripts/test_auth_api_session_runtime.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. ERC-1271 테스트를 먼저 추가하고 실패를 확인한다.
2. adapter/runtime/env/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/18-siwe-erc1271-auth/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- ERC-6492, bundler, paymaster, account deployment flow를 구현하지 마라.
- 컨트랙트 계정 검증 실패 시 EOA fallback으로 다른 주소를 허용하지 마라.
- RPC response, signature, message 원문을 access log에 남기지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

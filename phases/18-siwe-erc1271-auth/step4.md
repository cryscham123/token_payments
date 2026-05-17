# Step 4: siwe-erc1271-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/README.md`
- `/app/README.md`
- `/.env.example`
- `/scripts/test_siwe_message_contract.py`
- `/scripts/test_wallet_signature_verifier_port.py`
- `/scripts/test_erc1271_smart_wallet_auth.py`
- `/scripts/test_siwe_auth_api_public_contract.py`
- `/phases/index.json`
- `/phases/18-siwe-erc1271-auth/index.json`

## 작업

SIWE + ERC-1271 auth phase의 public verification을 고정한다.

1. `scripts/test_siwe_erc1271_auth_public_contracts.py`를 추가한다.
   - docs가 EOA, deployed smart wallet, unsupported ERC-6492/counterfactual account 범위를 명확히 설명하는지 검증한다.
   - auth tests가 SIWE parse/validate, EOA, ERC-1271 success/failure/revert를 커버하는지 검증한다.
   - runtime config/env docs가 RPC timeout/redaction/chain id mismatch를 설명하는지 검증한다.
   - phase metadata가 completed step summary와 top-level phase status를 일관되게 반영하는지 검증한다.
2. docs와 README를 최종 정리한다.
3. `/phases/18-siwe-erc1271-auth/index.json`와 `/phases/index.json` 상태를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_siwe_erc1271_auth_public_contracts.py scripts/test_siwe_message_contract.py scripts/test_wallet_signature_verifier_port.py scripts/test_erc1271_smart_wallet_auth.py scripts/test_siwe_auth_api_public_contract.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. public verification 테스트를 먼저 추가하고 실패를 확인한다.
2. docs/metadata를 갱신한 뒤 AC를 실행한다.
3. `/phases/18-siwe-erc1271-auth/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
4. `/phases/index.json`에서 `18-siwe-erc1271-auth`를 `completed`로 갱신한다.

## 금지사항

- ERC-6492, linked wallets, 자체 recovery, bundler/paymaster를 완료 범위로 표시하지 마라.
- smart wallet auth를 recovery 서비스 제공으로 문서화하지 마라.
- secret/signature/token 원문을 docs/fixtures에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 1: wallet-signature-verifier-port

## 읽어야 할 파일

- `/AGENTS.md`
- `/app/token_payments/contexts/auth/application/ports.py`
- `/app/token_payments/contexts/auth/application/service.py`
- `/app/token_payments/contexts/auth/adapter/wallet_signature.py`
- `/app/token_payments/runtime/composition.py`
- `/scripts/test_wallet_blockchain_boundaries.py`
- `/scripts/test_auth_api_session_runtime.py`
- `/scripts/test_siwe_message_contract.py`

## 작업

EOA 전용 `recover_address(message, signature)` 포트를 account-type neutral 검증 포트로 바꾼다. 이 step은 EOA 구현을 새 포트에 맞춰 이식하고, ERC-1271 hook point를 만든다.

1. `scripts/test_wallet_signature_verifier_port.py`를 추가한다.
   - application port가 `verify_signature(wallet, message, signature, chain_id)` 또는 동등한 boolean/result contract를 제공하는지 검증한다.
   - EOA verifier는 기존 recover result와 requested wallet을 비교해야 한다.
   - invalid signature, recovered wallet mismatch, unsupported chain은 bounded failure로 매핑되어야 한다.
   - application service는 recovered address를 직접 요구하지 않고 verifier result만 사용해야 한다.
2. `WalletSignatureVerifier` port와 adapter를 갱신한다.
   - 기존 fake/test clients가 새 port로 동작하게 한다.
   - backward-compatible client wrapper가 필요한 경우 내부에서 `recover_address`/`recover_message`를 계속 지원한다.
3. runtime composition wiring을 갱신한다.
   - live dependency가 chain id를 verifier에 전달할 수 있어야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_wallet_signature_verifier_port.py scripts/test_siwe_message_contract.py scripts/test_auth_api_session_runtime.py scripts/test_wallet_blockchain_boundaries.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. verifier port 테스트를 먼저 추가하고 실패를 확인한다.
2. application/adapter/runtime wiring을 갱신한 뒤 AC를 실행한다.
3. `/phases/18-siwe-erc1271-auth/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- auth service가 EOA recovered address에 직접 의존하는 구조를 유지하지 마라.
- invalid signature를 wallet mismatch와 혼동해서 challenge 상태를 잘못 저장하지 마라.
- ERC-1271 온체인 호출을 이 step에서 구현하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

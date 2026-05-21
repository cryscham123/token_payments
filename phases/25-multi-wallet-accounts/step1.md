# Step 1: wallet-link-unlink-api

## 읽어야 할 파일

- `/AGENTS.md`
- `/app/token_payments/api/auth.py`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/contexts/auth/application/service.py`
- `/app/token_payments/contexts/auth/application/ports.py`
- `/app/token_payments/contexts/auth/application/siwe.py`
- `/app/token_payments/runtime/composition.py`
- `/scripts/test_auth_api_session_runtime.py`
- `/scripts/test_siwe_message_contract.py`
- `/scripts/test_erc1271_smart_wallet_auth.py`
- `/phases/25-multi-wallet-accounts/index.json`

## 작업

인증된 사용자가 wallet을 추가 검증해서 연결하고, primary wallet을 선택하고, 사용하지 않는 wallet을 revoke할 수 있는 API를 추가한다.

1. `scripts/test_wallet_link_unlink_api.py`를 추가한다.
   - authenticated user만 wallet link challenge를 요청할 수 있어야 한다.
   - link challenge는 SIWE message를 사용하고 target wallet/chain id가 challenge와 일치해야 한다.
   - 이미 다른 active user에게 연결된 wallet은 link할 수 없어야 한다.
   - primary wallet 변경은 같은 chain의 verified active wallet에만 가능해야 한다.
   - 마지막 verified wallet revoke는 안전 정책에 따라 거부하거나 explicit recovery-ready 상태에서만 허용해야 한다.
   - unlink/revoke는 audit event를 남겨야 한다.
2. auth API route를 추가한다.
   - 권장 operation: `requestWalletLinkChallenge`, `linkWallet`, `listWallets`, `setPrimaryWallet`, `revokeWallet`
   - route manifest, Postman expected fixtures, docs를 함께 갱신한다.
3. auth service를 갱신한다.
   - login challenge와 wallet link challenge를 혼동하지 않도록 challenge purpose를 구분한다.
   - wallet verification event를 outbox 또는 auth event publisher contract에 남긴다.
4. runtime composition을 갱신한다.
   - live auth facade가 wallet repository와 challenge repository를 주입받도록 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_wallet_link_unlink_api.py scripts/test_auth_api_session_runtime.py scripts/test_siwe_message_contract.py scripts/test_erc1271_smart_wallet_auth.py scripts/test_route_surface_contract_docs.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. wallet link/unlink API 테스트를 먼저 추가하고 실패를 확인한다.
2. API/service/runtime/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/25-multi-wallet-accounts/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 로그인용 nonce를 wallet link에 재사용하지 마라.
- client가 넘긴 user id로 wallet ownership을 결정하지 마라.
- revoked wallet을 session refresh나 payment selection에 사용하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

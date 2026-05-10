# Step 1: auth-api-session-runtime

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/phases/0-foundation/index.json`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/3-api-worker-runtime/index.json`
- `/phases/3-api-worker-runtime/step0.md`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/contexts/auth/application/ports.py`
- `/app/token_payments/contexts/auth/adapter/wallet_signature.py`
- `/app/token_payments/runtime/`
- `/app/token_payments/api/`

## 작업

MetaMask login API와 session runtime을 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_auth_api_session_runtime.py`를 추가해 login challenge 발급, signing message shape, MetaMask signature login, challenge 재사용 거부, session refresh/logout, API error mapping을 검증한다.
2. `contexts/auth/application/service.py`를 추가해 `AuthUseCase` 구현을 만든다. clock, nonce generator, user/session id generator, repositories, `WalletSignatureVerifier`, `TokenIssuer`는 모두 constructor로 주입한다.
3. `contexts/auth/adapter/postgres.py`와 schema 변경을 추가해 user, login challenge, auth session 저장을 injected PostgreSQL connection 기반으로 구현한다. 테스트는 fake connection으로 검증한다.
4. `app/token_payments/api/auth.py`를 추가해 framework-independent handler를 구현한다: request login challenge, login with MetaMask, refresh session, logout, current user.
5. token issuer는 테스트 가능한 deterministic fake와 production boundary protocol을 분리한다. 실제 signing secret이나 private key는 코드/fixture에 넣지 않는다.
6. 실패 응답은 구조화한다: `INVALID_SIGNATURE`, `EXPIRED_CHALLENGE`, `REUSED_NONCE`, `WALLET_MISMATCH`, `VALIDATION_ERROR`.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_auth_api_session_runtime.py scripts/test_auth_context_skeleton.py scripts/test_runtime_contract_foundation.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. auth domain/application이 API, PostgreSQL, wallet client 구현을 직접 import하지 않는지 확인한다.
4. `phases/3-api-worker-runtime/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 테스트나 문서에 실제 private key, seed phrase, JWT signing secret을 쓰지 마라.
- nonce 재사용/만료 검증을 API adapter에서만 처리하지 마라. application service에서 강제하라.
- live MetaMask나 external wallet provider가 없으면 실패하는 테스트를 기본 AC에 넣지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

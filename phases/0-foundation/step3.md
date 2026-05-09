# Step 3: auth-context-skeleton

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/docs/ADR.md`
- Step 1과 Step 2에서 생성/수정한 파일

## 작업

MetaMask 로그인 context의 domain/application skeleton을 구현한다.

1. `User`, `LoginChallenge`, `AuthSession` aggregate/entity를 만든다.
2. `AuthNonce`, `ChallengeStatus`, `IssuedToken`, `RefreshTokenHash`, `LoginFailureReason`을 구현한다.
3. input port로 `requestLoginChallenge`, `loginWithMetaMask`, `refreshSession`, `logout`, `getCurrentUser`를 정의한다.
4. output port로 `UserRepository`, `LoginChallengeRepository`, `AuthSessionRepository`, `WalletSignatureVerifier`, `TokenIssuer`, `AuthEventPublisher`를 정의한다.
5. nonce 1회 사용, 만료, wallet address 정규화 비교에 대한 테스트를 추가한다.

## Acceptance Criteria

```bash
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. MetaMask나 외부 RPC를 직접 호출하지 않고 port로만 표현했는지 확인한다.
3. `phases/0-foundation/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 비밀번호 기반 인증을 추가하지 마라.
- nonce를 재사용 가능하게 만들지 마라.
- 실제 JWT secret 또는 private key를 커밋하지 마라.

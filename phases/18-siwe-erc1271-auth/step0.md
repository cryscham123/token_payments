# Step 0: siwe-message-contract

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/app/token_payments/contexts/auth/application/service.py`
- `/app/token_payments/contexts/auth/application/ports.py`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/api/auth.py`
- `/scripts/test_auth_api_session_runtime.py`
- `/scripts/test_auth_context_skeleton.py`
- `/phases/17-docker-compose-live-server/index.json`

## 작업

현재 custom MetaMask message를 SIWE 호환 message contract로 바꾼다. 이 step은 EOA 검증만 유지하고, ERC-1271은 다음 step에서 붙인다.

1. `scripts/test_siwe_message_contract.py`를 추가한다.
   - challenge response가 SIWE 필수 필드 `domain`, `address`, `uri`, `version`, `chainId`, `nonce`, `issuedAt`, `expirationTime`을 포함하는지 검증한다.
   - nonce는 SIWE 규칙에 맞는 충분한 길이의 alphanumeric value여야 한다.
   - login은 message의 nonce뿐 아니라 domain/address/chainId/expirationTime이 저장된 challenge와 일치하는지 검증해야 한다.
   - domain/chainId/address mismatch는 bounded auth error로 reject되어야 한다.
2. auth application service를 갱신한다.
   - SIWE message builder/parser를 도메인 외부 application layer에 둔다.
   - 기존 API field name은 backward-compatible하게 유지할 수 있지만 response/docs는 SIWE 기준으로 설명한다.
3. docs/API spec과 sequence를 갱신한다.
   - `loginWithMetaMask` 명칭은 route operation compatibility를 위해 유지할 수 있지만 설명은 SIWE login으로 바꾼다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_siwe_message_contract.py scripts/test_auth_api_session_runtime.py scripts/test_auth_context_skeleton.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. SIWE message contract 테스트를 먼저 추가하고 실패를 확인한다.
2. auth service/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/18-siwe-erc1271-auth/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- SIWE 검증을 nonce 추출만으로 끝내지 마라.
- 기존 EOA 로그인 happy path를 깨뜨리지 마라.
- ERC-6492, linked wallets, 자체 recovery 구현을 이 step에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

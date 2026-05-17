# Step 3: auth-api-runtime-docs

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/docs/SEQUENCES.md`
- `/README.md`
- `/app/README.md`
- `/.env.example`
- `/postman`
- `/app/token_payments/api/auth.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/runtime/session_transport.py`
- `/scripts/test_postman_cookie_auth_flow.py`
- `/scripts/test_cookie_session_transport.py`
- `/scripts/test_csrf_cors_request_guard.py`

## 작업

SIWE + ERC-1271 auth 변경을 API/docs/Postman/runtime contract에 반영한다. Browser auth는 계속 cookie-first로 유지한다.

1. `scripts/test_siwe_auth_api_public_contract.py`를 추가한다.
   - API spec이 SIWE challenge/session payload를 설명하는지 검증한다.
   - Postman fixtures가 SIWE field와 smart wallet verification metadata를 반영하는지 검증한다.
   - cookie auth, CSRF, CORS, refresh rotation contract가 변경 후에도 유지되는지 검증한다.
2. Auth API response를 필요시 갱신한다.
   - `signingMessage`는 SIWE message를 반환한다.
   - `walletType` 또는 `signatureVerificationMethod` 같은 metadata가 필요하면 non-sensitive 형태로 추가한다.
3. README/app README를 갱신한다.
   - EOA와 deployed smart wallet login 지원 범위를 명확히 한다.
   - linked wallets와 ERC-6492는 future scope로 표시한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_siwe_auth_api_public_contract.py scripts/test_postman_cookie_auth_flow.py scripts/test_cookie_session_transport.py scripts/test_csrf_cors_request_guard.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. API/docs/Postman contract 테스트를 먼저 추가하고 실패를 확인한다.
2. API/docs/fixtures를 갱신한 뒤 AC를 실행한다.
3. `/phases/18-siwe-erc1271-auth/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Browser 기본 auth transport를 Bearer/localStorage로 바꾸지 마라.
- signature, signed message, token, cookie 원문을 fixture expected output에 그대로 넣지 마라.
- linked wallets API를 이 step에 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

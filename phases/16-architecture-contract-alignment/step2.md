# Step 2: auth-storage-env-contract

## 읽어야 할 파일

- `/AGENTS.md`
- `/.env.example`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/contexts/auth/adapter/postgres.py`
- `/app/token_payments/runtime/session_transport.py`
- `/app/token_payments/runtime/composition.py`
- `/scripts/test_cookie_session_transport.py`
- `/scripts/test_live_api_runtime_public_contracts.py`

## 작업

Auth/session 저장소와 local env policy를 명확히 한다. 앞으로 `.env.example`은 가능한 한 로컬에서 실제로 동작하는 dev 값을 제공하되, private key, 운영 credential, 상용 RPC key 같은 secret은 커밋하지 않는다는 기준을 고정한다.

1. `scripts/test_auth_storage_env_contract_docs.py`를 추가한다.
   - 문서가 PostgreSQL을 auth user/session/login challenge source of truth로 설명하는지 검증한다.
   - Redis는 optional cache 후보이며 live 필수 구성요소가 아님을 검증한다.
   - `.env.example`이 local dev에서 검증을 통과할 수 있는 session/CSRF signing key 값을 제공하거나, live/prod 거부 placeholder와 dev override 절차를 명확히 문서화하는지 검증한다.
   - 문서와 env fixture가 secret 원문, private key, seed phrase, production credential을 포함하지 않는지 검증한다.
2. `docs/ARCHITECTURE.md`, `docs/DOMAIN_MODEL.md`, `docs/API_SPEC.md`, README/app README를 갱신한다.
   - Auth session refresh reuse detection은 PostgreSQL repository hash/salt/rotation model 기준이라고 명시한다.
   - Redis를 도입하더라도 cache-aside/TTL optimization으로 제한하며 source of truth를 대체하지 않는다고 명시한다.
3. `.env.example`의 local 실행 값 정책을 정리한다.
   - Docker compose와 Postman smoke가 같은 env key를 사용하도록 naming을 유지한다.
   - 실제 운영 secret으로 오해될 값은 쓰지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_auth_storage_env_contract_docs.py scripts/test_cookie_session_transport.py scripts/test_live_api_runtime_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. auth storage/env contract 테스트를 먼저 추가하고 실패를 확인한다.
2. 문서와 `.env.example`을 갱신한 뒤 AC를 실행한다.
3. `/phases/16-architecture-contract-alignment/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Redis를 live 필수 dependency로 만들지 마라.
- `.env.example`에 운영 secret, 실제 private key, seed phrase, 상용 RPC key를 넣지 마라.
- live/prod 환경에서 placeholder key가 통과하도록 완화하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

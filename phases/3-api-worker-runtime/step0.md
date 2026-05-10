# Step 0: runtime-contract-foundation

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/phases/0-foundation/index.json`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/3-api-worker-runtime/index.json`
- `/app/token_payments/__main__.py`
- `/app/token_payments/shared/adapter/__init__.py`
- `/app/token_payments/shared/adapter/kafka/__init__.py`
- `/app/token_payments/shared/adapter/postgres/__init__.py`

## 작업

API/worker runtime phase의 공통 계약을 만든다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_runtime_contract_foundation.py`를 추가해 runtime config, request/response envelope, command dispatch result, composition root contract, dependency boundary를 검증한다.
2. `app/token_payments/runtime/` 패키지를 추가한다. 여기에 env config parser, clock/id generator protocol, runtime container protocol, worker loop option, health status value를 둔다.
3. `app/token_payments/api/` 패키지를 추가한다. 이 step에서는 특정 web framework에 묶이지 않는 순수 request/response DTO와 JSON-safe response helper만 둔다.
4. `app/token_payments/__main__.py`는 runtime command entrypoint를 위임할 수 있는 구조로 바꾸되, 실제 long-running server/worker 시작은 이 step에서 하지 않는다.
5. `.env.example`에 API/worker runtime 설정 키를 민감정보 없이 추가한다: host/port, request timeout, worker batch size, worker poll interval, receipt polling interval.
6. domain/application layer가 runtime/API/adapter 구현을 import하지 않는지 테스트로 고정한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_runtime_contract_foundation.py scripts/test_adapter_infrastructure_public_contracts.py scripts/test_foundation_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. runtime config가 `.env.example`, README, `__main__` entrypoint와 모순되지 않는지 확인한다.
4. `phases/3-api-worker-runtime/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- live HTTP server, Kafka broker, PostgreSQL, blockchain node가 없으면 실패하는 테스트를 기본 AC에 넣지 마라.
- `scripts/execute.py`에 프로젝트 runtime 구현 로직을 넣지 마라.
- domain/application layer에서 API framework, PostgreSQL, Kafka, Blockchain RPC client를 직접 import하지 마라.
- 새 framework dependency를 추가한다면 dependency manifest와 README 검증 명령을 같이 갱신하라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

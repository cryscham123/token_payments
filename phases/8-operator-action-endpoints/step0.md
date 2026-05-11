# Step 0: operator-action-contract-foundation

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
- `/phases/6-order-lifecycle-compensation/index.json`
- `/phases/7-http-framework-adapter/index.json`
- `/app/token_payments/api/operator.py`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/api/__init__.py`
- `/app/token_payments/runtime/observability.py`
- `/scripts/test_operator_http_routes.py`
- `/scripts/test_api_worker_runtime_public_contracts.py`

## 작업

operator cancel/retry/replay action endpoint가 공유할 framework-neutral contract foundation을 추가한다. 동작 변경이므로 먼저 실패하는 테스트를 작성하고, 그 테스트가 통과하는 구현을 작성한다.

1. `scripts/test_operator_action_contracts.py`를 추가한다.
   - operator action 이름은 최소 `cancelOrder`, `retryOutboxMessage`, `replayMessage`를 안정적으로 표현해야 한다.
   - action command는 action name, target kind/id, `OperatorClaims`, request id, idempotency key, reason, requested_at, 추가 parameters를 검증해야 한다.
   - action result는 accepted/duplicate/rejected 계열 상태, target 정보, idempotency key, optional command/message/audit id, human-readable summary를 JSON-safe payload로 변환할 수 있어야 한다.
   - action audit record는 actor, action, target, idempotency key, request id, outcome, reason, recorded_at을 보존해야 한다.
   - action policy는 ADMIN role만 action 실행을 허용하고, read-only observability 권한과 혼동되지 않아야 한다.
2. API package 내부에 operator action contract를 둔다.
   - 기존 `OperatorApi` read-only 계약은 깨뜨리지 않는다.
   - 새 contract는 외부 web framework, Kafka, PostgreSQL client를 직접 import하지 않는다.
   - 필요한 경우 `app/token_payments/api/operator_actions.py`처럼 별도 모듈을 만들고 `token_payments.api`에서 public export한다.
3. public exports를 정리한다.
   - `token_payments.api`에서 새 action contract, policy, status/result 타입을 import할 수 있어야 한다.
   - 기존 `AdminRoleOperatorPolicy`, `OperatorAccessPolicy`, `OperatorApi`, `OperatorClaims` export는 유지한다.
4. phase metadata를 갱신한다.
   - `/phases/8-operator-action-endpoints/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_operator_action_contracts.py scripts/test_operator_http_routes.py scripts/test_api_worker_runtime_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/8-operator-action-endpoints/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- FastAPI, Flask, Django 같은 새 third-party web framework dependency를 추가하지 마라.
- 이 step에서 실제 DB/Kafka/RPC 연결을 만들지 마라.
- 기존 read-only operator dashboard/detail API 응답 shape를 깨뜨리지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 0: e2e-smoke-contract-foundation

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
- `/phases/4-customer-operator-ui/index.json`
- `/app/token_payments/runtime/entrypoint.py`
- `/app/token_payments/runtime/contracts.py`
- `/app/token_payments/contexts/checkout/application/process_manager.py`
- `/app/token_payments/contexts/order/application/service.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/payment/application/handler.py`
- `/app/token_payments/contexts/store_approval/application/service.py`

## 작업

Integration/e2e phase의 기반으로 외부 Docker, PostgreSQL, Kafka, Blockchain RPC 없이 실행 가능한 deterministic smoke contract를 추가한다. 실제 컨테이너 기동은 이 step에서 하지 않는다.

1. 먼저 실패하는 테스트를 추가한다.
   - `scripts/test_e2e_smoke_contract_foundation.py`
   - 테스트는 `token_payments.runtime.smoke` public contract가 존재하고 표준 라이브러리만으로 import 가능함을 검증한다.
2. `app/token_payments/runtime/smoke.py`를 추가한다.
   - `SmokeStep`, `SmokeResult`, `SmokeScenarioResult` 같은 작고 직렬화 가능한 dataclass를 둔다.
   - 각 result는 `to_dict()`를 제공해 CLI JSON details에 안전하게 들어갈 수 있어야 한다.
   - 상태 값은 문자열 enum으로 두고 최소 `"passed"`, `"failed"`, `"skipped"`를 지원한다.
   - scenario 이름은 최소 `"happy-path-checkout"`, `"compensation-checkout"`, `"compose-readiness"`를 예약한다.
   - 이 step에서는 실제 checkout flow를 구현하지 말고 빈 runner/registry와 명확한 unknown scenario error만 추가한다.
3. `dispatch_runtime_command`가 `smoke` command를 받아 smoke registry로 위임할 수 있게 한다.
   - `PYTHONPATH=app python3 -m token_payments smoke`는 사용 가능한 scenario 목록을 bounded JSON으로 반환한다.
   - `PYTHONPATH=app python3 -m token_payments smoke unknown`은 exit code 64와 구조화된 error details를 반환한다.
   - long-running process를 시작하지 않는다.
4. public export가 필요하면 `app/token_payments/runtime/__init__.py`에 최소 범위로 추가한다.
5. phase metadata를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_e2e_smoke_contract_foundation.py
python3 -m pytest scripts/test_runtime_contract_foundation.py scripts/test_api_worker_runtime_public_contracts.py
PYTHONPATH=app python3 -m token_payments smoke
PYTHONPATH=app python3 -m token_payments smoke unknown
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트를 먼저 추가하고 실패를 확인한다.
2. 구현 후 AC 커맨드를 실행한다.
3. `PYTHONPATH=app python3 -m token_payments smoke unknown`은 비정상 exit code가 의도된 동작이므로 구조화된 error가 출력되는지 확인한다.
4. `/phases/5-e2e-integration-readiness/index.json`의 step 0 status를 `completed`로 바꾸고 `summary`에 smoke contract, CLI command, unknown scenario error 계약을 구체적으로 적는다.

## 금지사항

- Docker, PostgreSQL, Kafka, Blockchain RPC를 이 step에서 기동하거나 네트워크 호출하지 마라.
- 실제 happy path 또는 compensation flow 구현을 이 step에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`의 orchestration 책임을 늘리지 마라.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

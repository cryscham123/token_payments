# Step 4: runtime-composition-modularization

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/runtime/api_server.py`
- `/app/token_payments/api/asgi.py`
- `/app/token_payments/contexts/auth/`
- `/app/token_payments/contexts/store_catalog/`
- `/app/token_payments/contexts/inventory/`
- `/app/token_payments/contexts/order/`
- `/app/token_payments/contexts/payment/`
- `/app/token_payments/contexts/checkout/`
- `/scripts/test_live_api_runtime_composition.py`
- `/scripts/test_live_api_facade_wiring.py`
- `/scripts/test_worker_runtime_orchestration.py`
- `/phases/26-security-hardening-architecture-refactoring/index.json`

## 작업

큰 단일 `runtime/composition.py`를 context별 factory/module로 나누고 기존 runtime contract를 유지한다.

1. `scripts/test_runtime_composition_modularization.py`를 추가한다.
   - top-level composition module은 context factory를 조립하는 얇은 composition root여야 한다.
   - auth/store_catalog/inventory/order/payment/checkout/API wiring이 별도 module 또는 factory function으로 분리되어야 한다.
   - public factory 함수와 CLI/server entrypoint contract는 기존 테스트와 호환되어야 한다.
   - dependency graph가 순환 import 없이 import 가능해야 한다.
2. composition package를 추가하거나 분리한다.
   - 권장 구조:

```text
app/token_payments/runtime/composition/
  __init__.py
  auth.py
  store_catalog.py
  inventory.py
  order.py
  payment.py
  checkout.py
  api.py
```

   - 기존 import path 호환이 필요한 경우 얇은 facade를 두되, 새 구현은 context별 module에 둔다.
3. live runtime wiring을 갱신한다.
   - API server, worker runtime, smoke/dry-run plan이 동일한 factory contract를 사용하게 한다.
   - test/dry-run environment에서 외부 network/Kafka/blockchain을 시작하지 않는 기존 경계를 유지한다.
4. docs를 갱신한다.
   - composition root의 책임은 조립이고, context별 구현 로직은 context module/service에 둔다는 규칙을 명시한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_runtime_composition_modularization.py scripts/test_live_api_runtime_composition.py scripts/test_live_api_facade_wiring.py scripts/test_worker_runtime_orchestration.py scripts/test_live_api_server_entrypoint.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. composition modularization 테스트를 먼저 추가하고 실패를 확인한다.
2. runtime composition module 분리와 docs 갱신 뒤 AC를 실행한다.
3. `/phases/26-security-hardening-architecture-refactoring/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- composition 분리 중 context별 구현 로직을 runtime layer로 끌어올리지 마라.
- live Docker/Kafka/blockchain 실행을 automated verification 필수 조건으로 만들지 마라.
- 기존 사용자 변경을 대규모 rename으로 덮어쓰지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

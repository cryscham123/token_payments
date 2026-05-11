# Step 4: operator-action-phase-verification

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
- `/phases/5-e2e-integration-readiness/index.json`
- `/phases/6-order-lifecycle-compensation/index.json`
- `/phases/7-http-framework-adapter/index.json`
- `/phases/8-operator-action-endpoints/index.json`
- `/app/token_payments/api/__init__.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/operator_actions.py`
- `/scripts/test_operator_action_contracts.py`
- `/scripts/test_operator_cancel_order_action.py`
- `/scripts/test_operator_outbox_actions.py`
- `/scripts/test_operator_action_http_routes.py`

## 작업

phase 8 산출물을 public contract, README 문서, phase metadata 관점에서 마감한다. 누락된 동작이 있으면 먼저 실패하는 테스트를 추가하고 구현을 보완한다.

1. `scripts/test_operator_action_public_contracts.py`를 추가한다.
   - `token_payments.api` public exports에서 operator action API/contracts/policy/routes/register helper를 import할 수 있어야 한다.
   - route manifest가 기존 phase 7 route family와 phase 8 action routes를 모두 포함해야 한다.
   - operator action modules가 외부 web framework, Kafka client, PostgreSQL client를 직접 import하지 않아야 한다.
   - 기존 API/runtime/UI/e2e public contract imports가 깨지지 않아야 한다.
2. README와 app README를 갱신한다.
   - operator action endpoint 검증 커맨드를 추가한다.
   - cancel/retry/replay action이 bounded framework-neutral endpoint contract이며 live Docker/Kafka publish를 자동 시작하지 않는다는 점을 명시한다.
   - 다음 phase 후보를 구체적으로 남긴다: ASGI/FastAPI thin adapter, live Docker compose integration, operator action UI wiring 중 적절한 후보.
3. 전체 관련 테스트를 실행한다.
   - phase 8 신규 테스트 전체와 기존 HTTP adapter/runtime/order lifecycle/e2e contract를 함께 검증한다.
4. phase metadata를 마감한다.
   - `/phases/8-operator-action-endpoints/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
   - top-level `/phases/index.json`는 하네스가 phase 완료 시 갱신하므로 수동으로 완료 처리하지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest \
  scripts/test_operator_action_contracts.py \
  scripts/test_operator_cancel_order_action.py \
  scripts/test_operator_outbox_actions.py \
  scripts/test_operator_action_http_routes.py \
  scripts/test_operator_action_public_contracts.py \
  scripts/test_operator_http_routes.py \
  scripts/test_wsgi_runtime_preview.py \
  scripts/test_http_adapter_public_contracts.py \
  scripts/test_api_worker_runtime_public_contracts.py \
  scripts/test_order_lifecycle_public_contracts.py \
  scripts/test_happy_path_checkout_e2e.py \
  scripts/test_compensation_checkout_e2e.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/8-operator-action-endpoints/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- live Docker compose 실행을 이 phase의 필수 검증으로 만들지 마라.
- ASGI/FastAPI adapter 구현을 이 phase에 끼워 넣지 마라.
- `scripts/execute.py`에 프로젝트별 operator action 구현 로직을 넣지 마라.
- Claude 전용 파일이나 명령을 새 실행 경로에 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

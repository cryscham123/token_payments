# Step 5: http-adapter-phase-verification

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
- `/phases/7-http-framework-adapter/index.json`
- `/app/token_payments/api/__init__.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/scripts/test_http_adapter_contract_foundation.py`
- `/scripts/test_auth_order_http_routes.py`
- `/scripts/test_checkout_payment_http_routes.py`
- `/scripts/test_operator_http_routes.py`
- `/scripts/test_wsgi_runtime_preview.py`

## 작업

phase 7 산출물을 public contract, 문서, phase metadata 관점에서 마감한다. 새 동작이 누락된 경우 먼저 실패하는 테스트를 추가하고 구현을 보완한다.

1. `scripts/test_http_adapter_public_contracts.py`를 추가한다.
   - `token_payments.api` public exports에서 HTTP router, route registration, WSGI factory, manifest helper를 import할 수 있어야 한다.
   - route manifest에 auth/order/checkout/payment/operator route가 모두 포함되어야 한다.
   - 기존 API/worker/UI/e2e public contract import가 깨지지 않아야 한다.
2. README와 app README를 갱신한다.
   - phase 7 HTTP adapter 검증 커맨드를 추가한다.
   - CLI `api`/`serve-api`가 bounded preview이며 long-running server가 아님을 명시한다.
   - 다음 phase 후보를 구체적으로 남긴다: real docker compose integration, ASGI/FastAPI thin adapter, operator lifecycle action endpoints 중 적절한 후보.
3. 전체 관련 테스트를 실행한다.
   - HTTP adapter 신규 테스트 전체와 기존 runtime/API/order lifecycle/public contract를 함께 검증한다.
4. phase metadata를 마감한다.
   - `/phases/7-http-framework-adapter/index.json`의 step 5 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
   - top-level `/phases/index.json`는 하네스가 phase 완료 시 갱신하므로 수동으로 완료 처리하지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest \
  scripts/test_http_adapter_contract_foundation.py \
  scripts/test_auth_order_http_routes.py \
  scripts/test_checkout_payment_http_routes.py \
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
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/7-http-framework-adapter/index.json`의 step 5 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 실제 network port를 bind하는 server를 테스트나 CLI 기본 경로에 추가하지 마라.
- live Docker compose 실행을 이 phase의 필수 검증으로 만들지 마라.
- `scripts/execute.py`에 프로젝트별 API 구현 로직을 넣지 마라.
- Claude 전용 파일이나 명령을 새 실행 경로에 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

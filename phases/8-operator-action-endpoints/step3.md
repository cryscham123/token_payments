# Step 3: operator-action-http-routes

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/phases/8-operator-action-endpoints/index.json`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/operator.py`
- `/app/token_payments/api/operator_actions.py`
- `/app/token_payments/api/__init__.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/scripts/test_operator_http_routes.py`
- `/scripts/test_wsgi_runtime_preview.py`
- `/scripts/test_http_adapter_public_contracts.py`

## 작업

operator action contract를 phase 7 HTTP adapter manifest/router/WSGI preview에 연결한다. 동작 변경이므로 먼저 실패하는 테스트를 추가하거나 기존 테스트를 갱신하고 구현한다.

1. `scripts/test_operator_action_http_routes.py`를 추가한다.
   - route manifest에 다음 operation이 안정적으로 포함되어야 한다.
     - `POST /operator/orders/{orderId}/cancel` → `cancelOperatorOrder`
     - `POST /operator/outbox/{messageId}/retry` → `retryOperatorOutboxMessage`
     - `POST /operator/messages/{messageId}/replay` → `replayOperatorMessage`
   - JSON body의 reason/idempotencyKey/kind/parameters가 action command로 전달되어야 한다.
   - `X-User-Id`, `X-User-Role`, `X-User-Scopes`, `X-Request-Id` header가 claims/request id로 보존되어야 한다.
   - forbidden, validation error, rejected result, duplicate result가 안정적인 JSON status/body로 직렬화되어야 한다.
2. `app/token_payments/api/http.py`를 갱신한다.
   - `OPERATOR_ACTION_HTTP_ROUTES`와 `register_operator_action_routes`를 추가한다.
   - `list_http_route_specs`/`http_route_manifest`/`describe_http_routes`에 action routes를 deterministic order로 포함한다.
   - 기존 read-only `register_operator_routes`는 유지한다.
3. runtime preview를 갱신한다.
   - `api`/`serve-api` bounded preview의 routeCount와 routes에 action routes가 포함되어야 한다.
   - long-running server나 network port bind는 계속 시작하지 않는다.
4. public exports를 갱신한다.
   - `token_payments.api`에서 action route specs와 registration helper를 import할 수 있어야 한다.
5. phase metadata를 갱신한다.
   - `/phases/8-operator-action-endpoints/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## Acceptance Criteria

```bash
python3 -m pytest \
  scripts/test_operator_action_http_routes.py \
  scripts/test_operator_outbox_actions.py \
  scripts/test_operator_cancel_order_action.py \
  scripts/test_operator_action_contracts.py \
  scripts/test_operator_http_routes.py \
  scripts/test_wsgi_runtime_preview.py \
  scripts/test_http_adapter_public_contracts.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/8-operator-action-endpoints/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 실제 network port를 bind하는 server를 테스트나 CLI 기본 경로에 추가하지 마라.
- 기존 13개 read-only/API route operation id를 변경하지 마라.
- action routes를 read-only `OperatorApi` query handler에 섞어 넣지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

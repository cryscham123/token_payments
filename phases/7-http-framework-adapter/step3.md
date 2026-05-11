# Step 3: operator-http-routes

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
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/operator.py`
- `/app/token_payments/runtime/observability.py`
- `/scripts/test_operator_observability_api.py`
- `/scripts/test_operator_dashboard_ui.py`
- `/scripts/test_order_lifecycle_public_contracts.py`

## 작업

operator observability facade를 HTTP route로 연결한다. phase 6에서 추가된 order lifecycle/cancellation 상태가 operator route payload에서 누락되지 않도록 읽기 계약을 검증한다.

1. `scripts/test_operator_http_routes.py`를 추가한다.
   - fake `OperatorObservabilityQueryPort`로 dashboard/detail 조회 route를 검증한다.
   - `GET /operator/dashboard`는 query filter(`status`, `context`, `failedOnly`, `retryCandidatesOnly`, `limit`, `pageToken`)를 facade까지 전달해야 한다.
   - `GET /operator/orders/{orderId}`는 order detail route로 연결되어 order lifecycle status/failure reason/latest event를 반환해야 한다.
   - `GET /operator/payments/{paymentId}`는 payment detail route로 연결되어야 한다.
   - `GET /operator/outbox/{messageId}`는 optional `kind` query를 보존해야 한다.
   - `X-User-Role: ADMIN` header가 없으면 facade의 `403`이 그대로 직렬화되어야 한다.
2. operator route registration helper를 추가한다.
   - 예: `register_operator_routes(router, operator_api)`.
   - 기존 `OperatorClaims`/policy contract를 변경하지 않는다.
3. route manifest를 확장한다.
   - operator route도 phase 7 전체 manifest에서 method/path/operation id로 조회 가능해야 한다.
4. phase 6 public contract와 이어지는 observability 항목을 보존한다.
   - cancellation/failure/retry 관련 필드를 adapter가 제거하거나 이름 변경하지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_operator_http_routes.py scripts/test_operator_observability_api.py scripts/test_operator_dashboard_ui.py scripts/test_order_lifecycle_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/7-http-framework-adapter/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step에서 operator UI layout을 재작성하지 마라.
- operator authorization을 adapter에서 우회하지 마라.
- retry action 실행 endpoint를 새로 만들지 마라. 이 phase는 read/submit txHash route까지만 다룬다.
- `step*-output.json`을 추적 대상으로 만들지 마라.

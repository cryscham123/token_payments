# Step 0: operator-action-ui-intents

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/ui/models.py`
- `/app/token_payments/ui/mappers.py`
- `/app/token_payments/ui/__init__.py`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/operator_actions.py`
- `/scripts/test_operator_dashboard_ui.py`
- `/scripts/test_operator_action_contracts.py`
- `/scripts/test_operator_action_http_routes.py`
- `/scripts/test_ui_public_contracts.py`
- `/phases/4-customer-operator-ui/index.json`
- `/phases/8-operator-action-endpoints/index.json`
- `/phases/11-browser-preview-runtime/index.json`

## 작업

운영자 dashboard가 기존 cancel/retry/replay endpoint contract를 UI intent로 표현할 수 있게 framework-neutral view model과 mapper 계약을 추가한다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_operator_action_ui_intents.py`를 추가한다.
   - `OperatorActionIntent` 같은 UI 전용 action intent 모델을 public export로 고정한다.
   - action intent는 최소한 `action_id`, `label`, `kind`, `method`, `endpoint`, `operation_id`, `target_kind`, `target_id`, `reason`, `enabled`, `confirmation`, `idempotency_key`, `body_template`를 가진다.
   - `kind`는 기존 UI 버튼 kind와 맞춰 `primary`, `secondary`, `danger`만 허용한다.
   - `body_template`는 JSON primitive만 담고 `reason`, `idempotencyKey`, `parameters.source="operator-dashboard"`를 포함해야 한다.
   - `cancelOrder` intent는 `POST /operator/orders/{orderId}/cancel`, operation id `cancelOperatorOrder`, deterministic idempotency key를 사용해야 한다.
   - `retryOutboxMessage` intent는 retry candidate outbox row에만 enabled 상태로 만들어지고 `POST /operator/outbox/{messageId}/retry`, operation id `retryOperatorOutboxMessage`, `kind` body field를 포함해야 한다.
   - `replayMessage` intent는 detail 또는 payload의 replay candidate message id가 있을 때 만들어지고 `POST /operator/messages/{messageId}/replay`, operation id `replayOperatorMessage`, `kind` body field를 포함해야 한다.
   - non-actionable row에는 action intent가 없어야 한다.
   - model은 불변 dataclass로 두고, mutable mapping/list를 외부에서 바꿔도 내부 상태가 변하지 않아야 한다.
   - 입력 payload의 HTML/script-like text는 mapper 단계에서 실행 가능한 HTML이 되지 않아야 하며 렌더러에서 escape될 수 있는 plain text로 유지해야 한다.
2. `app/token_payments/ui/models.py`에 action intent 모델을 추가한다.
   - 기존 `CheckoutAction`을 무리하게 재사용하지 말고 운영자 action endpoint contract에 맞는 UI 모델을 별도로 둔다.
   - URL endpoint는 path parameter가 치환된 absolute path여야 하며 외부 origin을 포함하지 않아야 한다.
   - API 호출을 실행하거나 네트워크 요청을 만들지 않는다.
3. `app/token_payments/ui/mappers.py`에서 operator payload/detail을 action intent로 매핑한다.
   - 기존 `operator_dashboard_from_api_payload()` public function signature는 깨지지 않게 유지한다.
   - 필요하면 keyword-only `actions` 또는 payload의 `actions`/`operatorActions` override를 받을 수 있게 하되, 기본은 orders/outbox/detail에서 안전하게 도출한다.
   - cancel action은 주문 row 중 `PENDING`, `AWAITING_SIGNATURE`, `SUBMITTED`, `FAILED`, `EXPIRED`, `CANCELLING` 같은 운영 개입 가능 상태에만 만들고 `APPROVED` 주문에는 만들지 않는다.
   - retry action은 outbox row `retryCandidate=true` 또는 `status=FAILED`에만 만든다.
   - replay action은 detail field `replayMessageId`, `messageId`, `messageKind` 또는 payload `replayMessages`에서 도출한다.
   - endpoint path와 operation id는 기존 `OPERATOR_ACTION_HTTP_ROUTES` 계약과 일치해야 한다.
4. `app/token_payments/ui/__init__.py` public export를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_operator_action_ui_intents.py scripts/test_operator_dashboard_ui.py scripts/test_operator_action_http_routes.py scripts/test_ui_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/12-operator-action-ui-wiring/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 실제 cancel/retry/replay API 요청을 실행하지 마라. 이 step은 UI intent contract만 만든다.
- UI layer에서 PostgreSQL, Kafka, Blockchain RPC, Docker, local `.env`에 접근하지 마라.
- 새 third-party dependency를 추가하지 마라.
- 기존 read-only observability API 또는 operator action endpoint contract를 깨뜨리지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

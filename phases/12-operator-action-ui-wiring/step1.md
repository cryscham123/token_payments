# Step 1: operator-action-controls-rendering

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/ui/models.py`
- `/app/token_payments/ui/mappers.py`
- `/app/token_payments/ui/renderers.py`
- `/app/token_payments/ui/preview.py`
- `/app/token_payments/runtime/browser_preview.py`
- `/scripts/browser_preview_smoke.py`
- `/scripts/test_operator_action_ui_intents.py`
- `/scripts/test_operator_dashboard_ui.py`
- `/scripts/test_browser_preview_smoke.py`
- `/scripts/test_browser_preview_server.py`
- `/phases/12-operator-action-ui-wiring/index.json`

## 작업

Step 0의 operator action intent를 운영자 dashboard HTML과 browser preview fixture에 노출한다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_operator_action_ui_controls.py`를 추가한다.
   - operator dashboard HTML이 cancel/retry/replay action controls를 렌더링하는지 검증한다.
   - control은 button 또는 form-like HTML이어야 하며 `data-action-id`, `data-method`, `data-endpoint`, `data-operation-id`, `data-target-kind`, `data-target-id`, `data-body-template`를 포함해야 한다.
   - `data-body-template`는 HTML attribute로 안전하게 escape된 JSON이어야 하며 `reason`, `idempotencyKey`, `parameters.source`를 포함해야 한다.
   - cancel action은 danger 버튼 스타일, retry/replay는 secondary 또는 primary 버튼 스타일을 써야 한다.
   - `confirmation` 텍스트와 endpoint path는 화면에서 확인 가능해야 한다.
   - action controls는 dashboard detail/action 영역에 모아서 표시하고, 테이블 밀도와 기존 copy affordance를 깨뜨리지 않아야 한다.
   - disabled action은 `disabled`, `aria-disabled="true"`, disabled reason을 포함해야 한다.
   - HTML escaping, secret-like value redaction, banned CSS pattern 회귀를 함께 검증한다.
   - 기존 테스트의 `read-only` 문구는 action endpoint intent가 표시되더라도 live execution이 자동 수행되지 않는다는 의미로 갱신한다.
2. `app/token_payments/ui/renderers.py`를 갱신한다.
   - operator dashboard에 `Operator Actions` 또는 동등한 action 영역을 추가한다.
   - action 영역은 UI guide에 맞춰 8px 이하 radius, 기존 색상 토큰, 안정적인 버튼 크기를 사용한다.
   - action 버튼은 실제 네트워크 요청을 자동 실행하는 JavaScript를 포함하지 않는다.
   - action metadata는 HTML data attributes로 제공해 browser preview에서 endpoint wiring을 확인할 수 있게 한다.
   - `DEFAULT_CSS`에 새 스타일을 추가하되 gradient/orb/glass/one-hue dominant pattern을 피한다.
3. `app/token_payments/ui/preview.py`의 operator fixture에 action 가능한 취소 주문, retry outbox, replay message 예시를 포함한다.
   - approved happy path row는 cancel action이 없어야 한다.
   - failed/expired/cancelling row는 cancel action 또는 retry/replay intent가 명확히 보이게 한다.
   - preview sample에는 operator action endpoint path와 operation id가 포함되어야 한다.
4. browser preview smoke/server 검증이 새 action controls를 확인하도록 필요한 최소 테스트를 갱신한다.
   - `/operator` preview에 `cancelOperatorOrder`, `retryOperatorOutboxMessage`, `replayOperatorMessage`가 보이는지 확인한다.
   - smoke 기본 실행은 여전히 Docker, Kafka, PostgreSQL, Blockchain RPC, local `.env`에 접근하지 않아야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_operator_action_ui_controls.py scripts/test_operator_action_ui_intents.py scripts/test_operator_dashboard_ui.py scripts/test_browser_preview_smoke.py scripts/test_browser_preview_server.py scripts/test_ui_public_contracts.py
PYTHONPATH=app python3 scripts/browser_preview_smoke.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/12-operator-action-ui-wiring/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- preview/render 단계에서 실제 operator action HTTP 요청, DB/Kafka/Docker/Blockchain RPC 호출, local `.env` 읽기를 수행하지 마라.
- 새 JavaScript framework, Playwright, Selenium, Node toolchain, third-party dependency를 추가하지 마라.
- dashboard를 마케팅 랜딩 페이지나 card-heavy hero layout으로 바꾸지 마라.
- 기존 customer checkout UI를 이 step 범위 밖으로 리팩터링하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

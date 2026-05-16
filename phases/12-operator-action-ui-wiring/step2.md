# Step 2: operator-action-ui-public-contracts

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/ui/__init__.py`
- `/app/token_payments/ui/models.py`
- `/app/token_payments/ui/mappers.py`
- `/app/token_payments/ui/renderers.py`
- `/app/token_payments/ui/preview.py`
- `/app/token_payments/runtime/browser_preview.py`
- `/scripts/test_operator_action_ui_intents.py`
- `/scripts/test_operator_action_ui_controls.py`
- `/scripts/test_operator_action_public_contracts.py`
- `/scripts/test_browser_preview_public_contracts.py`
- `/phases/index.json`
- `/phases/12-operator-action-ui-wiring/index.json`

## 작업

operator action UI wiring phase의 공개 계약, 문서, phase metadata를 고정한다. 동작 변경이 있으면 먼저 테스트를 갱신하고, 문서 변경도 테스트로 검증한다.

1. `scripts/test_operator_action_ui_public_contracts.py`를 추가한다.
   - `token_payments.ui` public export에 operator action intent 모델과 renderer/mapping surface가 포함되는지 검증한다.
   - operator dashboard preview가 기존 phase 8 action endpoint route manifest와 operation id를 그대로 노출하는지 검증한다.
   - `/operator` browser preview HTML에 action controls가 포함되지만 자동 실행 JavaScript나 external network origin이 없음을 검증한다.
   - UI source가 PostgreSQL/Kafka/Blockchain/Docker/local `.env` boundary를 import하거나 호출하지 않는지 검증한다.
   - README와 app README가 operator action UI wiring 사용 범위, verification commands, no-live-execution boundary를 문서화하는지 검증한다.
   - `phases/12-operator-action-ui-wiring/index.json` step summary/status와 `phases/index.json` top-level phase 상태가 `validate_phases`와 일관되어야 한다.
2. README와 app README에 `Operator Action UI Wiring` 섹션을 추가한다.
   - cancel/retry/replay control은 기존 framework-neutral operator action endpoint contract에 연결된 UI intent임을 설명한다.
   - browser preview에서 확인할 URL과 smoke command를 적는다.
   - preview/UI는 자동으로 operator action을 실행하지 않고, DB/Kafka/Docker/Blockchain RPC/local `.env`를 열지 않는다고 명시한다.
   - 검증 명령을 정확히 적는다.
3. 필요하면 `scripts/test_ui_public_contracts.py`의 public export와 README 기대값을 갱신한다.
4. phase 완료 시 다음 후보를 README에 갱신한다.
   - ASGI/FastAPI thin adapter
   - approved live Docker e2e
   - operator action execution audit persistence 또는 advanced operator filters

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_operator_action_ui_public_contracts.py scripts/test_operator_action_ui_controls.py scripts/test_operator_action_ui_intents.py scripts/test_operator_action_public_contracts.py scripts/test_browser_preview_public_contracts.py scripts/test_ui_public_contracts.py
PYTHONPATH=app python3 scripts/browser_preview_smoke.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/12-operator-action-ui-wiring/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- `scripts/execute.py`에 프로젝트별 UI wiring 구현 로직을 넣지 마라.
- live operator action execution, DB mutation, Kafka publish/replay, Docker daemon access, Blockchain RPC access를 자동화하지 마라.
- 새 third-party dependency를 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

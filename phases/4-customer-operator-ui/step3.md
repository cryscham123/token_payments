# Step 3: ui-runtime-preview

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
- `/phases/4-customer-operator-ui/index.json`
- Step 0-2에서 생성/수정한 UI 파일
- `/app/token_payments/runtime/entrypoint.py`
- `/app/token_payments/runtime/contracts.py`
- `/app/token_payments/__main__.py`

## 작업

Customer/operator UI를 로컬에서 확인할 수 있는 lightweight preview runtime을 추가한다. 동작 변경이므로 먼저 `scripts/test_ui_runtime_preview.py`를 추가하거나 갱신하고 실패를 확인한 뒤 구현한다.

1. preview 렌더링 entrypoint를 추가한다.
   - `PYTHONPATH=app python3 -m token_payments ui` 또는 기존 runtime command dispatch를 통해 customer/operator preview HTML을 생성할 수 있어야 한다.
   - long-running HTTP server를 시작하지 말고, 현재 runtime command 스타일처럼 bounded JSON 또는 HTML preview 결과를 반환한다.
   - stdout에는 secret/private key/seed phrase가 포함되지 않아야 한다.
2. sample data fixture를 추가한다.
   - customer checkout happy path, tx submitted/pending receipt, payment failed/expired 보상 상태를 표현한다.
   - operator dashboard에는 failed outbox, retry candidate, unhealthy worker, normal approved order가 함께 있어야 한다.
   - sample data는 application/domain 계약을 오염시키지 않도록 UI preview 전용으로 둔다.
3. preview 출력 contract를 고정한다.
   - customer/operator route 또는 view selector를 지원한다.
   - unknown view는 구조화된 error를 반환한다.
   - `ApiResponse`/runtime `CommandResult` 스타일과 충돌하지 않게 문서화한다.
4. README 또는 app README에 preview 명령을 추가한다.
   - 검증 명령과 UI phase 범위를 함께 정리한다.
5. 테스트로 CLI/runtime dispatch, sample data escaping, customer/operator preview 선택을 검증한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_ui_contract_foundation.py scripts/test_customer_checkout_ui.py scripts/test_operator_dashboard_ui.py scripts/test_ui_runtime_preview.py
PYTHONPATH=app python3 -m token_payments ui
PYTHONPATH=app python3 -m token_payments ui customer
PYTHONPATH=app python3 -m token_payments ui operator
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. preview command가 long-running process를 시작하지 않는지 확인한다.
3. README/app README의 명령이 실제 동작과 일치하는지 확인한다.
4. `/phases/4-customer-operator-ui/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 새 HTTP framework, frontend framework, npm build chain을 추가하지 마라.
- preview fixture를 production config나 DB seed로 취급하지 마라.
- 실제 외부 지갑, Kafka, PostgreSQL, Blockchain RPC 연결을 preview command에서 시도하지 마라.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

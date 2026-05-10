# Step 2: operator-dashboard-ui

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
- Step 0-1에서 생성/수정한 UI 파일
- `/app/token_payments/api/operator.py`
- `/app/token_payments/runtime/observability.py`

## 작업

운영자가 주문/결제/outbox/worker/error 상태를 빠르게 스캔하는 dashboard UI를 구현한다. 동작 변경이므로 먼저 `scripts/test_operator_dashboard_ui.py`를 추가하거나 갱신하고 실패를 확인한 뒤 구현한다.

1. operator dashboard renderer와 view model을 추가한다.
   - 주문, 결제, 재고, 가게 승인, outbox, worker health, retry candidate 상태를 한 화면에서 비교할 수 있게 한다.
   - 테이블 행은 44-52px 밀도를 유지하고 id/txHash/message id는 축약 + copy affordance를 표현한다.
   - 금액, 수량, gas 숫자는 우측 정렬한다.
2. filter와 summary surface를 구현한다.
   - context, status, chain id, store, createdAt, failed only 필터를 view model로 표현한다.
   - retry candidate, failed outbox, unhealthy worker count를 status summary로 표시한다.
3. detail panel을 구현한다.
   - aggregate id, latest event, outbox status, processed message/command 기록, error reason을 표시한다.
   - read-only operator UI임을 유지하고 destructive retry 실행은 구현하지 않는다. retry 가능 항목은 표시만 한다.
4. status semantics를 고정한다.
   - `PENDING`, `AWAITING_SIGNATURE`, `SUBMITTED`, `CONFIRMED`, `APPROVED`, `CANCELLED`, `FAILED` 같은 도메인 상태 label을 그대로 노출한다.
   - 색상만으로 상태를 구분하지 않고 항상 텍스트 label을 포함한다.
5. fixture 기반 HTML/semantic 테스트를 추가한다.
   - 필터 rendering, 실패 행, 상세 패널, empty state, HTML escaping, worker health badge를 검증한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_ui_contract_foundation.py scripts/test_customer_checkout_ui.py scripts/test_operator_dashboard_ui.py
python3 -m pytest scripts/test_operator_observability_api.py scripts/test_worker_runtime_orchestration.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. operator dashboard가 `docs/UI_GUIDE.md`의 운영 dashboard 요구사항을 만족하는지 확인한다.
3. Customer checkout UI와 foundation CSS/view model을 과도하게 중복하지 않았는지 확인한다.
4. `/phases/4-customer-operator-ui/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- operator UI에서 데이터 변경/재시도 실행 API를 새로 만들지 마라. 이 step은 read-only 관찰 화면이다.
- 카드 안에 카드를 중첩하지 마라.
- 보라/인디고 단색 계열이나 gradient text를 쓰지 마라.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 3: compensation-smoke-gap-closure

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
- `/phases/5-e2e-integration-readiness/index.json`
- `/phases/6-order-lifecycle-compensation/index.json`
- Step 0-2에서 생성/수정한 order lifecycle 파일
- `/app/token_payments/runtime/smoke.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/scripts/test_happy_path_checkout_e2e.py`
- `/scripts/test_compensation_checkout_e2e.py`
- `/scripts/test_e2e_integration_public_contracts.py`

## 작업

E2E smoke runtime에서 `CancelOrderCommand` handler 미연결 gap을 닫고, happy-path의 수동 order 상태 변경을 Step 1 projector 사용으로 교체한다. 동작 변경이므로 먼저 smoke 테스트를 갱신해 실패를 확인한 뒤 구현한다.

1. `scripts/test_compensation_checkout_e2e.py`를 갱신한다.
   - top-level `cancelOrderHandlerWired`는 `true`여야 한다.
   - failure/expiration/rejection sub-scenario의 `duplicateCommandResults.CancelOrderCommand`는 더 이상 `HANDLER_NOT_WIRED`가 아니어야 한다.
   - 각 sub-scenario에 `finalOrderStatus`가 포함되고 `CANCELLED`가 되어야 한다.
   - duplicate summary에는 cancel command가 멱등 처리되었다는 결과가 포함되어야 한다.
2. `scripts/test_happy_path_checkout_e2e.py`를 갱신한다.
   - smoke details에 order status projector가 `PaymentConfirmedEvent`와 `OrderApprovedEvent`를 처리했다는 증거를 담는다.
   - 최종 상태는 계속 `APPROVED`여야 한다.
3. `app/token_payments/runtime/smoke.py`를 갱신한다.
   - compensation fixture에 order repository, processed message/command repository, order lifecycle handler/projector를 연결한다.
   - release/refund/cancel command 실행 순서가 deterministic하게 details에 남아야 한다.
   - smoke payload는 계속 JSON primitive만 반환해야 한다.
4. CLI smoke 결과 크기와 import boundary를 유지한다.
   - `PYTHONPATH=app python3 -m token_payments smoke compensation-checkout`는 bounded JSON을 출력해야 한다.
   - `compose-readiness` smoke는 Docker를 시작하지 않는 기존 계약을 유지한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_happy_path_checkout_e2e.py scripts/test_compensation_checkout_e2e.py scripts/test_e2e_smoke_contract_foundation.py scripts/test_e2e_integration_public_contracts.py
PYTHONPATH=app python3 -m token_payments smoke happy-path-checkout
PYTHONPATH=app python3 -m token_payments smoke compensation-checkout
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/6-order-lifecycle-compensation/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- `HANDLER_NOT_WIRED` 문자열을 단순히 테스트에서 제거하지 마라. 실제 handler가 smoke flow에서 호출되어야 한다.
- Docker compose, DB, Kafka를 기동하지 마라.
- smoke runtime에 외부 network/client dependency를 추가하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

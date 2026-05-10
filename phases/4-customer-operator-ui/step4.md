# Step 4: ui-phase-verification

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
- Step 0-3에서 생성/수정한 파일

## 작업

Customer/operator UI phase 산출물이 다음 docker compose integration smoke 또는 happy-path e2e checkout phase로 넘어갈 수 있는지 검증하고 정리한다. 동작 변경이 필요하면 먼저 테스트를 추가/갱신하고 실패를 확인한 뒤 구현한다.

1. `scripts/test_ui_public_contracts.py`를 추가해 UI public exports, renderer contract, preview command, import boundary, HTML escaping, UI guide 핵심 금지 패턴을 검증한다.
2. README와 app README에 UI phase 산출물, preview 명령, 검증 명령, 다음 phase 후보를 최신화한다.
3. UI package의 `__all__`, fixture 위치, CSS token, responsive constraints가 안정적인지 정리한다.
4. 기존 API/worker runtime 계약과 UI 계약이 충돌하지 않는지 확인한다.
5. 다음 phase 후보를 integration/e2e 중심으로 정리한다.
   - docker compose integration smoke: `.env.example` 기반 PostgreSQL, Kafka, test network 기동과 runtime health/worker/ui preview 확인.
   - happy-path e2e checkout: 주문 생성부터 재고 예약, 결제 제출/확인, 가게 승인까지 정상 sequence 검증.
   - compensation e2e checkout: 결제 실패/만료/가게 반려의 보상 command 멱등성 검증.
6. 모든 phase metadata와 pre-commit 검증을 통과시킨다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_ui_contract_foundation.py scripts/test_customer_checkout_ui.py scripts/test_operator_dashboard_ui.py scripts/test_ui_runtime_preview.py scripts/test_ui_public_contracts.py
python3 -m pytest scripts/test_api_worker_runtime_public_contracts.py scripts/test_adapter_infrastructure_public_contracts.py scripts/test_checkout_core_public_contracts.py scripts/test_foundation_public_contracts.py
PYTHONPATH=app python3 -m token_payments ui customer
PYTHONPATH=app python3 -m token_payments ui operator
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. 모든 step의 `summary`가 다음 step 판단에 충분히 구체적인지 확인한다.
3. `phases/4-customer-operator-ui/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
4. `phases/index.json`에서 `4-customer-operator-ui`를 `completed`로 갱신한다.

## 금지사항

- docker compose integration smoke나 e2e checkout 구현을 이 step에 크게 추가하지 마라. 검증과 정리 중심으로 마무리한다.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 6: api-worker-runtime-verification

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
- Step 0-5에서 생성/수정한 파일

## 작업

API/worker runtime phase 산출물이 다음 customer/operator UI 또는 end-to-end integration phase로 넘어갈 수 있는지 검증하고 정리한다.

1. `scripts/test_api_worker_runtime_public_contracts.py`를 추가해 auth/order/checkout/payment/operator API exports, worker runtime exports, dependency boundaries, CLI entrypoint contract를 점검한다.
2. README 또는 app README에 API/worker runtime에서 구현된 계약, 실행 가능한 검증 명령, local runtime command를 최신화한다.
3. `.env.example`, docker compose, PostgreSQL schema, runtime config가 서로 모순되지 않는지 정리한다.
4. 누락된 `__all__` export, 불안정한 테스트 fixture, 과도한 cross-layer import가 있으면 보완한다.
5. 다음 phase 후보를 UI/e2e 중심으로 정리한다: customer checkout UI, operator status dashboard, docker compose integration smoke, happy-path e2e checkout.
6. 모든 phase metadata와 pre-commit 검증을 통과시킨다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_runtime_contract_foundation.py scripts/test_auth_api_session_runtime.py scripts/test_order_api_checkout_start.py scripts/test_checkout_tracking_payment_api.py scripts/test_worker_runtime_orchestration.py scripts/test_operator_observability_api.py scripts/test_api_worker_runtime_public_contracts.py scripts/test_adapter_infrastructure_public_contracts.py scripts/test_checkout_core_public_contracts.py scripts/test_foundation_public_contracts.py
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. 모든 step의 `summary`가 다음 step 판단에 충분히 구체적인지 확인한다.
3. `phases/3-api-worker-runtime/index.json`의 step 6 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
4. `phases/index.json`에서 `3-api-worker-runtime`을 `completed`로 갱신한다.

## 금지사항

- customer/operator UI 구현을 이 step에 크게 추가하지 마라. 검증과 정리 중심으로 마무리한다.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

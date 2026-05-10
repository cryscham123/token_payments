# Step 4: e2e-phase-verification

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
- `/phases/5-e2e-integration-readiness/index.json`
- Step 0-3에서 생성/수정한 smoke runtime, tests, docs

## 작업

E2E/integration readiness phase 산출물이 다음 실제 Docker compose integration 또는 HTTP adapter phase로 넘어갈 수 있는지 검증하고 정리한다. 동작 변경이 필요하면 먼저 테스트를 추가/갱신하고 실패를 확인한 뒤 구현한다.

1. `scripts/test_e2e_integration_public_contracts.py`를 추가한다.
   - smoke public exports, CLI dispatch, scenario registry, result serialization, import boundary, README/app README 문서화를 검증한다.
2. smoke runtime의 public API와 `__all__`을 정리한다.
   - app 외부 client dependency를 import하지 않아야 한다.
   - smoke result는 JSON 직렬화 가능한 primitive만 반환해야 한다.
3. README와 app README를 최신화한다.
   - e2e smoke commands
   - compose readiness smoke
   - 실제 Docker compose 수동 smoke 순서
   - 다음 phase 후보
4. 다음 phase 후보를 구체적으로 정리한다.
   - real docker compose integration: 컨테이너 기동, DB schema 적용, Kafka topic publish/consume, bounded runtime smoke 확인.
   - HTTP framework adapter: framework-neutral API facade를 실제 ASGI/WSGI route로 연결.
   - order status projection/handler gap: `CancelOrderCommand`와 order status update handler wiring.
5. 모든 phase metadata와 pre-commit 검증을 통과시킨다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_e2e_smoke_contract_foundation.py scripts/test_happy_path_checkout_e2e.py scripts/test_compensation_checkout_e2e.py scripts/test_compose_readiness_smoke.py scripts/test_e2e_integration_public_contracts.py
python3 -m pytest scripts/test_ui_public_contracts.py scripts/test_api_worker_runtime_public_contracts.py scripts/test_adapter_infrastructure_public_contracts.py scripts/test_checkout_core_public_contracts.py scripts/test_foundation_public_contracts.py
PYTHONPATH=app python3 -m token_payments smoke
PYTHONPATH=app python3 -m token_payments smoke happy-path-checkout
PYTHONPATH=app python3 -m token_payments smoke compensation-checkout
PYTHONPATH=app python3 -m token_payments smoke compose-readiness
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. 모든 step의 `summary`가 다음 step 판단에 충분히 구체적인지 확인한다.
3. `/phases/5-e2e-integration-readiness/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
4. `/phases/index.json`에서 `5-e2e-integration-readiness`를 `completed`로 갱신한다.

## 금지사항

- 실제 Docker compose integration, HTTP server, DB/Kafka client wiring을 이 step에 크게 추가하지 마라. 검증과 정리 중심으로 마무리한다.
- `.env`나 local secret을 읽어 문서 또는 테스트 결과에 남기지 마라.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

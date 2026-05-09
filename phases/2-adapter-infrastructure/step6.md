# Step 6: adapter-infrastructure-verification

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
- Step 0-5에서 생성/수정한 파일

## 작업

adapter infrastructure phase 산출물이 다음 API/UI 또는 end-to-end checkout phase로 넘어갈 수 있는지 검증하고 정리한다.

1. `scripts/test_adapter_infrastructure_public_contracts.py`를 추가해 public exports, dependency boundaries, repository/message adapter 계약을 점검한다.
2. README 또는 app README에 adapter infrastructure phase에서 구현된 PostgreSQL, Outbox Relay, Kafka, Wallet/Blockchain boundary 계약과 실행 가능한 검증 명령을 최신화한다.
3. `.env.example`, docker compose, PostgreSQL schema, dependency manifest가 서로 모순되지 않는지 정리한다.
4. 누락된 `__all__` export, 불안정한 테스트 fixture, 과도한 cross-layer import가 있으면 보완한다.
5. 다음 phase 후보를 API/UI 또는 end-to-end checkout 중심으로 정리한다: auth/order API, checkout tracking API, worker runtime, customer checkout UI, operator status dashboard.
6. 모든 phase metadata와 pre-commit 검증을 통과시킨다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_adapter_contract_foundation.py scripts/test_postgres_outbox_idempotency.py scripts/test_postgres_context_repositories.py scripts/test_outbox_relay_kafka_publisher.py scripts/test_kafka_listener_adapters.py scripts/test_wallet_blockchain_boundaries.py scripts/test_adapter_infrastructure_public_contracts.py scripts/test_checkout_core_public_contracts.py scripts/test_foundation_public_contracts.py
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. 모든 step의 `summary`가 다음 step 판단에 충분히 구체적인지 확인한다.
3. `phases/2-adapter-infrastructure/index.json`의 step 6 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 새 API/UI 구현을 크게 추가하지 마라. 검증과 정리 중심으로 마무리한다.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

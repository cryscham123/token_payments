# Step 2: inventory-listener-runtime-wiring

## 읽어야 할 파일

- `/AGENTS.md`
- `/app/token_payments/contexts/inventory/adapter/kafka.py`
- `/app/token_payments/runtime/workers.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/shared/adapter/messaging.py`
- `/scripts/test_kafka_listener_adapters.py`
- `/scripts/test_worker_runtime_orchestration.py`
- `/scripts/test_messaging_outbox_contracts.py`

## 작업

Inventory Kafka listener와 worker runtime이 `ConfirmInventoryCommand`를 실제로 소비할 수 있게 wiring한다.

1. `scripts/test_inventory_confirm_listener_wiring.py`를 추가한다.
   - inventory listener가 `ConfirmInventoryCommand` payload를 `ConfirmInventoryCommand` DTO로 변환하는지 검증한다.
   - malformed payload는 bounded listener error로 처리되어야 한다.
   - processed command duplicate는 mutation/outbox 없이 idempotent result로 반환되어야 한다.
   - topic resolver가 confirm command/event topic을 제공하는지 검증한다.
2. inventory Kafka adapter를 갱신한다.
   - reserve/release/confirm command dispatch를 모두 지원한다.
3. runtime worker composition을 갱신한다.
   - inventory command listener가 live worker registry에 포함되어야 한다.
   - no-server-start preview contract를 유지한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_inventory_confirm_listener_wiring.py scripts/test_kafka_listener_adapters.py scripts/test_worker_runtime_orchestration.py scripts/test_messaging_outbox_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. listener wiring 테스트를 먼저 추가하고 실패를 확인한다.
2. adapter/runtime/messaging code를 갱신한 뒤 AC를 실행한다.
3. `/phases/19-inventory-saga-finalization/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- worker preview/default command가 실제 Kafka loop를 자동 시작하게 만들지 마라.
- malformed confirm command를 silently ignore하지 마라.
- reserve/release listener behavior를 깨뜨리지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

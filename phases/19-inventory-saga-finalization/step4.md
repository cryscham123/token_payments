# Step 4: inventory-saga-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/docs/API_SPEC.md`
- `/README.md`
- `/app/README.md`
- `/scripts/test_inventory_confirm_command_contract.py`
- `/scripts/test_inventory_saga_confirm_flow.py`
- `/scripts/test_inventory_confirm_listener_wiring.py`
- `/scripts/test_inventory_saga_idempotency_observability.py`
- `/phases/index.json`
- `/phases/19-inventory-saga-finalization/index.json`

## 작업

Inventory saga finalization phase의 public contract를 고정한다.

1. `scripts/test_inventory_saga_public_contracts.py`를 추가한다.
   - docs가 reserve/release/confirm flow를 정확히 설명하는지 검증한다.
   - successful checkout이 inventory confirm을 포함하고, failure/rejection이 release를 포함하는지 검증한다.
   - confirm command가 public HTTP route가 아님을 검증한다.
   - phase metadata가 completed step summary와 top-level phase status를 일관되게 반영하는지 검증한다.
2. docs/README를 최종 정리한다.
3. `/phases/19-inventory-saga-finalization/index.json`와 `/phases/index.json` 상태를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_inventory_saga_public_contracts.py scripts/test_inventory_confirm_command_contract.py scripts/test_inventory_saga_confirm_flow.py scripts/test_inventory_confirm_listener_wiring.py scripts/test_inventory_saga_idempotency_observability.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. public verification 테스트를 먼저 추가하고 실패를 확인한다.
2. docs/metadata를 갱신한 뒤 AC를 실행한다.
3. `/phases/19-inventory-saga-finalization/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
4. `/phases/index.json`에서 `19-inventory-saga-finalization`을 `completed`로 갱신한다.

## 금지사항

- store owner 재고 관리 API를 이 phase에 섞지 마라.
- 수동 주문 승인 기능을 추가하지 마라.
- public customer/operator API route를 confirm command용으로 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

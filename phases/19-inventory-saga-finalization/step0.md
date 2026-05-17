# Step 0: confirm-inventory-command-contract

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/app/token_payments/shared/domain/messaging.py`
- `/app/token_payments/contexts/inventory/domain/model.py`
- `/app/token_payments/contexts/inventory/application/commands.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/inventory/application/ports.py`
- `/scripts/test_inventory_domain_model.py`
- `/scripts/test_inventory_application_contracts.py`
- `/phases/18-siwe-erc1271-auth/index.json`

## 작업

예약된 재고를 최종 판매 확정으로 전환하는 `ConfirmInventoryCommand` contract를 명확히 한다. 현재 `confirm_inventory` application method가 있더라도 shared messaging/handler/public exports와 일관되게 고정한다.

1. `scripts/test_inventory_confirm_command_contract.py`를 추가한다.
   - `ConfirmInventoryCommand`가 `command_id`, `order_id`, `product_id/store_id` 또는 필요한 identity, `requested_at`, `causation_id`, `event_message_id`를 검증하는지 확인한다.
   - `ProductInventory.confirm_reservation(order_id)`가 reserved stock을 줄이고 reservation status를 `CONFIRMED`로 바꾸며 멱등적으로 동작하는지 확인한다.
   - 이미 cancelled reservation confirm은 reject되어야 한다.
   - `InventoryConfirmedEvent` outbox payload가 `eventName`, `orderId`, `productId`, `storeId`, `occurredAt`, `correlationId`, `causationId`를 포함하는지 검증한다.
2. shared messaging enum/topic mapping을 갱신한다.
   - `ConfirmInventoryCommand`
   - `InventoryConfirmedEvent`
3. inventory application handler/export를 정리한다.
   - 기존 reserve/release contract를 깨뜨리지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_inventory_confirm_command_contract.py scripts/test_inventory_domain_model.py scripts/test_inventory_application_contracts.py scripts/test_adapter_contract_foundation.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. confirm command contract 테스트를 먼저 추가하고 실패를 확인한다.
2. shared/domain/application code를 갱신한 뒤 AC를 실행한다.
3. `/phases/19-inventory-saga-finalization/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- confirm을 public HTTP API로 노출하지 마라.
- confirm 실패를 release로 자동 변환하지 마라.
- 이미 cancelled reservation을 confirmed로 되살리지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

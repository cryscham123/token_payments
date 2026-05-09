# Step 1: inventory-application-contracts

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/PRD.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/phases/1-checkout-core/index.json`
- `/app/token_payments/shared/domain/messaging.py`
- `/app/token_payments/contexts/inventory/domain/model.py`
- `/app/token_payments/contexts/inventory/application/__init__.py`
- `/scripts/test_inventory_domain_model.py`

## 작업

재고 command 처리의 application contract와 순수 handler를 만든다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_inventory_application_contracts.py`를 추가해 command handler의 성공, 재고 부족, 중복 command 멱등 처리를 검증한다.
2. `app/token_payments/contexts/inventory/application/ports.py`를 추가해 `InventoryRepository`, `ProcessedCommandRepository`, `OutboxMessageRepository` Protocol을 정의한다.
3. `app/token_payments/contexts/inventory/application/commands.py`를 추가해 `ReserveInventoryCommand`, `ReleaseInventoryCommand`, `ConfirmInventoryCommand` 같은 입력 DTO를 정의한다.
4. `app/token_payments/contexts/inventory/application/handler.py`를 추가해 repository와 outbox port만 사용하는 순수 command handler를 구현한다.
5. handler는 `ProcessedCommandRepository`로 command id 중복을 확인하고, 중복이면 aggregate/outbox를 다시 저장하지 않고 명시적 결과를 반환한다.
6. 성공 시 aggregate 저장과 `OutboxMessage.record_event(...)` 저장을 같은 application method 흐름에서 호출하도록 port 계약을 고정한다.
7. `InventoryReservedEvent`는 checkout process manager가 소비할 수 있도록 `CheckoutEventName.INVENTORY_RESERVED` 이름, `OrderId` correlation/key, event payload를 포함한다.
8. `app/token_payments/contexts/inventory/application/__init__.py`에서 public contract를 export한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_inventory_domain_model.py scripts/test_inventory_application_contracts.py scripts/test_messaging_outbox_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. application layer가 adapter 구현체가 아니라 Protocol/port만 바라보는지 확인한다.
4. `phases/1-checkout-core/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- PostgreSQL/Kafka repository 구현체, Docker 설정, 네트워크 호출을 추가하지 마라.
- `scripts/execute.py`를 수정하지 마라.
- outbox 상태 전이에 phase status 값을 재사용하지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.

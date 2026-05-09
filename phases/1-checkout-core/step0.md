# Step 0: inventory-domain-model

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/PRD.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/phases/0-foundation/index.json`
- `/app/token_payments/shared/domain/ids.py`
- `/app/token_payments/shared/domain/messaging.py`
- `/app/token_payments/contexts/inventory/domain/__init__.py`
- `/scripts/test_shared_domain_kernel.py`
- `/scripts/test_messaging_outbox_contracts.py`

## 작업

재고관리 context의 순수 domain model을 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_inventory_domain_model.py`를 추가해 `ProductInventory`, `InventoryReservation`, `Quantity`, `ReservationStatus`의 핵심 계약을 검증한다.
2. `app/token_payments/contexts/inventory/domain/model.py`를 추가한다.
3. `ProductInventory`는 `ProductId`, `StoreId`, `available_stock`, `reserved_stock`, `total_stock`, `InventoryReservation[]`를 가진 불변 aggregate로 구현한다.
4. `reserve_inventory(order_id, quantity, reservation_id=None)`, `release_reservation(order_id)`, `confirm_reservation(order_id)`, `increase_stock(quantity)`, `decrease_stock(quantity)` 상태 전이를 구현한다.
5. `Quantity`는 음수와 bool을 거부하고 `add`, `subtract` 연산에서 음수 결과를 막는다.
6. 예약은 같은 `OrderId`에 대해 중복 예약을 만들지 않아야 하며, 이미 취소/확정된 예약의 재해제/재확정은 멱등적으로 동작하거나 명확한 예외로 보호되어야 한다.
7. `InventoryReservedEvent`, `InventoryConfirmedEvent`, `InventoryReleasedEvent`, `ReservationExpiredEvent`, `StockIncreasedEvent`, `StockDecreasedEvent`를 domain event로 추가한다.
8. `app/token_payments/contexts/inventory/domain/__init__.py`에서 public contract를 `__all__`로 export한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_inventory_domain_model.py scripts/test_shared_domain_kernel.py scripts/test_messaging_outbox_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. forbidden adapter dependency(`kafka`, `psycopg`, `sqlalchemy`, `web3`, `requests`, `blockchain`, `metamask`)가 inventory domain에 import되지 않았는지 테스트로 검증한다.
4. `phases/1-checkout-core/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- PostgreSQL, Kafka, Redis, Blockchain RPC, MetaMask, web3 의존성을 domain layer에 추가하지 마라.
- application service, repository 구현, adapter 구현은 이 step에서 만들지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

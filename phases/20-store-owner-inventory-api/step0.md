# Step 0: store-owner-inventory-domain-commands

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/contexts/inventory/domain/model.py`
- `/app/token_payments/contexts/inventory/application/commands.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/store_approval/domain/model.py`
- `/scripts/test_inventory_domain_model.py`
- `/scripts/test_inventory_application_contracts.py`
- `/phases/19-inventory-saga-finalization/index.json`

## 작업

가게 주인이 자기 가게 재고를 관리할 수 있는 domain/application command contract를 추가한다. 이 phase는 수동 주문 승인 기능이 아니라 재고 관리 기능만 다룬다.

1. `scripts/test_store_owner_inventory_domain_commands.py`를 추가한다.
   - stock intake/increase command가 total/available stock을 증가시키는지 검증한다.
   - stock correction/decrease command가 reserved stock보다 낮은 total/available 상태를 만들 수 없는지 검증한다.
   - sale pause/resume command가 신규 주문 가능 여부에 쓰일 product availability를 바꾸는지 검증한다.
   - 모든 mutation command는 `command_id`, `store_id`, `product_id`, `actor_user_id`, `reason`, `requested_at`을 요구해야 한다.
   - command result는 accepted/rejected/duplicate status를 구분해야 한다.
2. inventory application command/handler를 추가한다.
   - raw stock set이 아니라 audited business command로 구현한다.
   - existing reserve/release/confirm behavior를 깨뜨리지 않는다.
3. product sale availability가 inventory context와 store approval/order catalog projection 중 어디에 저장되는지 문서화한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_store_owner_inventory_domain_commands.py scripts/test_inventory_domain_model.py scripts/test_inventory_application_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. domain/application command 테스트를 먼저 추가하고 실패를 확인한다.
2. inventory command/handler/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/20-store-owner-inventory-api/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- store owner가 다른 가게 재고를 바꿀 수 있게 하지 마라.
- reserved stock보다 낮은 total/available stock correction을 허용하지 마라.
- 수동 주문 승인/거절 API를 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 2: postgres-context-repositories

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/phases/0-foundation/index.json`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/2-adapter-infrastructure/step0.md`
- `/phases/2-adapter-infrastructure/step1.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/contexts/inventory/domain/model.py`
- `/app/token_payments/contexts/inventory/application/ports.py`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/contexts/payment/application/ports.py`
- `/app/token_payments/contexts/store_approval/domain/model.py`
- `/app/token_payments/contexts/store_approval/application/ports.py`
- `/app/token_payments/shared/adapter/postgres/`

## 작업

inventory, payment, store approval context의 PostgreSQL aggregate repository adapter를 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_postgres_context_repositories.py`를 추가해 repository round-trip과 missing aggregate 조회 계약을 검증한다.
2. `contexts/inventory/adapter/postgres.py`에 `InventoryRepository` port 구현을 추가한다.
3. `contexts/payment/adapter/postgres.py`에 `PaymentRepository`, `PaymentAuthorizationRepository` port 구현을 추가한다.
4. `contexts/store_approval/adapter/postgres.py`에 `StoreRepository`, `OrderDetailRepository` port 구현을 추가한다.
5. row mapper는 domain 객체의 불변성과 value object 검증을 우회하지 않고 public constructor를 사용한다.
6. application handler가 같은 transaction boundary 안에서 aggregate 저장과 outbox 저장을 묶어 쓸 수 있도록 repository constructor와 테스트 fixture를 정리한다.
7. adapter module의 public contract는 각 `adapter/__init__.py`에서 필요한 범위만 export한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_postgres_context_repositories.py scripts/test_postgres_outbox_idempotency.py scripts/test_inventory_application_contracts.py scripts/test_payment_application_contracts.py scripts/test_store_approval_core.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. repository가 domain/application layer에 adapter dependency를 역으로 새기지 않는지 import 테스트로 확인한다.
4. `phases/2-adapter-infrastructure/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- domain model을 DB row 형태에 맞추기 위해 mutable하게 바꾸지 마라.
- Kafka, Blockchain RPC, MetaMask adapter 구현을 이 step에 넣지 마라.
- repository 테스트를 live DB 전용으로 만들지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

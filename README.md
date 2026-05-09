# Token Payments Harness Workspace

이 저장소는 MetaMask 기반 암호화폐 checkout 시스템을 DDD로 설계하고, Codex Harness phase/step으로 구현하기 위한 워크스페이스다.

## 문서

- [PRD](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Domain Model](docs/DOMAIN_MODEL.md)
- [Sequence Flows](docs/SEQUENCES.md)
- [ADR](docs/ADR.md)
- [UI Guide](docs/UI_GUIDE.md)
- [Harness Engineering](docs/HARNESS.md)

## 다이어그램

[다이어그램 이미지(DDD, sequence)](https://viewer.diagrams.net/?tags=%7B%7D&lightbox=1&highlight=0000ff&edit=_blank&layers=1&nav=1&title=DDD.drawio&dark=auto#Uhttps%3A%2F%2Fraw.githubusercontent.com%2Fcryscham123%2Ftoken_payments%2Fmaster%2Fdiagram%2FDDD.drawio)

원본 파일은 `diagram/DDD.drawio`다.

## Harness 실행

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/validate_phases.py
.venv/bin/python -m pytest scripts/test_*.py
python3 .githooks/pre_commit_check.py
python3 scripts/execute.py <phase-dir>
python3 scripts/execute.py <phase-dir> --push
```

## Application Runtime

Token Payments 애플리케이션 코드는 `app/token_payments` 아래에 둔다. 현재 런타임 기준은 Python 3.12이며, bounded context별로 `domain`, `application`, `adapter` 레이어를 추가할 수 있는 최소 패키지 구조만 준비되어 있다.

로컬 환경 변수는 민감정보가 없는 `.env.example`을 복사해 `.env`로 만든 뒤 값은 개발자 로컬에서만 채운다.

```bash
cp .env.example .env
PYTHONPATH=app .venv/bin/python -m token_payments
docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network
```

## Foundation 검증

Foundation phase는 runtime package, shared domain kernel, messaging/outbox contracts, MetaMask auth skeleton, order/checkout process skeleton을 다음 phase에서 import 가능한 public contract로 고정한다.

```bash
.venv/bin/python -m pytest \
  scripts/test_shared_domain_kernel.py \
  scripts/test_messaging_outbox_contracts.py \
  scripts/test_auth_context_skeleton.py \
  scripts/test_order_checkout_skeleton.py \
  scripts/test_foundation_public_contracts.py
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

다음 phase 작업 후보:

- `inventory`: `ProductInventory`, `InventoryReservation`, 재고 예약/확정/해제 command handler와 멱등 처리.
- `payment`: `Payment`, `PaymentAuthorization`, txHash 제출, receipt 확인, `AWAITING_SIGNATURE` 만료 scheduler.
- `store-approval`: 주문 상세 검증, 승인/반려 이벤트, 반려 시 보상 흐름 연결.
- `adapter`: PostgreSQL repository, outbox relay, Kafka publisher/listener, Blockchain RPC/MetaMask boundary 구현.

## Checkout Core 검증

Checkout core phase는 adapter 구현 전에 inventory, payment, store-approval bounded context의 순수 domain/application 계약을 고정한다. 현재 공개 계약은 다음을 포함한다.

- `inventory`: `ProductInventory`, `InventoryReservation`, 재고 예약/확정/해제 command DTO, `InventoryCommandHandler`, repository/outbox/processed-command port.
- `payment`: `Payment`, `PaymentAuthorization`, gas estimate buffer, txHash 제출, receipt 확인, 만료/환불 command DTO, `PaymentCommandHandler`, Blockchain RPC/timeout/transaction port.
- `store-approval`: `Store`, `OrderDetail`, 승인/반려 이벤트, `RequestStoreApprovalCommand`, `StoreApprovalService`, store/order-detail/outbox/processed-command port.

Checkout core 산출물 검증:

```bash
.venv/bin/python -m pytest \
  scripts/test_inventory_domain_model.py \
  scripts/test_inventory_application_contracts.py \
  scripts/test_payment_domain_model.py \
  scripts/test_payment_application_contracts.py \
  scripts/test_store_approval_core.py \
  scripts/test_checkout_core_public_contracts.py \
  scripts/test_foundation_public_contracts.py
.venv/bin/python scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

다음 phase 후보는 adapter 중심으로 진행한다.

- PostgreSQL repository: aggregate, outbox, processed command/message 저장소 구현.
- outbox relay: committed outbox row 조회, publish 상태 전이, 재시도/failure_count 관리.
- Kafka publisher/listener: context 간 이벤트/커맨드 topic, key, correlation/causation header 연결.
- Blockchain RPC/MetaMask boundary: gas estimate, receipt 조회, refund transaction, wallet signature request 경계 구현.

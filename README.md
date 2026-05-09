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

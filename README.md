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
PYTHONPATH=app .venv/bin/python -m token_payments health
PYTHONPATH=app python3 -m token_payments ui
PYTHONPATH=app python3 -m token_payments ui customer
PYTHONPATH=app python3 -m token_payments ui operator
docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network
```

`ui` preview command는 long-running HTTP server를 시작하지 않고 bounded JSON을 반환한다. HTML preview는 runtime `CommandDispatchResult.details.preview` 아래에 들어가며, `ApiResponse` 계약이 아니라 로컬 customer/operator UI phase 확인용 fixture 계약이다.

로컬 Docker smoke는 committed config readiness를 먼저 확인한 뒤 사람이 직접 컨테이너를 기동한다.

```bash
cp .env.example .env
PYTHONPATH=app python3 -m token_payments smoke compose-readiness
docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network
PYTHONPATH=app python3 -m token_payments health
PYTHONPATH=app python3 -m token_payments worker
PYTHONPATH=app python3 -m token_payments ui customer
PYTHONPATH=app python3 -m token_payments ui operator
PYTHONPATH=app python3 -m token_payments smoke happy-path-checkout
PYTHONPATH=app python3 -m token_payments smoke compensation-checkout
docker compose --env-file .env down
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

## Adapter Infrastructure 검증

Adapter infrastructure phase는 checkout core의 port를 실제 인프라 경계로 연결하되 외부 client는 모두 adapter package 내부에서 constructor injection으로 받는다. 현재 공개 계약은 다음을 포함한다.

- `shared.adapter.postgres`: outbox, processed message, processed command repository와 injected PostgreSQL connection protocol.
- `shared.adapter`: outbox relay, JSON message serializer, topic resolver, retry backoff, transaction/session protocol.
- `shared.adapter.kafka`: outbox 기반 publisher, inbound record decoder, consumer loop, malformed payload rejection.
- context Kafka adapters: checkout event listener, inventory/payment/store approval command listener, processed message/command idempotency.
- context PostgreSQL adapters: inventory/payment/store approval aggregate repository.
- wallet/blockchain boundaries: wallet signature recover, gas estimate mapping, transaction receipt mapping, signature request, refund transaction boundary.

Adapter infrastructure 산출물 검증:

```bash
.venv/bin/python -m pytest \
  scripts/test_adapter_contract_foundation.py \
  scripts/test_postgres_outbox_idempotency.py \
  scripts/test_postgres_context_repositories.py \
  scripts/test_outbox_relay_kafka_publisher.py \
  scripts/test_kafka_listener_adapters.py \
  scripts/test_wallet_blockchain_boundaries.py \
  scripts/test_adapter_infrastructure_public_contracts.py \
  scripts/test_checkout_core_public_contracts.py \
  scripts/test_foundation_public_contracts.py
.venv/bin/python scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

다음 phase 후보는 API/UI와 worker runtime 중심으로 정리한다.

- Auth/order API: MetaMask login challenge, session, order creation endpoint.
- Checkout tracking API: checkout process status, pending action, failure reason 조회.
- Worker runtime: outbox relay, Kafka consumer loops, payment receipt polling, timeout scheduler 실행 wiring.
- Customer checkout UI: wallet connect, payment signature request, txHash submission, progress tracking.
- Operator status dashboard: order/payment/outbox status 조회와 retry/failure 관찰 화면.

## API / Worker Runtime 검증

API/worker runtime phase는 다음 UI/e2e phase가 사용할 framework-neutral 계약을 고정한다. 현재 공개 계약은 다음을 포함한다.

- API facades: `AuthApi`, `OrdersApi`, `CheckoutApi`, `PaymentsApi`, `OperatorApi`.
- API DTO: `ApiRequest`, `ApiResponse`, `json_response`.
- Runtime: `RuntimeConfig`, `RuntimeContainer`, `ContractRuntimeContainer`, `dispatch_runtime_command`.
- Workers: `WorkerRuntime`, `OutboxRelayWorker`, `KafkaConsumerWorker`, `PaymentReceiptPollingWorker`, `PaymentTimeoutWorker`.
- Operator observability: read-only dashboard/detail snapshots, retry candidate 표시, worker health snapshot.

Entrypoint는 runtime command 위임만 검증한다. `health`, `worker`, `api` command는 bounded contract를 반환하며 long-running server를 시작하지 않는다.

```bash
.venv/bin/python -m pytest \
  scripts/test_runtime_contract_foundation.py \
  scripts/test_auth_api_session_runtime.py \
  scripts/test_order_api_checkout_start.py \
  scripts/test_checkout_tracking_payment_api.py \
  scripts/test_worker_runtime_orchestration.py \
  scripts/test_operator_observability_api.py \
  scripts/test_api_worker_runtime_public_contracts.py \
  scripts/test_adapter_infrastructure_public_contracts.py \
  scripts/test_checkout_core_public_contracts.py \
  scripts/test_foundation_public_contracts.py
.venv/bin/python scripts/validate_phases.py
PYTHONPATH=app .venv/bin/python -m token_payments health
PYTHONPATH=app .venv/bin/python -m token_payments worker
```

다음 phase 후보는 UI/e2e 중심으로 진행한다.

- customer checkout UI: 지갑 연결, 서명 대기, txHash 제출, checkout tracking 표시.
- operator status dashboard: 주문/결제/outbox/worker/error 상태 테이블과 상세 패널.
- docker compose integration smoke: `.env.example` 기반 PostgreSQL, Kafka, test network 기동과 runtime health 확인.
- happy-path e2e checkout: 주문 생성부터 재고 예약, 결제 제출/확인, 가게 승인까지의 정상 sequence 검증.

## Customer/Operator UI Preview 검증

customer/operator UI phase는 표준 라이브러리 기반 HTML renderer와 local-only preview fixture만 사용한다. preview fixture는 production config, DB seed, 지갑, Kafka, PostgreSQL, Blockchain RPC 연결로 취급하지 않는다.

```bash
python3 -m pytest \
  scripts/test_ui_contract_foundation.py \
  scripts/test_customer_checkout_ui.py \
  scripts/test_operator_dashboard_ui.py \
  scripts/test_ui_runtime_preview.py \
  scripts/test_ui_public_contracts.py
PYTHONPATH=app python3 -m token_payments ui
PYTHONPATH=app python3 -m token_payments ui customer
PYTHONPATH=app python3 -m token_payments ui operator
python3 scripts/validate_phases.py
```

다음 phase 후보는 integration/e2e 중심으로 진행한다.

- docker compose integration smoke: `.env.example` 기반 PostgreSQL, Kafka, test network 기동과 runtime health/worker/ui preview 확인.
- happy-path e2e checkout: 주문 생성부터 재고 예약, 결제 제출/확인, 가게 승인까지 정상 sequence 검증.
- compensation e2e checkout: 결제 실패/만료/가게 반려의 보상 command 멱등성 검증.

## E2E Integration Readiness 검증

E2E readiness phase는 실제 Docker, PostgreSQL, Kafka, Blockchain RPC를 자동으로 기동하지 않고 다음 phase로 넘길 수 있는 public contract와 smoke command를 고정한다. `token_payments.runtime.smoke`는 표준 라이브러리 import boundary를 유지하며 결과 payload는 `CommandDispatchResult.details.smoke` 아래 JSON primitive로 직렬화된다.

```bash
python3 -m pytest \
  scripts/test_e2e_smoke_contract_foundation.py \
  scripts/test_happy_path_checkout_e2e.py \
  scripts/test_compensation_checkout_e2e.py \
  scripts/test_compose_readiness_smoke.py \
  scripts/test_e2e_integration_public_contracts.py
PYTHONPATH=app python3 -m token_payments smoke
PYTHONPATH=app python3 -m token_payments smoke happy-path-checkout
PYTHONPATH=app python3 -m token_payments smoke compensation-checkout
PYTHONPATH=app python3 -m token_payments smoke compose-readiness
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

Manual Docker compose smoke order:

```bash
cp .env.example .env
PYTHONPATH=app python3 -m token_payments smoke compose-readiness
docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network
PYTHONPATH=app python3 -m token_payments health
PYTHONPATH=app python3 -m token_payments worker
PYTHONPATH=app python3 -m token_payments ui customer
PYTHONPATH=app python3 -m token_payments ui operator
PYTHONPATH=app python3 -m token_payments smoke happy-path-checkout
PYTHONPATH=app python3 -m token_payments smoke compensation-checkout
docker compose --env-file .env down
```

다음 phase 후보:

- real docker compose integration: 컨테이너를 실제로 기동하고, DB schema applied by app/postgres/init.d/001-token-payments-schema.sql 상태를 확인하며, Kafka topic publish/consume과 bounded runtime smoke command chain을 검증한다.
- HTTP framework adapter: framework-neutral API facade를 실제 ASGI/WSGI route로 연결하고 auth/order/checkout/payment/operator endpoint contract를 HTTP response로 고정한다.
- order status projection/handler gap: `CancelOrderCommand` 처리와 payment/store approval event 기반 order status update handler wiring을 추가해 compensation smoke의 남은 gap을 닫는다.

## Order Lifecycle Compensation 검증

Order lifecycle compensation phase는 보상 flow의 남은 `CancelOrderCommand` gap을 닫는다. `PaymentConfirmedEvent`와 `OrderApprovedEvent`는 order status projector가 `PAID`/`APPROVED`로 반영하고, `PaymentFailedEvent`, `PaymentExpiredEvent`, `OrderRejectedEvent` 이후의 최종 취소는 order command handler가 처리한다. Compensation smoke의 `cancelOrderHandlerWired=true`는 세 보상 sub-scenario가 실제 cancel handler를 호출하고 최종 order status를 `CANCELLED`까지 갱신한다는 의미다.

```bash
python3 -m pytest \
  scripts/test_order_lifecycle_compensation.py \
  scripts/test_order_status_event_projector.py \
  scripts/test_order_lifecycle_public_contracts.py \
  scripts/test_happy_path_checkout_e2e.py \
  scripts/test_compensation_checkout_e2e.py
PYTHONPATH=app python3 -m token_payments smoke happy-path-checkout
PYTHONPATH=app python3 -m token_payments smoke compensation-checkout
python3 scripts/validate_phases.py
```

다음 phase 후보:

- HTTP framework adapter: framework-neutral API facade를 실제 ASGI/WSGI route로 연결하고 auth/order/checkout/payment/operator endpoint contract를 HTTP response로 고정한다.
- real docker compose integration: 컨테이너를 실제로 기동하고 DB schema 적용, Kafka topic publish/consume, bounded runtime smoke command chain을 검증한다.
- operator order lifecycle observability: cancellation reason, compensation command idempotency, replay 상태를 operator API/UI에서 조회할 수 있게 한다.

## HTTP Framework Adapter 검증

HTTP framework adapter phase는 framework-neutral API facade를 route manifest, router, WSGI callable로 연결한다. `api`와 `serve-api` CLI command는 bounded HTTP adapter preview를 JSON으로 반환하며, 테스트나 기본 실행 경로에서 long-running server 또는 network port bind를 시작하지 않는다.

```bash
python3 -m pytest \
  scripts/test_http_adapter_contract_foundation.py \
  scripts/test_auth_order_http_routes.py \
  scripts/test_checkout_payment_http_routes.py \
  scripts/test_operator_http_routes.py \
  scripts/test_wsgi_runtime_preview.py \
  scripts/test_http_adapter_public_contracts.py \
  scripts/test_api_worker_runtime_public_contracts.py \
  scripts/test_order_lifecycle_public_contracts.py \
  scripts/test_happy_path_checkout_e2e.py \
  scripts/test_compensation_checkout_e2e.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

다음 phase 후보:

- real docker compose integration: committed compose stack을 실제로 기동하고 DB schema, Kafka publish/consume, bounded runtime smoke command chain을 live local infrastructure에서 검증한다.
- ASGI/FastAPI thin adapter: 현재 route manifest와 `build_wsgi_app` 계약을 유지한 채 production framework adapter를 얇게 추가한다.
- operator lifecycle action endpoints: cancel/retry/replay 같은 operator action endpoint를 policy, idempotency, audit trail과 함께 고정한다.

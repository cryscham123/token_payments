# Token Payments Harness Workspace

이 저장소는 MetaMask 기반 암호화폐 checkout 시스템을 DDD로 설계하고, Codex Harness phase/step으로 구현하기 위한 워크스페이스다.

## 문서

- [PRD](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Domain Model](docs/DOMAIN_MODEL.md)
- [Sequence Flows](docs/SEQUENCES.md)
- [API Spec](docs/API_SPEC.md)
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
```

`ui` preview command는 long-running HTTP server를 시작하지 않고 bounded JSON을 반환한다. HTML preview는 runtime `CommandDispatchResult.details.preview` 아래에 들어가며, `ApiResponse` 계약이 아니라 로컬 customer/operator UI phase 확인용 fixture 계약이다.

## Browser Preview Runtime

Browser Preview Runtime은 실제 브라우저 주소창에서 customer/operator preview HTML을 확인하기 위한 local-only preview fixture다. 이 경로는 production server나 external integration smoke가 아니다. It does not connect to DB, Kafka, Docker, Blockchain RPC, or local `.env`.

```bash
PYTHONPATH=app python3 scripts/browser_preview_server.py --host 127.0.0.1 --port 8765
PYTHONPATH=app python3 scripts/browser_preview_smoke.py
```

브라우저에서 다음 URL을 연다.

```text
http://127.0.0.1:8765/customer
http://127.0.0.1:8765/operator
```

서버는 명시적으로 실행한 터미널에서만 localhost port를 bind한다. 확인이 끝나면 같은 터미널에서 `Ctrl-C`로 종료한다.

## Docker Runtime Verification

Docker runtime image 계약은 루트 `Dockerfile`이 Python 3.12 기반으로 `app/token_payments`를 `/workspace/app/token_payments`에 복사하고, live smoke가 컨테이너 안에서도 같은 static contract를 검증할 수 있도록 `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`, `requirements-runtime.txt`, DB init script, test network Dockerfile을 함께 복사한다. 기본 command는 `PYTHONPATH=/workspace/app`에서 bounded `health` command를 실행한다. `docker-compose.yml`은 같은 image를 쓰는 compose one-shot services `token_payments_health`, `token_payments_worker`, `token_payments_smoke`와 local live API service `token_payments_api`를 제공한다.

Docker daemon/socket 권한이 없는 automated harness에서는 live container 실행이 아니라 static/config/smoke contract를 검증한다. Docker daemon 없이 compose 파일 해석만 확인하려면 committed `.env.example`으로 daemon-less compose config validation을 실행한다.

```bash
docker compose --env-file .env.example config --services
docker compose --env-file .env.example --profile runtime config --services
```

Docker runtime smoke는 live Docker/Kafka/PostgreSQL client를 열지 않고 committed 파일과 수동 실행 순서를 JSON contract로 검증한다.

```bash
PYTHONPATH=app python3 -m token_payments smoke docker-runtime-readiness
```

Docker live smoke runner는 automated harness에서 실제 Docker를 시작하지 않는 공개 계약을 제공한다. Automated harness commands는 dry-run 계획과 승인 없는 실행 거부를 모두 검증한다.

```bash
python3 scripts/docker_live_smoke.py --plan
python3 scripts/docker_live_smoke.py --execute
```

`--execute` by itself returns bounded refusal JSON and does not start Docker. 실제 live Docker 실행은 명시 승인/수동 작업으로 분리하며, 로컬 `.env`를 만든 뒤 승인 플래그를 함께 전달할 때만 컨테이너 명령을 실행한다. live 실행 중 실패하더라도 cleanup command is attempted even when a live step fails.

```bash
cp .env.example .env
python3 scripts/docker_live_smoke.py --execute --confirm-live-docker
```

Live local Docker 실행은 수동/승인 필요 작업이다. 필요한 경우 다음 순서로만 실행한다.

```bash
cp .env.example .env
docker compose --env-file .env --profile runtime config --services
docker compose --env-file .env --profile runtime build token_payments_health
docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network
docker compose --env-file .env --profile runtime run --rm token_payments_health
docker compose --env-file .env --profile runtime run --rm token_payments_worker
docker compose --env-file .env --profile smoke run --rm token_payments_smoke
docker compose --env-file .env config --services
docker compose --env-file .env build token_payments_api
docker compose up -d
curl --fail http://localhost:8000/healthz
curl --fail http://localhost:8000/readyz
docker compose down
```

For Postman-local API checks, copy `.env.example` to `.env`; its `COMPOSE_PROFILES=runtime,smoke,api` makes `token_payments_api` part of plain `docker compose up`. The service runs `python -m token_payments serve-api --live --confirm-live-api`. The committed `.env.example` session and CSRF signing values are local dev only; live/prod startup rejects committed local dev signing values, so replace `SESSION_ACTIVE_KEY_ID`, `SESSION_SIGNING_KEYS`, and CSRF/session secret values for any non-local environment. `SESSION_SIGNING_KEYS` supports active/previous key rotation: keep `SESSION_ACTIVE_KEY_ID` on the current active key and retain a previous key only for bounded local rotation verification.

Postman-ready API roadmap:

- `13-fastapi-asgi-adapter`: 기존 framework-neutral route manifest와 facade contract를 유지하면서 ASGI/FastAPI app factory를 얇게 추가한다.
- `14-live-api-runtime-composition`: 먼저 live config/dependency contract를 고정하고, 이후 step에서 실제 facade wiring과 long-running `token_payments_api` runtime entrypoint를 완성한다.
- `15-postman-docker-api-readiness`: `docker compose up -d ... token_payments_api` 후 Postman에서 호출할 collection/examples, seed flow, expected response contract를 고정한다.

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

- `inventory`: `ProductInventory`, `InventoryReservation`, `ReserveInventoryCommand`, `ConfirmInventoryCommand`, `ReleaseInventoryCommand`, `InventoryConfirmedEvent`, 재고 예약/확정/해제 command handler와 멱등 처리.
- `payment`: `Payment`, `PaymentAuthorization`, txHash 제출, receipt 확인, `AWAITING_SIGNATURE` 만료 scheduler.
- `store-approval`: 주문 상세 검증, 승인/반려 이벤트, 반려 시 보상 흐름 연결.
- `adapter`: PostgreSQL repository, outbox relay, Kafka publisher/listener, Blockchain RPC/MetaMask boundary 구현.

## Checkout Core 검증

Checkout core phase는 adapter 구현 전에 inventory, payment, store-approval bounded context의 순수 domain/application 계약을 고정한다. 현재 공개 계약은 다음을 포함한다.

- `inventory`: `ProductInventory`, `InventoryReservation`, `ReserveInventoryCommand`, `ConfirmInventoryCommand`, `ReleaseInventoryCommand`, `InventoryConfirmedEvent`, 재고 예약/확정/해제 command DTO, `InventoryCommandHandler`, repository/outbox/processed-command port.
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

FastAPI thin adapter는 optional production adapter다. `token_payments.api`와 `token_payments.api.fastapi` import는 FastAPI 설치를 요구하지 않으며, 실제 FastAPI app을 만들 때만 runtime 환경에 `pip install fastapi`가 필요하다. Automated harness 검증에서는 package install, ASGI server 실행, network port bind를 수행하지 않는다.

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

## Operator Action Endpoints 검증

Operator action endpoints phase는 `cancel/retry/replay operator actions`를 bounded framework-neutral endpoint contract로 고정한다. `cancelOrder`, `retryOutboxMessage`, `replayMessage`는 public `ApiRequest`/`ApiResponse`, route manifest, register helper, ADMIN-only policy, idempotency, audit payload를 검증하지만 live Docker/Kafka publish is not started automatically.

```bash
python3 -m pytest \
  scripts/test_operator_action_contracts.py \
  scripts/test_operator_cancel_order_action.py \
  scripts/test_operator_outbox_actions.py \
  scripts/test_operator_action_http_routes.py \
  scripts/test_operator_action_public_contracts.py \
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

- ASGI/FastAPI thin adapter: 현재 framework-neutral route manifest와 `build_wsgi_app` 계약을 유지하면서 production framework layer를 얇게 추가한다.
- live Docker compose integration: committed compose stack을 기동해 DB schema, Kafka publish/consume, bounded runtime smoke command chain을 live local infrastructure에서 검증한다.
- operator action UI wiring: 운영 dashboard에서 cancel/retry/replay action 버튼과 결과/audit 상태를 기존 action endpoint contract에 연결한다.

## Operator Action UI Wiring

The operator action UI wiring phase exposes cancel/retry/replay controls as UI intents connected to the existing framework-neutral operator action endpoint contract. The cancel/retry/replay controls are UI intents, and they render endpoint metadata, operation ids, target ids, idempotency keys, confirmations, and body templates for operator review; they do not call action APIs from the preview.

Use the browser preview to inspect the operator dashboard action controls:

```bash
PYTHONPATH=app python3 scripts/browser_preview_server.py --host 127.0.0.1 --port 8765
PYTHONPATH=app python3 scripts/browser_preview_smoke.py
```

Open the operator preview at:

```text
http://127.0.0.1:8765/operator
```

This is a no live operator action execution boundary. The preview/UI does not open DB, Kafka, Docker, Blockchain RPC, or local `.env`, and it does not publish, replay, mutate orders, or start live infrastructure.

Verification commands:

```bash
python3 -m pytest scripts/test_operator_action_ui_public_contracts.py scripts/test_operator_action_ui_controls.py scripts/test_operator_action_ui_intents.py scripts/test_operator_action_public_contracts.py scripts/test_browser_preview_public_contracts.py scripts/test_ui_public_contracts.py
PYTHONPATH=app python3 scripts/browser_preview_smoke.py
python3 scripts/validate_phases.py
```

Next phase candidates:

- ASGI/FastAPI thin adapter: add a production framework adapter while preserving the current route manifest and UI intent endpoint metadata.
- live API runtime composition: wire the real facades to PostgreSQL, Kafka, and test network adapters behind a long-running API entrypoint.
- Postman Docker API readiness: add the compose API service, request examples, seed flow, and expected responses for local Postman verification.

## ASGI/FastAPI Thin Adapter

The ASGI/FastAPI Thin Adapter keeps the existing route manifest and facade contract as the source of truth. `build_asgi_app` adapts the framework-neutral `HttpRouter` with only the standard library, while `build_fastapi_app` is optional FastAPI dependency production wiring. Importing `token_payments.api` and running the preview commands does not require FastAPI; the FastAPI app is built only when an explicit runtime has installed `fastapi` and calls the factory. The live API runtime composition remains the next layer that supplies real PostgreSQL, Kafka, and test network drivers. FastAPI optional dependency live smoke stays manual and outside the default no-server-start boundary.

### Live API Request Guard

The live API adapter uses a framework-neutral request guard before facade dispatch. `POST /auth/challenges`, `POST /auth/sessions`, and `POST /auth/sessions/refresh` issue a signed `csrfToken` response field and a `csrf_token` cookie. Browser clients using the HttpOnly session cookies must echo that value in `X-CSRF-Token` for mutating requests; `GET`, `HEAD`, and preflight `OPTIONS` do not require CSRF.

Credentialed CORS is allowlist-based through `CORS_ALLOWED_ORIGINS`, with `CORS_ALLOW_CREDENTIALS=true`; wildcard origins are not valid with credentials. Preflight requests are answered by the guard before route business logic. `REQUEST_BODY_MAX_BYTES` bounds request bodies and returns `413 REQUEST_BODY_TOO_LARGE` before JSON decoding, while malformed JSON remains `400 MALFORMED_JSON`.

### Postman Cookie Auth Flow

Phase 15 adds `postman/token-payments.local.postman_collection.json`, `postman/token-payments.local.postman_environment.json`, and `postman/token-payments.cookie-auth.expected.json` for local cookie auth verification. Run the auth requests in collection order: request a login challenge, sign the returned `signingMessage` in MetaMask, login with the signature, refresh the session, logout, then call `GET /auth/me`. Postman should rely on its cookie jar for `access_token`, `refresh_token`, and `csrf_token`; do not add manual `Cookie` headers to the happy path. Mutating cookie-auth requests send the latest `csrfToken` as `X-CSRF-Token`.

Auth login uses a SIWE v1 message for both EOA wallets and deployed ERC-1271 smart wallet contracts. The live verifier checks deployed smart wallets with `isValidSignature(bytes32,bytes)` on the configured auth chain RPC, while browser session transport stays cookie-first through HttpOnly cookies plus CSRF double-submit. Unsupported ERC-6492/counterfactual accounts are future scope; linked wallets are not implemented and do not add routes in this phase. `ADAPTER_AUTH_WALLET_SIGNATURE_TIMEOUT_SECONDS` bounds ERC-1271 RPC calls, `ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID` mismatch rejects before signature recovery or contract lookup, and `walletSignature.rpcUrl is redacted in runtime/debug output`.

Default PostgreSQL bootstrap uses `app/postgres/init.d/002-token-payments-default-seed.sh`. New postgres volumes run it after schema creation, and `docker compose up` also runs the idempotent `postgres_seed` one-shot service after postgres is healthy. It inserts only the RBAC role/permission catalog plus the local platform admin identity and memberships needed to authenticate as an admin. `BOOTSTRAP_ADMIN_WALLET_ADDRESS` can be set in `.env`; when it is empty the script defaults to `TEST_NETWORK_ACCOUNT`. User and group UUIDs are generated in PostgreSQL and then reused by lookup on later runs.

The manual seed and expected response contracts live in `postman/fixtures/token-payments.local.seed-plan.json` and `postman/expected/token-payments.api.expected.json`. The seed plan remains explicit fixture metadata for local Postman examples and uses committed schema table/column names. The expected response fixture records route-level status/body/header examples for auth, checkout, payment, compensation, and operator recovery while redacting signed tokens and cookie values.

Postman Docker API readiness/security smoke is a bounded dry-run contract for the live API service. The default automated path prints the plan and verifies the refusal boundary only; it does not start Docker, bind the API server, or open network clients.

```bash
python3 scripts/docker_live_smoke.py --api-readiness --plan
python3 scripts/docker_live_smoke.py --api-readiness --execute
```

`--execute` without `--confirm-live-docker` returns bounded refusal JSON. A confirmed manual run is local-only and should follow the documented service setup with a copied `.env`; local dev signing values are accepted only for `RUNTIME_ENVIRONMENT=local`. The plan order covers API service start, session signing key validation, `/healthz`, `/readyz`, cookie auth, invalid/expired signature rejection, CSRF failure/success, credentialed CORS preflight, oversized body, malformed JSON, idempotency duplicate, checkout happy path, and operator action smoke. Smoke output redacts session signing keys, signed tokens, cookie headers, and CSRF values.

```bash
cp .env.example .env
python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker
```

Final local backend order for Postman Docker API readiness:

```bash
cp .env.example .env
docker compose --env-file .env config --services
docker compose --env-file .env build token_payments_api
docker compose up -d
# Default DB bootstrap runs idempotently through postgres_seed after postgres is healthy.
# Optionally apply/review the manual Postman fixture plan in postman/fixtures/token-payments.local.seed-plan.json
# Import postman/token-payments.local.postman_collection.json and postman/token-payments.local.postman_environment.json
python3 scripts/docker_live_smoke.py --api-readiness --plan
python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker
docker compose down
```

`api` and `serve-api` return bounded JSON previews with `wsgiFactory`, `asgiFactory`, `fastapiFactory`, `fastapiAvailable`, `longRunning=false`, and `serverStarted=false`. The harness path does not start a server, does not bind a network port, and does not open DB, Kafka, Docker, Blockchain RPC, or local `.env`; this is the no-server-start boundary.

Verification commands:

```bash
python3 -m pytest scripts/test_api_seed_expected_responses.py scripts/test_postman_cookie_auth_flow.py scripts/test_happy_path_checkout_e2e.py scripts/test_compensation_checkout_e2e.py
python3 -m pytest scripts/test_postman_cookie_auth_flow.py scripts/test_cookie_session_transport.py scripts/test_csrf_cors_request_guard.py
python3 -m pytest scripts/test_fastapi_asgi_public_contracts.py scripts/test_fastapi_thin_adapter.py scripts/test_asgi_adapter_contract_foundation.py scripts/test_wsgi_runtime_preview.py scripts/test_api_worker_runtime_public_contracts.py scripts/test_browser_preview_public_contracts.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

manual production serve example after explicit dependency installation and real route composition:

```python
# production_api.py
from token_payments.api import HttpRouter, build_fastapi_app

router = HttpRouter()
# register_auth_routes/router facade wiring belongs in explicit production composition.
app = build_fastapi_app(router)
```

```bash
python3 -m pip install fastapi uvicorn
PYTHONPATH=app uvicorn production_api:app --host 0.0.0.0 --port 8000
```

Next phase order:

- Docker compose live server
- SIWE/ERC-1271 auth
- inventory saga finalization
- store owner inventory API

## Live API Runtime Composition Contract

Step 0 of live API runtime composition fixes the public contract for `LiveRuntimeConfig`, `LiveRuntimeDependencies`, `LiveApiComposition`, and `describe_live_runtime_dependencies`. The contract parses API and adapter environment keys, reports the externally injected PostgreSQL session factory, Kafka producer, wallet signature client, blockchain client, clock, and id generator, and returns redacted JSON-safe metadata for readiness tooling.

The explicit live server entrypoint is `PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run` for the bounded plan and `PYTHONPATH=app python3 -m token_payments serve-api --live --confirm-live-api` for an approved live start. `api` and `serve-api` without `--live` still return the no-server-start preview. `--live` without `--confirm-live-api` returns bounded refusal JSON, and dry-run/refusal paths do not bind a port, read local `.env`, or require FastAPI/Uvicorn.

The live server adds system-only `/healthz` and `/readyz` routes outside the public route manifest. `/healthz` is process-only, `/readyz` uses injected readiness probes, structured access log events are redacted, and mutating commands accept the standard `Idempotency-Key` header while preserving existing body-based command ids.

## Architecture Contract Alignment

Checkout Process is a separate saga/process context, not an order context submodule. `CheckoutProcessManager` lives under `contexts/checkout` and is limited to orchestration, compensation command decision, and idempotent saga decision; order context owns order creation, status projection, and checkout tracking.

`order.Store` and `store_approval.Store` are not the same aggregate. The order model is a catalog/order projection, while the store approval model is an approval verification projection and must not share persistence or DTOs by default.

PostgreSQL is the source of truth for auth users, login challenges, and sessions. Refresh reuse detection uses the PostgreSQL session repository hash/salt/rotation model. Redis is optional cache-aside/TTL optimization, not a live required dependency. Local runs must copy `.env.example` to `.env`; live/prod startup rejects committed local dev signing values, so replace session and CSRF signing material for non-local environments.

Public HTTP route surface stays bound to the current 33-route manifest, including admin store catalog provisioning, merchant member/invitation APIs, and the store owner inventory API. Initial `ADMIN` bootstrap is local/manual seed only, implemented as a local DB init seed controlled by `.env` `BOOTSTRAP_ADMIN_WALLET_ADDRESS`; public customer login never grants a global `STORE_OWNER` role. Store management authorization uses merchant group membership and permission scopes, not a global STORE_OWNER account role, so an existing customer wallet is reused as the same `auth_users.user_id` and checkout history is preserved. Store wallet and supported chains live on the store profile. Product registration is allowed for scoped merchant membership or explicit platform permission and writes canonical `store_catalog_products` plus checkout, inventory, and store approval projections together. Product description/category/search metadata is future scope. Stock intake, target stock correction, sale pause, and sale resume are audited, idempotent inventory commands. `approveOrder`/`request_store_approval` are Kafka/message listener inputs, and store owner manual order approval HTTP API is not in current scope. manual order approval HTTP API is not an active roadmap item. UI implementation remains a separate phase. ERC-20/USDC/USDT payment support is not an immediate roadmap phase.

Next phase order:

- Docker compose live server
- SIWE/ERC-1271 auth
- inventory saga finalization
- store owner inventory API

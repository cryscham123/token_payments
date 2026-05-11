# Token Payments Application

`app/token_payments` is the Python 3.12 application root. Existing sibling directories under `app/` provide local infrastructure for PostgreSQL, Kafka, and the test blockchain network.

## Runtime Commands

```bash
PYTHONPATH=app .venv/bin/python -m token_payments
PYTHONPATH=app .venv/bin/python -m token_payments health
PYTHONPATH=app .venv/bin/python -m token_payments worker
PYTHONPATH=app .venv/bin/python -m token_payments api
PYTHONPATH=app python3 -m token_payments ui
PYTHONPATH=app python3 -m token_payments ui customer
PYTHONPATH=app python3 -m token_payments ui operator
docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network
```

Use `.env.example` as the template for local `.env` values. The local blockchain RPC points at `test_network` on chain id `1337`. Do not commit real private keys, API keys, seed phrases, or production credentials.

Local Docker smoke order:

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

## Verification Commands

```bash
.venv/bin/python scripts/validate_phases.py
.venv/bin/python -m pytest scripts/test_*.py
python3 .githooks/pre_commit_check.py
```

Adapter infrastructure specific verification:

```bash
.venv/bin/python -m pytest \
  scripts/test_adapter_contract_foundation.py \
  scripts/test_postgres_outbox_idempotency.py \
  scripts/test_postgres_context_repositories.py \
  scripts/test_outbox_relay_kafka_publisher.py \
  scripts/test_kafka_listener_adapters.py \
  scripts/test_wallet_blockchain_boundaries.py \
  scripts/test_adapter_infrastructure_public_contracts.py
```

API/worker runtime contract verification:

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

customer/operator UI phase preview verification:

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

The `ui` runtime command returns bounded JSON and does not start an HTTP server. Rendered HTML lives under `CommandDispatchResult.details.preview`; this is a local preview contract, not an `ApiResponse`, DB seed, or production runtime configuration.

Next phase candidates:

- docker compose integration smoke: PostgreSQL, Kafka, test network, runtime health, worker, and UI preview from `.env.example`.
- happy-path e2e checkout: order creation through inventory reservation, payment confirmation, and store approval.
- compensation e2e checkout: payment failure, payment expiration, and store rejection compensation command idempotency.

## E2E Integration Readiness

The final readiness phase keeps smoke runtime execution deterministic and local-only. It verifies public exports, CLI dispatch, scenario registry, JSON result serialization, import boundaries, README coverage, and phase metadata without starting Docker or reading local `.env` secrets.

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

Next phase candidates:

- real docker compose integration: start the committed compose stack, verify DB schema applied by app/postgres/init.d/001-token-payments-schema.sql, exercise Kafka topic publish/consume, and confirm the bounded runtime smoke command chain against live local infrastructure.
- HTTP framework adapter: wire the framework-neutral API facade to real ASGI/WSGI route handlers while preserving the existing `ApiRequest`/`ApiResponse` contracts.
- order status projection/handler gap: wire `CancelOrderCommand` and the order status update handler for payment/store approval events so compensation flows update order state end to end.

## Order Lifecycle Compensation

Order lifecycle compensation closes the remaining compensation gap. `PaymentConfirmedEvent` and `OrderApprovedEvent` are projected into order `PAID`/`APPROVED` state, while payment failure, payment expiration, and store rejection drive `CancelOrderCommand` through the order command handler. In smoke output, `cancelOrderHandlerWired=true` means every compensation sub-scenario reached final order status `CANCELLED` through the real handler path.

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

Next phase candidates:

- HTTP framework adapter: wire the framework-neutral API facade to ASGI/WSGI route handlers.
- real docker compose integration: start local containers and verify schema, Kafka publish/consume, and bounded smoke commands against live infrastructure.
- operator order lifecycle observability: expose cancellation reason, compensation idempotency, and replay state in operator views.

## API / Worker Runtime Contracts

The API layer exposes framework-neutral facades: `AuthApi`, `OrdersApi`, `CheckoutApi`, `PaymentsApi`, and `OperatorApi`. They accept `ApiRequest` and return `ApiResponse` so a later HTTP framework can adapt them without changing the application contracts.

The runtime layer exposes `RuntimeConfig`, `RuntimeContainer`, `ContractRuntimeContainer`, `dispatch_runtime_command`, and `WorkerRuntime`. Worker exports cover outbox relay, Kafka consumer, payment receipt polling, and payment timeout batches. Current CLI commands return bounded JSON results and do not start a long-running API server or daemon worker in this phase.

Previous API/worker runtime phase candidates now covered by the UI phase:

- customer checkout UI: wallet connect, signature wait, txHash submission, and checkout tracking.
- operator status dashboard: order/payment/outbox/worker/error status table and detail panel.

## Package Layout

```text
app/token_payments/
  api/
  runtime/
  contexts/
    auth/
      domain/
      application/
      adapter/
    order/
      domain/
      application/
      adapter/
    checkout/
      domain/
      application/
      adapter/
    inventory/
      domain/
      application/
      adapter/
    payment/
      domain/
      application/
      adapter/
    store_approval/
      domain/
      application/
      adapter/
```

Domain code must stay free of PostgreSQL, Kafka, Blockchain RPC, and MetaMask client dependencies. Application services should depend on ports, and adapters should own external integrations.

## Adapter Boundaries

- PostgreSQL adapters use injected connection objects and live under context `adapter/postgres.py` files plus `shared/adapter/postgres`.
- Kafka adapters use injected producer/consumer objects and live under `shared/adapter/kafka` plus context `adapter/kafka.py` files.
- Wallet and blockchain adapters use injected clients under `contexts/auth/adapter/wallet_signature.py`, `contexts/payment/adapter/blockchain.py`, and `contexts/payment/adapter/transaction_service.py`.
- `.env.example` contains only local placeholder keys for adapter wiring. Real private keys, seed phrases, API keys, and production RPC URLs stay out of committed files.

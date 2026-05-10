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

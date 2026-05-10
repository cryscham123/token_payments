# Token Payments Application

`app/token_payments` is the Python 3.12 application root. Existing sibling directories under `app/` provide local infrastructure for PostgreSQL, Kafka, and the test blockchain network.

## Runtime Commands

```bash
PYTHONPATH=app .venv/bin/python -m token_payments
docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network
```

Use `.env.example` as the template for local `.env` values. Do not commit real private keys, API keys, seed phrases, or production credentials.

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

## Package Layout

```text
app/token_payments/
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

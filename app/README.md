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

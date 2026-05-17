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
```

Use `.env.example` as the template for local `.env` values. The local blockchain RPC points at `test_network` on chain id `1337`. Do not commit real private keys, API keys, seed phrases, or production credentials.

## Browser Preview Runtime

Browser Preview Runtime is a local-only preview fixture for opening the customer and operator UI previews in a real browser. It is not a production server or external integration smoke path, and it does not connect to DB, Kafka, Docker, Blockchain RPC, or local `.env`.

```bash
PYTHONPATH=app python3 scripts/browser_preview_server.py --host 127.0.0.1 --port 8765
PYTHONPATH=app python3 scripts/browser_preview_smoke.py
```

Open these URLs in the browser:

```text
http://127.0.0.1:8765/customer
http://127.0.0.1:8765/operator
```

The server binds a localhost port only when this explicit script is running. Stop it with `Ctrl-C` in the same terminal.

## Docker Runtime Verification

Docker runtime image verification fixes the root `Dockerfile` contract: Python 3.12, `/workspace`, `PYTHONPATH=/workspace/app`, copied `app/token_payments`, committed static smoke contract files, and a bounded `health` command. The compose one-shot services `token_payments_health`, `token_payments_worker`, and `token_payments_smoke` reuse that image for local runtime checks.

Automated harness verification does not require Docker daemon/socket access. It checks static/config/smoke contract coverage, including daemon-less compose config validation, committed runtime service definitions, and the `docker-runtime-readiness` smoke payload instead of starting live containers.

```bash
docker compose --env-file .env.example config --services
docker compose --env-file .env.example --profile runtime config --services
docker compose --env-file .env.example --profile api config --services
PYTHONPATH=app python3 -m token_payments smoke docker-runtime-readiness
```

Docker live smoke runner gives the automated harness a bounded public contract for the approved live sequence without opening Docker by default. Automated harness commands verify the dry-run plan and the refusal path.

```bash
python3 scripts/docker_live_smoke.py --plan
python3 scripts/docker_live_smoke.py --execute
```

`--execute` by itself returns bounded refusal JSON and does not start Docker. Real live Docker execution is manual/approval-only: create the local env file, then pass the explicit live confirmation flag. The cleanup command is attempted even when a live step fails.

```bash
cp .env.example .env
python3 scripts/docker_live_smoke.py --execute --confirm-live-docker
```

Live local Docker execution is manual/approval-only. Run it in this order when Docker daemon access is explicitly available.

```bash
cp .env.example .env
docker compose --env-file .env --profile runtime config --services
docker compose --env-file .env --profile runtime build token_payments_health
docker compose --env-file .env up -d postgres kafka kafka-ui pgweb test_network
docker compose --env-file .env --profile runtime run --rm token_payments_health
docker compose --env-file .env --profile runtime run --rm token_payments_worker
docker compose --env-file .env --profile smoke run --rm token_payments_smoke
docker compose --env-file .env --profile api config --services
docker compose --env-file .env --profile api build token_payments_api
docker compose --env-file .env --profile api up -d token_payments_api
curl --fail http://localhost:8000/healthz
curl --fail http://localhost:8000/readyz
docker compose --env-file .env down
```

The Postman-local API service is `token_payments_api` under the explicit `api` profile. It uses the root runtime image and the confirmed live command `python -m token_payments serve-api --live --confirm-live-api`. The committed `.env.example` session signing key is deliberately invalid for live/prod startup; copy it to `.env` and replace the session and CSRF signing values with local-only secrets before starting this service. `SESSION_SIGNING_KEYS` supports active/previous key rotation: keep `SESSION_ACTIVE_KEY_ID` on the current active key and keep a previous key only for bounded local rotation verification.

Postman-ready API roadmap:

- `13-fastapi-asgi-adapter`: add a thin ASGI/FastAPI app factory while preserving the current framework-neutral API route manifest.
- `14-live-api-runtime-composition`: first freeze the live config/dependency contract, then complete real facade wiring and the long-running API entrypoint in later steps.
- `15-postman-docker-api-readiness`: add the compose API service, Postman-ready request examples, seed flow, and expected response contracts.

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

## HTTP Framework Adapter

The HTTP adapter phase exposes the framework-neutral facades through stable route specs, registration helpers, a deterministic route manifest, and a WSGI-compatible callable. The `api` and `serve-api` commands return a bounded HTTP adapter preview as JSON; they do not start a long-running server or bind a network port.

The FastAPI thin adapter is optional production wiring. Importing `token_payments.api` or `token_payments.api.fastapi` does not require FastAPI; building the FastAPI app requires installing `fastapi` in the runtime environment. Automated harness verification does not install packages, start an ASGI server, or bind a network port.

```bash
python3 -m pytest \
  scripts/test_http_adapter_contract_foundation.py \
  scripts/test_auth_order_http_routes.py \
  scripts/test_checkout_payment_http_routes.py \
  scripts/test_operator_http_routes.py \
  scripts/test_wsgi_runtime_preview.py \
  scripts/test_http_adapter_public_contracts.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api
python3 scripts/validate_phases.py
```

Next phase candidates:

- real docker compose integration: start the committed compose stack and verify schema, Kafka publish/consume, and bounded smoke commands against live infrastructure.
- ASGI/FastAPI thin adapter: add a production framework adapter while preserving the existing route manifest and facade contracts.
- operator lifecycle action endpoints: expose cancel, retry, and replay commands with policy, idempotency, and audit behavior.

## Operator Action Endpoints

The operator action endpoints phase closes the `cancel/retry/replay operator actions` surface as a bounded framework-neutral endpoint contract. `cancelOrder`, `retryOutboxMessage`, and `replayMessage` are verified through public `ApiRequest`/`ApiResponse` facades, route manifests, register helpers, ADMIN-only policy, idempotency, and audit payloads; live Docker/Kafka publish is not started automatically.

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

Next phase candidates:

- ASGI/FastAPI thin adapter: add a thin production framework layer while keeping the current route manifest and `build_wsgi_app` contract stable.
- live Docker compose integration: start the committed compose stack and verify DB schema, Kafka publish/consume, and bounded runtime smoke commands against live local infrastructure.
- operator action UI wiring: connect dashboard cancel/retry/replay controls to the existing operator action endpoint contract and surface result/audit state.

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

The ASGI/FastAPI Thin Adapter keeps the existing route manifest and facade contract as the stable API boundary. `build_asgi_app` adapts the framework-neutral `HttpRouter` without new runtime packages, and `build_fastapi_app` is optional FastAPI dependency production wiring. Importing `token_payments.api` and running preview commands does not require FastAPI; an explicit production runtime installs `fastapi` and calls the factory when it is ready to serve.

### Live API Request Guard

The live API adapter runs a framework-neutral request guard before facade dispatch. `POST /auth/challenges`, `POST /auth/sessions`, and `POST /auth/sessions/refresh` issue a signed `csrfToken` response field plus a `csrf_token` cookie. Browser clients using HttpOnly auth cookies must send the same value in `X-CSRF-Token` on mutating requests; safe methods and CORS preflight do not require CSRF.

Credentialed CORS uses `CORS_ALLOWED_ORIGINS` and `CORS_ALLOW_CREDENTIALS=true`; wildcard origin with credentials is rejected. Preflight `OPTIONS` returns bounded CORS headers before business handlers run. `REQUEST_BODY_MAX_BYTES` rejects oversized bodies with `413 REQUEST_BODY_TOO_LARGE`, and malformed JSON remains `400 MALFORMED_JSON`.

### Postman Cookie Auth Flow

Phase 15 commits `postman/token-payments.local.postman_collection.json`, `postman/token-payments.local.postman_environment.json`, and `postman/token-payments.cookie-auth.expected.json`. The auth collection order is: `POST /auth/challenges`, sign `signingMessage` in MetaMask, `POST /auth/sessions`, `POST /auth/sessions/refresh`, `DELETE /auth/sessions`, then `GET /auth/me`. Postman must use its cookie jar for `access_token`, `refresh_token`, and `csrf_token`; the happy-path requests intentionally omit manual `Cookie` and Bearer headers. Mutating cookie-auth calls echo the latest `csrfToken` in `X-CSRF-Token`.

The manual seed plan is `postman/fixtures/token-payments.local.seed-plan.json`; it is explicit local fixture metadata and is not loaded by default database initialization. `postman/expected/token-payments.api.expected.json` is the expected response contract for route status, request id, idempotency, CSRF, cookie, checkout, compensation, and operator action examples with signed token values redacted.

Postman Docker API readiness/security smoke is exposed as a bounded plan for the local live API service. Automated verification uses the dry-run and refusal commands only, so it does not start Docker, bind the API server, or open network clients.

```bash
python3 scripts/docker_live_smoke.py --api-readiness --plan
python3 scripts/docker_live_smoke.py --api-readiness --execute
```

`--execute` without `--confirm-live-docker` returns bounded refusal JSON. A confirmed local run requires a copied `.env` with replaced session/CSRF secrets. The plan order includes API service start, session signing key validation, `/healthz`, `/readyz`, cookie auth, invalid/expired signature rejection, CSRF failure/success, CORS preflight, oversized body, malformed JSON, idempotency duplicate, checkout happy path, and operator action smoke. Outputs redact session signing keys, signed tokens, cookie headers, and CSRF values.

```bash
cp .env.example .env
python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker
```

Final local backend order for Postman Docker API readiness:

```bash
cp .env.example .env
docker compose --env-file .env --profile api config --services
docker compose --env-file .env --profile api build token_payments_api
docker compose --env-file .env up -d postgres kafka test_network
docker compose --env-file .env --profile api up -d token_payments_api
# Apply/review the manual seed plan in postman/fixtures/token-payments.local.seed-plan.json
# Import postman/token-payments.local.postman_collection.json and postman/token-payments.local.postman_environment.json
python3 scripts/docker_live_smoke.py --api-readiness --plan
python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker
docker compose --env-file .env down
```

`api` and `serve-api` return bounded JSON previews with `wsgiFactory`, `asgiFactory`, `fastapiFactory`, `fastapiAvailable`, `longRunning=false`, and `serverStarted=false`. The harness default path does not start a server, does not bind a network port, and does not access DB, Kafka, Docker, Blockchain RPC, or local `.env`; this is the no-server-start boundary.

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
# Register production facades and route helpers in the explicit composition module.
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

Step 0 exposes `LiveRuntimeConfig`, `LiveRuntimeDependencies`, `LiveApiComposition`, and `describe_live_runtime_dependencies` as the live API composition surface. The contract parses API and adapter environment keys, describes externally injected PostgreSQL, Kafka, wallet signature, blockchain, clock, and ID dependencies, and redacts DSN passwords and token-address placeholders from JSON/debug metadata.

The explicit live server entrypoint is `PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run` for the bounded plan and `PYTHONPATH=app python3 -m token_payments serve-api --live --confirm-live-api` for an approved live start. `api` and `serve-api` without `--live` still return the no-server-start preview. `--live` without `--confirm-live-api` returns bounded refusal JSON, and dry-run/refusal paths do not bind a port, read local `.env`, or require FastAPI/Uvicorn.

The live server adds system-only `/healthz` and `/readyz` routes outside the public route manifest. `/healthz` is process-only, `/readyz` uses injected readiness probes, structured access log events are redacted, and mutating commands accept the standard `Idempotency-Key` header while preserving existing body-based command ids.

## Architecture Contract Alignment

Checkout Process is a separate saga/process context, not an order context submodule. `CheckoutProcessManager` lives under `contexts/checkout` and is limited to orchestration, compensation command decision, and idempotent saga decision; order context owns order creation, status projection, and checkout tracking.

`order.Store` and `store_approval.Store` are not the same aggregate. The order model is a catalog/order projection, while the store approval model is an approval verification projection and must not share persistence or DTOs by default.

PostgreSQL is the source of truth for auth users, login challenges, and sessions. Refresh reuse detection uses the PostgreSQL session repository hash/salt/rotation model. Redis is optional cache-aside/TTL optimization, not a live required dependency. Local runs must copy `.env.example` to `.env` and replace session and CSRF signing placeholders; live/prod startup rejects committed placeholder signing values.

Public HTTP route surface stays bound to the current 16-route manifest. `approveOrder`/`request_store_approval` are Kafka/message listener inputs, and store owner manual order approval HTTP API is not in current scope. manual order approval HTTP API is not an active roadmap item. ERC-20/USDC/USDT payment support is not an immediate roadmap phase.

Next phase order:

- Docker compose live server
- SIWE/ERC-1271 auth
- inventory saga finalization
- store owner inventory API

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

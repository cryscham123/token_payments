# API Spec: Token Payments

This document captures the Live API Runtime Composition boundary for the local Token Payments backend.

Default `api`/`serve-api` commands keep the no-server-start preview boundary. Use `PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run` for a bounded live server plan, and `PYTHONPATH=app python3 -m token_payments serve-api --live --confirm-live-api` only when an approved live environment is ready to start the long-running server.

이 문서는 `21-admin-store-catalog-provisioning`이 끝난 뒤의 로컬 backend API를 기준으로 한 최종 명세 초안이다. Route surface는 현재 `app/token_payments/api/http.py`의 route manifest 25개를 기준으로 고정한다.

## Route Surface Contract

### Public HTTP route surface

Public HTTP route surface is exactly the current 25-route manifest from `app/token_payments/api/http.py`. This manifest contains auth session routes, order creation, checkout tracking, payment txHash submission, admin store catalog provisioning routes, store-owner product registration, store owner inventory query/mutation routes, operator dashboard/detail reads, and cancel/retry/replay operator actions. It does not include store owner manual approval routes or checkout saga command endpoints.

### Message listener input surface

`approveOrder`/`request_store_approval` are Kafka/message listener inputs. Store approval runs after payment confirmation when the checkout saga emits `RequestStoreApprovalCommand`; store owner manual order approval HTTP API is not in current scope. The current product flow keeps post-payment automatic approval/rejection validation and does not expose a manual approve/reject route.

### Internal application port surface

`ReserveInventoryCommand`, `ReleaseInventoryCommand`, and `ConfirmInventoryCommand` are checkout saga internal commands. They are emitted by `CheckoutProcessManager` and handled by application/message adapters, not exposed as public customer HTTP APIs. Successful `OrderApprovedEvent` processing emits `ConfirmInventoryCommand`, and the inventory context records `InventoryConfirmedEvent`; payment failure, payment expiration, and order rejection still emit release/compensation commands.

Operator action APIs are platform recovery endpoints. Current compatibility paths still use an admin role policy, but phase 22 migrates them to platform group permissions such as `operator:read`, `operator:action`, and `outbox:retry`. Store owner inventory API is a separate merchant surface with store ownership/membership, not a global STORE_OWNER account role, and must not be confused with platform operator recovery endpoints. Store owners can query or mutate only own store inventory through active membership; platform operators/admins need explicit policy permission for cross-store access. The store owner inventory API manages stock and sale pause/resume only. Store owner manual order approval HTTP API is not in current scope, and manual order approval HTTP API is not an active roadmap item.

### Admin store catalog provisioning API surface

`POST /admin/store-users`, `POST /admin/stores`, and `POST /admin/stores/{storeId}/memberships` are provisioning endpoints. Current compatibility paths require server-side admin authority and ignore any role-like value in the request body. Phase 22 migrates this surface to `admin:provision`/`rbac:manage` policy checks. Public customer login never grants a global `STORE_OWNER` role, and provisioning creates or reuses a normal auth user identity without changing an existing customer account role.

Store ownership is represented by canonical store records plus merchant group membership. Compatibility tables such as `store_catalog_store_memberships` may remain during migration, but new authorization paths use group membership and permission lookup. A wallet that already has a customer identity can become a store owner by adding merchant membership to the existing user id; the same wallet must not create a second `auth_users` row, and customer checkout history/profile rows are preserved. Platform operations authority is represented by platform group membership, not a global account role.

`POST /store-owner/stores/{storeId}/products` registers a minimal checkoutable product for an active store. The caller must have `product:write` for that store scope; platform override requires explicit policy permission. The command writes through canonical `store_catalog_products`, checkout `order_store_products`, approval `store_approval_products`, and `product_inventory` in one transaction. Product description, category, tags, images, and search index metadata are phase 23 catalog fields; search engine integration remains future scope.

### Store owner inventory API surface

`GET /store-owner/inventory` returns inventory rows visible to the authenticated session. Merchant sessions are limited by active membership and `inventory:read`, including optional `storeId` filtering; platform sessions need explicit inventory/operator policy permission for cross-store access. A customer identity that owns a store through merchant membership can query/mutate that store without changing its global role. Unauthenticated sessions are rejected.

Inventory mutations use audited business commands rather than raw stock writes. The supported actions are stock intake, target total stock correction, sale pause, and sale resume. Mutations require cookie/session auth, `Idempotency-Key`, CSRF for browser cookie auth, `reason`, and server-side role/ownership checks. Stock correction cannot set `totalStock` below `reservedStock`. Sale pause/resume only changes new-order availability and does not release existing reservations.

Product sale availability is stored canonically in the inventory context as `ProductInventory.sale_status`. Store approval/order catalog projections may consume that status in later projection work, but this phase does not add a customer public inventory route.

### Planned phase 22/23 RBAC and profile/catalog alignment

Phase 22 removes global account-role authorization from new execution paths. `User` remains the authenticated identity and audit actor. `Group` is a permission scope/resource boundary, not a user-like actor, and nested groups are not part of the model. `GroupMembership` connects a user to a `PERSONAL`, `MERCHANT`, or `PLATFORM` group with a role. Roles are permission bundles; API authorization checks permission plus resource scope through `AuthorizationPolicy.can(...)`.

`PERSONAL` groups are retained as the customer self-scope. They support self operations without granting merchant or platform authority. `MERCHANT` groups scope store owner/manager permissions to a store or merchant resource. `PLATFORM` groups scope operator/admin permissions.

Baseline permission-to-API mapping:

| Permission | API/function surface |
| --- | --- |
| `user:self` | current user profile/session and own checkout/order access |
| `user:manage` | platform-managed user profile detail/status operations |
| `store:read` | merchant private store detail/listing |
| `store:write` | store business profile updates: display name, description, support contact |
| `store:manage` | sensitive store status/settings approval; not owner transfer or membership CRUD |
| `product:read` | merchant product detail/draft reads |
| `product:write` | product create/update APIs |
| `inventory:read` | store owner inventory reads |
| `inventory:write` | stock intake/correction and sale pause/resume APIs |
| `operator:read` | operator dashboard/order/payment/outbox detail reads |
| `operator:action` | operator recovery actions such as cancel/replay |
| `outbox:retry` | outbox retry execution, in addition to `operator:action` |
| `rbac:manage` | group/membership/role/permission administration |
| `admin:provision` | platform bootstrap/provisioning APIs |

Role and permission definitions start as seed/static catalog data. Phase 22 may map existing admin store membership provisioning to merchant group membership, but full role/permission CRUD APIs are future surface. If RBAC management APIs are later added, they must be protected by `rbac:manage` and audited with `actorUserId`, optional `groupId`, `permission`, `resourceType`, and `resourceId`.

Phase 23 separates user identity from user profile, store business profile from store payment settings, and product catalog from inventory. Store/product slug fields and SKU fields are not required in phase 23; public and merchant lookup starts with stable `storeId` and `productId`. Human-readable URLs and merchant-managed inventory codes are future scope. User display names, store display names, and product titles are display/search fields and may be duplicated. Settlement wallet/supported chain changes are policy-gated payment settings flows, not `updateStoreProfile`. Owner transfer, member invite/remove, and role changes belong to RBAC/membership provisioning, not store profile update.

All user-provided profile/catalog text fields are data, not executable fragments. APIs must validate bounded length, required/optional emptiness, control characters, null bytes, and normalization policy before persistence. SQL adapters must use parameter binding for values and whitelist any dynamic identifiers such as sort columns or directions. UI/rendering layers must HTML-escape display names, store descriptions, product titles, tags, and media labels before output. Query text and filter values must be parameterized; wildcard behavior for `ILIKE`/text search must be explicit and tested.

User-facing capability summary:

| User type | Allowed capabilities |
| --- | --- |
| Anonymous visitor | public store/product listing and detail, auth challenge request |
| Logged-in customer | own profile, own sessions, checkout/order creation and tracking, payment tx hash submission |
| Merchant member/manager | own merchant store reads, allowed business profile updates, product writes, inventory reads/writes |
| Merchant owner | merchant member capabilities plus store management requests/approvals within RBAC policy |
| Platform operator | operator dashboard/detail reads and bounded recovery actions |
| Platform admin | provisioning, RBAC/membership administration, sensitive approval flows |

## Runtime Assumptions

- Local base URL: `http://localhost:8000`
- Content type: `application/json`
- Response body는 JSON object다.
- 모든 response는 가능하면 `X-Request-Id` header를 포함한다.
- Client는 `X-Request-Id`를 전달할 수 있다. 없으면 server가 결정적 request id를 생성한다.
- 운영자 API는 phase 22 이후 server-side policy check의 `operator:read` 또는 `operator:action` permission이 필요하다. Legacy `ADMIN` role checks are compatibility only until that migration lands.
- 브라우저 client의 기본 auth transport는 `HttpOnly; Secure; SameSite=Lax` cookie다.
- 상태 변경 요청은 cookie auth와 함께 `X-CSRF-Token` double-submit token을 전달해야 한다.
- `Authorization: Bearer <accessToken>`은 non-browser client 또는 explicit integration fallback으로만 사용한다.
- `X-User-Id`, `X-User-Role`, `X-User-Scopes` header는 local/dev fallback 전용이며 production/live path에서는 신뢰하지 않는다.

## Common Headers

| Header | Required | Description |
| --- | --- | --- |
| `Content-Type: application/json` | body가 있을 때 | JSON request body |
| `Cookie` | 인증 필요 endpoint | `access`/`refresh` session cookie. `HttpOnly`라 JS에서 직접 읽지 않는다. |
| `X-CSRF-Token` | cookie auth + mutating method | double-submit 또는 signed CSRF token |
| `Authorization: Bearer <accessToken>` | non-browser fallback | cookie를 쓸 수 없는 client용 fallback |
| `X-Request-Id` | optional | idempotency/correlation용 client request id |
| `Idempotency-Key` | recommended for mutating commands | 주문 생성, txHash 제출, operator action 중복 방지 |
| `X-User-Id` | local/dev only | production/live path에서는 신뢰하지 않음 |
| `X-User-Role` | local/dev only | production/live path에서는 신뢰하지 않음 |
| `X-User-Scopes` | local/dev only | production/live path에서는 신뢰하지 않음 |

## Cookie And CSRF Policy

Login/refresh 성공 시 server는 access/refresh cookie를 `Set-Cookie`로 내려준다. Browser checkout에서 이 cookie가 session source of truth이며, response body의 `token` object는 legacy facade 호환 metadata일 수 있다.

Required cookie attributes:

- `HttpOnly`
- `Secure`
- `SameSite=Lax` or stricter
- `Path=/`
- bounded `Max-Age` or `Expires`

Logout 성공 시 server는 auth cookie를 만료시키는 `Set-Cookie`를 내려준다.

Session cookie values are signed tokens. The live runtime loads signing keys from environment-backed configuration:

- `SESSION_ACTIVE_KEY_ID`
- `SESSION_SIGNING_KEYS`
- `SESSION_ACCESS_TTL_SECONDS`
- `SESSION_REFRESH_TTL_SECONDS`

`SESSION_SIGNING_KEYS`는 `kid=secret,kid2=previous_secret` 또는 동등한 object 형태로 active key와 previous key를 함께 표현한다. New tokens are signed with the active key. Verification accepts the active key and configured previous keys until token expiry. Tokens must carry a `kid` or equivalent key id. Current compatibility payloads may include `role`; phase 22 target payloads use `sub`, `sessionId`, `walletAddress`, bounded `activeGroupId`/`groupMemberships` or `scopes`, `iat`, `exp`, `typ`, and `jti` instead of global role authority. Missing signing keys or committed placeholder keys must make live/prod server startup fail with a bounded configuration error.

Session signing keys, signed token values, refresh token hashes/salts, and CSRF secrets must never be logged, committed in fixtures, or exposed in runtime previews.

Auth wallet verification for deployed smart contract wallets uses environment-backed chain settings:

- `ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL`
- `ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID`
- `ADAPTER_AUTH_WALLET_SIGNATURE_TIMEOUT_SECONDS`

If `ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL` is empty in local development, runtime composition reuses the configured blockchain RPC URL. Access logs must not include raw SIWE messages, signatures, RPC response bodies, or contract call data.
`ADAPTER_AUTH_WALLET_SIGNATURE_TIMEOUT_SECONDS` bounds ERC-1271 RPC calls and maps timeout to bounded auth failure. `ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID` mismatch rejects before signature recovery or contract lookup. `walletSignature.rpcUrl is redacted in runtime/debug output`; signed messages, signatures, call data, and RPC response bodies stay out of logs and fixtures.

PostgreSQL is the source of truth for auth users, login challenges, and sessions. refresh reuse detection uses the PostgreSQL session repository hash/salt/rotation model. Redis is optional cache-aside/TTL optimization, not a live required dependency. The committed `.env.example` values are local dev values; live/prod startup rejects committed local dev signing values, so local live runs must copy `.env.example` to `.env` and replace session and CSRF signing material for non-local environments.

CSRF token 발급 surface는 route manifest를 늘리지 않고 `POST /auth/challenges`, `POST /auth/sessions`, `POST /auth/sessions/refresh` 성공 응답에 포함된다. Server also sets a non-HttpOnly `csrf_token` cookie for double-submit validation. Browser clients send the response `csrfToken` value back in `X-CSRF-Token` for cookie-authenticated mutating requests.

Cookie-authenticated mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`) must include `X-CSRF-Token`. Safe methods (`GET`, `HEAD`, `OPTIONS`) do not require CSRF. Missing or invalid CSRF token returns `403` with one of:

- `CSRF_TOKEN_MISSING`
- `CSRF_TOKEN_INVALID`

Credentialed CORS must use an origin allowlist from `CORS_ALLOWED_ORIGINS`. `Access-Control-Allow-Origin: *` must not be used with credentials. Preflight `OPTIONS` is handled at the adapter guard before facade/application service dispatch and returns bounded CORS headers. Disallowed origins return `403 CORS_ORIGIN_FORBIDDEN`.

Request body size is bounded by `REQUEST_BODY_MAX_BYTES`. Exceeding it returns `413 REQUEST_BODY_TOO_LARGE`; malformed JSON remains `400 MALFORMED_JSON`.

## Live System Routes And Observability

`GET /healthz` and `GET /readyz` are live server-only system routes and are not part of the 25-route public facade manifest. `/healthz` reports process/runtime health only and must not open PostgreSQL, Kafka, Blockchain, Docker, or local `.env`. `/readyz` summarizes injected PostgreSQL/Kafka/Blockchain readiness probes; unavailable components return `503` with bounded component details.

All HTTP responses include `X-Request-Id` when a request id is known, and an incoming `X-Request-Id` is preserved. Live access log events include method, path template or route id, status, request id, duration, actor summary, and error code. Access logs must not record cookie values, signed tokens, authorization headers, private keys, signatures, or full request bodies.

`Idempotency-Key` is the standard header for mutating command endpoints. It is wired to order creation causation, payment transaction hash command ids, and operator action idempotency keys. Existing body fields (`commandId` or `idempotencyKey`) remain supported for compatibility. If a header and body id disagree, the API returns `400 IDEMPOTENCY_KEY_CONFLICT`.

## Common Error Shape

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "field is required"
  }
}
```

Common status codes:

| Status | Meaning |
| --- | --- |
| `400` | validation error or malformed JSON |
| `401` | invalid wallet signature or invalid auth token |
| `403` | CSRF failure or authenticated user lacks required operator permission |
| `404` | resource not found |
| `405` | method not allowed, with `Allow` header |
| `409` | state conflict, reused nonce, expired challenge, duplicate/invalid command state |
| `413` | request body too large |

## Route Summary

| Operation ID | Method | Path |
| --- | --- | --- |
| `requestLoginChallenge` | `POST` | `/auth/challenges` |
| `loginWithMetaMask` | `POST` | `/auth/sessions` |
| `refreshSession` | `POST` | `/auth/sessions/refresh` |
| `logout` | `DELETE` | `/auth/sessions` |
| `getCurrentUser` | `GET` | `/auth/me` |
| `createOrder` | `POST` | `/orders` |
| `getCheckoutTrackingByTrackingId` | `GET` | `/checkouts/tracking/{trackingId}` |
| `getCheckoutTrackingByOrderId` | `GET` | `/checkouts/orders/{orderId}` |
| `submitTransactionHash` | `POST` | `/payments/transaction-hashes` |
| `createOrReuseStoreUser` | `POST` | `/admin/store-users` |
| `createStore` | `POST` | `/admin/stores` |
| `grantStoreMembership` | `POST` | `/admin/stores/{storeId}/memberships` |
| `registerStoreProduct` | `POST` | `/store-owner/stores/{storeId}/products` |
| `listStoreOwnerInventory` | `GET` | `/store-owner/inventory` |
| `increaseStoreOwnerInventoryStock` | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/intake` |
| `correctStoreOwnerInventoryStock` | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/corrections` |
| `pauseStoreOwnerInventorySales` | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/pause` |
| `resumeStoreOwnerInventorySales` | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/resume` |
| `getOperatorDashboard` | `GET` | `/operator/dashboard` |
| `getOperatorOrderDetail` | `GET` | `/operator/orders/{orderId}` |
| `getOperatorPaymentDetail` | `GET` | `/operator/payments/{paymentId}` |
| `getOperatorOutboxDetail` | `GET` | `/operator/outbox/{messageId}` |
| `cancelOperatorOrder` | `POST` | `/operator/orders/{orderId}/cancel` |
| `retryOperatorOutboxMessage` | `POST` | `/operator/outbox/{messageId}/retry` |
| `replayOperatorMessage` | `POST` | `/operator/messages/{messageId}/replay` |

## Auth

### `POST /auth/challenges`

SIWE v1 서명용 login challenge를 발급한다. Operation id는 기존 client 호환성을 위해 `requestLoginChallenge`를 유지하지만, `signingMessage`는 nonce-only custom message가 아니라 SIWE 필수 필드를 포함한다. `uri`가 없으면 server가 `https://{domain}`으로 기본값을 만든다. `signatureVerification`은 서명 원문이나 결과가 아니라 이 API surface가 지원하는 non-sensitive 검증 계약 metadata다.

Request:

```json
{
  "walletAddress": "0x1111111111111111111111111111111111111111",
  "domain": "token-payments.local",
  "uri": "https://token-payments.local",
  "chainId": 1337
}
```

Response `201`:

```json
{
  "walletAddress": "0x1111111111111111111111111111111111111111",
  "domain": "token-payments.local",
  "address": "0x1111111111111111111111111111111111111111",
  "uri": "https://token-payments.local",
  "version": "1",
  "chainId": 1337,
  "nonce": "N0NCE001",
  "issuedAt": "2026-05-17T10:00:00+09:00",
  "expirationTime": "2026-05-17T10:30:00+09:00",
  "expiresAt": "2026-05-17T10:30:00+09:00",
  "signingMessage": "token-payments.local wants you to sign in with your Ethereum account:\n0x1111111111111111111111111111111111111111\n\nURI: https://token-payments.local\nVersion: 1\nChain ID: 1337\nNonce: N0NCE001\nIssued At: 2026-05-17T10:00:00+09:00\nExpiration Time: 2026-05-17T10:30:00+09:00",
  "signatureVerification": {
    "messageFormat": "SIWE_V1",
    "signatureVerificationMethod": "SIWE_PERSONAL_SIGN_EOA_OR_ERC1271",
    "supportedWalletTypes": ["EOA", "DEPLOYED_SMART_WALLET"],
    "smartWalletStandard": "ERC-1271",
    "erc1271MagicValue": "0x1626ba7e",
    "requiresDeployedCode": true,
    "erc6492": "future_scope"
  },
  "csrfToken": "csrf-token",
  "csrf": {
    "cookieName": "csrf_token",
    "headerName": "X-CSRF-Token"
  }
}
```

Response headers include `Set-Cookie: csrf_token=...; Secure; SameSite=Lax; Path=/`.

Errors: `400 VALIDATION_ERROR`.

### `POST /auth/sessions`

MetaMask `personal_sign`으로 서명한 SIWE v1 message를 검증하고 session/token을 발급한다. Operation id는 기존 route compatibility를 위해 `loginWithMetaMask`를 유지한다. Server는 message의 `nonce`, `domain`, `address`, `chainId`, `issuedAt`, `expirationTime`, `uri`, `version`이 저장된 challenge와 일치하는지 확인한 뒤 wallet account type에 따라 EOA signature recovery 또는 deployed ERC-1271 smart contract wallet verification을 수행한다. Session response의 `signatureVerification`은 어떤 account type으로 성공했는지에 대한 audit event가 아니라 지원 범위를 설명하는 redacted runtime contract metadata다.

ERC-1271 verification은 configured auth chain RPC에서 signer wallet의 `eth_getCode` 결과가 deployed contract일 때만 적용된다. Contract wallet은 SIWE `personal_sign` digest와 signature를 `isValidSignature(bytes32,bytes)`로 검증하며, success magic value `0x1626ba7e`만 유효하다. Revert, wrong magic value, timeout, unsupported chain, undeployed/counterfactual account verification failure는 `401 INVALID_SIGNATURE` 또는 chain mismatch에 대한 bounded auth failure로 매핑된다. Linked wallets API와 ERC-6492 counterfactual account deployment/signature wrapping은 future scope이며 현재 route surface에 추가하지 않는다. Unsupported ERC-6492/counterfactual accounts are future scope; linked wallets are not implemented.

Request:

```json
{
  "walletAddress": "0x1111111111111111111111111111111111111111",
  "message": "token-payments.local wants you to sign in with your Ethereum account:\n0x1111111111111111111111111111111111111111\n\nURI: https://token-payments.local\nVersion: 1\nChain ID: 1337\nNonce: N0NCE001\nIssued At: 2026-05-17T10:00:00+09:00\nExpiration Time: 2026-05-17T10:30:00+09:00",
  "signature": "0xsignature",
  "deviceId": "browser-1"
}
```

Response `200`:

```json
{
  "user": {
    "userId": "user-001",
    "walletAddress": "0x1111111111111111111111111111111111111111",
    "role": "CUSTOMER",
    "active": true,
    "lastLoginAt": "2026-05-17T10:00:00+09:00"
  },
  "session": {
    "sessionId": "session-001",
    "userId": "user-001",
    "walletAddress": "0x1111111111111111111111111111111111111111",
    "deviceId": "browser-1",
    "expiresAt": "2026-06-16T10:00:00+09:00",
    "revokedAt": null
  },
  "token": {
    "accessToken": "<set-cookie>",
    "refreshToken": "<set-cookie>",
    "expiresAt": "2026-05-17T11:00:00+09:00",
    "transport": "cookie"
  },
  "signatureVerification": {
    "messageFormat": "SIWE_V1",
    "signatureVerificationMethod": "SIWE_PERSONAL_SIGN_EOA_OR_ERC1271",
    "supportedWalletTypes": ["EOA", "DEPLOYED_SMART_WALLET"],
    "smartWalletStandard": "ERC-1271",
    "erc1271MagicValue": "0x1626ba7e",
    "requiresDeployedCode": true,
    "erc6492": "future_scope"
  },
  "csrfToken": "csrf-token",
  "csrf": {
    "cookieName": "csrf_token",
    "headerName": "X-CSRF-Token"
  }
}
```

Browser HTTP response headers include `Set-Cookie` values for signed access/refresh session tokens and the `csrf_token` double-submit cookie. Cookie values are not shown in response examples.

Errors: `400 VALIDATION_ERROR`, `401 INVALID_SIGNATURE`, `401 WALLET_MISMATCH`, `401 SIWE_MESSAGE_MISMATCH`, `409 EXPIRED_CHALLENGE`, `409 REUSED_NONCE`.

### `POST /auth/sessions/refresh`

Refresh cookie로 session token을 회전한다.

Final browser request uses the `refresh_token` HttpOnly cookie. Body can be empty, or include `sessionId` when a non-browser client cannot rely on cookie claim extraction:

```json
{}
```

Non-browser/private harness facade may still model refresh token hash internally. This internal hash/salt model is not a public browser response field:

```json
{
  "sessionId": "session-001",
  "refreshTokenHash": {
    "hash": "hash-1",
    "salt": "salt-1",
    "rotationVersion": 0
  }
}
```

Response `200`: same shape as `POST /auth/sessions`.

Response headers rotate the refresh cookie and reissue the access cookie. Reuse detection is backed by the server-side session repository hash/salt/rotation model.

Errors: `400 VALIDATION_ERROR`, `401 INVALID_SIGNATURE`, `409 EXPIRED_CHALLENGE`.

### `DELETE /auth/sessions`

Session을 로그아웃 처리한다.

Request:

```json
{
  "sessionId": "session-001"
}
```

Response `200`:

```json
{
  "session": {
    "sessionId": "session-001",
    "userId": "user-001",
    "walletAddress": "0x1111111111111111111111111111111111111111",
    "deviceId": "browser-1",
    "expiresAt": "2026-06-16T10:00:00+09:00",
    "revokedAt": "2026-05-17T10:10:00+09:00"
  }
}
```

### `GET /auth/me`

현재 사용자 정보를 조회한다.

Query fallback: `?userId=user-001`

Response `200`:

```json
{
  "user": {
    "userId": "user-001",
    "walletAddress": "0x1111111111111111111111111111111111111111",
    "role": "CUSTOMER",
    "active": true,
    "lastLoginAt": "2026-05-17T10:00:00+09:00"
  }
}
```

## Orders

### `POST /orders`

주문을 생성하고 checkout saga 시작 이벤트를 outbox에 기록한다.

Auth: customer user.

Request:

```json
{
  "storeId": "store-001",
  "deliveryAddress": {
    "id": "addr-001",
    "street": "1 Token St"
  },
  "items": [
    {
      "productId": "product-001",
      "quantity": 2
    }
  ]
}
```

Response `201`:

```json
{
  "order": {
    "orderId": "order-001",
    "trackingId": "tracking-001",
    "customerId": "customer-001",
    "storeId": "store-001",
    "status": "PENDING",
    "deliveryAddress": {
      "id": "addr-001",
      "street": "1 Token St"
    },
    "totalAmount": {
      "amount": "20.000000000000000000",
      "symbol": "ETH",
      "chainId": 1337,
      "tokenAddress": null,
      "decimals": 18
    },
    "items": [
      {
        "orderItemId": "order-item-001",
        "productId": "product-001",
        "name": "Demo Product",
        "quantity": 2,
        "unitPrice": {
          "amount": "10.000000000000000000",
          "symbol": "ETH",
          "chainId": 1337,
          "tokenAddress": null,
          "decimals": 18
        },
        "subTotal": {
          "amount": "20.000000000000000000",
          "symbol": "ETH",
          "chainId": 1337,
          "tokenAddress": null,
          "decimals": 18
        }
      }
    ]
  }
}
```

Errors: `400 VALIDATION_ERROR`, `404 CUSTOMER_NOT_FOUND`, `404 STORE_NOT_FOUND`.

## Checkout Tracking

### `GET /checkouts/tracking/{trackingId}`

Tracking id로 checkout 상태를 조회한다.

### `GET /checkouts/orders/{orderId}`

Order id로 checkout 상태를 조회한다.

Response `200`:

```json
{
  "checkout": {
    "orderId": "order-001",
    "trackingId": "tracking-001",
    "status": "PENDING",
    "currentStep": "AWAITING_SIGNATURE",
    "pendingAction": "SIGN_PAYMENT",
    "paymentRequest": {
      "requestId": "payment-request-001",
      "amount": {
        "amount": "20.000000000000000000",
        "symbol": "ETH",
        "chainId": 1337,
        "tokenAddress": null,
        "decimals": 18
      },
      "to": "0x2222222222222222222222222222222222222222",
      "expiresAt": "2026-05-17T10:15:00+09:00"
    },
    "gasEstimate": {
      "estimatedFee": {
        "amount": "0.001000000000000000",
        "symbol": "ETH",
        "chainId": 1337,
        "tokenAddress": null,
        "decimals": 18
      },
      "gasLimit": 21000,
      "bufferRate": "0.10",
      "maxFee": null
    },
    "txHash": null,
    "failureReason": null,
    "updatedAt": "2026-05-17T10:01:00+09:00",
    "outboxStatus": [
      {
        "messageId": "msg-001",
        "name": "OrderCreated",
        "status": "PENDING",
        "updatedAt": "2026-05-17T10:00:01+09:00"
      }
    ]
  }
}
```

Errors: `400 VALIDATION_ERROR`, `404 CHECKOUT_NOT_FOUND`.

## Payments

### `POST /payments/transaction-hashes`

MetaMask가 전송한 transaction hash를 제출한다.

Auth: customer user.

Request:

```json
{
  "orderId": "order-001",
  "paymentId": "payment-001",
  "txHash": "0xtransactionhash",
  "commandId": "order-001:SubmitTransactionHashCommand"
}
```

`commandId`는 optional이다. 없으면 server가 `orderId` 기반 결정적 command id를 사용한다.

Response `202`:

```json
{
  "payment": {
    "orderId": "order-001",
    "status": "TX_SUBMITTED",
    "currentStep": "RECEIPT_PENDING",
    "pendingAction": "WAIT_FOR_RECEIPT",
    "txHash": "0xtransactionhash",
    "updatedAt": "2026-05-17T10:02:00+09:00"
  }
}
```

Errors: `400 VALIDATION_ERROR`, `404 PAYMENT_NOT_FOUND`, `404 AUTHORIZATION_NOT_FOUND`, `409 INVALID_STATE`.

## Operator Observability

Operator auth: current compatibility uses admin role checks; phase 22 target uses `operator:read`.

Local fallback headers:

```text
X-User-Id: admin-001
X-User-Role: ADMIN
X-User-Scopes: operator:read,operator:action,outbox:retry
```

### `GET /operator/dashboard`

Query params:

| Param | Description |
| --- | --- |
| `context` or `contexts` | comma-separated `orders,payments,outbox` |
| `status` | comma-separated status filter |
| `chainId` | numeric chain id |
| `storeId` | store filter |
| `failedOnly` | boolean |
| `retryCandidatesOnly` | boolean |
| `sort` | `updatedAt` or `-updatedAt`, defaults to `-updatedAt` |
| `limit` | page size, defaults to `50` |
| `pageToken` | opaque page token |

Response `200`:

```json
{
  "orders": [],
  "payments": [],
  "outbox": [],
  "workers": [],
  "errors": [],
  "pagination": {
    "orders": {
      "limit": 50,
      "nextPageToken": null
    }
  }
}
```

### `GET /operator/orders/{orderId}`

Returns the same operator snapshot envelope, narrowed to one order detail.

Order item shape:

```json
{
  "orderId": "order-001",
  "trackingId": "tracking-001",
  "customerId": "customer-001",
  "storeId": "store-001",
  "status": "PENDING",
  "paymentId": "payment-001",
  "paymentStatus": "AWAITING_SIGNATURE",
  "totalAmount": {
    "amount": "20.000000000000000000",
    "symbol": "ETH",
    "chainId": 1337,
    "tokenAddress": null,
    "decimals": 18
  },
  "failureReason": null,
  "latestEvent": "OrderCreated",
  "createdAt": "2026-05-17T10:00:00+09:00",
  "updatedAt": "2026-05-17T10:00:00+09:00"
}
```

### `GET /operator/payments/{paymentId}`

Returns the same operator snapshot envelope, narrowed to one payment detail.

Payment item shape:

```json
{
  "paymentId": "payment-001",
  "orderId": "order-001",
  "customerId": "customer-001",
  "status": "TX_SUBMITTED",
  "amount": {
    "amount": "20.000000000000000000",
    "symbol": "ETH",
    "chainId": 1337,
    "tokenAddress": null,
    "decimals": 18
  },
  "chain": {
    "chainId": 1337,
    "name": "local"
  },
  "walletFrom": "0x1111111111111111111111111111111111111111",
  "walletTo": "0x2222222222222222222222222222222222222222",
  "txHash": "0xtransactionhash",
  "failureReason": null,
  "expiresAt": "2026-05-17T10:15:00+09:00",
  "createdAt": "2026-05-17T10:00:00+09:00",
  "updatedAt": "2026-05-17T10:02:00+09:00"
}
```

### `GET /operator/outbox/{messageId}`

Query params:

| Param | Description |
| --- | --- |
| `kind` | `EVENT` or `COMMAND`, defaults to `EVENT` |

Outbox item shape:

```json
{
  "messageId": "msg-001",
  "kind": "EVENT",
  "name": "OrderCreated",
  "topic": "checkout.events",
  "key": "order-001",
  "status": "FAILED",
  "failureCount": 3,
  "lastError": "temporary broker error",
  "retryCandidate": true,
  "retryReason": "failure count below max attempts",
  "createdAt": "2026-05-17T10:00:00+09:00",
  "publishedAt": null,
  "updatedAt": "2026-05-17T10:05:00+09:00"
}
```

Errors: `400 VALIDATION_ERROR`, `403 OPERATOR_FORBIDDEN`, `404 OPERATOR_RESOURCE_NOT_FOUND`.

## Operator Actions

Operator auth: current compatibility uses admin role checks; phase 22 target uses `operator:action`. Outbox retry also requires `outbox:retry`.

All action responses use:

```json
{
  "action": "cancelOrder",
  "status": "accepted",
  "target": {
    "kind": "order",
    "id": "order-001"
  },
  "idempotencyKey": "operator:cancelOrder:order-001:req-001",
  "commandId": "order-001:CancelOrderCommand",
  "messageId": null,
  "auditId": "audit-001",
  "summary": "cancel order accepted",
  "details": {}
}
```

Action status codes:

| Result status | HTTP status |
| --- | --- |
| `accepted` | `202` |
| `duplicate` | `200` |
| `rejected` with forbidden detail | `403` |
| `rejected` with validation detail | `400` |
| other `rejected` | `409` |

### `POST /operator/orders/{orderId}/cancel`

Request:

```json
{
  "reason": "customer requested cancellation",
  "idempotencyKey": "operator-cancel-order-001",
  "parameters": {
    "notifyCustomer": true
  }
}
```

### `POST /operator/outbox/{messageId}/retry`

Request:

```json
{
  "kind": "EVENT",
  "reason": "broker recovered",
  "idempotencyKey": "operator-retry-msg-001",
  "parameters": {
    "maxAttempts": 1
  }
}
```

`messageKind` is accepted as an alias for `kind`.

### `POST /operator/messages/{messageId}/replay`

Request:

```json
{
  "kind": "COMMAND",
  "reason": "manual replay after handler fix",
  "idempotencyKey": "operator-replay-msg-001",
  "parameters": {
    "targetConsumer": "checkout-process-manager"
  }
}
```

`messageKind` is accepted as an alias for `kind`.

Errors: `400 OPERATOR_ACTION_VALIDATION_FAILED`, `403 OPERATOR_FORBIDDEN`, `409 OPERATOR_ACTION_REJECTED`.

## State Values

Order status:

- `PENDING`
- `PAID`
- `APPROVED`
- `CANCELLING`
- `CANCELLED`

Payment status:

- `AWAITING_SIGNATURE`
- `TX_SUBMITTED`
- `CONFIRMED`
- `FAILED`
- `EXPIRED`
- `REFUNDED`

Checkout current/pending action examples:

- `AWAITING_SIGNATURE` / `SIGN_PAYMENT`
- `RECEIPT_PENDING` / `WAIT_FOR_RECEIPT`
- `PAYMENT_CONFIRMED` / `WAIT_FOR_STORE_APPROVAL`
- `PAYMENT_FAILED` / `WAIT_FOR_COMPENSATION`

Outbox/message kind:

- `EVENT`
- `COMMAND`

Operator action status:

- `accepted`
- `duplicate`
- `rejected`

## Postman Flow

Final local verification should run in this order:

1. `POST /auth/challenges`
2. Sign `signingMessage` in MetaMask.
3. `POST /auth/sessions`
4. `POST /orders`
5. Poll `GET /checkouts/tracking/{trackingId}` until `pendingAction=SIGN_PAYMENT`.
6. Send the payment transaction in MetaMask.
7. `POST /payments/transaction-hashes`
8. Poll `GET /checkouts/orders/{orderId}` until final status is `APPROVED` or `CANCELLED`.
9. Use operator dashboard/detail endpoints for observability.
10. Use operator action endpoints only for explicit manual recovery.

For cookie auth setup, import `postman/token-payments.local.postman_collection.json` and `postman/token-payments.local.postman_environment.json`. The auth folder runs `POST /auth/challenges`, MetaMask signing, `POST /auth/sessions`, `POST /auth/sessions/refresh`, `DELETE /auth/sessions`, and `GET /auth/me` in order. Postman stores `Set-Cookie` responses in its cookie jar; happy-path requests do not use manual `Cookie`, Bearer, localStorage, or sessionStorage auth. `postman/token-payments.cookie-auth.expected.json` records redacted signed token shape, active key id metadata, CSRF header/cookie names, cookie attributes, and expired/invalid-signature negative cases.

Manual seed data for local Postman runs is described by `postman/fixtures/token-payments.local.seed-plan.json`. It references demo customer/store/product/inventory/payment destination/test network ids using committed PostgreSQL schema table and column names, but it is not part of default init and does not run in automated verification. Route-level expected response examples live in `postman/expected/token-payments.api.expected.json`; the fixture covers auth, cookie/CSRF headers, `Idempotency-Key`, `X-Request-Id`, happy-path checkout, compensation cancellation, and operator action recovery while keeping signed token and cookie values redacted.

The Docker Compose API service is `token_payments_api`. After `cp .env.example .env`, `COMPOSE_PROFILES=runtime,smoke,api` makes it part of plain `docker compose up`; automated checks use daemon-less compose config and smoke plans and do not start Docker. Daemon-less compose config validation does not start Docker:

```bash
docker compose --env-file .env.example config --services
```

It runs `python -m token_payments serve-api --live --confirm-live-api` and must use env-backed session signing material: `SESSION_ACTIVE_KEY_ID` selects the active key, and `SESSION_SIGNING_KEYS` may retain a previous key only for bounded key rotation verification. The committed local dev signing values are valid only for `RUNTIME_ENVIRONMENT=local`; live/prod startup rejects committed local dev signing values. Browser auth is cookie-first through HttpOnly access/refresh cookies plus `X-CSRF-Token`; `Authorization: Bearer <accessToken>` is only a non-browser fallback. Credentialed CORS requires `CORS_ALLOW_CREDENTIALS=true` with an allowlisted origin, never wildcard credentials.

Postman Docker API readiness/security smoke is documented as a bounded local live plan. Automated verification runs only the dry-run/refusal path and does not start Docker or the API server. The plan covers API service start, session signing key validation, health/readiness, cookie auth, invalid/expired signature rejection, CSRF failure/success, credentialed CORS preflight, oversized body, malformed JSON, idempotency duplicate, checkout happy path, and operator action smoke.

Final local backend order for Postman Docker API readiness:

```bash
cp .env.example .env
docker compose --env-file .env config --services
docker compose --env-file .env build token_payments_api
docker compose up -d
curl --fail http://localhost:8000/healthz
curl --fail http://localhost:8000/readyz
# Apply/review the manual seed plan in postman/fixtures/token-payments.local.seed-plan.json
# Import postman/token-payments.local.postman_collection.json and postman/token-payments.local.postman_environment.json
python3 scripts/docker_live_smoke.py --api-readiness --plan
python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker
docker compose down
```

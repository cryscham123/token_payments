---
description: Token Payments public HTTP API, OAuth, Postman 계약을 GitBook에서 읽기 위한 한국어 명세
---

# Token Payments API 명세

이 문서는 로컬 Token Payments backend의 public HTTP API, OAuth identity API, Postman fixture, Live API Runtime Composition 경계를 함께 설명하는 기준 명세다. GitBook에서는 아래 분리 페이지를 먼저 읽고, 이 파일의 Route Summary와 endpoint별 상세 계약을 source of truth로 사용한다.

Default `api`/`serve-api` commands keep the no-server-start preview boundary. Use `PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run` for a bounded live server plan, and `PYTHONPATH=app python3 -m token_payments serve-api --live --confirm-live-api` only when an approved live environment is ready to start the long-running server.

이 문서는 현재 로컬 backend API와 Phase 27 privacy-first identity contract를 기준으로 한다. Route surface는 현재 `app/token_payments/api/http.py`의 route manifest 55개를 기준으로 고정한다.

## GitBook 탐색

- [API 개요](api/README.md): base URL, 인증 방식, 공통 헤더와 오류 규약.
- [OpenAPI Reference](api/openapi.yaml): GitBook OpenAPI import용 55-route interactive reference.
- [공통 계약](api/runtime-contract.md): API evolution guardrail, route surface, runtime, header, cookie/CSRF, error, state, Postman 계약.
- [전체 Route Summary](api/route-summary.md): 현재 55개 public HTTP route manifest의 GitBook용 전체 표.
- [인증과 OAuth](api/auth.md): SIWE, session, wallet link, user profile, provider-subject OAuth API.
- [주문, 체크아웃, 결제](api/orders-checkout-payments.md): 주문 생성, checkout tracking, txHash 제출.
- [상점과 상품 카탈로그](api/catalog-inventory.md): public store/product 읽기, merchant product 쓰기, store owner inventory.
- [머천트, 관리자, RBAC](api/merchant-admin-rbac.md): admin provisioning, merchant member/invitation, role catalog.
- [운영자와 런타임](api/operator-runtime.md): operator dashboard/detail/action API와 live runtime boundary.

아래 본문에는 자동 계약 테스트가 참조하는 canonical route manifest와 endpoint별 요청/응답 예시가 포함된다. 영어 계약 문구는 기존 public contract와 테스트 호환성을 위해 보존한다.

## API Evolution Guardrail

Feature API Companion Rule: 신규 사용자/업무 기능은 의도적으로 내부 전용이라고 명시하지 않는 한 API surface와 함께 설계한다. 새 기능 phase는 이 문서의 endpoint/operation contract, route manifest, public fixtures/Postman expected data, API tests를 함께 갱신해야 한다. API가 없는 순수 내부 기능은 phase step과 완료 summary에 `intentional internal-only exception` 및 이유를 남긴다.

## Phase 26 public security contract

Phase 26 hardens the public API and runtime architecture around externally safe identifiers, fail-closed writes, bounded context boundaries, modular composition, and membership projection.

- external payment submission uses `trackingId`; the server resolves order/payment ids internally after session ownership verification. The idempotency fallback is `payment.submit_tx:{trackingId}` and never embeds a raw internal order id.
- Session, order creation, and payment submission responses do not expose `sessionId`, `refreshTokenHash`, internal `customerId`, or internal store primary keys on public customer/browser surfaces.
- Inventory mutation requires `inventory:write` and canonical store membership (`OWNER` or `MANAGER`). Product registration requires `product:write` at the API boundary and canonical store membership in the service boundary. Both paths fail-closed when membership is missing, revoked, stale, or unavailable.
- bounded contexts exchange ports, DTOs, ACLs, snapshots, or shared-kernel value objects. They do not serialize another bounded context domain object as their own persistence schema.
- `store_catalog_store_memberships` is the canonical membership source. `auth_group_memberships` is an RBAC projection updated synchronously during admin/merchant membership writes and reconciled through transactional outbox events. projection lag never authorizes writes; replay uses the same idempotent event handler for rebuild/replay.
- runtime composition facade remains the public import path, while context-specific factories live in runtime composition modules and preserve the no-server-start dry-run boundary.

## Route Surface Contract

### Public HTTP route surface

Public HTTP route surface is exactly the current 55-route manifest from `app/token_payments/api/http.py`. This manifest contains auth session routes, OAuth provider-subject login/link/list/revoke routes, authenticated wallet link/list/primary/revoke routes, current user display profile routes, order creation, checkout tracking, customer payment history, payment txHash submission, public store profile reads, merchant store profile listing/update routes, admin store catalog provisioning routes, store-owner product registration, store owner inventory query/mutation routes, merchant member/invitation routes, operator dashboard/detail reads, and cancel/retry/replay operator actions. It does not include store owner manual approval routes, role/permission full CRUD, platform group CRUD, personal group CRUD, owner transfer, settlement wallet mutation, or checkout saga command endpoints.

### Message listener input surface

`approveOrder`/`request_store_approval` are Kafka/message listener inputs. Store approval runs after payment confirmation when the checkout saga emits `RequestStoreApprovalCommand`; store owner manual order approval HTTP API is not in current scope. The current product flow keeps post-payment automatic approval/rejection validation and does not expose a manual approve/reject route.

### Internal application port surface

`ReserveInventoryCommand`, `ReleaseInventoryCommand`, and `ConfirmInventoryCommand` are checkout saga internal commands. They are emitted by `CheckoutProcessManager` and handled by application/message adapters, not exposed as public customer HTTP APIs. Successful `OrderApprovedEvent` processing emits `ConfirmInventoryCommand`, and the inventory context records `InventoryConfirmedEvent`; payment failure, payment expiration, and order rejection still emit release/compensation commands.

Operator action APIs are platform recovery endpoints. Operator action APIs require explicit platform permissions such as `operator:read`, `operator:action`, and `outbox:retry`; a global admin role is not the authorization source for new execution paths. Store owner inventory API is a separate merchant surface with store ownership/membership, not a global STORE_OWNER account role, and must not be confused with platform operator recovery endpoints. Store owners can query or mutate only own store inventory through active membership; platform sessions need explicit inventory/operator policy permission for cross-store access. The store owner inventory API manages stock and sale pause/resume only. Store owner manual order approval HTTP API is not in current scope, and manual order approval HTTP API is not an active roadmap item.

### Admin store catalog provisioning API surface

`POST /admin/store-users`, `POST /admin/stores`, and `POST /admin/stores/{storeId}/memberships` require `admin:provision` or `rbac:manage` policy checks. These provisioning endpoints ignore any role-like value in the request body except the bounded merchant membership template accepted by the membership command. Public customer login never grants a global `STORE_OWNER` role, and provisioning creates or reuses a normal auth user identity without changing an existing customer account role.

Store ownership is represented by canonical store records plus merchant group membership. Canonical store records use internal `store_id` only for persistence and service boundaries, and expose stable external `public_store_id`/`publicStoreId` for public and merchant profile lookup. `public_store_id` is unique/indexed and is not the internal UUID primary key or a sequential id. Compatibility tables such as `store_catalog_store_memberships` may remain during migration, but new authorization paths use group membership and permission lookup. A wallet that already has a customer identity can become a store owner by adding merchant membership to the existing user id; the same wallet must not create a second `auth_users` row, and customer checkout history/profile rows are preserved. Platform operations authority is represented by platform group membership, not a global account role.

Store wallet and supported chains live on the store profile compatibility payload while phase 23 keeps public business profile fields and payment settings as separate policy-gated concerns.

`POST /merchant/stores/{publicStoreId}/products` registers a checkoutable catalog product for an active store using the public store identifier, not internal `store_id`. The request accepts internal `productId` only as a merchant write concern and exposes stable `publicProductId`/`public_product_id` for customer and merchant read paths. The caller must have `product:write` for that store scope; platform override requires explicit policy permission. The command writes through canonical `store_catalog_products`, checkout `order_store_products`, approval `store_approval_products`, and `product_inventory` in one transaction.

`PATCH /merchant/stores/{publicStoreId}/products/{publicProductId}` updates product catalog detail fields without mutating inventory sale status or stock. Product catalog records carry internal `product_id`, external `public_product_id`, internal `store_id`, external `public_store_id`, `title`, optional `description`, `category`, `tags`, `media`, JSON `attributes`, `status`, `visibility`, and timestamps. `public_product_id` is stable and unique inside the public store scope; it must not expose the internal UUID primary key or a sequential id. Search engine integration remains future scope.

`GET /stores`, `GET /stores/{publicStoreId}/products`, and `GET /stores/{publicStoreId}/products/{publicProductId}` are public read APIs keyed only by public store/product ids. Store responses expose business profile and bounded payment capability summaries, not internal settlement wallet values or internal UUID keys. Product responses expose `publicProductId`, display price, availability, and payment capability summaries while omitting internal `store_id`, `product_id`, and customer ids. `GET /merchant/stores/{publicStoreId}/products` and `GET /merchant/stores/{publicStoreId}/products/{publicProductId}` are permission-protected merchant reads that can include private/inactive catalog records and bounded filters for status, visibility, category, tag, query text, sort, limit, and offset.

Catalog query filtering is the PostgreSQL baseline for phase 23. Query text, category, tag, status, visibility, sort, and pagination values are bounded before persistence access; SQL values use parameter binding; `ILIKE` wildcard input is escaped; and ORDER BY columns/directions are allowlisted. Elasticsearch/OpenSearch search projection is future scope and should attach through outbox/projection without changing the public query contract.

Order creation and checkout start must revalidate server-side current store/product/price/inventory/payment capability state. Client-provided product detail, price, stock, chain, asset, or settlement capability values from public catalog reads are hints only and must not be trusted as authorization or pricing inputs.

Elasticsearch and DID-based account identity are future scope. Email account recovery is not supported because the backend does not persist user email or email hashes.

### Multi-wallet and stablecoin payment contract

The login wallet is the wallet that signs the SIWE session challenge. A linked wallet is an authenticated user's verified, active wallet record. A payer wallet is the linked wallet selected for checkout by `walletId`; when omitted, checkout chooses that user's primary linked wallet for the selected asset chain. A settlement wallet is the store-side destination for payment proceeds and is a separate store payment setting. wallet revocation does not recover assets and does not rewrite historical payment records.

Checkout write APIs accept `paymentAssetId` and optional `walletId`. They never accept a raw wallet address or arbitrary token address as proof of ownership or payment asset support. Store and product capability responses use `supportedChains` and `acceptedAssets`; display metadata is derived from the registry, while `chain_id` remains the canonical network key. `payment_authorizations` owns expected payer wallet, asset, recipient, chain, and amount terms. `payments` owns observed transaction hash, transaction status, and receipt verification result.

Stablecoin support is registry-driven. The local registry may enable native coin payments plus ERC-20 stablecoin assets such as USDC and USDT; disabled assets and arbitrary ERC-20 contracts are rejected. permit, gas sponsorship, swap, exchange-rate conversion, and DID identity remain future scope. Email account recovery remains unsupported because user email is not stored.

Roadmap status note: Kafka live worker, multi-wallet, and stablecoin support are implemented in the local runtime contract. Historical architecture wording, "ERC-20/USDC/USDT payment support is not an immediate roadmap phase", is superseded by phase 25. Counterfactual linked wallets are not implemented; verified linked wallets are implemented through the authenticated wallet link APIs.

### Privacy-first OAuth identity contract

OAuth/social identity is keyed by `provider` plus `providerSubject`, not by email. Google email claims are not persisted, and email/hash matching must not automatically merge accounts. A new social login creates or links the provider-subject identity to a user only through an authenticated session or an explicit EOA signature proof for existing wallet accounts. OAuth unlink is a soft revoke using `revokedAt`; unlink must not remove the final active login method, and wallet/social identity unlink is blocked while active payment, refund, or reservation work depends on that identity. Public OAuth API responses expose `oauthIdentityId`, `provider`, optional `walletId`, `linkedAt`, and `revokedAt`; they do not expose raw `providerSubject`, provider access/refresh tokens, email claims, or provider profile dumps.

### Store profile API surface

`GET /stores/{publicStoreId}` returns a public business profile projection only: `publicStoreId`, display name, optional description, status, escaped display/description variants for HTML rendering, and `supportEmail` only when the store has explicitly marked support email as public. It never returns internal `store_id`, owner user id, group id, settlement wallet, supported chains, private support contact, or business registration label.

`GET /merchant/stores` lists stores visible to the authenticated merchant session using scoped merchant membership and `store:read`. The response is keyed by `publicStoreId`; internal `store_id` remains a persistence detail.

`PATCH /merchant/stores/{publicStoreId}/profile` updates only business profile fields: `displayName`, `description`, `supportEmail`, `supportEmailPublic`, and `businessRegistrationLabel`. It requires `store:write` for the scoped merchant group or explicit platform override. `store:manage` or platform approval flows are reserved for sensitive status/settings changes. Settlement wallet and supported chain changes are separate policy-gated payment settings flows and are not accepted by `updateStoreProfile`. Owner transfer, member invite/remove, and role/permission changes remain RBAC/membership provisioning responsibilities.

Store profile input text is bounded data. `displayName`, `description`, and `businessRegistrationLabel` are Unicode-normalized, length-bounded, and reject control characters, null bytes, and log/CSV injection-prone prefixes. Store `displayName` is globally unique case-insensitively. `supportEmail` is length-bounded and email-shaped. SQL adapters use parameter binding for `public_store_id`, display fields, and contact fields; client rendering layers must use escaped response fields such as `displayNameHtml` and `descriptionHtml`.

### Store owner inventory API surface

`GET /store-owner/inventory` returns inventory rows visible to the authenticated session. Merchant sessions are limited by active membership and `inventory:read`, including optional `storeId` filtering; platform sessions need explicit inventory/operator policy permission for cross-store access. A customer identity that owns a store through merchant membership can query/mutate that store without changing its global role. Unauthenticated sessions are rejected.

Inventory mutations use audited business commands rather than raw stock writes. The supported actions are stock intake, target total stock correction, sale pause, and sale resume. Mutations require cookie/session auth, `Idempotency-Key`, CSRF for browser cookie auth, `reason`, and server-side permission plus ownership/membership checks. Stock correction cannot set `totalStock` below `reservedStock`. Sale pause/resume only changes new-order availability and does not release existing reservations.

Product sale availability is stored canonically in the inventory context as `ProductInventory.sale_status`. Store approval/order catalog projections may consume that status in later projection work, but this phase does not add a customer public inventory route.

### Planned phase 22/23 RBAC and profile/catalog alignment

Phase 22 removes global account-role authorization from new execution paths. User remains the authenticated identity and audit actor. `UserProfile` is optional bounded display data only and is not an authorization source. The backend does not store user email, email hash, locale, or timezone in profile data. `Group` is a permission scope/resource boundary, not a user-like actor, and nested groups are not part of the model. GroupMembership connects a user to a group with a role. `GroupMembership` connects a user to a `PERSONAL`, `MERCHANT`, or `PLATFORM` group with a role. Roles are permission bundles; API authorization checks permission plus resource scope through `AuthorizationPolicy.can(...)`.

`PERSONAL` groups are retained as the customer self-scope. They support self operations without granting merchant or platform authority. `MERCHANT` groups scope store owner/manager permissions to a store or merchant resource. `PLATFORM` groups scope operator/admin permissions.

Baseline permission-to-API mapping:

| Permission | API/function surface |
| --- | --- |
| `user:self` | current user profile/session and own checkout/order access |
| `user:manage` | platform-managed user profile detail/status operations |
| `store:read` | merchant private store detail/listing |
| `store:write` | store business profile updates: display name, description, support contact |
| `store:manage` | sensitive store status/settings approval; not owner transfer or membership CRUD |
| `merchant_member:read` | merchant member and invitation listing for the scoped store |
| `merchant_member:invite` | merchant staff invitation create/revoke using server-defined merchant role templates |
| `merchant_member:manage` | merchant staff role change/removal; never platform roles or owner transfer |
| `product:read` | merchant product detail/draft reads |
| `product:write` | product create/update APIs |
| `inventory:read` | store owner inventory reads |
| `inventory:write` | stock intake/correction and sale pause/resume APIs |
| `operator:read` | operator dashboard/order/payment/outbox detail reads |
| `operator:action` | operator recovery actions such as cancel/replay |
| `outbox:retry` | outbox retry execution, in addition to `operator:action` |
| `rbac:manage` | group/membership/role/permission administration |
| `admin:provision` | platform bootstrap/provisioning APIs |

Role and permission definitions start as seed/static catalog data. Merchant-facing APIs may select only server-defined merchant role templates. They must never accept raw permission arrays, platform roles, personal roles, or `MERCHANT_OWNER` assignment. Full role/permission CRUD APIs are future surface. If RBAC management APIs are later added, they must be protected by `rbac:manage` and audited with `actorUserId`, optional `groupId`, `permission`, `resourceType`, and `resourceId`.

Baseline role template catalog:

| Role template | Scope | Permissions |
| --- | --- | --- |
| `PERSONAL_CUSTOMER` | personal group | `user:self` |
| `MERCHANT_OWNER` | merchant group | store/product/inventory permissions plus merchant member read/invite/manage |
| `MERCHANT_MANAGER` | merchant group | store/product/inventory permissions plus merchant member read/invite within policy |
| `MERCHANT_STAFF` | merchant group | bounded store/product/inventory read permissions defined by seed |
| `PLATFORM_OPERATOR` | platform group | operator dashboard/detail and bounded recovery permissions |
| `PLATFORM_ADMIN` | platform group | provisioning, RBAC administration, user management, and sensitive approval permissions |

Externally exposed RBAC and membership API surface for phase 22:

| API/function surface | Required authority | Notes |
| --- | --- | --- |
| `POST /admin/stores` | `admin:provision` | Creates the canonical store and merchant group, and assigns initial `MERCHANT_OWNER` through provisioning |
| `POST /admin/stores/{storeId}/memberships` | `admin:provision` or `rbac:manage` | Admin-level compatibility path for setting store membership, including owner assignment during migration |
| `GET /merchant/stores/{storeId}/members` | `merchant_member:read` | Lists users in the caller's scoped merchant group |
| `GET /merchant/stores/{storeId}/invitations` | `merchant_member:read` | Lists pending/accepted/revoked invitations for the scoped merchant group |
| `POST /merchant/stores/{storeId}/invitations` | `merchant_member:invite` | Invites a displayName-resolved user, internal user id, or wallet target to a non-owner merchant role template |
| `POST /merchant/invitations/{invitationId}/accept` | authenticated target user | Accepts an invitation and creates membership in the invitation's merchant group |
| `POST /merchant/invitations/{invitationId}/revoke` | `merchant_member:invite` or `merchant_member:manage` | Revokes pending invitations in the scoped merchant group |
| `PATCH /merchant/stores/{storeId}/members/{userId}` | `merchant_member:manage` | Changes staff role templates only; cannot grant, revoke, or transfer `MERCHANT_OWNER` |
| `DELETE /merchant/stores/{storeId}/members/{userId}` | `merchant_member:manage` | Removes non-owner staff membership; must not remove the last owner |
| `GET /merchant/role-catalog` | authenticated merchant member | Returns server-defined merchant role templates, not raw permission mutation capability |

Platform group creation, platform role assignment, personal group management, permission CRUD, and owner transfer are not merchant/customer APIs. Personal groups are auto-created at signup. Merchant groups are created by store provisioning. Platform groups are seed/manual/admin-provisioned. Owner transfer is a sensitive admin/provisioning flow until a separate audited approval workflow exists.

MERCHANT_OWNER assignment or transfer is not merchant-facing; merchant APIs can invite, update, or remove only non-owner staff templates selected from the server-defined merchant role catalog.

Phase 23 separates user identity from user profile, store business profile from store payment settings, and product catalog from inventory. Store/product slug fields and SKU fields are not required in phase 23; public and merchant store/profile/product lookup starts with stable `publicStoreId` and `publicProductId`, while internal service/projection boundaries continue using `storeId` and `productId`. Human-readable URLs and merchant-managed inventory codes are future scope. User and store display names are unique display/search fields; product titles may be duplicated. Settlement wallet/supported chain changes are policy-gated payment settings flows, not `updateStoreProfile`. Owner transfer, member invite/remove, and role changes belong to RBAC/membership provisioning, not store profile update.

Historical phase 21 note: description/category/search metadata is future scope; phase 23 has since implemented product description/category fields while search metadata remains future scope.

All user-provided profile/catalog text fields are data, not executable fragments. APIs must validate bounded length, required/optional emptiness, control characters, null bytes, and normalization policy before persistence. User and store display names must remain unique outside product title search/display data. Product tags accept Unicode letters/numbers, including Korean, plus underscores and hyphens. SQL adapters must use parameter binding for values and whitelist any dynamic identifiers such as sort columns or directions. External client rendering layers must HTML-escape display names, store descriptions, product titles, tags, and media labels before output. Query text and filter values must be parameterized; wildcard behavior for `ILIKE`/text search must be explicit and tested.

User-facing capability summary:

| User type | Allowed capabilities |
| --- | --- |
| Anonymous visitor | public store/product listing and detail, auth challenge request |
| Logged-in customer | own profile, own sessions, checkout/order creation and tracking, payment tx hash submission; no merchant/platform authority from login alone |
| Merchant staff/member | scoped merchant store reads, role-template-limited product and inventory operations |
| Merchant manager | merchant staff capabilities plus allowed business profile updates and staff invitations within merchant policy |
| Merchant owner | merchant manager capabilities plus owner-only store management requests within RBAC policy; owner transfer is not merchant self-service |
| Platform operator | operator dashboard/detail reads and bounded recovery actions |
| Platform admin | provisioning, RBAC/membership administration, sensitive approval flows |

Current implementation coverage that phase 22/23 must preserve or close:

| Area | Status | Current coverage | Phase 22/23 requirement |
| --- | --- | --- | --- |
| UUID identifiers | Implemented | Existing value objects validate UUID-like ids for users, stores, products, orders, payments, messages | Reuse value objects at new API boundaries |
| Wallet and transaction hashes | Implemented | Existing value objects validate EVM wallet address and tx hash shape | Reuse for profile/payment settings flows; do not accept raw unchecked strings |
| Crypto values | Implemented | Existing value objects validate non-negative finite amounts, positive chain ids, decimals, and token address shape | Keep checkout/payment validation separate from product profile display fields |
| SQL injection baseline | Partially implemented | Current PostgreSQL adapters use parameter binding; operator/catalog dynamic sort is allowlisted | New profile/catalog query adapters must parameterize values and whitelist dynamic identifiers |
| Request body and browser mutation guards | Implemented | Current HTTP/runtime contracts include body size, malformed JSON, CSRF, and idempotency handling for important mutations | New mutating APIs must use the same bounded body, CSRF, and idempotency policies where applicable |
| Text fields | Implemented | Profile/catalog text checks include bounded length, normalization, control/null rejection, log/CSV prefix guards, and escaped response fields | Preserve those checks at new profile/catalog boundaries |
| Email/URL/media/tag/category/JSON attributes | Implemented | Profile/catalog validation covers email shape, media URL/object-key shape, tag/category shape, JSON depth/count/size, and JSON-safe serialization | Keep search/index projection from weakening those data contracts |
| Merchant invitation/member role changes | Implemented | Merchant-scoped invitation/member APIs use role-template allowlists and last-owner protections | Keep owner transfer out of merchant self-service |
| Role/permission CRUD | Future scope | Not exposed | Keep seed/static in phase 22; expose only safe merchant role catalog and membership actions |

## Runtime Assumptions

- Local base URL: `https://localhost`
- Content type: `application/json`
- Response body는 JSON object다.
- 모든 response는 가능하면 `X-Request-Id` header를 포함한다.
- Client는 `X-Request-Id`를 전달할 수 있다. 없으면 server가 결정적 request id를 생성한다.
- 운영자 API는 server-side policy check의 `operator:read` 또는 `operator:action` permission이 필요하다. Recovery outbox retry에는 `outbox:retry`도 필요하다.
- 브라우저 client의 기본 auth transport는 `HttpOnly; Secure; SameSite=Lax` cookie다.
- 상태 변경 요청은 cookie auth와 함께 `X-CSRF-Token` double-submit token을 전달해야 한다.
- `Authorization: Bearer <accessToken>`은 non-browser client 또는 explicit integration fallback으로만 사용한다.
- `X-User-Id`, `X-User-Scopes` header는 local/dev fallback 전용이며 production/live path에서는 신뢰하지 않는다.

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

`SESSION_SIGNING_KEYS`는 `kid=secret,kid2=previous_secret` 또는 동등한 object 형태로 active key와 previous key를 함께 표현한다. New tokens are signed with the active key. Verification accepts the active key and configured previous keys until token expiry. Tokens must carry a `kid` or equivalent key id. Signed session token payloads use `sub`, `sessionId`, `walletAddress`, bounded `activeGroupId`/`groupMemberships`, `scopes`, `iat`, `exp`, `typ`, `jti`, and rotation metadata instead of global role authority. Missing signing keys or committed placeholder keys must make live/prod server startup fail with a bounded configuration error.

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

`GET /healthz` and `GET /readyz` are live server-only system routes and are not part of the 55-route public facade manifest. `/healthz` reports process/runtime health only and must not open PostgreSQL, Kafka, Blockchain, Docker, or local `.env`. `/readyz` summarizes injected PostgreSQL/Kafka/Blockchain readiness probes; unavailable components return `503` with bounded component details.

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
| `requestOAuthAuthorization` | `POST` | `/auth/oauth/{provider}/authorize` |
| `completeOAuthSession` | `POST` | `/auth/oauth/{provider}/sessions` |
| `linkOAuthIdentity` | `POST` | `/auth/oauth/{provider}/links` |
| `listOAuthIdentities` | `GET` | `/auth/oauth/identities` |
| `revokeOAuthIdentity` | `DELETE` | `/auth/oauth/identities/{oauthIdentityId}` |
| `requestWalletLinkChallenge` | `POST` | `/auth/wallets/challenges` |
| `linkWallet` | `POST` | `/auth/wallets` |
| `listWallets` | `GET` | `/auth/wallets` |
| `setPrimaryWallet` | `PATCH` | `/auth/wallets/{walletId}/primary` |
| `revokeWallet` | `DELETE` | `/auth/wallets/{walletId}` |
| `refreshSession` | `POST` | `/auth/sessions/refresh` |
| `logout` | `DELETE` | `/auth/sessions` |
| `getCurrentUser` | `GET` | `/auth/me` |
| `getCurrentUserProfile` | `GET` | `/auth/me/profile` |
| `updateCurrentUserProfile` | `PATCH` | `/auth/me/profile` |
| `createOrder` | `POST` | `/orders` |
| `getCheckoutTrackingByTrackingId` | `GET` | `/checkouts/tracking/{trackingId}` |
| `getCheckoutTrackingByOrderId` | `GET` | `/checkouts/orders/{orderId}` |
| `listUserPayments` | `GET` | `/payments` |
| `submitTransactionHash` | `POST` | `/payments/transaction-hashes` |
| `getStoreProfile` | `GET` | `/stores/{publicStoreId}` |
| `listPublicStores` | `GET` | `/stores` |
| `listPublicProducts` | `GET` | `/stores/{publicStoreId}/products` |
| `getPublicProduct` | `GET` | `/stores/{publicStoreId}/products/{publicProductId}` |
| `listMerchantStores` | `GET` | `/merchant/stores` |
| `updateStoreProfile` | `PATCH` | `/merchant/stores/{publicStoreId}/profile` |
| `createOrReuseStoreUser` | `POST` | `/admin/store-users` |
| `createStore` | `POST` | `/admin/stores` |
| `grantStoreMembership` | `POST` | `/admin/stores/{storeId}/memberships` |
| `listMerchantProducts` | `GET` | `/merchant/stores/{publicStoreId}/products` |
| `getMerchantProduct` | `GET` | `/merchant/stores/{publicStoreId}/products/{publicProductId}` |
| `registerStoreProduct` | `POST` | `/merchant/stores/{publicStoreId}/products` |
| `updateStoreProduct` | `PATCH` | `/merchant/stores/{publicStoreId}/products/{publicProductId}` |
| `listStoreOwnerInventory` | `GET` | `/store-owner/inventory` |
| `increaseStoreOwnerInventoryStock` | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/intake` |
| `correctStoreOwnerInventoryStock` | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/corrections` |
| `pauseStoreOwnerInventorySales` | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/pause` |
| `resumeStoreOwnerInventorySales` | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/resume` |
| `listMerchantStoreMembers` | `GET` | `/merchant/stores/{storeId}/members` |
| `listMerchantStoreInvitations` | `GET` | `/merchant/stores/{storeId}/invitations` |
| `createMerchantStoreInvitation` | `POST` | `/merchant/stores/{storeId}/invitations` |
| `acceptMerchantInvitation` | `POST` | `/merchant/invitations/{invitationId}/accept` |
| `revokeMerchantInvitation` | `POST` | `/merchant/invitations/{invitationId}/revoke` |
| `updateMerchantStoreMemberRole` | `PATCH` | `/merchant/stores/{storeId}/members/{userId}` |
| `removeMerchantStoreMember` | `DELETE` | `/merchant/stores/{storeId}/members/{userId}` |
| `getMerchantRoleCatalog` | `GET` | `/merchant/role-catalog` |
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

ERC-1271 verification은 configured auth chain RPC에서 signer wallet의 `eth_getCode` 결과가 deployed contract일 때만 적용된다. Contract wallet은 SIWE `personal_sign` digest와 signature를 `isValidSignature(bytes32,bytes)`로 검증하며, success magic value `0x1626ba7e`만 유효하다. Revert, wrong magic value, timeout, unsupported chain, undeployed/counterfactual account verification failure는 `401 INVALID_SIGNATURE` 또는 chain mismatch에 대한 bounded auth failure로 매핑된다. Authenticated linked wallet APIs reuse SIWE messages with `WALLET_LINK` challenge purpose. ERC-6492 counterfactual account deployment/signature wrapping remains future scope.

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
    "active": true,
    "lastLoginAt": "2026-05-17T10:00:00+09:00"
  },
  "session": {
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

### `POST /auth/oauth/{provider}/authorize`

Starts an OAuth/social login or link flow for a configured provider such as `google`. The server returns a provider authorization URL plus bounded state/PKCE metadata. `mode=link` requires an authenticated session because it will attach the provider-subject identity to the current user after callback exchange.

Request:

```json
{
  "redirectUri": "https://token-payments.local/oauth/callback",
  "mode": "login"
}
```

Response `201`:

```json
{
  "oauthAuthorization": {
    "provider": "google",
    "authorizationUrl": "https://accounts.google.com/o/oauth2/v2/auth?...",
    "state": "oauth-state",
    "mode": "login",
    "expiresAt": "2026-05-24T03:05:00+00:00",
    "pkceRequired": true
  }
}
```

Errors: `400 VALIDATION_ERROR`, `400 OAUTH_PROVIDER_UNSUPPORTED`, `401 AUTHENTICATION_REQUIRED`.

### `POST /auth/oauth/{provider}/sessions`

Completes an OAuth callback and creates a cookie/session for an already-linked provider-subject identity. This endpoint does not auto-merge accounts by email and does not create a walletless user from an email claim. A first-time social identity must be linked to an authenticated wallet-backed account through `POST /auth/oauth/{provider}/links`.

Request:

```json
{
  "code": "oauth-code",
  "state": "oauth-state",
  "redirectUri": "https://token-payments.local/oauth/callback",
  "deviceId": "browser-1"
}
```

Response `200`:

```json
{
  "user": {
    "userId": "user-001",
    "walletAddress": "0x1111111111111111111111111111111111111111",
    "active": true,
    "lastLoginAt": "2026-05-24T03:00:00+00:00"
  },
  "session": {
    "userId": "user-001",
    "walletAddress": "0x1111111111111111111111111111111111111111",
    "deviceId": "browser-1",
    "expiresAt": "2026-06-23T03:00:00+00:00",
    "revokedAt": null
  },
  "token": {
    "accessToken": "<set-cookie>",
    "refreshToken": "<set-cookie>",
    "expiresAt": "2026-05-24T04:00:00+00:00",
    "transport": "cookie"
  },
  "oauthIdentity": {
    "oauthIdentityId": "oauth-identity-001",
    "provider": "google",
    "userId": "user-001",
    "walletId": "wallet-001",
    "linkedAt": "2026-05-24T03:00:00+00:00",
    "revokedAt": null
  },
  "authentication": {
    "method": "OAUTH_PROVIDER_SUBJECT",
    "provider": "google"
  },
  "csrfToken": "csrf-token"
}
```

Errors: `400 VALIDATION_ERROR`, `400 OAUTH_PROVIDER_UNSUPPORTED`, `404 OAUTH_IDENTITY_NOT_LINKED`.

### `POST /auth/oauth/{provider}/links`

Links a provider-subject OAuth identity to the current authenticated user after callback code exchange. The request may include an owned `walletId` to record which verified wallet authorized the link. If the provider-subject identity is already active for another user, the server returns `409 OAUTH_IDENTITY_ALREADY_LINKED`.

Request:

```json
{
  "code": "oauth-code",
  "state": "oauth-state",
  "redirectUri": "https://token-payments.local/oauth/callback",
  "walletId": "wallet-001"
}
```

Response `201`:

```json
{
  "oauthIdentity": {
    "oauthIdentityId": "oauth-identity-001",
    "provider": "google",
    "userId": "user-001",
    "walletId": "wallet-001",
    "linkedAt": "2026-05-24T03:00:00+00:00",
    "revokedAt": null
  }
}
```

Errors: `400 VALIDATION_ERROR`, `400 OAUTH_PROVIDER_UNSUPPORTED`, `401 AUTHENTICATION_REQUIRED`, `404 WALLET_NOT_FOUND`, `409 OAUTH_IDENTITY_ALREADY_LINKED`.

### `GET /auth/oauth/identities`

Lists the current authenticated user's OAuth/social login identities. The response intentionally omits raw `providerSubject`, email claims, provider profile data, and OAuth tokens.

Response `200`:

```json
{
  "oauthIdentities": [
    {
      "oauthIdentityId": "oauth-identity-001",
      "provider": "google",
      "userId": "user-001",
      "walletId": "wallet-001",
      "linkedAt": "2026-05-24T03:00:00+00:00",
      "revokedAt": null
    }
  ]
}
```

Errors: `401 AUTHENTICATION_REQUIRED`.

### `DELETE /auth/oauth/identities/{oauthIdentityId}`

Soft-revokes a current user's OAuth/social login identity by setting `revokedAt`. The route refuses to remove the last active login method and must not hard-delete the identity row.

Response `200`:

```json
{
  "oauthIdentity": {
    "oauthIdentityId": "oauth-identity-001",
    "provider": "google",
    "userId": "user-001",
    "walletId": "wallet-001",
    "linkedAt": "2026-05-24T03:00:00+00:00",
    "revokedAt": "2026-05-24T03:05:00+00:00"
  }
}
```

Errors: `401 AUTHENTICATION_REQUIRED`, `404 OAUTH_IDENTITY_NOT_FOUND`, `409 LAST_LOGIN_METHOD_REVOKE_DENIED`.

### `POST /auth/wallets/challenges`

인증된 사용자가 추가 wallet을 연결하기 위한 SIWE v1 challenge를 발급한다. Login challenge와 같은 nonce repository를 쓰지만 `purpose`는 `WALLET_LINK`이고 `targetUserId`는 현재 authenticated user id로 고정된다. 이미 다른 active user에게 같은 `(chainId, walletAddress)` wallet이 연결되어 있으면 `409 WALLET_ALREADY_LINKED`를 반환한다.

Request:

```json
{
  "walletAddress": "0x2222222222222222222222222222222222222222",
  "domain": "token-payments.local",
  "uri": "https://token-payments.local",
  "chainId": 1337
}
```

Response `201`: same SIWE challenge shape as `POST /auth/challenges`, plus:

```json
{
  "purpose": "WALLET_LINK",
  "targetUserId": "user-001"
}
```

Errors: `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `409 WALLET_ALREADY_LINKED`.

### `POST /auth/wallets`

`requestWalletLinkChallenge`로 발급받은 SIWE message와 signature를 검증하고 wallet을 현재 authenticated user에게 연결한다. Server는 request body의 user id를 신뢰하지 않고 session actor와 challenge `targetUserId`가 같은지 확인한다. 같은 `(chainId, walletAddress)` active wallet은 한 user에게만 연결될 수 있다.

Request:

```json
{
  "walletAddress": "0x2222222222222222222222222222222222222222",
  "message": "<siwe-wallet-link-message>",
  "signature": "0xsignature",
  "walletType": "EOA"
}
```

Response `201`:

```json
{
  "wallet": {
    "walletId": "wallet-002",
    "userId": "user-001",
    "walletAddress": "0x2222222222222222222222222222222222222222",
    "chainId": 1337,
    "walletType": "EOA",
    "verificationStatus": "VERIFIED",
    "primary": false,
    "linkedAt": "2026-05-22T01:00:00+00:00",
    "revokedAt": null
  }
}
```

Errors: `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `401 INVALID_SIGNATURE`, `401 WALLET_MISMATCH`, `401 SIWE_MESSAGE_MISMATCH`, `409 WALLET_LINK_CHALLENGE_MISMATCH`, `409 WALLET_ALREADY_LINKED`.

### `GET /auth/wallets`

현재 authenticated user의 wallet 목록을 반환한다. Revoked wallet도 audit/history 표시를 위해 포함될 수 있으며 login/payment selection에는 `verificationStatus=VERIFIED` and `revokedAt=null`인 wallet만 사용할 수 있다.

Response `200`:

```json
{
  "wallets": [
    {
      "walletId": "wallet-001",
      "userId": "user-001",
      "walletAddress": "0x1111111111111111111111111111111111111111",
      "chainId": 1337,
      "walletType": "EOA",
      "verificationStatus": "VERIFIED",
      "primary": true,
      "linkedAt": "2026-05-17T10:00:00+09:00",
      "revokedAt": null
    }
  ]
}
```

Errors: `401 AUTHENTICATION_REQUIRED`.

### `PATCH /auth/wallets/{walletId}/primary`

현재 authenticated user가 소유한 verified active wallet만 chain-scoped primary로 지정할 수 있다. 같은 chain의 다른 active wallet은 primary에서 해제되고 다른 chain의 primary wallet은 유지된다.

Response `200`: same `{ "wallet": ... }` shape as `POST /auth/wallets`.

Errors: `401 AUTHENTICATION_REQUIRED`, `404 WALLET_NOT_FOUND`, `409 WALLET_NOT_ACTIVE`.

### `DELETE /auth/wallets/{walletId}`

현재 authenticated user가 소유한 wallet을 revoke한다. 마지막 verified active wallet revoke는 복구 정책이 없으므로 `409 LAST_WALLET_REVOKE_DENIED`로 거부한다. Revoke는 wallet audit event를 남기며 revoked wallet은 session refresh나 payment selection에 사용할 수 없다.

Response `200`: same `{ "wallet": ... }` shape as `POST /auth/wallets`, with `verificationStatus=REVOKED`.

Errors: `401 AUTHENTICATION_REQUIRED`, `404 WALLET_NOT_FOUND`, `409 WALLET_NOT_ACTIVE`, `409 LAST_WALLET_REVOKE_DENIED`.

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

Request: body 없음. Browser/public contract는 signed session cookie 또는 framework auth context에서 active `sessionId`를 추출한다. Cookie-auth mutating request는 `X-CSRF-Token`을 함께 보낸다.

Non-browser facade harness는 내부 request model에서 `sessionId` body를 전달할 수 있지만, public GitBook/OpenAPI reference에는 DELETE request body를 노출하지 않는다. OpenAPI tooling에서 DELETE body semantics가 portable하게 정의되지 않기 때문이다.

Response `200`:

```json
{
  "session": {
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
    "publicStoreId": "st_3c6a3ed15f8e1abf7d84",
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
    "paymentId": "payment-001",
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

`paymentId` is present once the payment request has been created. In live API wiring, `POST /orders` creates the initial `AWAITING_SIGNATURE` payment request in the same transaction, so the first successful tracking read for that order can return `pendingAction=SIGN_PAYMENT`, non-null `paymentRequest`, and non-null `gasEstimate`. If `pendingAction=WAIT_FOR_PAYMENT_REQUEST`, the frontend should keep polling and must not open MetaMask yet.

`gasEstimate.estimatedFee` is computed from JSON-RPC `eth_estimateGas * eth_gasPrice`. `gasEstimate.maxFee` is the buffered total fee using `ADAPTER_BLOCKCHAIN_GAS_BUFFER_RATE`; the API does not expose EIP-1559 per-gas fields such as `maxFeePerGas`.

Errors: `400 VALIDATION_ERROR`, `404 CHECKOUT_NOT_FOUND`.

## Payments

### `GET /payments`

사용자가 결제한 전체 내역을 조회한다. 결제 내역은 authenticated user ownership으로 필터링되며 다른 사용자의 주문/결제는 보이지 않는다.

Auth: customer user.

Request: body 없음. Query `status`는 comma-separated `PaymentStatus` 값(`AWAITING_SIGNATURE`, `SUBMITTED`, `CONFIRMING`, `CONFIRMED`, `FAILED`, `EXPIRED`, `REFUNDED`)을 받는다. `limit`은 `1..100` 범위이며 기본값은 `50`이다. Header `X-Request-Id`를 사용할 수 있고, local dev에서는 `X-User-Id` fallback을 사용할 수 있다.

Response `200`:

```json
{
  "payments": [
    {
      "paymentId": "payment-001",
      "orderId": "order-001",
      "trackingId": "tracking-001",
      "status": "SUBMITTED",
      "currentStep": "RECEIPT_PENDING",
      "pendingAction": "WAIT_FOR_RECEIPT",
      "amount": {"amount": "25.00", "symbol": "USDC", "chainId": 11155111, "tokenAddress": "0x3333333333333333333333333333333333333333", "decimals": 6},
      "chain": {"chainId": 11155111, "name": "Sepolia"},
      "paymentAssetId": "local-usdc",
      "txHash": "0xabababababababababababababababababababababababababababababababab",
      "receipt": null,
      "failureReason": null,
      "updatedAt": "2026-05-17T10:02:00+09:00"
    }
  ],
  "pagination": {"limit": 50, "nextPageToken": null}
}
```

Errors: `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`.

### `POST /payments/transaction-hashes`

MetaMask가 전송한 transaction hash를 제출한다.

Auth: customer user.

Request:

```json
{
  "trackingId": "tracking-001",
  "txHash": "0xtransactionhash"
}
```

`Idempotency-Key` header is recommended. If it is omitted, the bounded fallback command id is `payment.submit_tx:{trackingId}`. The request must not include `orderId` or `paymentId`; those internal identifiers are resolved server-side from the authenticated session and tracking id.

Response `202`:

```json
{
  "payment": {
    "trackingId": "tracking-001",
    "status": "TX_SUBMITTED",
    "currentStep": "RECEIPT_PENDING",
    "pendingAction": "WAIT_FOR_RECEIPT",
    "txHash": "0xtransactionhash",
    "updatedAt": "2026-05-17T10:02:00+09:00"
  }
}
```

Errors: `400 VALIDATION_ERROR`, `403 FORBIDDEN`, `404 PAYMENT_NOT_FOUND`, `404 AUTHORIZATION_NOT_FOUND`, `409 INVALID_STATE`.

## Operator Observability

Operator auth requires `operator:read`.

Local fallback headers:

```text
X-User-Id: admin-001
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

Operator auth requires `operator:action`. Outbox retry also requires `outbox:retry`.

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

Default PostgreSQL bootstrap uses `app/postgres/init.d/002-token-payments-default-seed.sh`. New postgres volumes run it after schema creation, and `docker compose up` also runs the idempotent `postgres_seed` one-shot service after postgres is healthy. The script inserts only the static RBAC catalog plus the local platform admin identity and memberships needed to authenticate as an admin. The admin wallet is controlled by `.env` `BOOTSTRAP_ADMIN_WALLET_ADDRESS` and defaults to `TEST_NETWORK_ACCOUNT` when left empty. User and group UUIDs are generated in PostgreSQL and then reused by lookup on later runs.

Manual seed data for local Postman examples is still described by `postman/fixtures/token-payments.local.seed-plan.json`. It references demo customer/store/product/inventory/payment destination/test network ids using committed PostgreSQL schema table and column names, but it is fixture metadata rather than the default init path. Route-level expected response examples live in `postman/expected/token-payments.api.expected.json`; the fixture covers auth, cookie/CSRF headers, `Idempotency-Key`, `X-Request-Id`, happy-path checkout, compensation cancellation, and operator action recovery while keeping signed token and cookie values redacted.

The Docker Compose API service is `token_payments_api`. Public local traffic goes through `nginx` on ports 80/443; `token_payments_api` only exposes port 8000 inside the compose network and does not publish a host port. Nginx access logs are disabled, nginx does not forward client IP headers, and the token API disables uvicorn access logs so user IP addresses are not stored in nginx or token API logs. Async checkout progress, including inventory reservation, auth RBAC projection, and payment receipt confirmation, is handled by `token_payments_live_worker`. The live worker belongs to both the `runtime` and `api` profiles, and the API service depends on it so API-profile local runs process outbox/Kafka work automatically. After `cp .env.example .env`, `COMPOSE_PROFILES=runtime,smoke,api` makes both services part of plain `docker compose up`; automated checks use daemon-less compose config and smoke plans and do not start Docker. Daemon-less compose config validation does not start Docker:

```bash
docker compose --env-file .env.example config --services
```

It runs `python -m token_payments serve-api --live --confirm-live-api` and must use env-backed session signing material: `SESSION_ACTIVE_KEY_ID` selects the active key, and `SESSION_SIGNING_KEYS` may retain a previous key only for bounded key rotation verification. The committed local dev signing values are valid only for `RUNTIME_ENVIRONMENT=local`; live/prod startup rejects committed local dev signing values. Browser auth is cookie-first through HttpOnly access/refresh cookies plus `X-CSRF-Token`; `Authorization: Bearer <accessToken>` is only a non-browser fallback. Credentialed CORS requires `CORS_ALLOW_CREDENTIALS=true` with an allowlisted origin, never wildcard credentials.

Postman Docker API readiness/security smoke is documented as a bounded local live plan. Automated verification runs only the dry-run/refusal path and does not start Docker or the API server. The plan covers API service start, session signing key validation, health/readiness, cookie auth, invalid/expired signature rejection, CSRF failure/success, credentialed CORS preflight, oversized body, malformed JSON, idempotency duplicate, checkout happy path, and operator action smoke.

Final local backend order for Postman Docker API readiness:

```bash
cp .env.example .env
docker compose --env-file .env config --services
docker compose --env-file .env build token_payments_api nginx
docker compose up -d
curl --fail --insecure https://localhost/healthz
curl --fail --insecure https://localhost/readyz
# Default DB bootstrap runs idempotently through postgres_seed after postgres is healthy.
# Optionally apply/review the manual Postman fixture plan in postman/fixtures/token-payments.local.seed-plan.json
# Import postman/token-payments.local.postman_collection.json and postman/token-payments.local.postman_environment.json
python3 scripts/docker_live_smoke.py --api-readiness --plan
python3 scripts/docker_live_smoke.py --api-readiness --execute --confirm-live-docker
docker compose down
```

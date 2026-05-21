# Domain Model

원본 다이어그램은 `diagram/DDD.drawio`의 `Order Service Domain Logic` 페이지다. 이 문서는 phase step이 다이어그램을 직접 열지 않아도 aggregate, value object, event, port 경계를 판단할 수 있도록 정리한 기준이다. When diagram/DDD.drawio conflicts with code package layout, code package layout wins.

## 공통 규칙

- Aggregate root만 repository로 직접 저장한다.
- Value Object는 불변으로 다룬다.
- Domain Event는 aggregate 상태 변경 후 outbox에 저장한다.
- 외부 시스템 호출은 domain model에서 직접 수행하지 않는다.
- `summary`, `error_message`, `blocked_reason`처럼 다음 자동 실행 판단에 쓰이는 텍스트는 구체적으로 남긴다.
- 신규 user/store/product/profile 입력값은 표시용 데이터일 뿐 SQL fragment, HTML, log line, CSV cell, permission descriptor로 신뢰하지 않는다. 기존 UUID, wallet, transaction hash, crypto amount, operator sort/limit, request body/idempotency/CSRF 방어는 유지하고, profile/catalog text/email/URL/tag/category/JSON validation은 phase 23에서 명시적으로 추가한다.

## 사용자 인증 Context

### Aggregates

| Aggregate | 주요 필드 | 주요 행위 |
| --- | --- | --- |
| `User` | `UserId`, `WalletAddress primaryWallet`, `active`, `lastLoginAt` | `registerByWallet`, `linkWallet`, `recordLogin`, `deactivate` |
| `LoginChallenge` | `WalletAddress`, `AuthNonce`, SIWE `domain`, `uri`, `chainId`, `ChallengeStatus`, `expiresAt` | `issue`, `verifySignature`, `expire` |
| `AuthSession` | `SessionId`, `UserId`, `WalletAddress`, `RefreshTokenHash`, `deviceId`, `expiresAt`, `revokedAt` | `create`, `rotateRefreshToken`, `revoke` |
| `Group` | `GroupId`, `GroupType`, optional `resourceType`, optional `resourceId`, `active` | permission scope/resource boundary |
| `GroupMembership` | `UserId`, `GroupId`, `RoleId`, `active`, `joinedAt` | user와 permission scope 연결 |
| `GroupInvitation` | `GroupId`, invite target, `RoleId`, `InvitationStatus`, `expiresAt`, `createdByUserId` | merchant membership invitation |
| `Role` | `RoleId`, `name`, `active` | permission bundle |
| `Permission` | `PermissionName`, `description` | API authorization source of truth |
| `RolePermission` | `RoleId`, `PermissionName` | role-permission mapping |

### Value Objects

- `UserId(UUID)`
- `WalletAddress(address, normalize)`
- `AuthNonce(value, expiresAt)`
- `IssuedToken(accessToken, refreshToken, expiresAt)`
- `GroupId`, `RoleId`, `PermissionName`
- `GroupType`: `PERSONAL`, `MERCHANT`, `PLATFORM`
- `InvitationStatus`: `PENDING`, `ACCEPTED`, `REVOKED`, `EXPIRED`
- `UserRole`: legacy compatibility only while phase 22 migrates. New authorization paths must not use `User.role`, `X-User-Role`, `STORE_OWNER`, or `ADMIN` as the permission source.
- `ChallengeStatus`: `ISSUED`, `VERIFIED`, `EXPIRED`, `REJECTED`
- `RefreshTokenHash(hash, salt, rotationVersion)`
- `LoginFailureReason`: `INVALID_SIGNATURE`, `EXPIRED_CHALLENGE`, `REUSED_NONCE`, `WALLET_MISMATCH`, `SIWE_MESSAGE_MISMATCH`

### RBAC Authorization Model

`User` is the authenticated identity and audit actor. `auth_users.role` column is legacy compatibility only; auth_users.role column is legacy compatibility only and is not the permission source for new execution paths. `Group` is not a user-like actor; it is a permission scope/resource boundary. `GroupMembership` connects a user to a group with a role, and `RolePermission` defines the permissions granted by that role. Nested groups are not part of the model.

`PERSONAL` groups are retained as a thin customer self-scope so customer behavior can be represented without a global `CUSTOMER` role. `MERCHANT` groups scope store owner/manager permissions to one store or merchant resource. `PLATFORM` groups scope operator/admin permissions.

Baseline permission catalog:

| Permission | Scope |
| --- | --- |
| `user:self` | own profile/session/order/checkout access |
| `user:manage` | platform-managed user profile status/detail access |
| `store:read` | merchant private store detail |
| `store:write` | store business profile fields |
| `store:manage` | sensitive store status/settings approval |
| `merchant_member:read` | merchant member/invitation listing |
| `merchant_member:invite` | merchant staff invitation create/revoke |
| `merchant_member:manage` | merchant staff role change/removal |
| `product:read` | merchant product detail/draft reads |
| `product:write` | product create/update |
| `inventory:read` | merchant inventory reads |
| `inventory:write` | stock intake/correction and sale pause/resume |
| `operator:read` | operator dashboard/detail reads |
| `operator:action` | operator recovery actions |
| `outbox:retry` | outbox retry execution |
| `rbac:manage` | group/membership/role management |
| `admin:provision` | platform bootstrap/provisioning |

Baseline role templates are seed/static catalog data. `PERSONAL_CUSTOMER` grants `user:self` in the personal group. `MERCHANT_OWNER`, `MERCHANT_MANAGER`, and `MERCHANT_STAFF` grant merchant-scoped permission bundles; merchant-facing APIs may choose only server-defined non-owner staff templates. `PLATFORM_OPERATOR` and `PLATFORM_ADMIN` are platform group templates and are never selectable through merchant/customer APIs. Full CRUD APIs for role/permission management are future surface; phase 22 focuses on schema, seed, session claims, policy checks, merchant membership/invitation APIs, and provisioning compatibility.

Merchant groups are created by store provisioning and linked to one store or merchant resource. Personal groups are auto-created at signup. Platform groups are seed/manual/admin-provisioned. Nested groups are not supported. Owner transfer is not a merchant self-service mutation; initial owner assignment and sensitive owner changes stay behind `admin:provision` or `rbac:manage` until a separate audited approval workflow exists.

### Events

- `UserRegisteredEvent(userId, wallet, createdAt)`
- `WalletVerifiedEvent(userId, wallet, verifiedAt)`
- `UserLoggedInEvent(userId, sessionId, loggedInAt)`
- `LoginRejectedEvent(wallet, reason, rejectedAt)`

### Ports and Adapters

- Input: `requestLoginChallenge` (SIWE challenge), `loginWithMetaMask` (SIWE login, operation name retained for route compatibility), `refreshSession`, `logout`, `getCurrentUser` (Adapter type: HTTP)
- Output: `UserRepository`, `LoginChallengeRepository`, `AuthSessionRepository`, `OutboxMessageRepository`, `WalletSignatureVerifier`, `TokenIssuer`, `AuthEventPublisher`
- Adapters: MetaMask wallet client, signature verifier, PostgreSQL repositories, optional Redis cache-aside/TTL storage
- Storage contract: PostgreSQL is the source of truth for auth users, login challenges, and sessions. Refresh reuse detection uses the PostgreSQL session repository hash/salt/rotation model. Redis is optional cache-aside/TTL optimization, not a live required dependency.

## 주문 생성 Context

### Aggregates

| Aggregate | 주요 필드 | 주요 행위 |
| --- | --- | --- |
| `Order` | `OrderId`, `CustomerId`, `StoreId`, `Address deliveryAddress`, `OrderItem[]`, `TrackingId`, `OrderStatus`, `PaymentId`, `failureMessages` | `validateOrder`, `initializeOrder`, `initPayment`, `confirmPayment`, `approve`, `initiateRefund`, `completeRefund`, `cancel` |
| `OrderItem` | `OrderItemId`, `OrderId`, `ProductSnapshot`, `quantity`, `Crypto subTotal` | 주문 내부 entity |
| `Store` | `StoreId`, `ownerUserId`, `Product[]`, `active`, `storeAddress`, `storeWallet`, `supportChain[]` | 상품/지원 체인 기준 검증 |
| `Product` | `ProductId`, `name`, `Crypto price` | `snapshot` |
| `Customer` | `CustomerId`, `UserId`, `WalletAddress customerWallet` | 고객 식별 |

### Value Objects

- `OrderId(UUID)`, `CustomerId(UUID)`, `StoreId(UUID)`, `ProductId(UUID)`, `OrderItemId(UUID)`, `TrackingId(UUID)`
- `Address(id, street)`
- `WalletAddress(address)`
- `OrderStatus`: `PENDING`, `PAID`, `APPROVED`, `CANCELLING`, `CANCELLED`
- `ProductSnapshot(productId, createdDate, name, Crypto price)`
- `Crypto(amount, symbol, chainId, tokenAddress, decimals)`
- `TransactionHash(hash)`
- `ChainNetwork(chainId, name)`

### Events

- `OrderCreatedEvent(order, createdAt)`
- `OrderPaidEvent(order, createdAt)`
- `OrderCancelledEvent(order, createdAt)`

### Ports and Adapters

- Input: `createOrder`, `trackOrder` (Adapter type: HTTP), payment/store/inventory response listeners (Adapter type: Kafka/message)
- Output: `OrderRepository`, `CheckoutProcessRepository`, `ProcessedMessageRepository`, `OutboxMessageRepository`, `CustomerRepository`, `StoreRepository`, `InventoryCommandPublisher`, `PaymentRequestPublisher`, `StoreApprovalRequestMessagePublisher`, `OrderCanceledPaymentRequestMessagePublisher`
- Adapters: Kafka + Outbox messaging, PostgreSQL repositories

`order.Store` is the order/catalog projection for order creation and checkout tracking. `order.Store` and `store_approval.Store` are not the same aggregate and must not share persistence or DTOs by default.

## Store Catalog Context

### Aggregates

| Aggregate | 주요 필드 | 주요 행위 |
| --- | --- | --- |
| `StoreProfile` | `StoreId`, `GroupId`, `displayName`, `description`, `status`, `supportEmail`, `businessRegistrationLabel`, `createdAt`, `updatedAt` | public/private business profile 보존 |
| `StorePaymentSettings` | `StoreId`, `storeWallet`, `supportedChainIds`, `active` | payment destination/chain 설정 보존 |
| `StoreMembership` | `StoreId`, `UserId`, store-scoped `role`, `active` | compatibility path; new authorization uses merchant group membership |
| `StoreProduct` | `StoreId`, `ProductId`, `title`, `description`, `category`, `tags`, `media`, `attributes`, `status`, `visibility`, `Crypto price` | canonical product catalog item |

### Value Objects

- `StoreMembershipRole`: `OWNER`, `MANAGER` compatibility only while merchant group RBAC migrates.
- `StoreId`, `ProductId`, `UserId`, `GroupId`, `WalletAddress`, `Crypto`

### Ports and Adapters

- Input: `createOrReuseStoreUser`, `createStore`, `grantStoreMembership`, `registerStoreProduct` (Adapter type: HTTP)
- Output: `CatalogWriteRepository`, catalog idempotency/audit persistence, checkout catalog projection writers, store approval projection writers, inventory projection writer
- Adapters: PostgreSQL canonical `store_catalog_stores`, `store_catalog_store_memberships`, `store_catalog_products`, write-through projection tables

`store_catalog` is the canonical store ownership and catalog source. `order_stores`, `order_store_products`, `store_approval_stores`, `store_approval_products`, and `product_inventory` remain runtime projections so existing checkout, approval, and inventory flows keep their read paths. A customer wallet can own/manage a store by adding merchant group membership for the existing `auth_users.user_id`; no duplicate wallet row or global role change is required.

Store business profile and payment settings are separate. `store:write` updates business profile fields such as display name, description, and support contact. Settlement wallet and supported chain changes are policy-gated payment settings flows, not public profile edits. Owner transfer, member invite/remove, and role/permission changes belong to RBAC/membership provisioning, not `updateStoreProfile`.

Store/product slug fields and SKU fields are not part of phase 23. Public and merchant lookup starts with stable `storeId` and `productId`; human-readable URLs and merchant-managed inventory codes are future scope. User display names, store display names, and product titles are display/search fields and may be duplicated.

Profile/catalog text is persisted as bounded data. Domain validation must reject or normalize empty required values, excessive length, control characters, null bytes, and log/CSV injection-prone prefixes where applicable. Persistence adapters must use parameter binding/JSON-safe serialization rather than string-built SQL values, and presentation adapters must escape text before HTML output.

## Checkout Process Manager

`CheckoutProcessManager`는 `app/token_payments/contexts/checkout/application/process_manager.py`에 위치한 별도 checkout saga/process manager다. Checkout Process is a separate saga/process context, not an order context submodule.

### 처리 이벤트

- `OrderCreated`
- `InventoryReserved`
- `PaymentConfirmed`
- `PaymentFailed`
- `PaymentExpired`
- `OrderApproved`
- `OrderRejected`

### 발행 커맨드

- `ReserveInventory`
- `InitiatePayment`
- `RequestStoreApproval`
- `ConfirmInventory`
- `ReleaseInventory`
- `RefundPayment`
- `CancelOrder`

### 멱등성

- 수신 메시지는 `ignoreProcessed(MessageId, OrderId)`로 중복 여부를 확인한다.
- 보상 커맨드는 `commandId = OrderId + action`으로 생성한다.
- 이미 종료된 주문에는 신규 업무 커맨드를 발행하지 않는다.

## 주문 승인 Context

### Aggregates

| Aggregate | 주요 필드 | 주요 행위 |
| --- | --- | --- |
| `Store` | `StoreId`, `ownerUserId`, `OrderDetail[]`, `Product[]`, `active` | `validateOwner`, `validateOrder`, `constructOrderApproval` |
| `OrderDetail` | `OrderId`, `OrderStatus`, `Crypto totalAmount`, `ProductSnapshot[]` | 승인 검증 대상 |
| `Product` | `ProductId`, `name`, `Crypto price`, `available` | `updateInfo` |

### Value Objects

- `ApprovalStatus`: `PENDING`, `APPROVED`, `REJECTED`
- `StoreId`, `OrderId`, `OrderStatus`, `Crypto`, `ProductSnapshot`

### Events

- `OrderApprovedEvent(order, createdAt)`
- `OrderRejectedEvent(order, rejectionReasons, createdAt)`

### Ports and Adapters

- Input: `approveOrder` / `request_store_approval` (Adapter type: Kafka/message)
- Output: `OrderDetailRepository`, `StoreRepository`, `ProductRepository`, `OutboxMessageRepository`, `OrderApprovedMessagePublisher`, `OrderRejectedMessagePublisher`
- Adapters: `StoreApprovalRequestListener`, Kafka + Outbox publishers, PostgreSQL repositories

`store_approval.Store` is an approval verification projection. `order.Store` and `store_approval.Store` are not the same aggregate and must not share persistence or DTOs by default.

## 결제 Context

### Aggregates

| Aggregate | 주요 필드 | 주요 행위 |
| --- | --- | --- |
| `Payment` | `PaymentId`, `OrderId`, `CustomerId`, `Crypto amount`, `PaymentStatus`, `walletFrom`, `walletTo`, `ChainNetwork`, `TransactionHash`, `GasEstimate`, `expiresAt` | `initializePayment`, `markAwaitingSignature`, `submitTxHash`, `confirmPayment`, `failPayment`, `expireAwaitingSignature`, `refundPayment` |
| `PaymentAuthorization` | `PaymentId`, `UserId`, `WalletAddress`, `ChainNetwork`, `TransactionSignatureRequest`, `AuthorizationStatus`, `authorizedAt` | `requestTransactionSignature`, `authorizeTxHash`, `expire` |
| `TransactionRecord` | `TransactionHash`, `Crypto amount`, `Crypto gasFee` | `toReceipt` |

### Value Objects

- `PaymentId(UUID)`, `UserId(UUID)`, `MessageId(UUID)`
- `PaymentStatus`: `INITIATED`, `AWAITING_SIGNATURE`, `SUBMITTED`, `CONFIRMING`, `CONFIRMED`, `FAILED`, `EXPIRED`, `REFUNDED`
- `AuthorizationStatus`: `REQUESTED`, `AUTHORIZED`, `EXPIRED`, `REJECTED`
- `WalletBalance(amount, lastUpdated)`
- `TransactionReceipt(hash, blockNum, gasUsed)`
- `GasPrice(gasPricePerUnit, gasLimit)`
- `GasEstimate(estimatedFee, gasLimit, bufferRate, maxFee, applyBuffer)`
- `TransactionSignatureRequest(requestId, amount, to, expiresAt)`
- `WalletSignature(message, signature, signer)`
- `BlockNumber(number)`
- `Crypto(amount, symbol, chainId, tokenAddress, decimals)`

### Events

- `PaymentProcessingStartedEvent(payment, createdAt)`
- `PaymentConfirmedEvent(paymentId, orderId, txHash, receipt, createdAt)`
- `PaymentFailedEvent(paymentId, orderId, failureReason, createdAt)`
- `PaymentRefundedEvent(paymentId, orderId, refundReceipt, createdAt)`
- `PaymentExpiredEvent(paymentId, orderId, reason, expiredAt)`

### Ports and Adapters

- Input: `getPaymentStatus` (Adapter type: HTTP), `initiatePayment`, `handleBlockchainCallback`, `verifyConnectedWallet`, `expireAwaitingSignaturePayments` (Adapter type: internal application)
- Output: `PaymentRepository`, `PaymentAuthorizationRepository`, `ProcessedCommandRepository`, `OutboxMessageRepository`, `PaymentTimeoutScheduler`, `BlockchainAdapter`, `PaymentEventPublisher`, `TransactionService`
- Adapters: Blockchain RPC, MetaMask client, PostgreSQL repositories, scheduler, outbox relay

## 재고관리 Context

### Aggregates

| Aggregate | 주요 필드 | 주요 행위 |
| --- | --- | --- |
| `ProductInventory` | `ProductId`, `StoreId`, `availableStock`, `reservedStock`, `totalStock`, `saleStatus`, `InventoryReservation[]` | `reserveInventory`, `releaseReservation`, `confirmReservation`, `increaseStock`, `correctTotalStock`, `pauseSales`, `resumeSales` |
| `InventoryReservation` | `ReservationId`, `OrderId`, `reservedQty`, `ReservationStatus`, `createdAt` | `confirm`, `cancel` |

### Value Objects

- `ReservationId(UUID)`, `ProductId(UUID)`, `StoreId(UUID)`, `OrderId(UUID)`
- `Quantity(value, isValid, add, subtract)`
- `ReservationStatus`: `PENDING`, `CONFIRMED`, `CANCELLED`
- `InventorySaleStatus`: `ACTIVE`, `PAUSED`

### Events

- `InventoryReservedEvent(inv, orderId, createdAt)`
- `InventoryConfirmedEvent(inv, orderId, createdAt)`
- `InventoryReleasedEvent(inv, orderId, createdAt)`
- `ReservationExpiredEvent(inv, reservationId, expiredAt)`
- `StockIncreasedEvent(inv, createdAt)`
- `StockDecreasedEvent(inv, createdAt)`

### Ports and Adapters

- Input: `reserveInventory` / `ReserveInventoryCommand`, `confirmReservation` / `ConfirmInventoryCommand`, `releaseReservation` / `ReleaseInventoryCommand`, `handleReservationTimeout` (Adapter type: internal application), `listStoreOwnerInventory`, `increaseStoreOwnerInventoryStock`, `correctStoreOwnerInventoryStock`, `pauseStoreOwnerInventorySales`, `resumeStoreOwnerInventorySales` (Adapter type: HTTP for store owner inventory API)
- Output: `InventoryRepository`, `InventoryQueryRepository`, `InventoryAuditRepository`, `ProcessedCommandRepository`, `OutboxMessageRepository`, `InventoryEventPublisher`, `OrderEventListener`, `PaymentEventListener`, `StoreRepository`
- Adapters: Kafka + Outbox messaging, PostgreSQL repositories

Product sale availability is stored canonically in the inventory context as `ProductInventory.saleStatus`. Store owners/managers are authorized by merchant group membership and `inventory:read`/`inventory:write`; a customer identity can manage its own store inventory through merchant membership without global role coercion. Platform cross-store access requires explicit operator/admin policy permission. Store approval/order catalog projections can consume this status in later projection work; this phase does not expose customer public inventory or manual order approval HTTP APIs.

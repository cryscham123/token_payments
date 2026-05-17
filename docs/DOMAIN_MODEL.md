# Domain Model

원본 다이어그램은 `diagram/DDD.drawio`의 `Order Service Domain Logic` 페이지다. 이 문서는 phase step이 다이어그램을 직접 열지 않아도 aggregate, value object, event, port 경계를 판단할 수 있도록 정리한 기준이다. When diagram/DDD.drawio conflicts with code package layout, code package layout wins.

## 공통 규칙

- Aggregate root만 repository로 직접 저장한다.
- Value Object는 불변으로 다룬다.
- Domain Event는 aggregate 상태 변경 후 outbox에 저장한다.
- 외부 시스템 호출은 domain model에서 직접 수행하지 않는다.
- `summary`, `error_message`, `blocked_reason`처럼 다음 자동 실행 판단에 쓰이는 텍스트는 구체적으로 남긴다.

## 사용자 인증 Context

### Aggregates

| Aggregate | 주요 필드 | 주요 행위 |
| --- | --- | --- |
| `User` | `UserId`, `WalletAddress primaryWallet`, `UserRole`, `active`, `lastLoginAt` | `registerByWallet`, `linkWallet`, `recordLogin`, `deactivate` |
| `LoginChallenge` | `WalletAddress`, `AuthNonce`, SIWE `domain`, `uri`, `chainId`, `ChallengeStatus`, `expiresAt` | `issue`, `verifySignature`, `expire` |
| `AuthSession` | `SessionId`, `UserId`, `WalletAddress`, `RefreshTokenHash`, `deviceId`, `expiresAt`, `revokedAt` | `create`, `rotateRefreshToken`, `revoke` |

### Value Objects

- `UserId(UUID)`
- `WalletAddress(address, normalize)`
- `AuthNonce(value, expiresAt)`
- `IssuedToken(accessToken, refreshToken, expiresAt)`
- `UserRole`: `CUSTOMER`, `STORE_OWNER`, `ADMIN`
- `ChallengeStatus`: `ISSUED`, `VERIFIED`, `EXPIRED`, `REJECTED`
- `RefreshTokenHash(hash, salt, rotationVersion)`
- `LoginFailureReason`: `INVALID_SIGNATURE`, `EXPIRED_CHALLENGE`, `REUSED_NONCE`, `WALLET_MISMATCH`, `SIWE_MESSAGE_MISMATCH`

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
| `ProductInventory` | `ProductId`, `StoreId`, `availableStock`, `reservedStock`, `totalStock`, `InventoryReservation[]` | `reserveInventory`, `releaseReservation`, `confirmReservation`, `increaseStock`, `decreaseStock` |
| `InventoryReservation` | `ReservationId`, `OrderId`, `reservedQty`, `ReservationStatus`, `createdAt` | `confirm`, `cancel` |

### Value Objects

- `ReservationId(UUID)`, `ProductId(UUID)`, `StoreId(UUID)`, `OrderId(UUID)`
- `Quantity(value, isValid, add, subtract)`
- `ReservationStatus`: `PENDING`, `CONFIRMED`, `CANCELLED`

### Events

- `InventoryReservedEvent(inv, orderId, createdAt)`
- `InventoryConfirmedEvent(inv, orderId, createdAt)`
- `InventoryReleasedEvent(inv, orderId, createdAt)`
- `ReservationExpiredEvent(inv, reservationId, expiredAt)`
- `StockIncreasedEvent(inv, createdAt)`
- `StockDecreasedEvent(inv, createdAt)`

### Ports and Adapters

- Input: `reserveInventory`, `confirmReservation`, `releaseReservation`, `handleReservationTimeout` (Adapter type: internal application), `getInventoryStatus`, `updateStock` (future Adapter type: HTTP for store owner inventory API)
- Output: `InventoryRepository`, `ProcessedCommandRepository`, `OutboxMessageRepository`, `InventoryEventPublisher`, `OrderEventListener`, `PaymentEventListener`, `StoreRepository`
- Adapters: Kafka + Outbox messaging, PostgreSQL repositories

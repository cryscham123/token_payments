# Sequence Flows

원본 sequence 다이어그램은 `diagram/DDD.drawio`의 `Checkout Payment Sequence`와 `MetaMask Login Sequence` 페이지다.

## Checkout Crypto Payment

### 참여자

- Customer Browser + MetaMask
- Order API
- CheckoutProcessManager
- Kafka
- Inventory Context
- Payment Context
- Blockchain RPC
- Store Approval Context

### 성공 흐름

1. Customer Browser가 `createOrder(authenticatedUser, command)`를 Order API에 호출한다.
2. Order API가 `Order(PENDING)`을 저장하고 `OrderCreatedEvent`를 outbox에 저장한다.
3. Kafka를 통해 `OrderCreatedEvent`가 전달되고, CheckoutProcessManager가 소비한다.
4. CheckoutProcessManager가 `ReserveInventoryCommand`를 outbox/Kafka로 발행한다.
5. Inventory Context가 `ReserveInventoryCommand`를 수신한다.
6. Inventory Context가 `reserveInventory()`를 수행하고 `InventoryReservedEvent`를 발행한다.
7. CheckoutProcessManager가 `InventoryReservedEvent`를 소비한다.
8. CheckoutProcessManager가 `InitiatePaymentCommand`를 발행한다.
9. Payment Context가 `InitiatePaymentCommand`를 수신한다.
10. Payment Context가 `Payment(AWAITING_SIGNATURE, expiresAt)`를 만들고 `paymentRequest + gasEstimate(buffered)`를 반환한다.
11. Customer Browser가 MetaMask 지갑 연결, nonce 서명, 결제 트랜잭션 전송을 진행한다.
12. Customer Browser가 `txHash`를 Payment Context에 제출하고, Payment가 `SUBMITTED`로 전이한다.
13. Payment Context가 Blockchain RPC에 `monitorTransaction(txHash)`를 호출한다.
14. Blockchain RPC가 confirmed receipt를 반환한다.
15. Payment Context가 `PaymentConfirmedEvent`를 발행한다.
16. CheckoutProcessManager가 `PaymentConfirmedEvent`를 소비한다.
17. CheckoutProcessManager가 `RequestStoreApprovalCommand`를 발행한다.
18. Store Approval Context가 주문을 검증하고 승인한다.
19. Store Approval Context가 `OrderApprovedEvent`를 발행한다.
20. Order API 또는 주문 context listener가 주문을 `APPROVED`로 완료한다.

### 트랜잭션 규칙

- 각 context는 aggregate 저장과 outbox row 저장을 같은 트랜잭션으로 커밋한다.
- Outbox Relay만 Kafka 발행을 담당한다.
- 발행 완료 후 outbox row는 `markPublished(MessageId)`로 표시한다.

### 실패/보상 흐름

| 이벤트 | 후속 처리 |
| --- | --- |
| `PaymentFailedEvent` | CheckoutProcessManager가 `ReleaseInventoryCommand`와 `CancelOrderCommand`를 발행한다 |
| `PaymentExpiredEvent` | CheckoutProcessManager가 `ReleaseInventoryCommand`와 `CancelOrderCommand`를 발행한다 |
| `OrderRejectedEvent` | CheckoutProcessManager가 `RefundPaymentCommand`, `ReleaseInventoryCommand`, `CancelOrderCommand`를 발행한다 |
| 중복 `MessageId` | 이미 처리된 메시지로 판단하고 추가 커맨드를 발행하지 않는다 |

보상 커맨드는 결정적 `commandId = OrderId + action`을 사용한다. 재시도 시에도 같은 command id가 사용되어 환불, 재고 해제, 주문 취소가 중복 실행되지 않아야 한다.

## MetaMask Login

### 참여자

- Customer Browser + MetaMask
- Auth API
- 사용자 인증 Context
- Signature Verifier
- User / Session Storage

### 성공 흐름

1. Customer Browser가 `connectWallet()`을 실행하고 계정을 선택한다.
2. Customer Browser가 `requestLoginChallenge(walletAddress)`를 Auth API에 호출한다.
3. 사용자 인증 Context가 `LoginChallenge(nonce, expiresAt)`를 발급한다.
4. 인증 저장소가 nonce를 `ISSUED` 상태로 저장한다.
5. Auth API가 서명할 login message를 Customer Browser에 반환한다.
6. Customer Browser가 MetaMask `personal_sign(login message)`를 실행한다.
7. Customer Browser가 `loginWithMetaMask(wallet, message, signature)`를 호출한다.
8. 사용자 인증 Context가 `verifyLoginSignature(wallet, message, signature)`를 수행한다.
9. Signature Verifier가 `recoverAddress(message, signature)`를 수행한다.
10. 복구된 주소와 요청 wallet 주소를 정규화 후 비교한다.
11. 검증 성공 시 challenge를 `VERIFIED`로 표시하고, `User`를 생성/조회한 뒤 `AuthSession`을 만든다.
12. Auth API가 `IssuedToken + current user`를 반환한다.

### 보안 가드레일

- wallet address는 저장/비교 전 정규화한다.
- nonce는 1회만 사용할 수 있다.
- challenge 만료를 반드시 확인한다.
- 서명 메시지에는 domain, chainId, issuedAt, nonce, wallet address를 포함한다.
- 토큰은 `UserId`와 `WalletAddress`를 claim으로 가진다.
- 실패 사유는 `INVALID_SIGNATURE`, `EXPIRED_CHALLENGE`, `REUSED_NONCE`, `WALLET_MISMATCH` 중 하나로 구조화한다.

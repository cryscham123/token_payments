# API Spec: Token Payments

이 문서는 `14-live-api-runtime-composition`과 `15-postman-docker-api-readiness`가 끝난 뒤의 로컬 backend API를 기준으로 한 최종 명세 초안이다. Route surface는 현재 `app/token_payments/api/http.py`의 route manifest 16개를 기준으로 고정한다.

## Runtime Assumptions

- Local base URL: `http://localhost:8000`
- Content type: `application/json`
- Response body는 JSON object다.
- 모든 response는 가능하면 `X-Request-Id` header를 포함한다.
- Client는 `X-Request-Id`를 전달할 수 있다. 없으면 server가 결정적 request id를 생성한다.
- 운영자 API는 server-side session claim의 `ADMIN` role이 필요하다.
- 브라우저 client의 기본 auth transport는 `HttpOnly; Secure; SameSite=Lax` cookie다.
- 상태 변경 요청은 cookie auth와 함께 CSRF token을 전달해야 한다.
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

Login/refresh 성공 시 server는 access/refresh cookie를 `Set-Cookie`로 내려준다.

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

New tokens are signed with the active key. Verification accepts the active key and configured previous keys until token expiry. Tokens must carry a `kid` or equivalent key id. Missing signing keys or committed placeholder keys must make live server startup fail with a bounded configuration error.

Session signing keys, signed token values, refresh token hashes, and CSRF secrets must never be logged or committed in fixtures.

Cookie-authenticated mutating requests must include `X-CSRF-Token`. Missing or invalid CSRF token returns `403` with one of:

- `CSRF_TOKEN_MISSING`
- `CSRF_TOKEN_INVALID`

Credentialed CORS must use an origin allowlist. `Access-Control-Allow-Origin: *` must not be used with credentials.

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
| `getOperatorDashboard` | `GET` | `/operator/dashboard` |
| `getOperatorOrderDetail` | `GET` | `/operator/orders/{orderId}` |
| `getOperatorPaymentDetail` | `GET` | `/operator/payments/{paymentId}` |
| `getOperatorOutboxDetail` | `GET` | `/operator/outbox/{messageId}` |
| `cancelOperatorOrder` | `POST` | `/operator/orders/{orderId}/cancel` |
| `retryOperatorOutboxMessage` | `POST` | `/operator/outbox/{messageId}/retry` |
| `replayOperatorMessage` | `POST` | `/operator/messages/{messageId}/replay` |

## Auth

### `POST /auth/challenges`

MetaMask 서명용 nonce challenge를 발급한다.

Request:

```json
{
  "walletAddress": "0x1111111111111111111111111111111111111111",
  "domain": "token-payments.local",
  "chainId": 1337
}
```

Response `201`:

```json
{
  "walletAddress": "0x1111111111111111111111111111111111111111",
  "nonce": "nonce-001",
  "expiresAt": "2026-05-17T10:30:00+09:00",
  "signingMessage": "Sign in to token-payments.local with nonce nonce-001"
}
```

Errors: `400 VALIDATION_ERROR`.

### `POST /auth/sessions`

MetaMask `personal_sign` 결과로 session/token을 발급한다.

Request:

```json
{
  "walletAddress": "0x1111111111111111111111111111111111111111",
  "message": "Sign in to token-payments.local with nonce nonce-001",
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
    "accessToken": "access-token",
    "refreshToken": "refresh-token",
    "expiresAt": "2026-05-17T11:00:00+09:00"
  }
}
```

Errors: `400 VALIDATION_ERROR`, `401 INVALID_SIGNATURE`, `401 WALLET_MISMATCH`, `409 EXPIRED_CHALLENGE`, `409 REUSED_NONCE`.

### `POST /auth/sessions/refresh`

Refresh token으로 session token을 회전한다.

Final public request:

```json
{
  "sessionId": "session-001",
  "refreshToken": "refresh-token"
}
```

Current harness facade may still model refresh token hash internally:

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

Operator auth: `ADMIN`.

Local fallback headers:

```text
X-User-Id: admin-001
X-User-Role: ADMIN
X-User-Scopes: operator:read,operator:write
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

Operator auth: `ADMIN`.

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

Phase 15 should add committed Postman collection/examples, seed data, and expected response fixtures for this flow.

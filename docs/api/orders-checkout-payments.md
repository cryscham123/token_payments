# 주문, 체크아웃, 결제

주문과 결제 API는 public customer/browser surface다. 내부 `order_id`, `customer_id`, payment primary key를 public response에 노출하지 않고, checkout 추적과 결제 제출은 `trackingId`를 중심으로 연결한다.

## Route

빠른 참조: `POST /orders`, `GET /checkouts/tracking/{trackingId}`, `GET /checkouts/orders/{orderId}`, `POST /payments/transaction-hashes`.

| 목적 | Method | Path | 요청 |
| --- | --- | --- | --- |
| 주문 생성 | `POST` | `/orders` | `publicStoreId`, item 목록, `paymentAssetId`, optional `walletId` |
| tracking id로 checkout 조회 | `GET` | `/checkouts/tracking/{trackingId}` | active session owner scope |
| order id로 checkout 조회 | `GET` | `/checkouts/orders/{orderId}` | 내부 호환 조회, owner scope |
| transaction hash 제출 | `POST` | `/payments/transaction-hashes` | `trackingId`, `txHash`, optional client metadata |

## 주문 생성

`POST /orders`는 client가 전달한 상품명, 가격, 재고, chain, asset 값을 신뢰하지 않는다. 서버가 현재 store/product/price/inventory/payment capability를 다시 확인한 뒤 주문과 checkout authorization을 만든다.

응답에는 `orderId`, `trackingId`, `publicStoreId`처럼 public API에서 추적 가능한 값만 포함한다. `customerId`, 내부 `storeId`, 내부 payment id는 response에 포함하지 않는다.

## Checkout tracking

`GET /checkouts/tracking/{trackingId}`는 사용자가 자신의 checkout 상태를 조회하는 기본 API다. 결제 대기, txHash 제출 여부, confirmation 상태, store approval 결과를 bounded 상태값으로 반환한다.

`GET /checkouts/orders/{orderId}`는 현재 route manifest에 포함되어 있지만, 신규 client는 가능한 한 `trackingId` 기반 조회를 우선한다.

## 결제 제출

`POST /payments/transaction-hashes`는 결제 transaction hash를 제출한다. 요청 body에는 raw `orderId` 대신 `trackingId`를 사용하며, idempotency fallback key도 `payment.submit_tx:{trackingId}` 형태를 사용한다.

```json
{
  "trackingId": "trk_001",
  "txHash": "0xabababababababababababababababababababababababababababababababab"
}
```

결제 API는 session ownership을 먼저 확인한 뒤 내부 order/payment id를 resolution한다. 실패 응답은 validation, unauthorized, conflict, not found 범주로 제한한다.

## Endpoint 상세

| Endpoint | 인증/권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- |
| `POST /orders` | active customer session | JSON body: `publicStoreId` 또는 호환 `storeId`, `deliveryAddress`, `items[]`, optional `paymentAssetId`, optional `walletId`; header `Idempotency-Key` 권장 | `201` `order` with `orderId`, `trackingId`, `publicStoreId`, `status`, `deliveryAddress`, `totalAmount`, `items[]`; `customerId`와 내부 `storeId`는 제외 | `400 VALIDATION_ERROR`, `404 CUSTOMER_NOT_FOUND`, `404 STORE_NOT_FOUND`, `409 INVENTORY_UNAVAILABLE`, `409 PAYMENT_ASSET_UNSUPPORTED` |
| `GET /checkouts/tracking/{trackingId}` | active customer session, checkout owner | path `trackingId` | `200` `checkout` with `trackingId`, `status`, `currentStep`, `pendingAction`, optional `paymentRequest`, `gasEstimate`, `txHash`, `outboxStatus` | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 CHECKOUT_NOT_FOUND` |
| `GET /checkouts/orders/{orderId}` | active customer session, checkout owner | path `orderId`; 신규 client는 `trackingId` 조회 우선 | `200` same `checkout` envelope as tracking lookup | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 CHECKOUT_NOT_FOUND` |
| `POST /payments/transaction-hashes` | active customer session, checkout owner | JSON body: `trackingId`, `txHash`; header `Idempotency-Key` 권장. `orderId`/`paymentId` body는 받지 않음 | `202` `payment` with `trackingId`, `status=TX_SUBMITTED`, `currentStep=RECEIPT_PENDING`, `pendingAction=WAIT_FOR_RECEIPT`, `txHash`, `updatedAt` | `400 VALIDATION_ERROR`, `403 FORBIDDEN`, `404 PAYMENT_NOT_FOUND`, `404 AUTHORIZATION_NOT_FOUND`, `409 INVALID_STATE` |

## 응답 예시

Checkout tracking:

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
      "amount": {"amount": "20.000000000000000000", "symbol": "ETH", "chainId": 1337},
      "to": "0x2222222222222222222222222222222222222222",
      "expiresAt": "2026-05-17T10:15:00+09:00"
    },
    "txHash": null
  }
}
```

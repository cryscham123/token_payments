# 상점과 상품 카탈로그

카탈로그 API는 public customer read surface와 merchant write/read surface를 분리한다. public API는 `publicStoreId`, `publicProductId`만 사용하고 내부 `store_id`, `product_id`, settlement wallet 값은 노출하지 않는다.

## Public store/product route

빠른 참조: `GET /stores`, `GET /stores/{publicStoreId}`, `GET /stores/{publicStoreId}/products`, `GET /stores/{publicStoreId}/products/{publicProductId}`.

| 목적 | Method | Path | 요청 |
| --- | --- | --- | --- |
| public store 목록 | `GET` | `/stores` | optional query filter |
| public store profile 조회 | `GET` | `/stores/{publicStoreId}` | public store id |
| public product 목록 | `GET` | `/stores/{publicStoreId}/products` | category, tag, query, pagination |
| public product 상세 | `GET` | `/stores/{publicStoreId}/products/{publicProductId}` | public product id |

public response는 display profile, availability, display price, accepted payment asset summary를 반환한다. settlement wallet, private support contact, 내부 UUID primary key는 반환하지 않는다.

## Merchant product route

빠른 참조: `GET /merchant/stores/{publicStoreId}/products`, `GET /merchant/stores/{publicStoreId}/products/{publicProductId}`, `POST /merchant/stores/{publicStoreId}/products`, `PATCH /merchant/stores/{publicStoreId}/products/{publicProductId}`.

| 목적 | Method | Path | 권한 |
| --- | --- | --- | --- |
| merchant product 목록 | `GET` | `/merchant/stores/{publicStoreId}/products` | `product:read` |
| merchant product 상세 | `GET` | `/merchant/stores/{publicStoreId}/products/{publicProductId}` | `product:read` |
| product 등록 | `POST` | `/merchant/stores/{publicStoreId}/products` | `product:write` |
| product 상세 수정 | `PATCH` | `/merchant/stores/{publicStoreId}/products/{publicProductId}` | `product:write` |

`POST /merchant/stores/{publicStoreId}/products`는 checkout 가능한 catalog product를 등록한다. command는 canonical product catalog, checkout product projection, approval product projection, product inventory를 하나의 transaction 경계에서 생성한다.

`PATCH /merchant/stores/{publicStoreId}/products/{publicProductId}`는 상품 설명, category, tag, media, visibility 같은 catalog detail만 수정한다. 재고 수량과 판매 중지는 inventory API에서 처리한다.

## Store owner inventory route

빠른 참조: `GET /store-owner/inventory`, `POST /store-owner/stores/{storeId}/inventory/{productId}/intake`, `POST /store-owner/stores/{storeId}/inventory/{productId}/corrections`, `POST /store-owner/stores/{storeId}/inventory/{productId}/pause`, `POST /store-owner/stores/{storeId}/inventory/{productId}/resume`.

| 목적 | Method | Path | 권한 |
| --- | --- | --- | --- |
| inventory 목록 | `GET` | `/store-owner/inventory` | `inventory:read` |
| stock intake | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/intake` | `inventory:write` |
| target total correction | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/corrections` | `inventory:write` |
| sale pause | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/pause` | `inventory:write` |
| sale resume | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/resume` | `inventory:write` |

inventory mutation 요청은 active merchant membership, permission, `Idempotency-Key`, CSRF, `reason`을 요구한다. stock correction은 `totalStock`을 `reservedStock`보다 낮게 만들 수 없다. sale pause/resume은 신규 주문 가능성만 바꾸며 기존 reservation을 해제하지 않는다.

## Endpoint 상세

| Endpoint | 인증/권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- |
| `GET /stores` | anonymous | optional query filter, pagination | `200` `stores[]` with public profile fields and bounded payment capability summary | `400 VALIDATION_ERROR` |
| `GET /stores/{publicStoreId}` | anonymous | path `publicStoreId` | `200` `store` with `publicStoreId`, display fields, optional public `supportEmail`; internal store keys 제외 | `404 STORE_NOT_FOUND` |
| `GET /stores/{publicStoreId}/products` | anonymous | path `publicStoreId`; query `category`, `tag`, `q`, `sort`, `limit`, `offset` | `200` `products[]` with `publicProductId`, display price, availability, accepted asset summary | `400 VALIDATION_ERROR`, `404 STORE_NOT_FOUND` |
| `GET /stores/{publicStoreId}/products/{publicProductId}` | anonymous | path `publicStoreId`, `publicProductId` | `200` `product` public detail; internal `product_id`/`store_id` 제외 | `404 STORE_NOT_FOUND`, `404 PRODUCT_NOT_FOUND` |
| `GET /merchant/stores/{publicStoreId}/products` | active merchant session, `product:read` | path `publicStoreId`; bounded filters for status, visibility, category, tag, query, sort, limit, offset | `200` merchant `products[]`, private/inactive catalog 포함 가능 | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 STORE_NOT_FOUND` |
| `GET /merchant/stores/{publicStoreId}/products/{publicProductId}` | active merchant session, `product:read` | path `publicStoreId`, `publicProductId` | `200` merchant `product` detail including draft/private fields allowed by scope | `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 PRODUCT_NOT_FOUND` |
| `POST /merchant/stores/{publicStoreId}/products` | active merchant session, `product:write` | JSON body: title, description, category, tags, media, attributes, price/payment display data, initial inventory fields as supported; CSRF for browser auth | `201` `product` with stable `publicProductId`; canonical product and inventory projections created transactionally | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 STORE_NOT_FOUND`, `409 PRODUCT_CONFLICT` |
| `PATCH /merchant/stores/{publicStoreId}/products/{publicProductId}` | active merchant session, `product:write` | JSON body: catalog detail fields only. Inventory stock/sale status 제외 | `200` updated `product` | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 PRODUCT_NOT_FOUND`, `409 PRODUCT_CONFLICT` |
| `GET /store-owner/inventory` | active merchant session with `inventory:read`; platform needs explicit inventory/operator permission | optional `storeId` filter | `200` `inventory[]` rows visible to membership scope | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN` |
| `POST /store-owner/stores/{storeId}/inventory/{productId}/intake` | active merchant session, `inventory:write` | path `storeId`, `productId`; JSON body `quantity`, `reason`; headers `Idempotency-Key`, `X-CSRF-Token` for browser | `202` accepted inventory command/audit result | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 INVENTORY_NOT_FOUND`, `409 INVALID_INVENTORY_STATE` |
| `POST /store-owner/stores/{storeId}/inventory/{productId}/corrections` | active merchant session, `inventory:write` | JSON body `totalStock`, `reason`; `totalStock >= reservedStock` 필요 | `202` accepted inventory correction result | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 INVENTORY_NOT_FOUND`, `409 STOCK_BELOW_RESERVED` |
| `POST /store-owner/stores/{storeId}/inventory/{productId}/pause` | active merchant session, `inventory:write` | JSON body `reason`; headers `Idempotency-Key`, `X-CSRF-Token` for browser | `202` sale paused for new orders | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 INVENTORY_NOT_FOUND`, `409 INVALID_INVENTORY_STATE` |
| `POST /store-owner/stores/{storeId}/inventory/{productId}/resume` | active merchant session, `inventory:write` | JSON body `reason`; headers `Idempotency-Key`, `X-CSRF-Token` for browser | `202` sale resumed for new orders | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 INVENTORY_NOT_FOUND`, `409 INVALID_INVENTORY_STATE` |

## 요청 예시

Product 등록:

```json
{
  "title": "Demo Product",
  "description": "checkout 가능한 테스트 상품",
  "category": "demo",
  "tags": ["demo", "stablecoin"],
  "visibility": "PUBLIC",
  "status": "ACTIVE"
}
```

Inventory intake:

```json
{
  "quantity": 10,
  "reason": "new stock arrival"
}
```

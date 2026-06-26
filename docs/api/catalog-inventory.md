# 상점과 상품 카탈로그

카탈로그 API는 public customer read surface와 merchant write/read surface를 분리한다. public API는 `publicStoreId`, `publicProductId`만 사용하고 내부 `store_id`, `product_id`, settlement wallet 값은 노출하지 않는다.

## Public store/product route

빠른 참조: `GET /stores`, `GET /stores/{publicStoreId}`, `GET /stores/{publicStoreId}/products`, `GET /stores/{publicStoreId}/products/{publicProductId}`, `GET /product-assets/{publicStoreId}/{assetFile}`.

| 목적 | Method | Path | 요청 |
| --- | --- | --- | --- |
| public store 목록 | `GET` | `/stores` | optional query filter |
| public store profile 조회 | `GET` | `/stores/{publicStoreId}` | public store id |
| public product 목록 | `GET` | `/stores/{publicStoreId}/products` | category, tag, query, pagination |
| public product 상세 | `GET` | `/stores/{publicStoreId}/products/{publicProductId}` | public product id |
| product asset 조회 | `GET` | `/product-assets/{publicStoreId}/{assetFile}` | uploaded product image/PDF asset file |

public response는 display profile, availability, display price, accepted payment asset summary를 반환한다. settlement wallet, private support contact, 내부 UUID primary key는 반환하지 않는다.

## Merchant product route

빠른 참조: `GET /merchant/stores/{publicStoreId}/products`, `GET /merchant/stores/{publicStoreId}/products/{publicProductId}`, `POST /merchant/stores/{publicStoreId}/assets`, `POST /merchant/stores/{publicStoreId}/products`, `PATCH /merchant/stores/{publicStoreId}/products/{publicProductId}`.

| 목적 | Method | Path | 권한 |
| --- | --- | --- | --- |
| merchant product 목록 | `GET` | `/merchant/stores/{publicStoreId}/products` | `product:read` |
| merchant product 상세 | `GET` | `/merchant/stores/{publicStoreId}/products/{publicProductId}` | `product:read` |
| product asset 업로드 | `POST` | `/merchant/stores/{publicStoreId}/assets` | `product:write` |
| product 등록 | `POST` | `/merchant/stores/{publicStoreId}/products` | `product:write` |
| product 상세 수정 | `PATCH` | `/merchant/stores/{publicStoreId}/products/{publicProductId}` | `product:write` |

`POST /merchant/stores/{publicStoreId}/assets`는 product image 또는 product detail PDF bytes를 JSON base64 payload로 업로드하고 내부 `asset.mediaRef`를 반환한다. 서버는 `assetType`, `contentType`, decoded byte size, magic bytes, idempotency key, active merchant membership을 검증한다. 상품 이미지에는 반환된 `asset.mediaRef`를 `media[]`에 저장하고, 상품 상세 PDF에는 반환된 `asset.mediaRef`를 `attributes.detailPdfAssetKey`에 저장한다.

`POST /merchant/stores/{publicStoreId}/products`는 checkout 가능한 catalog product를 등록한다. command는 canonical product catalog, checkout product projection, approval product projection, product inventory를 하나의 transaction 경계에서 생성한다. 요청은 `options[]`와 `variants[]`를 받을 수 있다. `VARIANT` 옵션은 필수 옵션 조합과 variant 재고 단위를 정의하고, `ADD_ON` 옵션은 선택 옵션으로 저장된다. option value와 variant는 각각 `priceDelta`를 가질 수 있으며, variant별 초기 재고는 `variants[].initialTotalStock`으로 지정한다. 상품 상세 PDF는 `attributes.detailPdfAssetKey`에 내부 asset key로 저장한다.

`PATCH /merchant/stores/{publicStoreId}/products/{publicProductId}`는 상품 설명, category, tag, media, visibility, 옵션/variant 구성 같은 catalog detail을 수정한다. 요청에 `options` 또는 `variants`가 포함되면 해당 상품의 옵션 구성을 요청 payload 기준으로 교체한다. 재고 수량과 판매 중지는 inventory API에서 처리하며, merchant dashboard의 variant별 입고도 `/store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/intake`를 사용한다. `media`는 HTTPS/IPFS URL 또는 object key 참조만 저장하고, 브라우저 파일 업로드의 base64 data URL은 `StoreProduct.media`에 저장하지 않는다.

## Store owner inventory route

빠른 참조: `GET /store-owner/inventory`, `POST /store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/intake`, `POST /store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/corrections`, `POST /store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/pause`, `POST /store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/resume`.

| 목적 | Method | Path | 권한 |
| --- | --- | --- | --- |
| inventory 목록 | `GET` | `/store-owner/inventory` | `inventory:read` |
| stock intake | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/intake` | `inventory:write` |
| target total correction | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/corrections` | `inventory:write` |
| sale pause | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/pause` | `inventory:write` |
| sale resume | `POST` | `/store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/resume` | `inventory:write` |

inventory mutation 요청은 active merchant membership, permission, `Idempotency-Key`, CSRF, path `publicVariantId`, `reason`을 요구한다. 재고 수량과 판매 상태는 항상 variant 단위로 변경한다. stock correction은 해당 variant의 `totalStock`을 `reservedStock`보다 낮게 만들 수 없다. sale pause/resume은 신규 주문 가능성만 바꾸며 기존 reservation을 해제하지 않는다.

## Endpoint 상세

| Endpoint | 인증/권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- |
| `GET /stores` | anonymous | optional query filter, pagination | `200` `stores[]` with public profile fields and bounded payment capability summary | `400 VALIDATION_ERROR` |
| `GET /stores/{publicStoreId}` | anonymous | path `publicStoreId` | `200` `store` with `publicStoreId`, display fields, optional public `supportEmail`; internal store keys 제외 | `404 STORE_NOT_FOUND` |
| `GET /stores/{publicStoreId}/products` | anonymous | path `publicStoreId`; query `category`, `tag`, `q`, `sort`, `limit`, `offset` | `200` `products[]` with `publicProductId`, display price, availability, accepted asset summary | `400 VALIDATION_ERROR`, `404 STORE_NOT_FOUND` |
| `GET /stores/{publicStoreId}/products/{publicProductId}` | anonymous | path `publicStoreId`, `publicProductId` | `200` `product` public detail; internal `product_id`/`store_id` 제외 | `404 STORE_NOT_FOUND`, `404 PRODUCT_NOT_FOUND` |
| `GET /product-assets/{publicStoreId}/{assetFile}` | anonymous | path `publicStoreId`, asset filename returned by upload API | `200` raw image/PDF bytes with stored `Content-Type`, `nosniff` | `400 VALIDATION_ERROR`, `404 ASSET_NOT_FOUND` |
| `GET /merchant/stores/{publicStoreId}/products` | active merchant session, `product:read` | path `publicStoreId`; bounded filters for status, visibility, category, tag, query, sort, limit, offset | `200` merchant `products[]`, private/inactive catalog 포함 가능 | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 STORE_NOT_FOUND` |
| `GET /merchant/stores/{publicStoreId}/products/{publicProductId}` | active merchant session, `product:read` | path `publicStoreId`, `publicProductId` | `200` merchant `product` detail including draft/private fields allowed by scope | `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 PRODUCT_NOT_FOUND` |
| `POST /merchant/stores/{publicStoreId}/assets` | active merchant session, `product:write` | JSON body: `assetType`, `fileName`, `contentType`, `contentBase64`; headers `Idempotency-Key`, CSRF for browser auth | `201` `asset` with internal `mediaRef`, content type, size, sha256 | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 STORE_NOT_FOUND` |
| `POST /merchant/stores/{publicStoreId}/products` | active merchant session, `product:write` | JSON body: title, description, category, tags, media refs, attributes including optional `detailPdfAssetKey`, price, `initialTotalStock`, optional `options[]`, optional `variants[]`; CSRF for browser auth | `201` `product` with stable `publicProductId`, options, variants, and variant availability; canonical product and inventory projections created transactionally | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 STORE_NOT_FOUND`, `409 PRODUCT_CONFLICT` |
| `PATCH /merchant/stores/{publicStoreId}/products/{publicProductId}` | active merchant session, `product:write` | JSON body: catalog detail fields plus optional replacement `options[]`/`variants[]`. Inventory stock/sale status 제외 | `200` updated `product` with current options/variants | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 PRODUCT_NOT_FOUND`, `409 PRODUCT_CONFLICT` |
| `GET /store-owner/inventory` | active merchant session with `inventory:read`; platform needs explicit inventory/operator permission | optional `storeId` filter | `200` `inventory[]` rows visible to membership scope | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN` |
| `POST /store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/intake` | active merchant session, `inventory:write` | path `storeId`, `productId`, `publicVariantId`; JSON body `quantity`, `reason`; headers `Idempotency-Key`, `X-CSRF-Token` for browser | `202` accepted inventory command/audit result for the variant | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 INVENTORY_NOT_FOUND`, `409 INVALID_INVENTORY_STATE` |
| `POST /store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/corrections` | active merchant session, `inventory:write` | path `publicVariantId`; JSON body `targetTotalStock`, `reason`; `targetTotalStock >= reservedStock` 필요 | `202` accepted inventory correction result for the variant | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 INVENTORY_NOT_FOUND`, `409 STOCK_BELOW_RESERVED` |
| `POST /store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/pause` | active merchant session, `inventory:write` | path `publicVariantId`; JSON body `reason`; headers `Idempotency-Key`, `X-CSRF-Token` for browser | `202` variant sale paused for new orders | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 INVENTORY_NOT_FOUND`, `409 INVALID_INVENTORY_STATE` |
| `POST /store-owner/stores/{storeId}/inventory/{productId}/variants/{publicVariantId}/resume` | active merchant session, `inventory:write` | path `publicVariantId`; JSON body `reason`; headers `Idempotency-Key`, `X-CSRF-Token` for browser | `202` variant sale resumed for new orders | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 INVENTORY_NOT_FOUND`, `409 INVALID_INVENTORY_STATE` |

## 요청 예시

Product asset 업로드:

```json
{
  "assetType": "PRODUCT_IMAGE",
  "fileName": "demo-hoodie.png",
  "contentType": "image/png",
  "contentBase64": "iVBORw0KGgo..."
}
```

Product 등록:

```json
{
  "title": "Demo Product",
  "description": "checkout 가능한 테스트 상품",
  "category": "demo",
  "tags": ["demo", "stablecoin"],
  "media": ["product-assets/st_demo_store_001/4d9679e1a8c3f0bdf0c3d9b1.png"],
  "attributes": {
    "detailPdfAssetKey": "product-assets/st_demo_store_001/0e5751c026e543b2e8ab2eb0.pdf"
  },
  "price": {
    "amount": "29.00",
    "currency": "USD"
  },
  "initialTotalStock": 0,
  "options": [
    {
      "key": "size",
      "displayName": "Size",
      "required": true,
      "optionType": "VARIANT",
      "values": [
        {"value": "small", "displayValue": "Small", "priceDelta": {"amount": "0", "currency": "USD"}},
        {"value": "large", "displayValue": "Large", "priceDelta": {"amount": "1.50", "currency": "USD"}}
      ]
    },
    {
      "key": "gift_wrap",
      "displayName": "Gift wrap",
      "required": false,
      "optionType": "ADD_ON",
      "values": [
        {"value": "yes", "displayValue": "Add gift wrap", "priceDelta": {"amount": "2.50", "currency": "USD"}}
      ]
    }
  ],
  "variants": [
    {
      "publicVariantId": "var_demo_hoodie_small",
      "displayName": "Small",
      "optionValues": {"size": "small"},
      "priceDelta": {"amount": "0", "currency": "USD"},
      "initialTotalStock": 12
    }
  ],
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

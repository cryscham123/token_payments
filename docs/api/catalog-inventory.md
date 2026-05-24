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

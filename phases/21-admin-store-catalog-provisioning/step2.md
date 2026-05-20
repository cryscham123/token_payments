# Step 2: store-owner-product-registration-api

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/api/http.py`
- `/app/token_payments/api/inventory.py`
- `/app/token_payments/contexts/order/adapter/postgres.py`
- `/app/token_payments/contexts/store_approval/adapter/postgres.py`
- `/app/token_payments/contexts/inventory/adapter/postgres.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/phases/20-store-owner-inventory-api/index.json`
- `/phases/21-admin-store-catalog-provisioning/index.json`

## 작업

해당 가게를 소유하거나 membership으로 연결된 계정이 checkout 가능한 상품을 등록하는 API를 추가한다. `ADMIN`은 운영자 override로 같은 작업을 수행할 수 있다. 상품 설명, 카테고리, 검색 metadata는 이 phase에서 다루지 않는다.

1. `scripts/test_store_owner_product_registration_api.py`를 추가한다.
   - authenticated user가 대상 store의 owner/member이면 상품 등록이 가능해야 한다.
   - `ADMIN` session도 운영자 override로 상품 등록이 가능해야 한다.
   - unrelated customer, unrelated store owner/member, unauthenticated request는 거부되어야 한다.
   - 등록 대상 store가 존재하고 active여야 한다.
   - 상품 등록 권한은 store ownership/membership으로 판단해야 하며, 전역 `STORE_OWNER` role에 의존하지 않아야 한다.
   - 상품 price chain id가 store의 `supportedChainIds`에 포함되어야 한다.
   - `initialTotalStock`은 0 이상이어야 하며, 등록 시 `product_inventory` 초기 row를 만들어야 한다.
   - 상품 등록 후 checkout에서 읽는 `order_store_products`와 승인 검증에서 읽는 `store_approval_products`가 함께 갱신되어야 한다.
   - `order_store_products`와 `store_approval_products`의 price/name/availability projection은 canonical `store_catalog_products`와 일관되어야 한다.
2. route manifest에 상품 등록 endpoint를 추가한다.
   - 권장 route: `POST /store-owner/stores/{storeId}/products` (`registerStoreProduct`)
   - `ADMIN` override가 필요하면 같은 command handler를 재사용하고 권한 판정만 shared guard에 둔다.
3. command handler는 한 logical transaction 안에서 다음을 맞춘다.
   - canonical `store_catalog_products`
   - `order_store_products`
   - `store_approval_products`
   - `product_inventory`
   - 하나라도 실패하면 모든 write가 rollback되어야 한다.
4. response는 생성된 `storeId`, `productId`, price, initial stock, projection write 결과를 bounded JSON으로 반환한다.
5. future catalog fields를 위한 문서 메모만 남긴다.
   - description/category/tags/images/search index는 later phase로 명시한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_store_owner_product_registration_api.py scripts/test_order_api_checkout_start.py scripts/test_store_owner_inventory_query_api.py scripts/test_store_approval_core.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. product registration API 테스트를 먼저 추가하고 실패를 확인한다.
2. command/API/projection writes를 구현한 뒤 AC를 실행한다.
3. `/phases/21-admin-store-catalog-provisioning/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 상품 설명, 카테고리, 태그, 이미지, 검색 route를 추가하지 마라.
- 상품 등록 권한 모델을 전역 `STORE_OWNER` role에 묶지 마라.
- product registration이 inventory stock correction API를 우회해서 reserved stock 불변식을 깨뜨리게 하지 마라.
- `order_store_products`만 쓰고 `store_approval_products` 또는 `product_inventory`를 누락하지 마라.
- canonical product만 쓰고 checkout/runtime projection 갱신을 나중 작업으로 미루지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

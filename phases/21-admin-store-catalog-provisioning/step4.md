# Step 4: admin-store-catalog-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/README.md`
- `/app/README.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/ARCHITECTURE.md`
- `/postman/token-payments.local.postman_collection.json`
- `/postman/expected/token-payments.api.expected.json`
- `/postman/fixtures/token-payments.local.seed-plan.json`
- `/scripts/test_admin_store_provisioning_contracts.py`
- `/scripts/test_admin_store_provisioning_api.py`
- `/scripts/test_store_owner_product_registration_api.py`
- `/scripts/test_admin_catalog_projection_consistency.py`
- `/phases/21-admin-store-catalog-provisioning/index.json`
- `/phases/index.json`

## 작업

관리자 store/catalog provisioning phase의 public contract, docs, Postman fixtures, phase metadata를 고정한다.

1. `scripts/test_admin_store_catalog_public_contracts.py`를 추가한다.
   - route manifest, docs, Postman expected fixtures가 admin store ownership provisioning과 store-owner product operations를 모두 포함하는지 검증한다.
   - docs가 관리자 생성형 owner provisioning과 public customer login의 차이를 설명하는지 검증한다.
   - docs가 모든 계정이 store ownership/membership으로 가게를 소유/관리할 수 있고 동일 wallet duplicate user를 만들지 않는다는 점을 설명하는지 검증한다.
   - docs가 `STORE_OWNER`를 새 실행 경로의 전역 계정 타입으로 쓰지 않는다는 점을 설명하는지 검증한다.
   - docs가 상품 설명/카테고리/search를 future scope로 둔다는 점을 명시하는지 검증한다.
   - docs/fixtures가 canonical catalog와 기존 checkout/store approval/inventory projection의 write-through 관계를 설명하는지 검증한다.
2. README와 API spec을 갱신한다.
   - 최초 `ADMIN` bootstrap 절차를 local/manual seed 기준으로 설명한다.
   - customer wallet reuse 정책, customer checkout history 보존 정책, store ownership 기반 권한 정책을 설명한다.
   - 가게 wallet/chain 설정은 store 단위에 둔다는 정책을 설명한다.
   - 상품 등록은 해당 store owner/member 또는 `ADMIN` override로 가능하고, canonical catalog와 checkout/inventory/store approval projection을 함께 갱신한다는 점을 설명한다.
3. Postman fixture를 갱신한다.
   - admin cookie auth 흐름 후 owner/store 생성 request skeleton을 추가하고, store owner cookie auth 흐름 후 product 생성 request skeleton을 추가한다.
   - seed plan은 owner `auth_users` row, store ownership/membership row, canonical store/product row, runtime projection row가 서로 참조 가능해야 한다.
   - 기존 checkout smoke가 계속 동작하도록 `order_stores`, `order_store_products`, `product_inventory`, `store_approval_stores`, `store_approval_products` seed를 유지하거나 새 provisioning flow로 대체한다.
   - 실제 private key, seed phrase, signed token, signature는 커밋하지 않는다.
4. phase metadata를 갱신한다.
   - 모든 step이 완료되면 `/phases/21-admin-store-catalog-provisioning/index.json` step status를 `completed`로 갱신한다.
   - `/phases/index.json`에서 `21-admin-store-catalog-provisioning`을 `completed`로 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_admin_store_catalog_public_contracts.py scripts/test_admin_store_provisioning_contracts.py scripts/test_admin_store_provisioning_api.py scripts/test_store_owner_product_registration_api.py scripts/test_admin_catalog_projection_consistency.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. public contract/docs/Postman 테스트를 먼저 추가하고 실패를 확인한다.
2. docs/fixtures/metadata를 갱신한 뒤 AC를 실행한다.
3. `/phases/21-admin-store-catalog-provisioning/index.json`와 `/phases/index.json`의 완료 상태와 summary를 구체적으로 작성한다.

## 금지사항

- admin provisioning을 customer public API로 문서화하지 마라.
- 가게 관리 권한을 전역 `STORE_OWNER` 계정 타입으로 문서화하지 마라.
- Postman/local seed에서 FK가 깨진 owner/store/product 참조를 남기지 마라.
- 상품 검색, 카테고리, 설명 관리 UI를 이 phase 완료 조건으로 섞지 마라.
- secret material, signed cookie token, MetaMask signature를 fixture에 커밋하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

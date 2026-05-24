# 머천트, 관리자, RBAC

머천트 API는 global account role이 아니라 merchant group membership과 permission scope로 권한을 판단한다. 관리자 provisioning API는 local/bootstrap 성격이며 public customer login이 `STORE_OWNER` 같은 global role을 만들지 않는다.

## Admin provisioning route

빠른 참조: `POST /admin/store-users`, `POST /admin/stores`, `POST /admin/stores/{storeId}/memberships`.

| 목적 | Method | Path | 권한 |
| --- | --- | --- | --- |
| store user 생성 또는 재사용 | `POST` | `/admin/store-users` | `admin:provision` 또는 `rbac:manage` |
| store 생성 | `POST` | `/admin/stores` | `admin:provision` 또는 `rbac:manage` |
| store membership 부여 | `POST` | `/admin/stores/{storeId}/memberships` | `admin:provision` 또는 `rbac:manage` |

`POST /admin/stores`는 canonical store record와 stable `publicStoreId`를 만든다. `POST /admin/stores/{storeId}/memberships`는 서버가 허용한 merchant role template만 사용한다.

## Merchant store profile route

| 목적 | Method | Path | 권한 |
| --- | --- | --- | --- |
| merchant store 목록 | `GET` | `/merchant/stores` | `store:read` |
| business profile 수정 | `PATCH` | `/merchant/stores/{publicStoreId}/profile` | `store:write` |

business profile 수정은 `displayName`, `description`, `supportEmail`, `supportEmailPublic`, `businessRegistrationLabel`만 받는다. settlement wallet, supported chain, owner transfer, member management는 이 API의 요청 범위가 아니다.

## Merchant member와 invitation route

빠른 참조: `GET /merchant/stores/{storeId}/members`, `GET /merchant/stores/{storeId}/invitations`, `POST /merchant/stores/{storeId}/invitations`, `POST /merchant/invitations/{invitationId}/accept`, `POST /merchant/invitations/{invitationId}/revoke`, `PATCH /merchant/stores/{storeId}/members/{userId}`, `DELETE /merchant/stores/{storeId}/members/{userId}`, `GET /merchant/role-catalog`.

| 목적 | Method | Path | 권한 |
| --- | --- | --- | --- |
| member 목록 | `GET` | `/merchant/stores/{storeId}/members` | `merchant_member:read` |
| invitation 목록 | `GET` | `/merchant/stores/{storeId}/invitations` | `merchant_member:read` |
| invitation 생성 | `POST` | `/merchant/stores/{storeId}/invitations` | `merchant_member:invite` |
| invitation 수락 | `POST` | `/merchant/invitations/{invitationId}/accept` | invited user |
| invitation revoke | `POST` | `/merchant/invitations/{invitationId}/revoke` | `merchant_member:invite` |
| member role 변경 | `PATCH` | `/merchant/stores/{storeId}/members/{userId}` | `merchant_member:manage` |
| member 제거 | `DELETE` | `/merchant/stores/{storeId}/members/{userId}` | `merchant_member:manage` |
| merchant role catalog 조회 | `GET` | `/merchant/role-catalog` | active merchant/admin session |

merchant-facing 요청은 platform role, personal role, raw permission array, `MERCHANT_OWNER` transfer를 받지 않는다. owner transfer와 full role/permission CRUD는 현재 public HTTP surface가 아니다.

## Permission 기준

RBAC 판단은 `AuthorizationPolicy.can(...)`에 permission과 resource scope를 전달해 수행한다. 주요 permission은 `store:read`, `store:write`, `product:read`, `product:write`, `inventory:read`, `inventory:write`, `merchant_member:read`, `merchant_member:invite`, `merchant_member:manage`, `operator:read`, `operator:action`, `outbox:retry`, `admin:provision`, `rbac:manage`다.

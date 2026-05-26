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

## Endpoint 상세

| Endpoint | 인증/권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- |
| `POST /admin/store-users` | platform/admin session, `admin:provision` 또는 `rbac:manage` | JSON body: wallet/user bootstrap 식별자와 display metadata; customer login role 변경 없음 | `201` 또는 `200` reused `user`/provisioning result | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 ADMIN_REQUIRED`, `409 USER_CONFLICT` |
| `POST /admin/stores` | platform/admin session, `admin:provision` 또는 `rbac:manage` | JSON body: store business profile, optional owner/provisioning metadata | `201` `store` with stable `publicStoreId` and internal admin reference | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 ADMIN_REQUIRED`, `409 STORE_CONFLICT` |
| `POST /admin/stores/{storeId}/memberships` | platform/admin session, `admin:provision` 또는 `rbac:manage` | path `storeId`; JSON body: `userId`, server-defined merchant role template | `201` `membership` scoped to merchant group/store | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 ADMIN_REQUIRED`, `404 STORE_NOT_FOUND`, `404 USER_NOT_FOUND`, `409 MEMBERSHIP_CONFLICT` |
| `GET /merchant/stores` | active merchant session, `store:read` | optional pagination/filter | `200` `stores[]` visible through active merchant membership; keyed by `publicStoreId` | `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN` |
| `PATCH /merchant/stores/{publicStoreId}/profile` | active merchant session, `store:write` | JSON body: `displayName`, `description`, `supportEmail`, `supportEmailPublic`, `businessRegistrationLabel`; CSRF for browser | `200` updated business profile with escaped display fields | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 STORE_NOT_FOUND`, `409 STORE_PROFILE_CONFLICT` |
| `GET /merchant/stores/{storeId}/members` | active merchant session, `merchant_member:read` | path `storeId`; optional pagination | `200` `members[]` with user id, role template, membership status | `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 STORE_NOT_FOUND` |
| `GET /merchant/stores/{storeId}/invitations` | active merchant session, `merchant_member:read` | path `storeId`; optional status filter | `200` `invitations[]` | `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 STORE_NOT_FOUND` |
| `POST /merchant/stores/{storeId}/invitations` | active merchant session, `merchant_member:invite` | JSON body: invitee wallet/user target and server-defined merchant role template; CSRF for browser | `201` `invitation` with bounded expiration/status | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 STORE_NOT_FOUND`, `409 INVITATION_CONFLICT` |
| `POST /merchant/invitations/{invitationId}/accept` | invited active user/session | path `invitationId`; optional body confirmation | `200` accepted invitation and active `membership` | `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 INVITATION_NOT_FOUND`, `409 INVITATION_NOT_ACCEPTABLE` |
| `POST /merchant/invitations/{invitationId}/revoke` | active merchant session, `merchant_member:invite` | path `invitationId`; JSON body optional `reason`; CSRF for browser | `200` revoked `invitation` | `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 INVITATION_NOT_FOUND`, `409 INVITATION_NOT_REVOKABLE` |
| `PATCH /merchant/stores/{storeId}/members/{userId}` | active merchant session, `merchant_member:manage` | path `storeId`, `userId`; JSON body server-defined merchant role template; platform/personal roles 거부 | `200` updated `membership` | `400 VALIDATION_ERROR`, `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 MEMBERSHIP_NOT_FOUND`, `409 ROLE_CHANGE_REJECTED` |
| `DELETE /merchant/stores/{storeId}/members/{userId}` | active merchant session, `merchant_member:manage` | path `storeId`, `userId`; optional reason | `200` removed/revoked `membership` | `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN`, `404 MEMBERSHIP_NOT_FOUND`, `409 MEMBER_REMOVE_REJECTED` |
| `GET /merchant/role-catalog` | active merchant/admin session | no body | `200` server-defined merchant role templates and assignability metadata | `401 AUTHENTICATION_REQUIRED`, `403 FORBIDDEN` |

## 요청 예시

Store profile 수정:

```json
{
  "displayName": "Token Demo Store",
  "description": "USDC 결제를 지원하는 데모 상점",
  "supportEmail": "support@example.com",
  "supportEmailPublic": true,
  "businessRegistrationLabel": "Demo Registration"
}
```

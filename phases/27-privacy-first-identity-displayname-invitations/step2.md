# Step 2: profile-and-invitation-implementation

## 작업

Step 1 테스트를 통과시키는 최소 구현을 한다.

1. `UserProfile` domain에서 contact/locale/timezone 필드를 제거한다.
2. `UpdateUserProfileCommand`, `AuthApplicationService`, `AuthApi`, Postgres profile repository를 displayName-only 계약으로 정리한다.
3. `AUTH_HTTP_ROUTES`와 `register_auth_routes`에 current profile get/update route를 추가한다.
4. `GroupInvitation`, merchant membership service/API/repository/schema에서 `targetEmail`을 제거한다.
5. Merchant membership repository에 `user_id_for_active_display_name(display_name)` lookup port를 추가한다.
6. `targetDisplayName`은 저장하지 않고 생성 시점에 `targetUserId`로 resolve한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_user_profile_contracts.py scripts/test_merchant_group_membership_api.py scripts/test_auth_order_http_routes.py scripts/test_route_surface_contract_docs.py
```

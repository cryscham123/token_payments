# Step 2: policy-enforcement-migration

## 읽어야 할 파일

- `/AGENTS.md`
- `/app/token_payments/api/operator.py`
- `/app/token_payments/api/operator_actions.py`
- `/app/token_payments/api/inventory.py`
- `/app/token_payments/api/auth.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/inventory/adapter/postgres.py`
- `/app/token_payments/contexts/store_catalog/`
- `/app/token_payments/runtime/composition.py`
- `/scripts/test_inventory_authz_audit_idempotency.py`
- `/scripts/test_operator_outbox_actions.py`
- `/scripts/test_operator_observability_api.py`
- `/scripts/test_admin_store_provisioning_contracts.py`
- `/phases/22-resource-scoped-rbac/index.json`

## 작업

Inventory, catalog, operator API의 role 분기를 `AuthorizationPolicy.can(...)` 기반으로 전환한다.

1. `scripts/test_rbac_policy_enforcement.py`를 추가한다.
   - platform admin group member만 `operator:read`, `operator:action`, `outbox:retry`를 수행할 수 있어야 한다.
   - merchant group의 `MERCHANT_OWNER` 또는 권한 있는 manager만 해당 store의 `product:write`, `inventory:write`를 수행할 수 있어야 한다.
   - 같은 user가 여러 merchant group에 속할 때 요청 resource의 group/store scope만 허용해야 한다.
   - inactive membership, inactive role, permission 없는 role은 거부되어야 한다.
   - customer personal group만 가진 user는 operator/catalog/inventory mutation을 수행할 수 없어야 한다.
   - customer self operation은 `user:self` 또는 authenticated self check로만 허용하고, merchant/platform permission으로 승격하지 않아야 한다.
   - store business profile update는 `store:write`, 민감 store 설정은 `store:manage`, product detail write는 `product:write`, inventory mutation은 `inventory:write`로 분리되어야 한다.
   - outbox retry는 operator action 중에서도 `operator:action`과 `outbox:retry` permission을 함께 요구해야 한다.
2. authz application module을 추가한다.
   - 권장 위치: `/app/token_payments/contexts/auth/application/authorization.py`
   - `AuthorizationPolicy`는 injected repository/port를 통해 user memberships와 role permissions를 조회한다.
   - public method는 `can(user_id, permission, resource)` 또는 구체 command-style API를 제공한다.
   - API layer는 permission string과 resource identity만 전달하고 DB 상세를 직접 알지 않는다.
3. 기존 API와 application command를 migration한다.
   - inventory mutation command의 `actor_role` 의존을 제거하거나 optional audit metadata로 낮춘다.
   - operator claims는 role 대신 `user_id`와 policy check로 검증한다.
   - store-owner inventory/product APIs는 store membership policy로 검증한다.
   - API layer는 role 이름이 아니라 permission name과 resource identity만 policy에 넘긴다.
4. live runtime composition을 갱신한다.
   - policy repository를 PostgreSQL adapter와 연결한다.
   - 기존 fake tests는 policy fake를 주입할 수 있어야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_rbac_policy_enforcement.py scripts/test_inventory_authz_audit_idempotency.py scripts/test_operator_outbox_actions.py scripts/test_operator_observability_api.py scripts/test_admin_store_provisioning_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. policy enforcement 테스트를 먼저 추가하고 실패를 확인한다.
2. authz policy, API, runtime wiring을 갱신한 뒤 AC를 실행한다.
3. `/phases/22-resource-scoped-rbac/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- API handler마다 role 이름을 직접 비교하는 분기를 새로 만들지 마라.
- policy repository가 HTTP request header를 직접 읽게 만들지 마라.
- permission denial을 validation error나 500으로 처리하지 마라. bounded forbidden response를 유지한다.
- store profile, product catalog, inventory, operator recovery 권한을 하나의 coarse admin/operator permission으로 합치지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

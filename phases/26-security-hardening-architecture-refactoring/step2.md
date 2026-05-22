# Step 2: fail-closed-authorization-hardening

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/API_SPEC.md`
- `/docs/DOMAIN_MODEL.md`
- `/app/token_payments/api/inventory.py`
- `/app/token_payments/api/store_catalog.py`
- `/app/token_payments/contexts/inventory/application/commands.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/inventory/application/ports.py`
- `/app/token_payments/contexts/store_catalog/application/service.py`
- `/app/token_payments/contexts/store_catalog/application/ports.py`
- `/app/token_payments/contexts/auth/application/authorization.py`
- `/scripts/test_store_owner_inventory_mutation_api.py`
- `/scripts/test_store_owner_product_registration_api.py`
- `/scripts/test_rbac_policy_enforcement.py`
- `/phases/26-security-hardening-architecture-refactoring/index.json`

## 작업

Inventory/product write authorization을 scope + canonical resource membership 구조로 통일하고 projection lag 보안 구멍을 닫는다.

1. `scripts/test_fail_closed_authorization_hardening.py`를 추가한다.
   - inventory mutation은 `inventory:write` scope가 없으면 store owner라도 실패해야 한다.
   - `inventory:write` scope가 있고 canonical store membership이 `OWNER` 또는 `MANAGER`이면 inventory mutation이 성공해야 한다.
   - `inventory:write` scope가 있어도 canonical store membership이 없거나 revoked 상태이면 실패해야 한다.
   - auth RBAC projection에 stale membership이 남아 있어도 canonical membership revoke 후 write operation은 fail-closed로 실패해야 한다.
   - product registration은 API layer에서 `product:write` scope를 요구하고, service layer에서 canonical store ownership/membership을 검증해야 한다.
   - API layer가 DB ownership을 직접 판단하거나 service layer가 scope bypass를 만들면 실패해야 한다.
2. inventory API legacy fallback을 제거한다.
   - `claims.role == STORE_OWNER`와 owner lookup만으로 `inventory:write`를 우회하는 경로를 제거한다.
   - MANAGER 지원은 fallback 확장이 아니라 scope 발급 + canonical membership 검증으로 처리한다.
3. service layer authorization port를 정리한다.
   - resource membership check는 inventory/store catalog service boundary 안에서 canonical store catalog membership port로 수행한다.
   - scope check는 API/session authorization boundary에서 수행한다.
   - auth RBAC projection은 read model 또는 token/scope 발급 참고 정보일 수 있으나 write authorization의 최종 membership authority가 아니다.
   - 캐시를 쓰는 경우 revocation-aware invalidation 또는 매우 짧은 TTL을 두고, 불확실하면 fail-closed 한다.
4. docs/Postman expected fixture를 갱신한다.
   - owner/manager inventory write에는 `inventory:write` scope와 canonical store membership이 모두 필요하다는 점을 명시한다.
   - product write의 2단계 검증 구조를 API contract와 architecture docs에 반영한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_fail_closed_authorization_hardening.py scripts/test_store_owner_inventory_mutation_api.py scripts/test_store_owner_product_registration_api.py scripts/test_rbac_policy_enforcement.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. fail-closed authorization 테스트를 먼저 추가하고 실패를 확인한다.
2. inventory/store catalog/API/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/26-security-hardening-architecture-refactoring/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- scope가 없는 session을 role fallback으로 write 허용하지 마라.
- MANAGER 지원을 legacy fallback 확장으로 구현하지 마라.
- write authorization을 stale auth projection만으로 통과시키지 마라.
- service layer ownership check를 API layer로 끌어올려 DB access를 흩뜨리지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

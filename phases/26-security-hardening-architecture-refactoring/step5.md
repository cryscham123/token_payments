# Step 5: membership-outbox-projection

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/token_payments/api/merchant.py`
- `/app/token_payments/contexts/auth/application/merchant_membership.py`
- `/app/token_payments/contexts/auth/adapter/postgres.py`
- `/app/token_payments/contexts/store_catalog/application/service.py`
- `/app/token_payments/contexts/store_catalog/adapter/postgres.py`
- `/app/token_payments/shared/adapter/postgres/outbox.py`
- `/app/token_payments/shared/adapter/outbox_relay.py`
- `/app/token_payments/shared/adapter/kafka/`
- `/scripts/test_admin_catalog_projection_consistency.py`
- `/scripts/test_postgres_outbox_idempotency.py`
- `/scripts/test_kafka_listener_adapters.py`
- `/phases/26-security-hardening-architecture-refactoring/index.json`

## 작업

Store catalog membership과 auth RBAC membership의 이중 관리를 canonical + projection 구조로 정리하고 legacy direct write API를 폐기한다.

1. `scripts/test_membership_outbox_projection.py`를 추가한다.
   - 권장 canonical source는 `store_catalog_store_memberships`이고, `auth_group_memberships`는 RBAC projection/read model이어야 한다.
   - canonical membership 변경은 같은 DB transaction에서 transactional outbox event를 기록해야 한다.
   - auth RBAC membership table은 projection으로 갱신되며 직접 수동 수정 write path를 갖지 않아야 한다.
   - 기존 Auth Group Membership 직접 수정 API가 있다면 제거/비활성화하거나 Store Catalog Membership command로 proxy해야 한다.
   - projection consumer는 event idempotency, ordering tolerance, retry를 만족해야 한다.
   - projection lag 상황에서 read model은 stale할 수 있지만 write authorization은 step 2의 canonical membership fail-closed 정책을 따라야 한다.
   - rebuild/replay 전략이 테스트 fixture나 docs에 있어야 한다.
2. membership domain/application을 갱신한다.
   - store catalog membership이 store domain canonical이고 auth group membership은 RBAC projection임을 명시한다.
   - membership change event schema를 정의한다.
   - event payload에는 internal table details보다 stable integration ids와 role/membership state를 담는다.
3. legacy auth group write API를 정리한다.
   - `POST /groups/{id}/members`, member role update/remove 등 직접 auth membership write route가 남아 있으면 public route에서 제거하거나 store catalog membership command로 위임한다.
   - disabled route는 bounded `410 Gone` 또는 `403/404` 정책을 문서화하고, silent dual-write를 만들지 않는다.
   - platform bootstrap/admin seed처럼 필요한 system path는 명시적 internal provisioning path로 제한한다.
4. outbox relay/listener를 갱신한다.
   - projection update는 멱등 처리한다.
   - duplicate event, stale event, partial failure negative case를 처리한다.
5. docs/sequences를 갱신한다.
   - membership change sequence와 projection lag policy를 명시한다.
   - 물리적 JOIN 통합이 아니라 context boundary를 유지하는 이유를 ADR 또는 architecture note에 남긴다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_membership_outbox_projection.py scripts/test_admin_catalog_projection_consistency.py scripts/test_postgres_outbox_idempotency.py scripts/test_kafka_listener_adapters.py scripts/test_rbac_policy_enforcement.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. membership outbox/projection 테스트를 먼저 추가하고 실패를 확인한다.
2. store catalog/auth/outbox/listener/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/26-security-hardening-architecture-refactoring/index.json`의 step 5 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 두 membership table을 물리 JOIN으로 합쳐 bounded context schema를 강결합하지 마라.
- canonical table과 projection table을 둘 다 직접 write 가능한 source of truth로 유지하지 마라.
- legacy auth group membership 직접 write API를 canonical path처럼 유지하지 마라.
- outbox event를 membership write transaction 밖에서 best-effort로만 발행하지 마라.
- projection lag policy 없이 authorization behavior를 암묵적으로 두지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Step 6: security-refactor-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/README.md`
- `/app/README.md`
- `/docs/ARCHITECTURE.md`
- `/docs/API_SPEC.md`
- `/docs/ADR.md`
- `/docs/SEQUENCES.md`
- `/docs/DOMAIN_MODEL.md`
- `/postman/token-payments.local.postman_collection.json`
- `/postman/expected/token-payments.api.expected.json`
- `/postman/fixtures/token-payments.local.seed-plan.json`
- `/scripts/test_route_surface_contract_docs.py`
- `/scripts/test_api_seed_expected_responses.py`
- `/phases/26-security-hardening-architecture-refactoring/index.json`

## 작업

API 보안, fail-closed authorization, context boundary, composition, membership projection 변경을 public verification으로 잠근다.

1. `scripts/test_security_refactor_public_contracts.py`를 추가한다.
   - API spec과 route examples는 payment submit을 `trackingId` 기반으로 설명해야 한다.
   - session/order/payment examples는 `orderId`, `customerId`, `sessionId`, `refreshTokenHash` 금지 필드를 포함하지 않아야 한다.
   - inventory write examples는 `inventory:write` scope와 canonical store membership requirement를 포함해야 한다.
   - product write examples는 `product:write` scope와 store membership/ownership 검증 실패 case를 포함해야 한다.
   - docs는 write authorization이 canonical membership을 fail-closed로 확인한다고 설명해야 한다.
   - docs는 bounded context import 규칙과 shared kernel 사용 기준을 설명해야 한다.
   - docs는 membership canonical/projection/outbox/rebuild 정책과 legacy auth group write API 폐기 정책을 설명해야 한다.
   - runtime composition docs는 context별 factory 구조와 no-server-start dry-run boundary를 유지해야 한다.
2. docs/fixtures를 갱신한다.
   - public DTO와 internal persistence object를 명확히 구분한다.
   - idempotency fallback은 implementation note로만 설명하고 raw internal id를 노출하지 않는다.
   - membership projection lag와 rebuild operation은 operational note로 남긴다.
3. route manifest와 expected JSON을 갱신한다.
   - 제거/비활성화한 legacy auth group membership write route가 public contract에 남지 않게 한다.
   - context cleanup이 route surface를 바꾸지 않는 부분은 architecture tests로 잠근다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_security_refactor_public_contracts.py scripts/test_route_surface_contract_docs.py scripts/test_postman_docker_api_public_contracts.py scripts/test_api_seed_expected_responses.py scripts/test_architecture_alignment_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. public verification 테스트를 먼저 추가하고 실패를 확인한다.
2. docs/Postman/fixtures/route expected files를 갱신한 뒤 AC를 실행한다.
3. `/phases/26-security-hardening-architecture-refactoring/index.json`의 step 6 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- docs나 fixtures에 금지 필드를 예시로 남기지 마라.
- context boundary cleanup을 public architecture contract 없이 완료 처리하지 마라.
- membership projection lag/rebuild 정책을 운영자에게 보이지 않는 암묵 지식으로 남기지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

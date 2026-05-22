# Step 3: context-boundary-ports-dtos

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/DOMAIN_MODEL.md`
- `/app/token_payments/contexts/inventory/application/commands.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/store_catalog/application/service.py`
- `/app/token_payments/contexts/store_catalog/application/ports.py`
- `/app/token_payments/contexts/order/adapter/postgres.py`
- `/app/token_payments/contexts/order/application/queries.py`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/shared/domain/`
- `/scripts/test_architecture_alignment_public_contracts.py`
- `/scripts/test_architecture_contract_alignment.py`
- `/phases/26-security-hardening-architecture-refactoring/index.json`

## 작업

Bounded context 간 domain object 직접 import를 port/DTO/ACL로 대체한다.

1. `scripts/test_context_boundary_ports_dtos.py`를 추가한다.
   - inventory application command/service layer는 `auth.domain.UserRole`을 직접 import하지 않아야 한다.
   - store catalog application service는 `auth.domain.User`, `GroupId`, `UserRole`을 직접 import하지 않아야 한다.
   - order postgres adapter는 `payment.domain.GasEstimate`, `TransactionSignatureRequest`를 직접 import하지 않아야 한다.
   - 허용되는 cross-context dependency는 application port, integration DTO, query snapshot, shared kernel value object로 제한해야 한다.
2. auth boundary를 정리한다.
   - user/session actor 정보는 `Actor`, `Principal`, `Requester`, `UserRef` 같은 얇은 DTO로 전달한다.
   - auth login role과 store membership role을 같은 enum으로 섞지 않는다.
   - resource authorization은 port를 통해 질의하고 auth domain entity를 다른 context에 넘기지 않는다.
3. order-payment boundary를 정리한다.
   - checkout tracking snapshot에 필요한 payment data는 order-owned snapshot/query DTO로 복사한다.
   - payment domain value object를 order persistence adapter schema에 직접 물리지 않는다.
   - 필요한 변환은 application boundary 또는 ACL mapper에서 수행한다.
4. shared kernel 사용 규칙을 문서화한다.
   - shared로 이동하는 타입은 여러 context에서 같은 의미로 쓰이는 안정된 value object에 한정한다.
   - 편의성 때문에 auth/payment domain 타입을 shared로 옮기지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_context_boundary_ports_dtos.py scripts/test_architecture_contract_alignment.py scripts/test_inventory_application_contracts.py scripts/test_payment_application_contracts.py scripts/test_postgres_context_repositories.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. context boundary import 테스트를 먼저 추가하고 실패를 확인한다.
2. DTO/port/ACL/repository mapping을 갱신한 뒤 AC를 실행한다.
3. `/phases/26-security-hardening-architecture-refactoring/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- auth/payment domain 타입을 shared로 옮겨 import 위반만 숨기지 마라.
- adapter에서 다른 bounded context domain object를 persistence schema로 직접 serialize하지 마라.
- 테스트 allowlist로 실제 경계 침범을 영구 허용하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

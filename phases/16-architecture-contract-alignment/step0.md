# Step 0: checkout-store-boundary-docs

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/docs/API_SPEC.md`
- `/diagram/DDD.drawio`
- `/app/token_payments/contexts/checkout/application/process_manager.py`
- `/app/token_payments/contexts/order/domain/model.py`
- `/app/token_payments/contexts/store_approval/domain/model.py`
- `/phases/15-postman-docker-api-readiness/index.json`

## 작업

문서와 실제 코드의 bounded context 경계를 먼저 맞춘다. 이 step은 구현 동작을 바꾸지 않고, 다음 phase가 잘못된 다이어그램 해석에 끌려가지 않도록 public architecture contract를 정리한다.

1. `scripts/test_architecture_contract_alignment.py`를 추가하거나 갱신한다.
   - `docs/ARCHITECTURE.md`가 `Checkout Process`를 `order` 내부가 아닌 별도 saga/process context로 설명하는지 검증한다.
   - `docs/DOMAIN_MODEL.md`가 `CheckoutProcessManager`를 `contexts/checkout` 기준으로 설명하는지 검증한다.
   - `order.Store`와 `store_approval.Store`가 같은 aggregate가 아니라 context별 projection/model임을 문서가 명시하는지 검증한다.
   - 다이어그램 원본을 직접 파싱하지 못하는 경우, 문서가 다이어그램과 코드가 충돌할 때 코드/package layout을 우선하는 기준을 명시하는지 검증한다.
2. `docs/ARCHITECTURE.md`와 `docs/DOMAIN_MODEL.md`를 갱신한다.
   - `Checkout Process`의 책임은 orchestration, compensation command decision, idempotent saga decision으로 제한한다.
   - `order` context는 주문 생성/상태 projection/checkout tracking에 집중한다고 정리한다.
   - `store_approval` context의 `Store`는 승인 검증 projection이며, `order` context의 `Store` catalog model과 persistence/DTO를 무조건 공유하지 않는다고 명시한다.
3. 필요한 경우 `docs/SEQUENCES.md`에 checkout process manager가 이벤트를 소비하는 위치를 명확히 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_architecture_contract_alignment.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 문서 contract 테스트를 먼저 추가하고 실패를 확인한다.
2. 문서를 갱신한 뒤 AC를 실행한다.
3. `/phases/16-architecture-contract-alignment/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step에서 domain/application/runtime 코드를 리팩터링하지 마라.
- `CheckoutProcessManager`를 `order` package로 되돌리지 마라.
- `order.Store`와 `store_approval.Store`를 하나의 공유 domain class로 합치지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

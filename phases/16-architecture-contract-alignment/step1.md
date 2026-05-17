# Step 1: input-port-route-surface-contract

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/docs/SEQUENCES.md`
- `/app/token_payments/api/http.py`
- `/app/token_payments/contexts/store_approval/application/service.py`
- `/app/token_payments/contexts/store_approval/adapter/kafka.py`
- `/app/token_payments/contexts/inventory/application/handler.py`
- `/app/token_payments/contexts/inventory/adapter/kafka.py`
- `/app/token_payments/shared/domain/messaging.py`
- `/scripts/test_http_adapter_public_contracts.py`
- `/scripts/test_operator_action_public_contracts.py`

## 작업

Input port가 HTTP route와 1:1로 대응한다고 오해하지 않도록 API route surface contract를 문서화한다. 수동 주문 승인 기능은 현재 제품 범위에서 제외하고, 결제 후 자동 승인/거절 검증 흐름을 유지한다.

1. `scripts/test_route_surface_contract_docs.py`를 추가한다.
   - `docs/API_SPEC.md`가 현재 public HTTP route manifest를 기준으로 route surface를 설명하는지 검증한다.
   - `approveOrder`/`request_store_approval`은 Kafka/message input이며 store owner 수동 승인 HTTP API가 현재 범위가 아님을 문서가 명시하는지 검증한다.
   - `reserveInventory`/`releaseInventory`/향후 `confirmInventory`는 public HTTP가 아닌 checkout saga 내부 command임을 문서가 명시하는지 검증한다.
   - store owner 재고 관리는 별도 future phase로 분리되어 있음을 문서가 명시하는지 검증한다.
2. `docs/API_SPEC.md`의 route surface 섹션을 정리한다.
   - Public HTTP, message listener input, internal application port를 구분한다.
   - 운영자 action API와 store owner inventory API의 권한 경계를 구분하되, store owner inventory API는 아직 미구현이라고 표시한다.
3. `docs/DOMAIN_MODEL.md`의 input port 설명에 adapter type을 표시한다.
   - `HTTP`
   - `Kafka/message`
   - `internal application`

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_route_surface_contract_docs.py scripts/test_http_adapter_public_contracts.py scripts/test_operator_action_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. route surface 문서 테스트를 먼저 추가하고 실패를 확인한다.
2. 문서를 갱신한 뒤 AC를 실행한다.
3. `/phases/16-architecture-contract-alignment/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 수동 주문 승인/거절 HTTP API를 추가하지 마라.
- checkout 내부 재고 reserve/release/confirm command를 public customer API로 노출하지 마라.
- route manifest 수를 문서만 맞추기 위해 임의로 늘리지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

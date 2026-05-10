# Step 0: ui-contract-foundation

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/phases/0-foundation/index.json`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/phases/3-api-worker-runtime/index.json`
- `/app/token_payments/api/contracts.py`
- `/app/token_payments/api/checkout.py`
- `/app/token_payments/api/operator.py`

## 작업

Customer/operator UI가 기존 framework-neutral API/runtime 계약 위에서 동작할 수 있도록 Python 표준 라이브러리 기반 UI foundation을 만든다. 동작 변경이므로 먼저 `scripts/test_ui_contract_foundation.py`를 추가하거나 갱신하고 실패를 확인한 뒤 구현한다.

1. `app/token_payments/ui/` 패키지를 추가하고 UI render contract를 정의한다.
   - 외부 npm/브라우저 빌드 도구 없이 테스트 가능한 구조여야 한다.
   - public export는 다음 step에서 import할 수 있게 명확히 둔다.
   - domain/API DTO를 직접 변경하지 말고, UI 전용 view model/renderer 경계에서 매핑한다.
2. 공통 HTML/CSS foundation을 구현한다.
   - `docs/UI_GUIDE.md` 색상, radius, table/timeline 밀도, 상태 badge 규칙을 반영한다.
   - glass UI, gradient text, gradient orb/bokeh, 과한 단색 보라/인디고 팔레트를 쓰지 않는다.
   - 텍스트가 버튼/표/timeline 안에서 넘치지 않도록 고정 치수와 responsive constraint를 둔다.
3. UI 상태 모델을 추가한다.
   - wallet address, network/chain id, token amount, gas estimate, payment expiration, txHash, checkout timeline, operator filter/detail에 필요한 타입을 포함한다.
   - 상태 label은 도메인 enum 문자열과 일치하게 유지한다.
4. accessibility와 보안 기본값을 고정한다.
   - HTML escaping을 테스트로 검증한다.
   - id/txHash는 monospace와 copy affordance를 표현하되 실제 secret/private key를 노출하지 않는다.
5. `__all__` export와 import boundary 테스트를 추가한다.
   - UI package가 PostgreSQL/Kafka/Blockchain client에 직접 의존하지 않게 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_ui_contract_foundation.py
python3 -m pytest scripts/test_api_worker_runtime_public_contracts.py scripts/test_foundation_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `AGENTS.md`와 `docs/*.md`의 CRITICAL 규칙 위반 여부를 확인한다.
3. UI foundation이 다음 step의 customer/operator 화면에서 재사용 가능한지 확인한다.
4. `/phases/4-customer-operator-ui/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 새 npm/package manager 의존성이나 브라우저 빌드 체인을 추가하지 마라.
- API/runtime/application 계약을 UI 편의를 위해 깨지 마라.
- PostgreSQL, Kafka, Blockchain RPC client를 UI package에서 직접 import하지 마라.
- landing page나 마케팅 hero를 만들지 마라. 첫 화면은 checkout/operator 업무 화면이어야 한다.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

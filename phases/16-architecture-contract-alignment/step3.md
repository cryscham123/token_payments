# Step 3: architecture-contract-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/API_SPEC.md`
- `/docs/SEQUENCES.md`
- `/README.md`
- `/app/README.md`
- `/.env.example`
- `/phases/index.json`
- `/phases/16-architecture-contract-alignment/index.json`
- `/scripts/test_architecture_contract_alignment.py`
- `/scripts/test_route_surface_contract_docs.py`
- `/scripts/test_auth_storage_env_contract_docs.py`

## 작업

Architecture alignment phase의 public verification을 고정한다. 이 step은 구현 동작을 바꾸지 않고 문서/phase metadata가 다음 phase의 guardrail로 충분한지 검증한다.

1. `scripts/test_architecture_alignment_public_contracts.py`를 추가한다.
   - architecture/domain/API/sequence docs가 checkout boundary, store projection split, input adapter type, auth storage source of truth, env policy를 모두 포함하는지 검증한다.
   - phase metadata가 pending/completed 상태와 step summary 규칙을 지키는지 검증한다.
   - 수동 주문 승인 feature가 active roadmap으로 다시 들어가지 않았는지 검증한다.
2. README/app README에 다음 phase 순서를 간단히 갱신한다.
   - Docker compose live server
   - SIWE/ERC-1271 auth
   - inventory saga finalization
   - store owner inventory API
3. `/phases/16-architecture-contract-alignment/index.json`와 `/phases/index.json` 상태를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_architecture_contract_alignment.py scripts/test_route_surface_contract_docs.py scripts/test_auth_storage_env_contract_docs.py scripts/test_architecture_alignment_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. public verification 테스트를 먼저 추가하고 실패를 확인한다.
2. 문서와 phase metadata를 갱신한 뒤 AC를 실행한다.
3. `/phases/16-architecture-contract-alignment/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
4. `/phases/index.json`에서 `16-architecture-contract-alignment`를 `completed`로 갱신한다.

## 금지사항

- 이 step에서 production code 동작을 바꾸지 마라.
- 수동 주문 승인/자동 승인 선택 기능을 새 phase에 추가하지 마라.
- ERC-20/USDC/USDT 결제 지원을 이번 roadmap의 즉시 phase로 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

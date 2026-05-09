# Step 5: foundation-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/PRD.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/SEQUENCES.md`
- `/docs/HARNESS.md`
- `/phases/0-foundation/index.json`
- Step 0-4에서 생성/수정한 파일

## 작업

foundation phase 산출물이 다음 phase로 넘어갈 수 있는지 검증하고 정리한다.

1. 생성된 런타임, domain, messaging, auth, order/checkout skeleton의 public contract를 점검한다.
2. README 또는 docs에 실제 실행 가능한 개발 명령을 최신화한다.
3. 누락된 테스트 또는 불안정한 설계를 보완한다.
4. 다음 phase에서 구현할 `inventory`, `payment`, `store-approval`, adapter 작업 후보를 짧게 정리한다.
5. phase metadata validator와 pre-commit 검증이 통과하는지 확인한다.

## Acceptance Criteria

```bash
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. 모든 step의 `summary`가 다음 step 판단에 충분히 구체적인지 확인한다.
3. `phases/0-foundation/index.json`의 step 5 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 새 기능을 크게 추가하지 마라. 검증과 정리 중심으로 마무리한다.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

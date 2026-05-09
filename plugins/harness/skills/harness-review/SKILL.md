---
name: harness-review
description: Use when the user asks to review Harness framework changes, phase plans, step files, or implementation diffs against AGENTS.md and docs guardrails. Prioritize bugs, regressions, missing tests, and CRITICAL rule violations.
---

# Harness Review

이 스킬은 Harness 프레임워크 변경 사항을 코드 리뷰 관점으로 검증할 때 사용한다.

## Workflow

1. 먼저 `/AGENTS.md`, `/docs/ARCHITECTURE.md`, `/docs/ADR.md`를 읽는다.
2. 변경된 파일을 확인한다.
3. 아래 체크리스트로 위험을 검토한다.
4. Findings를 심각도 높은 순서로 먼저 작성한다.

## Checklist

| 항목 | 기준 |
|------|------|
| 아키텍처 준수 | `ARCHITECTURE.md`에 정의된 구조와 의도를 따르는가? |
| 기술 스택 준수 | `ADR.md`에 정의된 선택을 벗어나지 않았는가? |
| 테스트 존재 | 새로운 기능 또는 동작 변경에 대한 테스트가 있는가? |
| CRITICAL 규칙 | `AGENTS.md`의 CRITICAL 규칙을 위반하지 않았는가? |
| 빌드 가능 | 해당 프로젝트의 검증 명령이 통과하는가? |

## Output

1. Findings: 심각도 높은 순서로 파일/라인을 포함해 작성한다.
2. Open Questions: 판단에 필요한 질문이 있으면 작성한다.
3. Verification: 실행한 명령과 결과를 적는다.
4. Summary: 변경 의도와 남은 리스크를 짧게 정리한다.

문제가 없으면 "발견된 문제 없음"이라고 명확히 말하고, 실행하지 못한 검증이 있으면 이유를 적는다.

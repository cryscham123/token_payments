---
name: harness-phase-planner
description: Use when the user asks to plan, split, scaffold, or prepare phased Harness work under phases/ for Codex execution. Applies to creating phases/index.json, phases/{task}/index.json, and self-contained stepN.md files.
---

# Harness Phase Planner

이 스킬은 Harness 프레임워크의 phase/step 작업 계획을 만들 때 사용한다.

## Workflow

1. `AGENTS.md`와 `docs/` 하위 문서(PRD, ARCHITECTURE, ADR 등)를 읽고 프로젝트 의도를 파악한다.
2. 구현에 필요한 결정이 불명확하면 사용자와 먼저 정리한다.
3. 사용자가 계획 작성을 원하면 여러 step으로 나눠 초안을 제시한다.
4. 사용자가 승인하면 `phases/index.json`, `phases/{task-name}/index.json`, `phases/{task-name}/step{N}.md`를 생성하거나 갱신한다.

## Step Design Rules

1. Scope 최소화: 하나의 step은 하나의 레이어 또는 모듈만 다룬다.
2. 자기완결성: 각 step 파일은 독립된 Codex 세션에서 실행된다. 외부 대화 맥락을 참조하지 않는다.
3. 사전 준비: 읽어야 할 문서와 이전 step 산출물 경로를 명시한다.
4. 시그니처 수준 지시: 인터페이스와 핵심 규칙은 명확히 쓰되, 구현 세부는 에이전트 재량에 둔다.
5. 실행 가능한 AC: `npm run build`, `python3 -m pytest`처럼 실제 검증 커맨드를 적는다.
6. 금지사항은 구체적으로 쓴다: "X를 하지 마라. 이유: Y".
7. step name은 kebab-case slug로 작성한다.
8. Feature API Companion Rule: 신규 사용자/업무 기능 phase에는 API contract step 또는 API 변경 AC를 포함한다. `docs/API_SPEC.md`, route manifest, API tests/fixtures 갱신을 계획에 넣고, API가 필요 없는 순수 내부 기능이면 `intentional internal-only exception`과 이유를 step 지시문과 완료 summary에 남기도록 한다.

## File Shapes

`phases/index.json`:

```json
{
  "phases": [
    {
      "dir": "0-mvp",
      "status": "pending"
    }
  ]
}
```

`phases/{task-name}/index.json`:

```json
{
  "project": "<프로젝트명>",
  "phase": "<task-name>",
  "steps": [
    { "step": 0, "name": "project-setup", "status": "pending" },
    { "step": 1, "name": "core-types", "status": "pending" },
    { "step": 2, "name": "api-layer", "status": "pending" }
  ]
}
```

Step 상태는 `"pending"`, `"completed"`, `"error"`, `"blocked"`만 사용한다. `created_at`, `started_at`, `completed_at`, `failed_at`, `blocked_at`은 `scripts/execute.py`가 기록한다.

## Step Template

````markdown
# Step {N}: {name}

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/API_SPEC.md`
- {이전 step에서 생성/수정된 파일 경로}

## 작업

{구체적인 구현 지시}

Feature API Companion Rule:
- 사용자/업무 기능이면 API surface를 함께 설계/구현한다.
- `docs/API_SPEC.md`, route manifest, API tests/fixtures를 갱신한다.
- API가 필요 없는 순수 내부 기능이면 `intentional internal-only exception`과 이유를 남긴다.

## Acceptance Criteria

```bash
npm run build
npm test
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. AGENTS.md와 docs/*.md의 CRITICAL 규칙 위반 여부를 확인한다.
3. `phases/{task-name}/index.json`의 해당 step 상태를 업데이트한다.

## 금지사항

- {이 step에서 하지 말아야 할 것}
- 기존 테스트를 깨뜨리지 마라
````

## Execution

```bash
python3 scripts/execute.py {task-name}
python3 scripts/execute.py {task-name} --push
```

에러 복구 시에는 해당 step의 `status`를 `"pending"`으로 되돌리고 `error_message` 또는 `blocked_reason`을 삭제한 뒤 재실행한다.

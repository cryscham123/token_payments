# Harness Engineering

이 저장소는 Token Payments 구현을 Harness phase/step 단위로 진행하기 위한 Codex 워크스페이스다.

## 핵심 규칙

- 자동 실행 경로는 Codex CLI (`codex exec`) 기준으로 유지한다.
- Claude 전용 파일이나 명령을 새 실행 경로에 추가하지 않는다.
- `scripts/execute.py`는 phase 실행 오케스트레이션만 담당한다.
- 제품 구현 로직은 phase/step 또는 대상 애플리케이션 코드에 둔다.
- step 실행 프롬프트는 `AGENTS.md`와 `docs/*.md`를 포함해야 한다.
- phase step 상태는 `"pending"`, `"completed"`, `"error"`, `"blocked"`만 사용한다.

## 파일 역할

| 경로 | 역할 |
| --- | --- |
| `AGENTS.md` | 저장소 전체 실행 규칙 |
| `docs/*.md` | 제품, 아키텍처, 도메인, UI, 하네스 가드레일 |
| `phases/index.json` | 실행 가능한 phase 목록 |
| `phases/{phase}/index.json` | phase 내 step 상태 |
| `phases/{phase}/step{N}.md` | 독립 실행 가능한 step 지시문 |
| `scripts/execute.py` | pending step을 Codex CLI로 순차 실행 |
| `.codex/hooks.json` | Codex hook wiring |
| `.githooks/pre-commit` | 커밋 전 Python/JSON/pytest 검증 |
| `plugins/harness/` | repo-local Codex plugin |

## Phase Index

`phases/index.json`은 top-level phase 목록만 관리한다.

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

## Phase Step Index

`phases/{phase}/index.json`은 실행 상태의 source of truth다.

```json
{
  "project": "Token Payments",
  "phase": "0-mvp",
  "steps": [
    {
      "step": 0,
      "name": "project-setup",
      "status": "pending"
    }
  ]
}
```

상태 전이:

- `pending`: 아직 실행하지 않았거나 재실행 대상
- `completed`: AC를 통과했고 `summary`가 있음
- `error`: 자동 재시도 후 실패했고 `error_message`가 있음
- `blocked`: API key, 인증, 수동 설정 등 사용자 개입이 필요하고 `blocked_reason`이 있음

## Step 작성 규칙

각 step 파일은 독립적인 Codex 세션에서 실행된다. 외부 대화 맥락 없이 이해될 수 있어야 한다.

필수 섹션:

- 읽어야 할 파일
- 작업
- Acceptance Criteria
- 검증 절차
- 금지사항

권장 AC:

```bash
.venv/bin/python scripts/validate_phases.py
.venv/bin/python -m pytest scripts/test_*.py
```

애플리케이션 코드가 생긴 후에는 해당 프로젝트의 lint/build/test 커맨드를 AC에 추가한다.

## 실행

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/validate_phases.py
python3 scripts/execute.py <phase-dir>
python3 scripts/execute.py <phase-dir> --push
```

Codex CLI 옵션은 현재 CLI 형식에 맞춰 최상위 옵션을 `exec` 앞에 둔다.

## 산출물 관리

- `phases/**/step*-output.json`은 추적하지 않는다.
- 필요한 장기 상태는 `phases/{phase}/index.json`에 남긴다.
- `summary`, `error_message`, `blocked_reason`은 다음 step 판단에 쓰이므로 구체적으로 작성한다.

## Hook 설정

로컬 git hook을 사용하려면 다음 설정이 필요하다.

```bash
git config core.hooksPath .githooks
```

pre-commit은 다음을 검증한다.

- `.venv/bin/python`이 있으면 해당 Python을 우선 사용한다.
- `scripts/*.py`와 `.codex/hooks/*.py` 컴파일
- 주요 JSON 파일 parse
- `phases/index.json`과 각 phase step metadata 검증
- `scripts/test_*.py` pytest 실행

Codex hook은 다음을 수행한다.

- 위험한 shell 명령 차단
- 위험한 승인 요청 차단
- Codex 종료 시 lightweight Python/JSON 검증

## Live Kafka Worker 실행 가이드

Token Payments 라이브 워커(Outbox Relay, 7개의 Kafka Consumers, payment receipt polling)는 `worker` 명령어 아래 `--live` 플래그를 제공하여 실행합니다.

- Bounded plan (dry-run): `PYTHONPATH=app python3 -m token_payments worker --live --dry-run`
- Run once (single batch): `PYTHONPATH=app python3 -m token_payments worker --live --once`
- Run loop (long-running daemon): `PYTHONPATH=app python3 -m token_payments worker --live --loop --confirm-live-worker`

또한, `docker-compose.yml` 내 `token_payments_live_worker` 서비스가 구성되어 있어 컨테이너 형태로 실행할 수도 있습니다.

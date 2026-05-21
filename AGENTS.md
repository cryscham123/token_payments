# 프로젝트: Harness Codex Framework

## 기술 스택
- Python 3.12 기반 실행 하네스
- pytest 테스트
- Markdown/JSON 기반 phase 및 step 명세
- Codex CLI (`codex exec`) 기반 비대화형 step 실행

## 아키텍처 규칙
- CRITICAL: Claude 전용 파일이나 명령을 새 실행 경로에 추가하지 말 것. 자동 실행은 Codex CLI를 기준으로 유지한다.
- CRITICAL: `scripts/execute.py`는 phase 실행 오케스트레이션만 담당한다. 프로젝트별 구현 로직은 생성되는 phase/step 또는 대상 프로젝트 코드에 둔다.
- CRITICAL: step 실행 프롬프트에는 `AGENTS.md`와 `docs/*.md` 가드레일이 포함되어야 한다.
- CRITICAL: `phases/{phase}/index.json`의 상태 전이는 `"pending"`, `"completed"`, `"error"`, `"blocked"`만 사용한다.
- `summary`, `error_message`, `blocked_reason`은 다음 step의 판단에 직접 쓰이므로 구체적으로 작성한다.
- `step*-output.json` 같은 실행 산출물은 추적하지 않는다. 필요한 상태는 index JSON에 남긴다.
- Codex CLI 옵션은 현재 CLI 형식에 맞춰 최상위 옵션을 `exec` 앞에 둔다.

## 개발 프로세스
- CRITICAL: 동작 변경 시 먼저 테스트를 갱신하고, 테스트가 통과하는 구현을 작성한다.
- 기존 사용자 변경을 되돌리지 말고, 현재 작업과 충돌하는 경우에만 최소 범위로 조정한다.
- CRITICAL: 작업이 완료되면 별도 지시가 없는 한 즉시 커밋까지 완료한다.
- CRITICAL: 이 프로젝트는 아직 production level이 아니므로 legacy compatibility를 기본 제약으로 두지 않는다. 현재 목표 설계와 충돌하는 legacy code/path는 필요한 범위에서 수정하거나 삭제할 수 있다.
- 커밋 메시지는 conventional commits 형식을 따른다 (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- 커밋은 GPG signing 없이 수행한다. repo-local `commit.gpgsign=false`를 유지하고, 필요하면 `git commit --no-gpg-sign`을 사용한다.

## 명령어
```bash
python3 -m pytest scripts/test_execute.py
python3 scripts/execute.py <phase-dir>
python3 scripts/execute.py <phase-dir> --push
```

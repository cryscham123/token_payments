# Step 0: runtime-baseline

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/PRD.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/HARNESS.md`
- `/docs/DOMAIN_MODEL.md`

## 작업

Token Payments 애플리케이션 구현을 시작할 수 있는 최소 런타임 구조를 만든다.

1. 현재 저장소 구조를 확인하고, 기존 Harness 파일을 변경하지 않는다.
2. 애플리케이션 코드 위치를 하나로 정한다. 기본값은 `/app` 하위로 둔다.
3. 선택한 런타임과 실행 명령을 README 또는 별도 문서에 기록한다.
4. 로컬 개발에 필요한 env 예시 파일을 민감정보 없이 정리한다.
5. 이후 step에서 domain/application/adapter 레이어를 추가할 수 있도록 빈 디렉토리 또는 최소 skeleton을 만든다.

## Acceptance Criteria

```bash
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. 생성한 런타임 구조가 `docs/ARCHITECTURE.md`의 context/layer 경계를 침범하지 않는지 확인한다.
3. `phases/0-foundation/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- Claude 전용 설정 파일이나 실행 명령을 추가하지 마라.
- 실제 private key, API key, seed phrase를 커밋하지 마라.

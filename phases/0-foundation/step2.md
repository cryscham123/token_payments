# Step 2: messaging-outbox-contracts

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- `/docs/SEQUENCES.md`
- `/docs/DOMAIN_MODEL.md`
- Step 1에서 생성/수정한 공통 domain 파일

## 작업

context 간 통신에 필요한 메시지와 outbox 계약을 정의한다.

1. `MessageId`, event metadata, command metadata 구조를 만든다.
2. `OutboxMessage` 모델과 publish 상태 전이를 정의한다.
3. `ProcessedMessage` 또는 `ProcessedCommand` 모델을 정의해 멱등 처리 기준을 만든다.
4. checkout sequence에 필요한 이벤트/커맨드 이름을 상수 또는 타입으로 정리한다.
5. 보상 커맨드 id가 `OrderId + action`으로 결정적으로 생성되는지 테스트한다.

## Acceptance Criteria

```bash
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. outbox 저장과 Kafka 발행을 같은 함수에 섞지 않았는지 확인한다.
3. `phases/0-foundation/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- Outbox Relay 구현을 이 step에서 과하게 만들지 마라. 계약과 테스트 가능한 모델까지만 만든다.
- 메시지 status에 `pending`, `completed`, `error`, `blocked`를 재사용하지 마라. 해당 값은 Harness phase 상태 전용이다.
- 중복 메시지를 예외로만 처리하는 설계를 하지 마라. 멱등 무시 경로를 명시하라.

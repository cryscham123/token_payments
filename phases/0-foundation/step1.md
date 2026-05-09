# Step 1: shared-domain-kernel

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/ADR.md`
- `/phases/0-foundation/index.json`
- Step 0에서 생성/수정한 런타임 파일

## 작업

bounded context들이 공유할 최소 domain kernel을 구현한다.

1. `Crypto`, `WalletAddress`, `ChainNetwork`, `TransactionHash` 같은 공통 value object를 만든다.
2. `OrderId`, `PaymentId`, `CustomerId`, `StoreId`, `ProductId`, `UserId`, `MessageId` 같은 id 타입을 만든다.
3. 값 객체는 불변으로 다루고, 생성 시 기본 검증을 수행한다.
4. domain layer가 PostgreSQL, Kafka, MetaMask, Blockchain RPC에 직접 의존하지 않게 한다.
5. 공통 타입의 단위 테스트를 추가한다.

## Acceptance Criteria

```bash
python3 scripts/validate_phases.py
python3 .githooks/pre_commit_check.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. 공통 value object 테스트가 실행되는지 확인한다.
3. `phases/0-foundation/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 공통 kernel에 context별 업무 규칙을 넣지 마라.
- 외부 adapter 코드를 domain model에 섞지 마라.
- 기존 Harness 테스트를 깨뜨리지 마라.

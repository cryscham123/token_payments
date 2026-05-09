# Architecture Decision Records

## 철학

이 프로젝트는 결제/재고/주문처럼 실패 비용이 큰 업무를 다룬다. 빠른 MVP보다 재시도 안전성, 상태 추적 가능성, 명확한 도메인 경계를 우선한다. 자동 구현은 Harness phase/step 단위로 수행하고, step 실행 프롬프트는 항상 `AGENTS.md`와 `docs/*.md` 가드레일을 포함한다.

---

### ADR-001: DDD bounded context로 업무 경계를 분리한다

**결정**: 사용자 인증, 주문 생성, Checkout Process, 재고관리, 결제, 주문 승인을 bounded context로 분리한다.

**이유**: 각 context는 상태 전이, 실패 처리, 외부 의존성이 다르다. 결제 실패가 주문/재고/가게 승인 모델을 직접 침범하지 않게 하기 위해 업무 언어와 aggregate를 분리한다.

**트레이드오프**: 초기 구현 파일 수와 메시지 계약이 늘어난다. 단순 CRUD보다 테스트와 운영 관찰 지점이 많아진다.

### ADR-002: Hexagonal architecture를 context 내부 기본 구조로 사용한다

**결정**: Domain Core, Application Service, Adapters 구조를 사용한다. Application Service는 input/output port를 통해 repository, publisher, 외부 시스템을 호출한다.

**이유**: PostgreSQL, Kafka, Blockchain RPC, MetaMask client가 도메인 모델에 새지 않도록 하기 위함이다. 테스트에서는 port를 대체해 상태 전이와 보상 로직을 빠르게 검증할 수 있다.

**트레이드오프**: 작은 기능에도 port/interface가 생긴다. 단, 결제 도메인의 실패 처리 복잡도를 고려하면 장기 유지보수 비용을 낮춘다.

### ADR-003: Kafka + Outbox로 context 간 메시지를 발행한다

**결정**: aggregate 저장과 `OutboxMessage` 저장을 같은 DB 트랜잭션으로 커밋하고, Outbox Relay가 Kafka에 발행한다.

**이유**: DB commit 성공 후 메시지 발행 실패, 메시지 발행 성공 후 DB rollback 같은 이중 쓰기 문제를 줄인다.

**트레이드오프**: Outbox table, relay worker, published marker 관리가 필요하다. 메시지 전달은 at-least-once로 보고 소비자 멱등성을 반드시 구현해야 한다.

### ADR-004: CheckoutProcessManager를 saga/process manager로 둔다

**결정**: checkout 전체 흐름은 `CheckoutProcessManager`가 이벤트를 소비하고 다음 커맨드를 발행하는 방식으로 조율한다.

**이유**: 주문, 재고, 결제, 가게 승인을 동기 트랜잭션으로 묶을 수 없다. process manager가 각 단계의 성공/실패 이벤트를 기준으로 다음 액션 또는 보상을 결정한다.

**트레이드오프**: 최종 일관성 모델이므로 UI는 중간 상태를 표시해야 한다. process manager의 상태와 처리 이력 저장이 필요하다.

### ADR-005: 모든 메시지 처리와 보상 커맨드는 멱등적이어야 한다

**결정**: 이벤트/커맨드는 `MessageId` 또는 결정적 `commandId`를 가진다. 보상 커맨드는 `OrderId + action`으로 id를 만든다.

**이유**: Kafka와 Outbox는 재시도와 중복 발행을 허용한다. 결제 환불, 재고 해제, 주문 취소는 중복 실행되면 손실로 이어질 수 있다.

**트레이드오프**: `ProcessedMessageRepository`, `ProcessedCommandRepository`와 중복 처리 테스트가 필요하다.

### ADR-006: MetaMask nonce 로그인으로 비밀번호 없는 인증을 사용한다

**결정**: 서버가 nonce 기반 login challenge를 발급하고, 사용자는 MetaMask `personal_sign`으로 서명한다. 비밀번호는 저장하지 않는다.

**이유**: 지갑 주소가 결제 주체 식별자이므로 지갑 소유권 증명이 로그인과 자연스럽게 연결된다.

**트레이드오프**: 지갑 분실/변경, nonce 재사용 방지, chain/domain binding 검증을 명확히 구현해야 한다.

### ADR-007: 결제는 `AWAITING_SIGNATURE` 만료를 명시적으로 처리한다

**결정**: 결제 생성 시 `expiresAt`을 저장하고, scheduler가 만료된 결제를 찾아 `PaymentExpiredEvent`를 발행한다.

**이유**: 고객이 MetaMask 서명 또는 트랜잭션 전송을 중단하면 주문/재고가 무기한 점유될 수 있다.

**트레이드오프**: 만료 기준과 사용자 재시도 UX를 정의해야 한다.

### ADR-008: Harness는 구현 오케스트레이션만 담당한다

**결정**: `scripts/execute.py`는 phase/step 실행, 가드레일 주입, 상태 갱신, 커밋 오케스트레이션만 담당한다. 제품 구현 로직은 생성되는 phase/step 또는 대상 애플리케이션 코드에 둔다.

**이유**: Harness를 프로젝트별 로직으로 오염시키면 다른 phase에서 재사용하기 어렵고, 자동 실행 경로가 불명확해진다.

**트레이드오프**: 프로젝트별 규칙은 docs와 step 명세에 구체적으로 써야 한다.

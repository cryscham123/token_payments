# 아키텍처

## 기준 문서

- DDD와 sequence 원본: `diagram/DDD.drawio`
- 도메인 상세: `docs/DOMAIN_MODEL.md`
- 업무 흐름 상세: `docs/SEQUENCES.md`
- Harness 실행 규칙: `docs/HARNESS.md`

When diagram/DDD.drawio conflicts with code package layout, code package layout wins. The checked-in package layout is the executable architecture contract for phase execution, and the diagram is interpreted as supporting context rather than an override.

## 전체 구조

Token Payments는 주문, checkout process, 재고, 결제, 가게 승인, 사용자 인증을 bounded context로 분리한 이벤트 기반 DDD 시스템이다. 각 context는 hexagonal architecture를 따른다.

```text
Client / MetaMask
  -> API Adapter
  -> Application Service / Process Manager
  -> Domain Aggregate
  -> Repository + Outbox
  -> Kafka
  -> Other Context Listeners
```

DB 상태 변경과 `OutboxMessage` 저장은 같은 트랜잭션으로 커밋한다. 외부 발행은 Outbox Relay가 Kafka로 수행한다.

## Bounded Context

| Context | 책임 | 핵심 Aggregate |
| --- | --- | --- |
| 사용자 인증 | MetaMask nonce 로그인, 세션/토큰 발급, 서명 검증 | `User`, `LoginChallenge`, `AuthSession` |
| 주문 생성 | 주문 생성, 상태 projection, checkout tracking, 결제/승인/취소 상태 반영 | `Order`, `Store`, `Customer` |
| Checkout Process | checkout saga orchestration, compensation command decision, idempotent saga decision | `CheckoutProcessManager` |
| 재고관리 | 상품 재고 예약, 확정, 해제, 수량 변경 | `ProductInventory` |
| 결제 | 결제 요청, txHash 제출, receipt 확인, 만료/환불 | `Payment`, `PaymentAuthorization` |
| 주문 승인 | 가게 소유자/상품/주문 상세 검증, 승인/반려 | `Store` |

## Architecture Boundary Contract

Checkout Process is a separate saga/process context, not an order context submodule. The executable code path is `app/token_payments/contexts/checkout/application/process_manager.py`, and its responsibility is limited to orchestration, compensation command decision, and idempotent saga decision. Order context owns order creation, status projection, and checkout tracking.

`order.Store` and `store_approval.Store` are not the same aggregate. `order.Store` is the order/catalog projection used to validate product, chain, wallet, and checkout data at order creation time. `store_approval.Store` is the approval verification projection used when a checkout saga asks the store approval context to validate an order detail. They must not share persistence or DTOs by default; any future mapping must be explicit adapter translation.

PostgreSQL is the source of truth for auth users, login challenges, and sessions. Refresh reuse detection uses the PostgreSQL session repository hash/salt/rotation model. Redis is optional cache-aside/TTL optimization, not a live required dependency, and must not replace PostgreSQL as the auth source of truth.

## Context 내부 레이어

```text
context/
  domain/
    model/             # Aggregate, Entity, Value Object
    event/             # Domain Event
  application/
    port/in/           # Use case input port
    port/out/          # Repository, Publisher, External service port
    service/           # Use case orchestration
    process/           # CheckoutProcessManager 같은 saga
  adapter/
    in/                # REST, message listener, scheduler
    out/               # PostgreSQL, Kafka, RPC, MetaMask bridge
```

도메인 레이어는 외부 기술에 의존하지 않는다. Application Service는 input/output port만 바라본다. Kafka, PostgreSQL, Blockchain RPC, MetaMask client는 adapter에서만 다룬다.

## Checkout 성공 흐름

1. 고객이 `createOrder(authenticatedUser, command)`를 호출한다.
2. 주문 context가 `Order(PENDING)`을 저장하고 `OrderCreatedEvent`를 outbox에 저장한다.
3. `CheckoutProcessManager`가 `OrderCreatedEvent`를 소비하고 `ReserveInventoryCommand`를 발행한다.
4. 재고 context가 재고를 예약하고 `InventoryReservedEvent`를 발행한다.
5. `CheckoutProcessManager`가 `InitiatePaymentCommand`를 발행한다.
6. 결제 context가 `Payment(AWAITING_SIGNATURE, expiresAt)`를 생성하고 `paymentRequest + gasEstimate`를 반환한다.
7. 고객이 MetaMask로 트랜잭션을 전송하고 `txHash`를 제출한다.
8. 결제 context가 Blockchain RPC로 receipt를 확인하고 `PaymentConfirmedEvent`를 발행한다.
9. `CheckoutProcessManager`가 `RequestStoreApprovalCommand`를 발행한다.
10. 주문 승인 context가 주문을 검증하고 `OrderApprovedEvent`를 발행한다.
11. 주문 context가 주문을 `APPROVED`로 완료한다.

## 실패와 보상

| 실패 이벤트 | Process Manager 보상 |
| --- | --- |
| `PaymentFailedEvent` | `ReleaseInventoryCommand`, `CancelOrderCommand` |
| `PaymentExpiredEvent` | `ReleaseInventoryCommand`, `CancelOrderCommand` |
| `OrderRejectedEvent` | `RefundPaymentCommand`, `ReleaseInventoryCommand`, `CancelOrderCommand` |

보상 커맨드는 `commandId = OrderId + action` 형식의 결정적 id를 사용한다. 같은 메시지가 재처리되어도 재고 해제, 환불, 주문 취소가 중복 실행되지 않아야 한다.

## 멱등성과 메시징

- 모든 이벤트/커맨드는 `MessageId` 또는 결정적 `commandId`를 가진다.
- 각 context는 `ProcessedMessageRepository` 또는 `ProcessedCommandRepository`로 처리 이력을 저장한다.
- 이미 처리한 `MessageId` 또는 이미 종료된 `OrderId`는 부작용 없이 무시한다.
- Kafka publish는 Outbox Relay가 커밋된 outbox row만 발행하고, 발행 후 `markPublished(MessageId)`를 수행한다.

## 저장소와 외부 시스템

| 시스템 | 용도 |
| --- | --- |
| PostgreSQL | aggregate, outbox, processed message/command, transaction record |
| Kafka | context 간 이벤트/커맨드 전달 |
| Redis | optional cache-aside/TTL 후보. PostgreSQL auth/session source of truth를 대체하지 않음 |
| Blockchain RPC / Web3j | tx receipt 조회, gas estimate, wallet balance 확인 |
| MetaMask Client | 지갑 연결, `personal_sign`, 결제 트랜잭션 전송 |

## 저장소 구조

현재 저장소는 Harness 기반 구현 워크스페이스다. 애플리케이션 코드는 phase 실행을 통해 추가될 수 있으며, 하네스와 도메인 문서는 다음 구조를 기준으로 유지한다.

```text
AGENTS.md                 # Codex 실행 가드레일
diagram/DDD.drawio        # DDD + sequence 원본
docs/                     # 제품/아키텍처/도메인/하네스 문서
phases/                   # Harness phase/step 명세
scripts/execute.py        # phase 실행 오케스트레이터
scripts/test_execute.py   # Harness 테스트
plugins/harness/          # repo-local Codex plugin
.codex/                   # Codex hook 설정
.githooks/                # git pre-commit 검증
```

`scripts/execute.py`는 phase 실행 오케스트레이션만 담당한다. 프로젝트별 구현 로직은 phase step 또는 대상 애플리케이션 코드에 둔다.

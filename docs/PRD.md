# PRD: Token Payments

## 목표

Token Payments는 고객이 MetaMask 지갑으로 로그인하고, 가게 상품을 암호화폐로 결제하며, 주문/재고/결제/가게 승인 흐름을 이벤트 기반으로 안전하게 완료하는 체크아웃 시스템이다.

## 문제 정의

암호화폐 결제는 결제 승인, 트랜잭션 확인, 재고 선점, 가게 승인, 실패 보상 처리가 서로 다른 시스템에서 비동기로 발생한다. 이 프로젝트는 각 업무 경계를 DDD bounded context로 분리하고, Kafka + Outbox + 멱등성으로 재시도와 중복 메시지에도 일관된 주문 상태를 유지한다.

## 사용자

- 고객: MetaMask 지갑으로 로그인하고 상품을 주문/결제한다.
- 가게 소유자: 상품, 지갑 주소, 지원 체인, 주문 승인 상태를 관리한다.
- 운영자/관리자: 주문, 결제, 재고, 보상 처리 상태를 추적한다.
- 개발자/에이전트: Harness phase/step 단위로 기능을 구현하고 검증한다.

## 핵심 기능

1. MetaMask 기반 인증
   - 서버가 nonce 기반 로그인 메시지를 발급한다.
   - 고객은 `personal_sign`으로 지갑 소유권을 증명한다.
   - 비밀번호는 저장하지 않고, 토큰은 `UserId`와 `WalletAddress` claim을 가진다.

2. 주문 생성과 추적
   - 고객, 가게, 상품 스냅샷, 배송지, 결제 금액을 기준으로 주문을 생성한다.
   - 주문 상태는 `PENDING`, `PAID`, `APPROVED`, `CANCELLING`, `CANCELLED`를 사용한다.
   - 고객은 `TrackingId`로 주문 처리 상태를 조회한다.

3. 재고 선점
   - 주문 생성 후 `ReserveInventoryCommand`로 상품 재고를 선점한다.
   - 재고 context는 예약, 확정, 해제, 만료 이벤트를 발행한다.
   - 재고 수량 변경은 `Quantity` 값 객체를 통해 검증한다.

4. 암호화폐 결제
   - 결제 context는 `Payment` aggregate를 생성하고 `AWAITING_SIGNATURE` 상태와 만료 시각을 기록한다.
   - MetaMask가 결제 트랜잭션을 전송하면 `txHash`를 제출하고 블록체인 RPC로 receipt를 확인한다.
   - gas estimate에는 buffer rate를 적용한다.

5. 가게 승인
   - 결제 확인 후 가게 승인 context가 주문 상세와 상품 상태를 검증한다.
   - 승인 시 `OrderApprovedEvent`, 반려 시 `OrderRejectedEvent`를 발행한다.

6. CheckoutProcessManager
   - `OrderCreated`, `InventoryReserved`, `PaymentConfirmed`, `PaymentFailed`, `PaymentExpired`, `OrderApproved`, `OrderRejected` 이벤트를 처리한다.
   - `MessageId`와 `OrderId` 기준 멱등성으로 중복 처리를 막는다.
   - 실패 시 재고 해제, 결제 환불, 주문 취소 보상 커맨드를 발행한다.

## MVP 포함 범위

- MetaMask 로그인 challenge 발급/검증
- 고객 주문 생성 API와 주문 추적 API
- 재고 예약/확정/해제 API 또는 메시지 핸들러
- 결제 생성, txHash 제출, receipt 확인, 결제 만료 처리
- 가게 주문 승인/반려
- Kafka + Outbox 기반 이벤트 발행
- PostgreSQL 기반 aggregate 저장소
- Redis 또는 PostgreSQL 기반 nonce/session 저장소
- Harness phase/step 실행 문서와 기본 `phases/index.json`

## MVP 제외 사항

- 실시간 환율 견적과 법정화폐 정산
- 다중 지갑 연결 관리 UI의 고급 기능
- 부분 배송, 부분 환불, 부분 취소
- 크로스체인 브리지 또는 토큰 스왑
- 관리자용 정산/회계 리포트
- 복잡한 상품 옵션, 쿠폰, 포인트, 구독 결제

## 성공 기준

- 정상 checkout sequence가 주문 승인까지 완료된다.
- 결제 실패, 결제 만료, 가게 반려 상황에서 보상 커맨드가 멱등적으로 발행된다.
- 모든 DB 상태 변경과 Outbox row 저장은 같은 트랜잭션으로 커밋된다.
- 중복 메시지 또는 재시도 상황에서 같은 주문에 대해 중복 결제/환불/재고 해제가 발생하지 않는다.
- Harness step 실행 프롬프트가 `AGENTS.md`와 `docs/*.md` 가드레일을 포함한다.

## 디자인 방향

- 첫 화면은 실제 checkout 또는 운영 대시보드여야 한다. 마케팅 랜딩 페이지를 기본 화면으로 두지 않는다.
- 고객 화면은 지갑 연결, 주문 금액, 네트워크, gas estimate, 결제 만료 시간을 명확히 보여준다.
- 운영 화면은 주문/결제/재고/승인 상태를 빠르게 스캔할 수 있는 조밀한 업무형 UI로 구성한다.
- 시각 스타일은 중립 배경, 명확한 상태 색상, 과한 glass/gradient 장식을 배제한다.

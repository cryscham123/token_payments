# UI 디자인 가이드

## 디자인 원칙

1. 체크아웃과 운영 업무가 첫 화면이어야 한다. 기능 설명용 랜딩 페이지를 기본 화면으로 만들지 않는다.
2. 암호화폐 결제의 불안 요소를 줄인다. 네트워크, 지갑 주소, 결제 금액, gas estimate, 만료 시간, txHash 상태를 명확히 노출한다.
3. 운영 화면은 조밀하고 스캔 가능해야 한다. 주문/결제/재고/승인 상태를 비교하기 쉬운 테이블과 필터를 우선한다.
4. 상태 전이는 숨기지 않는다. `PENDING`, `AWAITING_SIGNATURE`, `SUBMITTED`, `CONFIRMED`, `APPROVED`, `CANCELLED` 같은 도메인 상태를 UI에 그대로 반영한다.

## 금지 패턴

| 금지 사항 | 이유 |
| --- | --- |
| `backdrop-filter: blur()` 중심 glass UI | 결제/운영 UI에서 정보 대비를 낮춘다 |
| gradient text | 금액과 상태를 읽기 어렵게 만든다 |
| 보라/인디고 단색 계열 지배 팔레트 | 결제/운영 도메인과 무관한 AI SaaS 느낌이 강하다 |
| 배경 gradient orb, bokeh 장식 | 상태 정보보다 장식이 눈에 띈다 |
| 모든 영역을 큰 카드로 감싸기 | 업무형 화면의 정보 밀도를 낮춘다 |
| 애매한 "Processing..."만 표시 | 사용자가 wallet 서명 대기, tx 제출, receipt 확인 중 무엇인지 알 수 없다 |

## 핵심 화면

### 고객 Checkout

- 상단: 연결된 지갑 주소, 네트워크, 주문 번호
- 본문: 상품 스냅샷, 수량, 토큰 금액, 수수료 추정치, 수신 지갑 주소
- 액션: 지갑 연결, 서명 요청, txHash 제출, 주문 추적
- 상태: 결제 만료 countdown, 현재 checkout step, 실패 원인

### 주문 추적

- 주문 상태 timeline: 주문 생성, 재고 예약, 결제 대기, tx 제출, 결제 확인, 가게 승인, 완료
- 각 단계에는 이벤트 시각과 메시지 id를 표시한다.
- 실패 단계는 보상 상태를 함께 보여준다.

### 운영 Dashboard

- 기본 뷰는 주문/결제/재고/승인 상태 테이블이다.
- 필터: context, status, chainId, store, createdAt, failed only
- 상세 패널: aggregate id, latest event, outbox status, processed message 기록

### Store Owner Inventory

- API/backend contract supports own store inventory query, stock intake, target total correction, sale pause, and sale resume.
- `STORE_OWNER` screens must be scoped to own store inventory; admin can query or mutate any store inventory from operational tooling.
- Manual order approval HTTP API is not in current scope for this surface.
- UI implementation remains a separate phase; this phase only fixes the backend/API contract.

## 색상

### 배경과 표면

| 용도 | 값 |
| --- | --- |
| 페이지 | `#f7f8fa` |
| 주요 표면 | `#ffffff` |
| 보조 표면 | `#eef1f4` |
| 경계선 | `#d5dbe3` |
| 어두운 운영 패널 | `#111827` |

### 텍스트

| 용도 | 값 |
| --- | --- |
| 주 텍스트 | `#111827` |
| 본문 | `#374151` |
| 보조 | `#6b7280` |
| 비활성 | `#9ca3af` |
| 어두운 표면 텍스트 | `#f9fafb` |

### 데이터/시맨틱 색상

| 상태 | 값 | 사용 |
| --- | --- | --- |
| 성공 | `#15803d` | 승인, 결제 확인, 재고 확정 |
| 진행 | `#2563eb` | tx 제출, receipt 확인, process manager 처리 |
| 대기 | `#b45309` | 서명 대기, 가게 승인 대기, 재고 예약 |
| 실패 | `#b91c1c` | 결제 실패, 서명 만료, 반려 |
| 중립 | `#475569` | 취소, 무시된 중복 메시지 |

## 컴포넌트

### 버튼

```text
Primary:   radius 6px, solid #111827, white text
Secondary: radius 6px, white surface, #d5dbe3 border
Danger:    radius 6px, solid #b91c1c, white text
Icon:      36x36 fixed square, tooltip required
```

버튼 문구는 도메인 액션을 그대로 쓴다. 예: `Connect Wallet`, `Sign Payment`, `Submit txHash`, `Retry Refund`.

### 상태 Badge

```text
height 24px, radius 999px, compact padding
label은 domain status enum과 일치
```

색상만으로 상태를 구분하지 않는다. 항상 텍스트 label을 함께 보여준다.

### 테이블

- 행 높이는 44-52px로 유지한다.
- id는 축약 표시하되 복사 버튼을 둔다.
- 금액, 수량, gas는 우측 정렬한다.
- 실패 행은 error reason과 마지막 이벤트 시각을 한 줄에 표시한다.

### Timeline

- 각 step은 고정 높이를 유지한다.
- 완료/진행/실패/대기 아이콘을 사용한다.
- txHash, messageId, commandId는 복사 가능한 monospace 텍스트로 표시한다.

## 레이아웃

- 고객 checkout: 최대 너비 `960px`, 좌측 주문 정보, 우측 결제 실행 패널.
- 운영 dashboard: 전체 너비를 사용하고, 좌측 필터 + 중앙 테이블 + 우측 상세 패널 구조를 허용한다.
- 모바일 checkout: 결제 실행 패널을 상단으로 올리고 timeline은 접을 수 있게 한다.
- 카드 중첩은 금지한다. 반복 item, modal, 상세 패널에만 card 스타일을 사용한다.

## 타이포그래피

| 용도 | 스타일 |
| --- | --- |
| 페이지 제목 | 28px, weight 650 |
| 섹션 제목 | 18px, weight 650 |
| 테이블 헤더 | 12px, weight 600, uppercase 금지 |
| 본문 | 14px, line-height 1.5 |
| id/txHash | 13px monospace |
| 금액 | 15px monospace, weight 600 |

## 애니메이션

- 허용: 120-180ms opacity/transform transition
- 허용: 결제 대기 countdown의 숫자 변경
- 금지: glow, pulse loop, background movement, 과한 success confetti

## 아이콘

- 기존 프론트엔드에서 icon library가 있으면 그 라이브러리를 사용한다.
- 새 React UI를 만들 경우 `lucide-react`를 우선 사용한다.
- 지갑, 복사, 새로고침, 필터, 경고, 외부 링크는 텍스트 대신 아이콘 버튼을 사용할 수 있으며 tooltip을 둔다.

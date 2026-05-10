# Step 1: customer-checkout-ui

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/phases/4-customer-operator-ui/index.json`
- Step 0에서 생성/수정한 UI foundation 파일
- `/app/token_payments/api/auth.py`
- `/app/token_payments/api/orders.py`
- `/app/token_payments/api/checkout.py`
- `/app/token_payments/api/payments.py`

## 작업

Customer checkout 화면을 실제 결제 업무 첫 화면으로 구현한다. 동작 변경이므로 먼저 `scripts/test_customer_checkout_ui.py`를 추가하거나 갱신하고 실패를 확인한 뒤 구현한다.

1. 고객 checkout renderer와 view model을 추가한다.
   - 연결된 지갑 주소, 네트워크/chain id, 주문 번호, 상품 스냅샷, 수량, 토큰 금액, gas estimate, 수신 지갑 주소를 표시한다.
   - payment expiration countdown 값과 현재 checkout step을 명확히 표현한다.
   - `txHash` 제출 상태와 실패 원인, pending action을 표시한다.
2. checkout timeline을 구현한다.
   - 주문 생성, 재고 예약, 결제 대기, tx 제출, 결제 확인, 가게 승인, 완료 단계를 고정 순서로 보여준다.
   - 각 단계에 도메인 상태 label, 이벤트 시각, message id 또는 command id를 표시할 수 있어야 한다.
   - 실패 단계에는 보상 상태를 함께 표시한다.
3. 고객 액션 표면을 구현한다.
   - `Connect Wallet`, `Sign Payment`, `Submit txHash`, `Track Order` 같은 도메인 액션을 button/action model로 노출한다.
   - 아이콘/툴팁 affordance는 CSS class와 accessible label로 표현한다. 외부 icon library는 추가하지 않는다.
4. responsive layout을 고정한다.
   - desktop은 좌측 주문 정보와 우측 결제 실행 패널 구조를 유지한다.
   - mobile은 결제 실행 패널이 먼저 읽히고 timeline이 겹치거나 넘치지 않아야 한다.
5. fixture 기반 HTML snapshot/semantic 테스트를 추가한다.
   - wallet/txHash/order id escaping, status badge label, amount/gas right alignment, disabled action state를 검증한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_ui_contract_foundation.py scripts/test_customer_checkout_ui.py
python3 -m pytest scripts/test_checkout_tracking_payment_api.py scripts/test_order_api_checkout_start.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. customer checkout이 `docs/UI_GUIDE.md`의 checkout/주문 추적 요구사항을 만족하는지 확인한다.
3. Step 0 foundation을 중복 없이 재사용했는지 확인한다.
4. `/phases/4-customer-operator-ui/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 마케팅 랜딩/hero 화면을 추가하지 마라.
- 실제 MetaMask secret, private key, seed phrase 입력 UI를 만들지 마라.
- checkout UI에서 operator dashboard 전용 기능을 구현하지 마라.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

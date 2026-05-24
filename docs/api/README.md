# API 개요

Token Payments API는 로컬 backend의 public HTTP surface를 설명한다. 상세 요청/응답 예시와 canonical route manifest는 [API 명세](../API_SPEC.md)를 기준으로 한다.

## 기본 정보

| 항목 | 값 |
| --- | --- |
| 기본 URL | `http://127.0.0.1:8000` 또는 live runtime에서 노출한 host |
| 데이터 형식 | JSON |
| 인증 | SIWE session cookie 또는 bearer-style local session context |
| CSRF | browser cookie auth write 요청은 `X-CSRF-Token` 필요 |
| Idempotency | write 요청 중 주문/결제/재고/운영자 action은 `Idempotency-Key` 사용 |

## GitBook에서 읽는 순서

1. [인증과 OAuth](auth.md)에서 session 생성과 wallet/OAuth identity 연결 규약을 확인한다.
2. [상점과 상품 카탈로그](catalog-inventory.md)에서 public read와 merchant write의 identifier 차이를 확인한다.
3. [주문, 체크아웃, 결제](orders-checkout-payments.md)에서 `trackingId` 중심 결제 흐름을 확인한다.
4. [머천트, 관리자, RBAC](merchant-admin-rbac.md)에서 merchant membership과 권한 scope를 확인한다.
5. [운영자와 런타임](operator-runtime.md)에서 operator recovery API와 no-server-start runtime boundary를 확인한다.

## 현재 public route surface

현재 public HTTP route surface는 `app/token_payments/api/http.py`의 54개 route manifest와 일치해야 한다. Postman collection과 expected response fixture도 같은 surface를 따라야 하며, 새 기능 phase는 API가 내부 전용 예외인지 명시하지 않는 한 API 명세와 테스트를 함께 갱신한다.

## 공통 응답 규약

성공 응답은 endpoint별 resource wrapper를 사용한다. 오류 응답은 bounded error code와 message를 포함하며, 민감한 내부 id, provider token, raw signature verification detail은 public response에 노출하지 않는다.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "request body is invalid"
  }
}
```

## Postman

로컬 검증용 Postman 파일은 `postman/token-payments.local.postman_collection.json`, `postman/token-payments.local.postman_environment.json`, `postman/expected/token-payments.api.expected.json`을 사용한다.

# 공통 계약

이 페이지는 API 공통 계약을 GitBook에서 한국어로 읽기 쉽게 정리한 상세 페이지다. endpoint별 요청/응답 예시는 각 도메인 페이지와 [전체 Route Summary](route-summary.md)를 함께 본다.

## API Evolution Guardrail

신규 사용자/업무 기능은 의도적으로 내부 전용이라고 명시하지 않는 한 API surface와 함께 설계한다. 새 기능 phase는 endpoint/operation contract, route manifest, public fixtures, Postman expected data, API tests를 같이 갱신해야 한다.

API가 없는 순수 내부 기능은 phase step과 완료 summary에 `intentional internal-only exception`과 이유를 남긴다.

## Route Surface Contract

현재 public HTTP route surface는 `app/token_payments/api/http.py`의 54개 route manifest와 정확히 일치해야 한다. 여기에는 auth session, OAuth provider-subject login/link/list/revoke, wallet link/list/primary/revoke, current user profile, order creation, checkout tracking, payment txHash submission, public/merchant store profile, admin provisioning, merchant product, store owner inventory, merchant member/invitation, operator dashboard/detail/action API가 포함된다.

현재 범위에 포함되지 않는 HTTP API는 store owner manual approval, role/permission full CRUD, platform group CRUD, personal group CRUD, owner transfer, settlement wallet mutation, checkout saga command endpoint다.

### Message listener input surface

`approveOrder`와 `request_store_approval`은 Kafka/message listener 입력이다. Store approval은 payment confirmation 이후 checkout saga가 `RequestStoreApprovalCommand`를 emit할 때 실행되며, store owner manual order approval HTTP API는 현재 범위가 아니다.

### Internal application port surface

`ReserveInventoryCommand`, `ReleaseInventoryCommand`, `ConfirmInventoryCommand`는 checkout saga 내부 command다. public customer HTTP API로 노출하지 않는다.

### Admin store catalog provisioning API surface

`POST /admin/store-users`, `POST /admin/stores`, `POST /admin/stores/{storeId}/memberships`는 `admin:provision` 또는 `rbac:manage` 권한이 필요하다. Public customer login은 global `STORE_OWNER` role을 부여하지 않는다.

### Multi-wallet and stablecoin payment contract

로그인 wallet, linked wallet, payer wallet, settlement wallet은 서로 다른 개념이다. Checkout write API는 `paymentAssetId`와 optional `walletId`를 받으며, raw wallet address나 arbitrary token address를 소유 증명/asset support로 신뢰하지 않는다.

Stablecoin support는 registry 기반이다. local registry는 native coin과 USDC/USDT 같은 ERC-20 stablecoin asset을 활성화할 수 있으며, disabled asset과 임의 ERC-20 contract는 거부한다.

### Privacy-first OAuth identity contract

OAuth/social identity는 email이 아니라 `provider`와 `providerSubject`로 식별한다. Google email claim은 저장하지 않고 email/hash matching으로 계정을 자동 병합하지 않는다. Public OAuth response는 `oauthIdentityId`, `provider`, optional `walletId`, `linkedAt`, `revokedAt`만 노출하고 provider subject, provider token, email claim, profile dump는 숨긴다.

### Store profile API surface

`GET /stores/{publicStoreId}`는 public business profile projection만 반환한다. 내부 `store_id`, owner user id, group id, settlement wallet, supported chains, private support contact, business registration label은 반환하지 않는다.

`PATCH /merchant/stores/{publicStoreId}/profile`은 business profile 필드만 수정한다. Settlement wallet, supported chain 변경, owner transfer, member invite/remove, role/permission 변경은 별도 정책-gated 흐름이다.

### Store owner inventory API surface

`GET /store-owner/inventory`는 active membership과 `inventory:read` 권한으로 볼 수 있는 inventory row만 반환한다. Mutation은 `inventory:write`, `Idempotency-Key`, CSRF, `reason`, membership/ownership 검사를 요구한다.

## Runtime Assumptions

Runtime은 local development와 bounded live execution을 분리한다. 기본 `api`/`serve-api` 명령은 no-server-start preview boundary를 유지하고, live server 시작은 명시 flag와 승인된 환경을 요구한다.

```bash
PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run
PYTHONPATH=app python3 -m token_payments serve-api --live --confirm-live-api
```

## Common Headers

| Header | 용도 |
| --- | --- |
| `Content-Type: application/json` | JSON 요청 body |
| `Idempotency-Key` | 주문, 결제, 재고, operator action 같은 write command의 멱등성 |
| `X-Request-Id` | request correlation. 응답에도 보존 |
| `X-CSRF-Token` | browser cookie auth write 요청의 double-submit CSRF token |
| `X-User-Id`, `X-User-Scopes` | local/operator harness fallback context |

## Cookie And CSRF Policy

Browser auth는 signed HttpOnly access/refresh cookie와 `csrf_token` double-submit cookie를 사용한다. Cookie 값, signed token, authorization header, signature, private key, full request body는 public response와 access log에 기록하지 않는다.

Browser cookie auth write 요청은 CSRF header 검증을 통과해야 한다. CSRF 실패는 bounded `403` 오류로 매핑한다.

## Live System Routes And Observability

`GET /healthz`와 `GET /readyz`는 live server-only system route이며 54개 public facade manifest에 포함하지 않는다. `/healthz`는 process/runtime health만 보고, `/readyz`는 주입된 PostgreSQL/Kafka/Blockchain readiness probe 결과를 bounded component detail로 요약한다.

모든 HTTP response는 가능한 경우 `X-Request-Id`를 포함한다. Access log는 method, path template 또는 route id, status, request id, duration, actor summary, error code를 기록하되 secret payload는 기록하지 않는다.

## Common Error Shape

오류 응답은 bounded error code와 message를 포함한다.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "request body is invalid"
  }
}
```

공통 HTTP status는 `400`, `401`, `403`, `404`, `405`, `409`, `413`을 사용한다.

## State Values

Order status는 `PENDING`, `PAID`, `APPROVED`, `CANCELLING`, `CANCELLED`를 사용한다. Payment status는 `AWAITING_SIGNATURE`, `TX_SUBMITTED`, `CONFIRMED`, `FAILED`, `EXPIRED`, `REFUNDED`를 사용한다.

Checkout pending action 예시는 `SIGN_PAYMENT`, `WAIT_FOR_RECEIPT`, `WAIT_FOR_STORE_APPROVAL`, `WAIT_FOR_COMPENSATION`이다. Outbox/message kind는 `EVENT`, `COMMAND`이고 operator action status는 `accepted`, `duplicate`, `rejected`다.

## Postman Flow

Local happy path는 `POST /auth/challenges`, MetaMask signing, `POST /auth/sessions`, `POST /orders`, `GET /checkouts/tracking/{trackingId}`, payment transaction 전송, `POST /payments/transaction-hashes`, `GET /checkouts/orders/{orderId}` polling 순서로 검증한다.

Postman 파일은 `postman/token-payments.local.postman_collection.json`, `postman/token-payments.local.postman_environment.json`, `postman/expected/token-payments.api.expected.json`을 사용한다. Expected fixture는 signed token과 cookie 값을 redacted shape로 유지한다.

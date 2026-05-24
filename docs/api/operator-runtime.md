# 운영자와 런타임

운영자 API는 platform recovery surface다. global admin role이 아니라 `operator:read`, `operator:action`, `outbox:retry` 같은 명시 permission으로 권한을 판단한다.

## Operator read route

빠른 참조: `GET /operator/dashboard`, `GET /operator/orders/{orderId}`, `GET /operator/payments/{paymentId}`, `GET /operator/outbox/{messageId}`.

| 목적 | Method | Path | 권한 |
| --- | --- | --- | --- |
| dashboard 조회 | `GET` | `/operator/dashboard` | `operator:read` |
| order 상세 | `GET` | `/operator/orders/{orderId}` | `operator:read` |
| payment 상세 | `GET` | `/operator/payments/{paymentId}` | `operator:read` |
| outbox 상세 | `GET` | `/operator/outbox/{messageId}` | `operator:read` |

read API는 운영자가 recovery 판단에 필요한 bounded projection만 반환한다. customer/browser surface에 노출하지 않는 내부 id가 operator response에는 포함될 수 있지만, provider token이나 raw OAuth subject 같은 secret payload는 포함하지 않는다.

## Operator action route

빠른 참조: `POST /operator/orders/{orderId}/cancel`, `POST /operator/outbox/{messageId}/retry`, `POST /operator/messages/{messageId}/replay`.

| 목적 | Method | Path | 권한 |
| --- | --- | --- | --- |
| order cancel | `POST` | `/operator/orders/{orderId}/cancel` | `operator:action` |
| outbox retry | `POST` | `/operator/outbox/{messageId}/retry` | `operator:action` + `outbox:retry` |
| message replay | `POST` | `/operator/messages/{messageId}/replay` | `operator:action` |

action 요청은 `Idempotency-Key`, actor audit context, bounded reason을 요구한다. retry/replay는 멱등성과 outbox 상태 전이를 보존해야 한다.

## Runtime boundary

기본 `api`와 `serve-api` 명령은 no-server-start preview boundary를 유지한다. live server를 시작하기 전에는 다음 dry-run으로 bounded plan을 확인한다.

```bash
PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run
```

장시간 실행 server는 승인된 live 환경에서만 다음 confirm flag로 시작한다.

```bash
PYTHONPATH=app python3 -m token_payments serve-api --live --confirm-live-api
```

Docker smoke와 Postman 검증도 같은 public route manifest, readiness contract, expected fixture를 기준으로 한다.

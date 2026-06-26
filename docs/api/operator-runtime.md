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

## Endpoint 상세

| Endpoint | 인증/권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- |
| `GET /operator/dashboard` | platform/operator session, `operator:read` | query `context`/`contexts`, `status`, `chainId`, `storeId`, `failedOnly`, `retryCandidatesOnly`, `sort`, `limit`, `pageToken` | `200` snapshot envelope with `orders`, `payments`, `outbox`, `workers`, `errors`, `pagination` | `400 VALIDATION_ERROR`, `403 OPERATOR_FORBIDDEN` |
| `GET /operator/orders/{orderId}` | platform/operator session, `operator:read` | path `orderId` | `200` operator snapshot narrowed to one order; may include internal recovery ids | `403 OPERATOR_FORBIDDEN`, `404 OPERATOR_RESOURCE_NOT_FOUND` |
| `GET /operator/payments/{paymentId}` | platform/operator session, `operator:read` | path `paymentId` | `200` operator snapshot narrowed to one payment with chain/wallet/tx status | `403 OPERATOR_FORBIDDEN`, `404 OPERATOR_RESOURCE_NOT_FOUND` |
| `GET /operator/outbox/{messageId}` | platform/operator session, `operator:read` | path `messageId`; query `kind=EVENT|COMMAND`, default `EVENT` | `200` outbox item with status, failure count, retry candidate metadata | `400 VALIDATION_ERROR`, `403 OPERATOR_FORBIDDEN`, `404 OPERATOR_RESOURCE_NOT_FOUND` |
| `POST /operator/orders/{orderId}/cancel` | platform/operator session, `operator:action` | JSON body `reason`, `idempotencyKey`, optional `parameters`; header `Idempotency-Key` accepted | `202 accepted`, `200 duplicate`, or bounded rejected action envelope | `400 OPERATOR_ACTION_VALIDATION_FAILED`, `403 OPERATOR_FORBIDDEN`, `409 OPERATOR_ACTION_REJECTED` |
| `POST /operator/outbox/{messageId}/retry` | platform/operator session, `operator:action` + `outbox:retry` | JSON body `kind` 또는 `messageKind`, `reason`, `idempotencyKey`, optional `parameters` | `202 accepted`, `200 duplicate`, or bounded rejected action envelope with `messageId` | `400 OPERATOR_ACTION_VALIDATION_FAILED`, `403 OPERATOR_FORBIDDEN`, `409 OPERATOR_ACTION_REJECTED` |
| `POST /operator/messages/{messageId}/replay` | platform/operator session, `operator:action` | JSON body `kind` 또는 `messageKind`, `reason`, `idempotencyKey`, optional `parameters` | `202 accepted`, `200 duplicate`, or bounded rejected action envelope | `400 OPERATOR_ACTION_VALIDATION_FAILED`, `403 OPERATOR_FORBIDDEN`, `409 OPERATOR_ACTION_REJECTED` |

## Live system route

| Endpoint | 인증/권한 | 요청 | 성공 응답 | 오류 |
| --- | --- | --- | --- | --- |
| `GET /healthz` | live system route | no body | `200` process/runtime health only | `503` if process health fails |
| `GET /readyz` | live system route | no body | `200` when injected PostgreSQL/Kafka/Blockchain readiness probes are ready | `503` with bounded component details |

`GET /healthz`와 `GET /readyz`는 public facade 62-route manifest에는 포함되지 않는다.

## 요청 예시

Outbox retry:

```json
{
  "kind": "EVENT",
  "reason": "broker recovered",
  "idempotencyKey": "operator-retry-msg-001",
  "parameters": {
    "maxAttempts": 1
  }
}
```

# Step 5: readiness-observability-idempotency

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/API_SPEC.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/api/http.py`
- `/app/token_payments/runtime/config.py`
- `/app/token_payments/runtime/contracts.py`
- `/app/token_payments/runtime/observability.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/runtime/session_transport.py`
- `/app/token_payments/runtime/security.py`
- `/app/token_payments/runtime/api_server.py`
- `/app/token_payments/shared/adapter/postgres/outbox.py`
- `/app/token_payments/shared/adapter/postgres/idempotency.py`
- `/scripts/test_operator_observability_api.py`
- `/scripts/test_operator_action_public_contracts.py`
- `/scripts/test_live_api_server_entrypoint.py`
- `/phases/14-live-api-runtime-composition/index.json`

## 작업

live API runtime의 운영 기본 계약을 닫는다: health/readiness route, request id propagation, structured access log contract, `Idempotency-Key` header 표준화. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_readiness_observability_idempotency.py`를 추가한다.
   - `/healthz`는 process/runtime health만 반환하고 DB/Kafka/Blockchain을 열지 않아야 한다.
   - `/readyz`는 injected readiness probes를 통해 PostgreSQL/Kafka/Blockchain dependency 준비 상태를 요약해야 하며, 테스트에서는 fake probe를 사용한다.
   - readiness 실패는 `503`과 component별 bounded JSON details를 반환해야 하며 secret/config raw value를 노출하지 않아야 한다.
   - 모든 HTTP response는 `X-Request-Id`를 포함하고 incoming `X-Request-Id`를 보존해야 한다.
   - structured access log event contract는 method, path template 또는 route id, status, request id, duration, actor summary, error code를 포함하되 token/cookie/body secret을 기록하지 않아야 한다.
   - `Idempotency-Key` header를 주문 생성, payment txHash submit, operator action endpoints에 표준 입력으로 연결해야 한다.
   - body의 `commandId`/`idempotencyKey`와 header가 함께 오면 충돌을 deterministic validation error로 처리해야 한다.
   - 기존 body 기반 idempotency와 결정적 command id fallback은 backward-compatible하게 유지해야 한다.
2. route manifest를 확장한다.
   - `GET /healthz`, `GET /readyz`를 추가할지, live server-only system routes로 둘지 선택한다.
   - public route manifest에 추가한다면 기존 route count 기대값 테스트를 함께 갱신한다.
   - live server-only route로 두면 phase 15 Docker readiness가 접근할 수 있는 별도 manifest/metadata를 제공한다.
3. `app/token_payments/runtime/observability.py` 또는 새 module을 확장한다.
   - readiness probe protocol과 access log event DTO를 둔다.
   - live entrypoint에 guard/router wrapper로 연결한다.
4. `docs/API_SPEC.md`와 README/app README를 갱신한다.
   - `/healthz`, `/readyz`, `Idempotency-Key`, request id propagation, access log redaction 기준을 문서화한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_readiness_observability_idempotency.py scripts/test_live_api_server_entrypoint.py scripts/test_operator_observability_api.py scripts/test_operator_action_public_contracts.py scripts/test_http_adapter_public_contracts.py
PYTHONPATH=app python3 -m token_payments api
PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 readiness/observability/idempotency 테스트를 먼저 추가하고 실패를 확인한다.
2. AC 커맨드를 실행한다.
3. `/phases/14-live-api-runtime-composition/index.json`의 step 5 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- `/healthz`가 live infrastructure 연결을 필수로 열게 만들지 마라.
- access log에 cookie, token, signature, private key, full request body를 기록하지 마라.
- idempotency behavior를 endpoint마다 제각각 구현하지 마라.
- Docker compose API service나 Postman collection을 이 step에 추가하지 마라.
- 새 third-party dependency를 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

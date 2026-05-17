# Step 3: health-readiness-live-probes

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/API_SPEC.md`
- `/app/token_payments/runtime/api_server.py`
- `/app/token_payments/runtime/composition.py`
- `/app/token_payments/runtime/contracts.py`
- `/app/token_payments/runtime/observability.py`
- `/scripts/test_readiness_observability_idempotency.py`
- `/scripts/test_docker_api_readiness_security_smoke.py`
- `/scripts/docker_live_smoke.py`

## 작업

Live server의 `/healthz`와 `/readyz`가 실제 local dependencies 상태를 안전하게 보고하도록 readiness probe를 완성한다. `/healthz`는 process health만 보고, `/readyz`는 PostgreSQL/Kafka/Blockchain readiness를 bounded timeout으로 확인한다.

1. `scripts/test_live_readiness_probe_wiring.py`를 추가한다.
   - `/healthz`는 DB/Kafka/Blockchain을 열지 않고 process/config 상태만 반환해야 한다.
   - `/readyz`는 injected probe를 통해 PostgreSQL, Kafka, Blockchain readiness를 확인해야 한다.
   - 실패한 component는 redacted bounded detail과 `503`을 반환해야 한다.
   - access log/readiness payload는 cookie, token, signing key, private key, DSN password, RPC credential을 노출하지 않아야 한다.
2. runtime readiness probe를 구현한다.
   - PostgreSQL lightweight query
   - Kafka metadata or producer readiness check
   - Blockchain RPC chain id check
   - 각 probe timeout과 error mapping
3. Docker/Postman smoke plan을 갱신한다.
   - API start 후 `/healthz`, `/readyz`, auth challenge/session, checkout happy path의 순서를 문서화한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_live_readiness_probe_wiring.py scripts/test_readiness_observability_idempotency.py scripts/test_docker_api_readiness_security_smoke.py
PYTHONPATH=app python3 -m token_payments smoke postman-docker-api-readiness
python3 scripts/validate_phases.py
```

## 검증 절차

1. readiness probe wiring 테스트를 먼저 추가하고 실패를 확인한다.
2. runtime/smoke/docs를 갱신한 뒤 AC를 실행한다.
3. `/phases/17-docker-compose-live-server/index.json`의 step 3 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- `/healthz`에서 DB/Kafka/Blockchain 연결을 열지 마라.
- readiness failure를 200으로 숨기지 마라.
- secret 원문이나 full connection string을 readiness/access log에 노출하지 마라.
- automated harness에서 실제 Docker compose stack을 시작하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

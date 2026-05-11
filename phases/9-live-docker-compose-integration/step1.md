# Step 1: compose-runtime-service-contract

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/README.md`
- `/app/README.md`
- `/docker-compose.yml`
- `/Dockerfile`
- `/.dockerignore`
- `/.env.example`
- `/scripts/test_compose_readiness_smoke.py`
- `/scripts/test_docker_runtime_image_contracts.py`
- `/app/token_payments/runtime/smoke.py`
- `/phases/9-live-docker-compose-integration/index.json`

## 작업

기존 PostgreSQL/Kafka/test_network compose stack에 Token Payments runtime one-shot service 계약을 추가한다. 동작 변경이므로 먼저 테스트를 작성하거나 갱신하고 실패를 확인한 뒤 구현한다.

1. `scripts/test_docker_compose_runtime_services.py`를 추가한다.
   - `docker-compose.yml`에 app runtime image를 공유하는 one-shot service들이 있어야 한다.
   - service 이름은 명확해야 한다: `token_payments_health`, `token_payments_worker`, `token_payments_smoke`.
   - 세 service 모두 repository root `Dockerfile`을 build context로 사용하고 `.env`를 `env_file`로 참조해야 한다.
   - 세 service 모두 `PYTHONPATH=/workspace/app` 또는 Dockerfile과 일치하는 container app path를 가져야 한다.
   - health service command는 `python -m token_payments health`여야 한다.
   - worker service command는 bounded one-batch worker command(`python -m token_payments worker`)여야 한다.
   - smoke service command는 deterministic smoke command(`python -m token_payments smoke compose-readiness`)여야 한다.
   - app runtime services는 `restart: "no"` 또는 동등한 one-shot contract여야 하며 long-running server를 기본 실행하지 않아야 한다.
   - app runtime services는 `postgres`, `kafka`, `test_network`에 명시적으로 의존해야 한다. 가능한 경우 `postgres`는 `service_healthy` 조건을 유지한다.
   - 기존 required infrastructure services(`postgres`, `kafka`, `kafka-ui`, `pgweb`, `test_network`) 계약을 깨뜨리지 않아야 한다.
2. `docker-compose.yml`을 갱신한다.
   - `x-token-payments-runtime` YAML anchor 같은 중복 제거는 허용하되, 표준 Docker Compose가 해석할 수 있는 문법만 사용한다.
   - app one-shot services는 필요하면 `profiles: ["runtime"]` 또는 `profiles: ["smoke"]`로 묶되, 테스트가 명시적으로 확인할 수 있게 작성한다.
   - 기존 infra service 이름과 env/volume/healthcheck 계약은 유지한다.
3. 기존 `compose-readiness` smoke와 `scripts/test_compose_readiness_smoke.py`의 infrastructure 계약이 계속 통과해야 한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_docker_compose_runtime_services.py scripts/test_compose_readiness_smoke.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/9-live-docker-compose-integration/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step에서 Docker daemon이 필요한 live container 실행을 필수 검증으로 만들지 마라.
- `compose-readiness` 기존 public payload shape를 깨뜨리지 마라.
- Kafka/PostgreSQL/test_network service 이름을 바꾸지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

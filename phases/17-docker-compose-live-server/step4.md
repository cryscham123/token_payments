# Step 4: compose-live-public-verification

## 읽어야 할 파일

- `/AGENTS.md`
- `/README.md`
- `/app/README.md`
- `/docs/API_SPEC.md`
- `/.env.example`
- `/Dockerfile`
- `/docker-compose.yml`
- `/scripts/test_docker_compose_live_server_default.py`
- `/scripts/test_live_runtime_driver_factory.py`
- `/scripts/test_local_env_seed_contract.py`
- `/scripts/test_live_readiness_probe_wiring.py`
- `/scripts/test_postman_docker_api_public_contracts.py`
- `/phases/index.json`
- `/phases/17-docker-compose-live-server/index.json`

## 작업

`docker compose up` local live server phase의 public contract를 고정한다. 이 step에서 실제 운영 보증을 주장하지 말고, local dev live stack이 어떤 env/seed/smoke 기준으로 동작하는지 명확히 문서화한다.

1. `scripts/test_compose_live_server_public_contracts.py`를 추가한다.
   - README/app README/API spec이 `cp .env.example .env` 후 `docker compose up` 경로를 설명하는지 검증한다.
   - Docker daemon 없는 테스트에서는 compose config/static contract만 검증한다고 명시하는지 검증한다.
   - `.env.example`의 local dev 값과 live/prod secret validation 경계가 문서화되어 있는지 검증한다.
   - phase metadata가 completed summaries와 top-level status를 일관되게 반영하는지 검증한다.
2. README/app README/API spec 최종 정리.
   - local stack start
   - seed
   - Postman import
   - readiness/security smoke
   - cleanup
3. `/phases/17-docker-compose-live-server/index.json`와 `/phases/index.json` 상태를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_compose_live_server_public_contracts.py scripts/test_docker_compose_live_server_default.py scripts/test_live_runtime_driver_factory.py scripts/test_local_env_seed_contract.py scripts/test_live_readiness_probe_wiring.py
docker compose --env-file .env.example config --services
python3 scripts/validate_phases.py
```

## 검증 절차

1. public contract 테스트를 먼저 추가하고 실패를 확인한다.
2. docs/metadata를 갱신한 뒤 AC를 실행한다.
3. Docker config command가 불가능하면 이유를 summary에 남긴다.
4. `/phases/17-docker-compose-live-server/index.json`의 step 4 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.
5. `/phases/index.json`에서 `17-docker-compose-live-server`를 `completed`로 갱신한다.

## 금지사항

- automated harness에서 `docker compose up`을 실행하지 마라.
- local live server를 production-ready 운영 배포로 문서화하지 마라.
- secret 원문을 docs/fixtures/smoke output에 넣지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `scripts/execute.py`에 프로젝트별 구현 로직을 넣지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

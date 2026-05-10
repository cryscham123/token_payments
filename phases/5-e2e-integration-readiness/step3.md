# Step 3: compose-readiness-smoke

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/README.md`
- `/app/README.md`
- `/docker-compose.yml`
- `/.env.example`
- `/app/postgres/init.d/001-token-payments-schema.sql`
- `/app/test_network/Dockerfile`
- `/phases/5-e2e-integration-readiness/index.json`
- Step 0-2에서 생성/수정한 smoke runtime 파일

## 작업

실제 Docker compose 기동 전, committed config만으로 검증 가능한 compose readiness smoke를 추가한다. 이 step도 컨테이너를 기동하지 않고 네트워크를 호출하지 않는다.

1. 먼저 실패하는 테스트를 추가한다.
   - `scripts/test_compose_readiness_smoke.py`
2. runtime smoke 구현을 확장한다.
   - `run_smoke_scenario("compose-readiness")` 또는 동등한 public API를 구현한다.
   - `.env.example`의 필수 key와 placeholder 안전성을 검증한다.
   - `docker-compose.yml`의 필수 service 이름을 검증한다: `postgres`, `kafka`, `kafka-ui`, `pgweb`, `test_network`.
   - compose가 참조하는 init script와 test network Dockerfile이 존재하는지 검증한다.
   - runtime command smoke가 `health`, `worker`, `ui customer`, `ui operator`, `smoke happy-path-checkout`, `smoke compensation-checkout`로 이어질 수 있음을 command list/details에 남긴다.
3. YAML 파싱은 표준 라이브러리만으로 안전하게 처리한다.
   - PyYAML 같은 새 dependency를 추가하지 않는다.
   - 가능하면 `docker compose config`에 의존하지 말고 committed file contract를 직접 검증한다.
   - 단순 문자열 검증을 쓰는 경우 false positive를 줄이도록 service block, env_file, volume/path 존재를 함께 확인한다.
4. CLI를 확장한다.
   - `PYTHONPATH=app python3 -m token_payments smoke compose-readiness`가 bounded JSON을 출력한다.
5. README/app README에 실제 로컬 Docker smoke를 사람이 실행할 때의 순서를 짧게 추가한다.
   - 예: `.env.example` 복사, `docker compose --env-file .env up -d ...`, runtime smoke commands, teardown.
6. phase metadata를 갱신한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_compose_readiness_smoke.py
python3 -m pytest scripts/test_compensation_checkout_e2e.py scripts/test_happy_path_checkout_e2e.py scripts/test_e2e_smoke_contract_foundation.py
PYTHONPATH=app python3 -m token_payments smoke compose-readiness
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 compose readiness 테스트를 먼저 추가하고 실패를 확인한다.
2. 구현 후 AC 커맨드를 실행한다.
3. CLI 출력이 실제 Docker를 실행하지 않고도 필수 service/env/path/readiness command를 검증하는지 확인한다.
4. `/phases/5-e2e-integration-readiness/index.json`의 step 3 status를 `completed`로 바꾸고 `summary`에 compose readiness 검증 범위와 실제 기동을 하지 않은 이유를 구체적으로 적는다.

## 금지사항

- `docker compose up`, `docker build`, image pull, 네트워크 호출을 실행하지 마라.
- `.env`의 실제 local secret 값을 읽어서 테스트 snapshot이나 문서에 쓰지 마라. committed `.env.example`만 검증한다.
- 새 Python package dependency를 추가하지 마라.
- 실패한 테스트를 삭제하거나 skip 처리해서 통과시키지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

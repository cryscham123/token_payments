# Step 0: docker-runtime-image-contract

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/README.md`
- `/app/README.md`
- `/docker-compose.yml`
- `/.env.example`
- `/.gitignore`
- `/app/token_payments/__main__.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/phases/5-e2e-integration-readiness/index.json`
- `/phases/7-http-framework-adapter/index.json`
- `/phases/8-operator-action-endpoints/index.json`

## 작업

Token Payments Python runtime을 Docker 이미지로 실행할 수 있는 최소 runtime image contract를 추가한다. 동작 변경이므로 먼저 테스트를 작성하거나 갱신하고 실패를 확인한 뒤 구현한다.

1. `scripts/test_docker_runtime_image_contracts.py`를 추가한다.
   - repository root의 `Dockerfile`이 존재해야 한다.
   - Python 3.12 계열 base image를 사용해야 한다.
   - `PYTHONPATH`가 container 내부 app 경로를 가리켜야 한다.
   - default command는 bounded runtime command인 `python -m token_payments health`여야 하며 long-running server를 시작하지 않아야 한다.
   - Dockerfile이 `.env`, local data directory, phase output artifact, git metadata, virtualenv를 image에 복사하지 않는다는 계약을 검증한다.
   - `.dockerignore`가 `.env`, `.venv`, `**/data`, `phases/**/step*-output.json`, `phases/**/phase*-output.json`, `.git`, `__pycache__`, `.pytest_cache`를 제외해야 한다.
   - Dockerfile에 Claude 전용 명령/파일이나 민감정보 placeholder 값이 없어야 한다.
2. repository root에 `Dockerfile`을 추가한다.
   - Python 3.12 기반 runtime image를 사용한다.
   - working directory는 안정적인 container 경로(`/workspace` 등)를 사용한다.
   - `app/`만 runtime 코드로 복사하고 `PYTHONPATH`를 설정한다.
   - 외부 package 설치가 필요하지 않다면 불필요한 `pip install`을 추가하지 않는다.
   - default `CMD`는 bounded JSON health command로 둔다.
3. repository root에 `.dockerignore`를 추가한다.
   - local secret/env/data/cache/git/test artifact가 Docker build context에 들어가지 않게 한다.
   - `app/postgres/init.d`와 `app/test_network/Dockerfile` 같은 committed infrastructure contract는 제외하지 않는다.
4. 기존 `.gitignore`, `.env.example`, runtime entrypoint 계약을 깨뜨리지 않는다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_docker_runtime_image_contracts.py scripts/test_runtime_contract_foundation.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/9-live-docker-compose-integration/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 이 step에서 Docker daemon이 필요한 `docker build`, `docker compose up`, `docker run`을 필수 검증으로 만들지 마라.
- runtime command를 long-running server나 daemon으로 바꾸지 마라.
- 새 third-party Python dependency를 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

# Token Payments Harness Workspace

MetaMask 기반 암호화폐 checkout 시스템을 DDD bounded context와 Codex Harness phase/step으로 구현하는 워크스페이스다.

이 파일은 저장소 진입점만 담당한다. 상세 런타임 계약, API 명세, phase 이력은 아래 source of truth 문서에서 관리한다.

## Source Of Truth

| 주제 | 위치 |
| --- | --- |
| 제품 목표와 사용자 흐름 | [docs/PRD.md](docs/PRD.md), [docs/SEQUENCES.md](docs/SEQUENCES.md) |
| 실행 아키텍처와 bounded context | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md) |
| public HTTP API, route manifest, OpenAPI, Postman | [docs/API_SPEC.md](docs/API_SPEC.md), [docs/api/README.md](docs/api/README.md) |
| 애플리케이션 런타임, Docker, live worker | [app/README.md](app/README.md) |
| Harness phase/step 작성과 실행 규칙 | [docs/HARNESS.md](docs/HARNESS.md), [phases/README.md](phases/README.md) |
| 현재 phase 상태와 작업 이력 | [phases/index.json](phases/index.json), [SUMMARY.md](SUMMARY.md) |

원본 다이어그램은 `diagram/DDD.drawio`에 있다. 다이어그램과 코드 패키지 구조가 충돌하면 코드 패키지 구조를 우선한다.

## Quick Start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/validate_phases.py
.venv/bin/python -m pytest scripts/test_*.py
```

Harness phase 실행:

```bash
python3 scripts/execute.py <phase-dir>
python3 scripts/execute.py <phase-dir> --push
```

런타임 preview:

```bash
PYTHONPATH=app .venv/bin/python -m token_payments
PYTHONPATH=app .venv/bin/python -m token_payments health
PYTHONPATH=app .venv/bin/python -m token_payments worker
PYTHONPATH=app .venv/bin/python -m token_payments api
PYTHONPATH=app .venv/bin/python -m token_payments serve-api
```

기본 `api`와 `serve-api` 명령은 no-server-start preview boundary를 유지한다. live API 실행, `/healthz`, `/readyz`, `token_payments_live_worker`, Postman Docker API readiness, ASGI/FastAPI Thin Adapter 세부 사항은 [app/README.md](app/README.md)와 [docs/API_SPEC.md](docs/API_SPEC.md)를 기준으로 본다.

## Local Environment

로컬 실행 값은 `.env.example`을 복사해서 만든다. 커밋된 값은 local dev placeholder이며 real private keys, seed phrases, API keys, production RPC URLs는 커밋하지 않는다.

```bash
cp .env.example .env
```

Docker daemon 없이 compose 계약만 확인:

```bash
docker compose --env-file .env.example config --services
docker compose --env-file .env.example --profile runtime config --services
```

명시 승인 없는 live Docker/API 명령은 bounded refusal 또는 dry-run plan만 반환해야 한다.

## Current Contracts

- Public HTTP route surface는 `app/token_payments/api/http.py`의 55-route manifest가 기준이다. 문서 기준은 [docs/API_SPEC.md](docs/API_SPEC.md)다.
- Operator action APIs는 global admin role이 아니라 `operator:read`, `operator:action`, `outbox:retry` 같은 explicit permission으로 판단한다.
- Admin provisioning APIs는 `admin:provision` 또는 `rbac:manage` permission을 요구한다.
- `scripts/execute.py`는 phase 실행 오케스트레이션만 담당한다. 프로젝트별 구현 로직은 phase/step 또는 `app/token_payments` 코드에 둔다.
- 신규 사용자/업무 기능은 의도적으로 내부 전용이라고 명시하지 않는 한 API surface, route manifest, API tests/fixtures를 함께 갱신한다.

## Useful Commands

```bash
python3 .githooks/pre_commit_check.py
PYTHONPATH=app python3 -m token_payments smoke
PYTHONPATH=app python3 -m token_payments worker --live --dry-run
PYTHONPATH=app python3 -m token_payments worker --live --once
PYTHONPATH=app python3 -m token_payments worker --live --loop --confirm-live-worker
PYTHONPATH=app python3 -m token_payments serve-api --live --dry-run
PYTHONPATH=app python3 -m token_payments serve-api --live --confirm-live-api
```

명령별 전제 조건과 live 실행 순서는 [app/README.md](app/README.md)에 둔다. root README에는 phase별 완료 로그나 다음 phase 후보를 누적하지 않는다.

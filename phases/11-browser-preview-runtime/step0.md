# Step 0: browser-preview-server-contract

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/ui/preview.py`
- `/app/token_payments/ui/renderers.py`
- `/app/token_payments/runtime/entrypoint.py`
- `/scripts/test_ui_runtime_preview.py`
- `/scripts/test_wsgi_runtime_preview.py`
- `/phases/4-customer-operator-ui/index.json`
- `/phases/7-http-framework-adapter/index.json`
- `/phases/10-docker-live-smoke-runner/index.json`

## 작업

실제 브라우저에서 customer/operator UI preview를 열 수 있는 localhost 전용 preview server 계약을 추가한다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_browser_preview_server.py`를 추가한다.
   - preview server는 표준 라이브러리만 사용해야 한다.
   - 기본 host는 `127.0.0.1`, 기본 port는 `8765`여야 한다.
   - 테스트는 server를 `127.0.0.1`의 ephemeral port에 background thread로 띄운 뒤 `urllib.request`로 실제 HTTP 요청을 보내야 한다.
   - `/`, `/customer`, `/operator`는 browser-openable HTML을 반환해야 한다.
   - `/`는 customer preview로 redirect 또는 customer HTML을 반환하되, 브라우저 주소에서 바로 열 수 있어야 한다.
   - `/customer` 응답은 `<!doctype html>`, `data-view="checkout"`, `OrderApprovedEvent`, `PaymentFailedEvent`, `PaymentExpiredEvent`, `Ledger Mug &lt;sample&gt;`를 포함해야 한다.
   - `/operator` 응답은 `<!doctype html>`, `data-view="operator"`, `Operator Dashboard`, `Retry candidate`, `outbox-relay`를 포함해야 한다.
   - HTML 응답은 `Content-Type: text/html; charset=utf-8`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`를 포함해야 한다.
   - `/healthz`는 bounded JSON health payload를 반환해야 하며, `/api/routes`는 기존 HTTP route manifest를 JSON으로 반환해야 한다.
   - 알 수 없는 path는 bounded 404 HTML 또는 JSON을 반환해야 하며 server process를 종료하지 않아야 한다.
   - server 시작과 테스트 과정에서 Docker, Kafka, PostgreSQL, Blockchain RPC, local `.env`를 읽거나 연결하지 않아야 한다.
   - 응답과 source에 Claude 전용 명령/파일명, private key, seed phrase, mnemonic, secret placeholder가 없어야 한다.
2. preview server 구현을 추가한다.
   - 재사용 가능한 server logic은 `app/token_payments/runtime/browser_preview.py`에 둔다.
   - 실행 script는 `scripts/browser_preview_server.py`에 얇게 둔다.
   - script 실행 예시는 `PYTHONPATH=app python3 scripts/browser_preview_server.py --host 127.0.0.1 --port 8765`가 되어야 한다.
   - route HTML은 기존 `token_payments.ui.preview.render_ui_preview()` 산출물을 사용한다.
   - `/api/routes` JSON은 기존 `token_payments.api.http_route_manifest()` 산출물을 사용한다.
   - explicit server command에서만 network port를 bind한다. 기존 `token_payments health`, `ui`, `api`, `serve-api` runtime command는 long-running server를 시작하지 않아야 한다.
   - startup log에는 실제 브라우저에 넣을 URL을 stdout으로 출력한다.
3. public export가 필요하면 `app/token_payments/runtime/__init__.py`에 최소 export만 추가한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_browser_preview_server.py scripts/test_ui_runtime_preview.py scripts/test_wsgi_runtime_preview.py
PYTHONPATH=app python3 scripts/browser_preview_server.py --help
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/11-browser-preview-runtime/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- `scripts/execute.py`에 browser preview 구현 로직을 넣지 마라.
- 기존 `token_payments ui`, `api`, `serve-api` 명령이 long-running server나 port bind를 시작하게 만들지 마라.
- 새 third-party dependency를 추가하지 마라.
- Docker daemon, Kafka, PostgreSQL, Blockchain RPC, local `.env` 접근을 자동으로 수행하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

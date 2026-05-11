# Step 1: browser-preview-smoke-checklist

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/HARNESS.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/runtime/browser_preview.py`
- `/scripts/browser_preview_server.py`
- `/scripts/test_browser_preview_server.py`
- `/phases/11-browser-preview-runtime/index.json`

## 작업

브라우저에서 열 수 있는 preview server를 자동으로 검증하고, 수동 브라우저 확인 URL/checklist를 JSON으로 출력하는 smoke runner를 추가한다. 동작 변경이므로 먼저 실패하는 테스트를 작성한 뒤 구현한다.

1. `scripts/test_browser_preview_smoke.py`를 추가한다.
   - `scripts/browser_preview_smoke.py`가 표준 라이브러리만 사용함을 검증한다.
   - 기본 실행은 preview server를 `127.0.0.1` ephemeral port에 background thread로 띄우고 `/`, `/customer`, `/operator`, `/healthz`, `/api/routes`를 HTTP로 검증해야 한다.
   - smoke stdout은 bounded JSON이어야 하며 `contract`, `status`, `serverStarted`, `browserReady`, `baseUrl`, `manualBrowserUrls`, `checks`, `openBrowserRequested`를 포함해야 한다.
   - `manualBrowserUrls`는 `customer`, `operator`, `health`, `routes` URL을 포함해야 하며 실제 브라우저 주소창에 붙여넣을 수 있는 absolute localhost URL이어야 한다.
   - 각 check는 `name`, `url`, `statusCode`, `passed`, `summary`를 포함해야 한다.
   - customer/operator HTML check는 중요한 visible text와 `data-view` marker를 검증해야 한다.
   - `--base-url http://127.0.0.1:<port>` 옵션은 이미 떠 있는 preview server를 검증해야 하며 새 server를 시작하지 않아야 한다.
   - `--open-browser` 옵션은 존재해야 하지만 테스트에서는 실제 GUI 브라우저를 열지 않도록 dependency injection 또는 dry path로 검증해야 한다.
   - 실패 시 exit code는 1이고 JSON `status`는 `FAILED`여야 한다.
   - smoke 실행 중 Docker, Kafka, PostgreSQL, Blockchain RPC, local `.env`를 읽거나 연결하지 않아야 한다.
2. `scripts/browser_preview_smoke.py`를 추가한다.
   - 표준 라이브러리만 사용한다.
   - 기본 실행은 background preview server를 시작하고 검증 후 반드시 shutdown 한다.
   - `--base-url`이 있으면 외부 server 검증만 수행한다.
   - `--open-browser`가 있으면 `webbrowser.open()`으로 customer/operator URL을 열 수 있게 하되, 실패해도 smoke 검증 결과 JSON은 유지한다.
   - 출력 JSON에는 secret-like value나 local env 값이 들어가지 않아야 한다.
3. preview server module에 테스트 가능한 lifecycle helper가 부족하면 최소 범위로 추가한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_browser_preview_smoke.py scripts/test_browser_preview_server.py
PYTHONPATH=app python3 scripts/browser_preview_smoke.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/11-browser-preview-runtime/index.json`의 step 1 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- 테스트나 기본 smoke 실행에서 실제 GUI 브라우저를 열지 마라.
- 새 third-party dependency, Playwright, Selenium, Node toolchain을 추가하지 마라.
- Docker/Kafka/PostgreSQL/Blockchain RPC/local `.env` 접근을 자동으로 수행하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

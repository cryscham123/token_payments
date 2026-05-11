# Step 2: browser-preview-public-contracts

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/HARNESS.md`
- `/docs/UI_GUIDE.md`
- `/README.md`
- `/app/README.md`
- `/scripts/browser_preview_server.py`
- `/scripts/browser_preview_smoke.py`
- `/scripts/test_browser_preview_server.py`
- `/scripts/test_browser_preview_smoke.py`
- `/app/token_payments/runtime/browser_preview.py`
- `/app/token_payments/runtime/__init__.py`
- `/phases/index.json`
- `/phases/11-browser-preview-runtime/index.json`

## 작업

브라우저 preview phase의 공개 계약과 사용 문서를 고정한다. 동작 변경이 있으면 먼저 테스트를 갱신하고, 문서 변경도 테스트로 검증한다.

1. `scripts/test_browser_preview_public_contracts.py`를 추가한다.
   - `token_payments.runtime` public export가 browser preview server lifecycle helper를 안정적으로 노출하는지 검증한다.
   - README와 app README가 실제 브라우저 확인 명령을 포함해야 한다.
     - `PYTHONPATH=app python3 scripts/browser_preview_server.py --host 127.0.0.1 --port 8765`
     - `PYTHONPATH=app python3 scripts/browser_preview_smoke.py`
     - `http://127.0.0.1:8765/customer`
     - `http://127.0.0.1:8765/operator`
   - README와 app README가 browser preview server가 local-only fixture이며 DB/Kafka/Docker/Blockchain RPC/local `.env`에 연결하지 않는다고 명시해야 한다.
   - source와 docs에 Claude 전용 명령/파일명, private key, seed phrase, mnemonic, committed secret value가 없어야 한다.
   - `phases/11-browser-preview-runtime/index.json`의 step summary/status 규칙과 phase metadata가 `validate_phases`와 일관되어야 한다.
2. README와 app README에 `Browser Preview Runtime` 섹션을 추가한다.
   - 실제 브라우저 확인 순서를 간결하게 적는다.
   - server 실행, smoke 검증, customer/operator URL을 분리해서 적는다.
   - server를 종료하려면 터미널에서 `Ctrl-C`를 누르도록 안내한다.
   - 이 경로가 local-only preview fixture이며 production server나 external integration smoke가 아니라고 명시한다.
3. 필요한 경우 `phases/README.md`는 일반 규칙만 유지하고 프로젝트별 browser 구현 세부사항은 README/app README에 둔다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_browser_preview_public_contracts.py scripts/test_browser_preview_smoke.py scripts/test_browser_preview_server.py
PYTHONPATH=app python3 scripts/browser_preview_smoke.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. AC 커맨드를 실행한다.
2. `/phases/11-browser-preview-runtime/index.json`의 step 2 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- `scripts/execute.py`에 프로젝트별 browser preview 구현 로직을 넣지 마라.
- production server, DB seed, Docker live smoke, Kafka publish/consume, Blockchain RPC 호출을 이 phase에 섞지 마라.
- 새 third-party dependency를 추가하지 마라.
- Claude 전용 파일이나 명령을 추가하지 마라.
- `step*-output.json`을 추적 대상으로 만들지 마라.

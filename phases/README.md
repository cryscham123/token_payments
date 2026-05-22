# Harness Phases

이 디렉토리는 Codex Harness가 실행할 phase/step 명세를 보관한다.

## 구조

```text
phases/
  index.json
  0-mvp/
    index.json
    step0.md
    step1.md
```

## 상태

`phases/{phase}/index.json`의 step 상태는 다음 값만 사용한다.

- `pending`
- `completed`
- `error`
- `blocked`

`step*-output.json`은 실행 산출물이므로 git에 추적하지 않는다. 다음 step 판단에 필요한 내용은 `index.json`의 `summary`, `error_message`, `blocked_reason`에 남긴다.

## 현재 통합 로드맵

Phase 23~26은 중복 schema/API migration을 줄이기 위해 다음 4개 흐름으로 통합한다.

- `23-catalog-domain-public-read-apis`: store/product catalog, public ids, public read APIs
- `24-live-kafka-worker-runtime`: live outbox/Kafka worker runtime
- `25-multi-wallet-stablecoin-asset-payments`: multi-wallet, selected payer wallet, asset/chain registry, stablecoin authorization/receipts
- `26-security-hardening-architecture-refactoring`: API redaction, trackingId submit, fail-closed authorization, context boundary cleanup, composition split, membership outbox projection

## 검증

```bash
python3 scripts/validate_phases.py
```

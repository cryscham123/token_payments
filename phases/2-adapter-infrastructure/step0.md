# Step 0: adapter-contract-foundation

## 읽어야 할 파일

- `/AGENTS.md`
- `/docs/ADR.md`
- `/docs/ARCHITECTURE.md`
- `/docs/DOMAIN_MODEL.md`
- `/docs/HARNESS.md`
- `/docs/PRD.md`
- `/docs/SEQUENCES.md`
- `/docs/UI_GUIDE.md`
- `/phases/0-foundation/index.json`
- `/phases/1-checkout-core/index.json`
- `/phases/2-adapter-infrastructure/index.json`
- `/README.md`
- `/app/README.md`
- `/app/token_payments/shared/domain/messaging.py`
- `/app/token_payments/contexts/checkout/application/process_manager.py`
- `/app/token_payments/contexts/inventory/application/ports.py`
- `/app/token_payments/contexts/payment/application/ports.py`
- `/app/token_payments/contexts/store_approval/application/ports.py`
- `/app/token_payments/contexts/auth/application/ports.py`

## 작업

adapter infrastructure phase의 공통 기반을 만든다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_adapter_contract_foundation.py`를 추가해 adapter 레이어에서 사용할 메시지 직렬화, topic 매핑, transaction boundary 계약을 검증한다.
2. `app/token_payments/shared/adapter/` 패키지를 추가하고 `__init__.py`에서 public contract를 `__all__`로 export한다.
3. `shared/adapter`에는 domain/application이 의존하지 않는 기술 경계 객체만 둔다: JSON-safe message serializer, topic resolver, transaction/session protocol, retry/backoff configuration.
4. `app/postgres/init.d/001-token-payments-schema.sql`을 추가해 outbox, processed message/command, inventory, payment, payment_authorization, store approval order detail 저장에 필요한 최소 PostgreSQL table/index 초안을 작성한다.
5. `.env.example` 또는 app README에 새 adapter 설정 키가 필요하면 민감정보 없이 추가한다.
6. domain과 application layer가 `psycopg`, `sqlalchemy`, `kafka`, `web3`, `requests`, `metamask` 같은 adapter dependency를 import하지 않는지 테스트로 고정한다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_adapter_contract_foundation.py scripts/test_messaging_outbox_contracts.py scripts/test_checkout_core_public_contracts.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. PostgreSQL schema 초안이 `docker-entrypoint-initdb.d`에서 실행 가능한 plain SQL인지 확인한다.
4. `phases/2-adapter-infrastructure/index.json`의 step 0 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- `scripts/execute.py`에 프로젝트별 adapter 구현 로직을 넣지 마라.
- domain/application layer에서 외부 client 라이브러리를 직접 import하지 마라.
- live PostgreSQL, Kafka, Blockchain node가 없으면 실패하는 테스트를 기본 AC에 넣지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

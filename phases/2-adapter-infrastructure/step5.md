# Step 5: wallet-blockchain-boundaries

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
- `/phases/2-adapter-infrastructure/step0.md`
- `/app/token_payments/contexts/auth/application/ports.py`
- `/app/token_payments/contexts/auth/domain/model.py`
- `/app/token_payments/contexts/payment/application/ports.py`
- `/app/token_payments/contexts/payment/domain/model.py`
- `/app/token_payments/shared/domain/value_objects.py`

## 작업

MetaMask login signature와 blockchain payment boundary adapter를 구현한다. 먼저 실패하는 테스트를 추가한 뒤 통과하도록 구현한다.

1. `scripts/test_wallet_blockchain_boundaries.py`를 추가해 wallet signature recover, gas estimate mapping, transaction receipt mapping, refund transaction boundary를 검증한다.
2. `contexts/auth/adapter/metamask.py` 또는 `wallet_signature.py`에 `WalletSignatureVerifier` port 구현을 추가한다.
3. `contexts/payment/adapter/blockchain.py`에 `BlockchainAdapter` port 구현을 추가한다.
4. `contexts/payment/adapter/transaction_service.py`에 `TransactionService` port 구현을 추가한다.
5. 외부 client는 constructor로 주입해 테스트에서 fake client를 사용할 수 있게 한다.
6. chain id, token address, wallet address, tx hash는 shared value object 검증을 거쳐 domain으로 전달한다.
7. private key, seed phrase, production RPC URL 같은 민감정보는 코드와 테스트 fixture에 넣지 않는다. 필요한 설정 키만 `.env.example`에 둔다.

## Acceptance Criteria

```bash
python3 -m pytest scripts/test_wallet_blockchain_boundaries.py scripts/test_auth_context_skeleton.py scripts/test_payment_application_contracts.py scripts/test_payment_domain_model.py
python3 scripts/validate_phases.py
```

## 검증 절차

1. 새 테스트가 실패하는 것을 확인한 뒤 구현한다.
2. AC 커맨드를 실행한다.
3. wallet/blockchain 라이브러리 import가 auth/payment adapter 패키지 안에만 머무는지 확인한다.
4. `phases/2-adapter-infrastructure/index.json`의 step 5 상태를 `completed`로 바꾸고 `summary`를 구체적으로 작성한다.

## 금지사항

- domain/application layer에 `web3`, `requests`, MetaMask client, RPC client import를 추가하지 마라.
- 테스트나 문서에 실제 private key, seed phrase, production API key를 쓰지 마라.
- Kafka listener 또는 outbox relay 구현을 이 step에 섞지 마라.
- 실패한 테스트를 삭제하거나 skip 처리하지 마라.
- phase 상태에 `"running"` 같은 비허용 값을 쓰지 마라.

from __future__ import annotations

import sys
from pathlib import Path

from eth_account.messages import _hash_eip191_message, encode_defunct


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.contexts.auth.adapter.wallet_signature import (  # noqa: E402
    ClientWalletSignatureVerifier,
)
from token_payments.contexts.auth.application import (  # noqa: E402
    WalletSignatureVerificationFailure,
    WalletSignatureVerificationResult,
)
from token_payments.shared.domain import WalletAddress  # noqa: E402


CHAIN_ID = 1337
OTHER_CHAIN_ID = 1
SMART_WALLET = WalletAddress("0x9999999999999999999999999999999999999999")
EOA_WALLET = WalletAddress("0x1111111111111111111111111111111111111111")
MESSAGE = "\n".join(
    (
        "token-payments.local wants you to sign in with your Ethereum account:",
        str(SMART_WALLET),
        "",
        "URI: https://token-payments.local",
        "Version: 1",
        f"Chain ID: {CHAIN_ID}",
        "Nonce: N0NCE001",
        "Issued At: 2026-05-18T00:00:00+00:00",
        "Expiration Time: 2026-05-18T00:05:00+00:00",
    )
)
SIGNATURE = "0x" + "ab" * 65
ERC1271_MAGIC = "0x1626ba7e"


def test_contract_wallet_verification_checks_code_and_calls_erc1271_with_digest_and_signature() -> None:
    client = ContractWalletClient(code="0x60016000", call_result=ERC1271_MAGIC + "00" * 28)
    verifier = ClientWalletSignatureVerifier(client, supported_chain_ids=(CHAIN_ID,))

    result = verifier.verify_signature(SMART_WALLET, MESSAGE, SIGNATURE, CHAIN_ID)

    assert result == WalletSignatureVerificationResult.verified()
    assert client.get_code_requests == [{"address": str(SMART_WALLET), "chain_id": CHAIN_ID}]
    assert len(client.call_contract_requests) == 1
    call = client.call_contract_requests[0]
    assert call["to"] == str(SMART_WALLET)
    assert call["chain_id"] == CHAIN_ID
    assert call["data"].startswith(ERC1271_MAGIC)
    assert _erc1271_digest_word(call["data"]) == _personal_sign_digest_hex(MESSAGE)[2:]
    assert _erc1271_signature_bytes(call["data"]) == SIGNATURE[2:]
    assert client.recover_calls == []


def test_contract_wallet_accepts_only_erc1271_success_magic_value() -> None:
    client = ContractWalletClient(code="0x60016000", call_result="0xdeadbeef" + "00" * 28)
    verifier = ClientWalletSignatureVerifier(client, supported_chain_ids=(CHAIN_ID,))

    result = verifier.verify_signature(SMART_WALLET, MESSAGE, SIGNATURE, CHAIN_ID)

    assert result == WalletSignatureVerificationResult.failed(
        WalletSignatureVerificationFailure.INVALID_SIGNATURE
    )
    assert client.call_contract_requests
    assert client.recover_calls == []


def test_contract_wallet_revert_maps_to_bounded_invalid_signature_without_eoa_fallback() -> None:
    client = ContractWalletClient(code="0x60016000", call_error=RuntimeError("execution reverted"))
    verifier = ClientWalletSignatureVerifier(client, supported_chain_ids=(CHAIN_ID,))

    result = verifier.verify_signature(SMART_WALLET, MESSAGE, SIGNATURE, CHAIN_ID)

    assert result == WalletSignatureVerificationResult.failed(
        WalletSignatureVerificationFailure.INVALID_SIGNATURE
    )
    assert client.call_contract_requests
    assert client.recover_calls == []


def test_contract_wallet_timeout_maps_to_bounded_invalid_signature() -> None:
    client = ContractWalletClient(code="0x60016000", call_error=TimeoutError("rpc timeout"))
    verifier = ClientWalletSignatureVerifier(client, supported_chain_ids=(CHAIN_ID,))

    result = verifier.verify_signature(SMART_WALLET, MESSAGE, SIGNATURE, CHAIN_ID)

    assert result == WalletSignatureVerificationResult.failed(
        WalletSignatureVerificationFailure.INVALID_SIGNATURE
    )
    assert client.recover_calls == []


def test_chain_mismatch_is_rejected_before_contract_lookup() -> None:
    client = ContractWalletClient(code="0x60016000", call_result=ERC1271_MAGIC + "00" * 28)
    verifier = ClientWalletSignatureVerifier(client, supported_chain_ids=(OTHER_CHAIN_ID,))

    result = verifier.verify_signature(SMART_WALLET, MESSAGE, SIGNATURE, CHAIN_ID)

    assert result == WalletSignatureVerificationResult.failed(
        WalletSignatureVerificationFailure.UNSUPPORTED_CHAIN
    )
    assert client.get_code_requests == []
    assert client.call_contract_requests == []
    assert client.recover_calls == []


def test_no_code_uses_existing_eoa_recovery_path() -> None:
    client = ContractWalletClient(code="0x", recovered_wallet=str(EOA_WALLET))
    verifier = ClientWalletSignatureVerifier(client, supported_chain_ids=(CHAIN_ID,))

    result = verifier.verify_signature(EOA_WALLET, MESSAGE, SIGNATURE, CHAIN_ID)

    assert result == WalletSignatureVerificationResult.verified()
    assert client.get_code_requests == [{"address": str(EOA_WALLET), "chain_id": CHAIN_ID}]
    assert client.call_contract_requests == []
    assert client.recover_calls == [(MESSAGE, SIGNATURE)]


def test_no_code_with_bad_eoa_signature_maps_to_invalid_signature() -> None:
    client = ContractWalletClient(code="0x", recover_error=ValueError("bad signature"))
    verifier = ClientWalletSignatureVerifier(client, supported_chain_ids=(CHAIN_ID,))

    result = verifier.verify_signature(EOA_WALLET, MESSAGE, SIGNATURE, CHAIN_ID)

    assert result == WalletSignatureVerificationResult.failed(
        WalletSignatureVerificationFailure.INVALID_SIGNATURE
    )
    assert client.call_contract_requests == []


def test_eoa_client_without_provider_methods_keeps_existing_recover_address_path() -> None:
    client = RecoverOnlyClient(recovered_wallet=str(EOA_WALLET))
    verifier = ClientWalletSignatureVerifier(client, supported_chain_ids=(CHAIN_ID,))

    result = verifier.verify_signature(EOA_WALLET, MESSAGE, SIGNATURE, CHAIN_ID)

    assert result == WalletSignatureVerificationResult.verified()
    assert client.calls == [(MESSAGE, SIGNATURE)]


def test_runtime_config_wires_auth_wallet_rpc_chain_and_timeout_to_signature_client() -> None:
    from token_payments.runtime import LiveRuntimeConfig, build_live_runtime_dependencies_from_env

    env = _runtime_env() | {
        "ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL": "https://auth-rpc.local/path?token=secret",
        "ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID": "11155111",
        "ADAPTER_AUTH_WALLET_SIGNATURE_TIMEOUT_SECONDS": "2.5",
    }

    config = LiveRuntimeConfig.from_env(env)
    dependencies = build_live_runtime_dependencies_from_env(env, config=config)
    debug_payload = config.to_redacted_dict()

    assert config.wallet_signature_rpc_url == "https://auth-rpc.local/path?token=secret"
    assert config.wallet_signature_chain_id == 11155111
    assert config.wallet_signature_timeout_seconds == 2.5
    assert debug_payload["adapters"]["walletSignature"]["rpcUrl"] == "https://auth-rpc.local/path?<redacted>"
    assert debug_payload["adapters"]["walletSignature"]["supportedChainIds"] == [11155111]
    assert debug_payload["adapters"]["walletSignature"]["timeoutSeconds"] == 2.5
    assert dependencies.wallet_signature_client.rpc_url == config.wallet_signature_rpc_url
    assert dependencies.wallet_signature_client.chain_id == config.wallet_signature_chain_id
    assert dependencies.wallet_signature_client.timeout_seconds == config.wallet_signature_timeout_seconds


def test_runtime_config_reuses_blockchain_rpc_for_auth_wallet_verifier_when_auth_url_is_empty() -> None:
    from token_payments.runtime import LiveRuntimeConfig

    config = LiveRuntimeConfig.from_env(_runtime_env() | {"ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL": ""})

    assert config.wallet_signature_rpc_url == config.blockchain_rpc_url
    assert config.wallet_signature_chain_id == config.blockchain_chain_id


def _personal_sign_digest_hex(message: str) -> str:
    return "0x" + _hash_eip191_message(encode_defunct(text=message)).hex()


def _erc1271_digest_word(calldata: str) -> str:
    data = calldata.removeprefix("0x")
    return data[8:72]


def _erc1271_signature_bytes(calldata: str) -> str:
    data = calldata.removeprefix("0x")
    signature_length = int(data[136:200], 16)
    return data[200 : 200 + signature_length * 2]


class ContractWalletClient:
    def __init__(
        self,
        *,
        code: str,
        call_result: str | None = None,
        call_error: Exception | None = None,
        recovered_wallet: str | None = None,
        recover_error: Exception | None = None,
    ) -> None:
        self.code = code
        self.call_result = call_result
        self.call_error = call_error
        self.recovered_wallet = recovered_wallet
        self.recover_error = recover_error
        self.get_code_requests: list[dict[str, object]] = []
        self.call_contract_requests: list[dict[str, object]] = []
        self.recover_calls: list[tuple[str, str]] = []

    def get_code(self, **request: object) -> str:
        self.get_code_requests.append(dict(request))
        return self.code

    def call_contract(self, **request: object) -> str:
        self.call_contract_requests.append(dict(request))
        if self.call_error is not None:
            raise self.call_error
        if self.call_result is None:
            raise AssertionError("call_result was not configured")
        return self.call_result

    def recover_address(self, message: str, signature: str) -> str:
        self.recover_calls.append((message, signature))
        if self.recover_error is not None:
            raise self.recover_error
        if self.recovered_wallet is None:
            raise AssertionError("recovered_wallet was not configured")
        return self.recovered_wallet


class RecoverOnlyClient:
    def __init__(self, *, recovered_wallet: str) -> None:
        self.recovered_wallet = recovered_wallet
        self.calls: list[tuple[str, str]] = []

    def recover_address(self, message: str, signature: str) -> str:
        self.calls.append((message, signature))
        return self.recovered_wallet


def _runtime_env() -> dict[str, str]:
    return {
        "RUNTIME_ENVIRONMENT": "local",
        "ADAPTER_POSTGRES_DSN": "postgresql://token_payments:local_dev_only_password@postgres:5432/token_payments",
        "ADAPTER_KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
        "ADAPTER_KAFKA_CLIENT_ID": "token-payments-local",
        "ADAPTER_WALLET_SIGNATURE_DOMAIN": "token-payments.local",
        "ADAPTER_BLOCKCHAIN_RPC_URL": "http://localhost:8545",
        "ADAPTER_BLOCKCHAIN_CHAIN_ID": str(CHAIN_ID),
        "ADAPTER_BLOCKCHAIN_NATIVE_SYMBOL": "ETH",
        "ADAPTER_BLOCKCHAIN_NATIVE_DECIMALS": "18",
        "ADAPTER_BLOCKCHAIN_GAS_BUFFER_RATE": "0.10",
        "SESSION_ACTIVE_KEY_ID": "local-dev-2026",
        "SESSION_SIGNING_KEYS": "local-dev-2026=local_dev_only_session_signing_key_32_bytes_for_tests",
        "CSRF_ACTIVE_KEY_ID": "local-dev-csrf-2026",
        "CSRF_SIGNING_KEY": "local_dev_only_csrf_signing_key_32_bytes_for_tests",
    }

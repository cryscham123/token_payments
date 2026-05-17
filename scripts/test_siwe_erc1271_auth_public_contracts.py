from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_SPEC_PATH = ROOT / "docs" / "API_SPEC.md"
DOMAIN_MODEL_PATH = ROOT / "docs" / "DOMAIN_MODEL.md"
SEQUENCES_PATH = ROOT / "docs" / "SEQUENCES.md"
README_PATH = ROOT / "README.md"
APP_README_PATH = ROOT / "app" / "README.md"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
PHASE_INDEX_PATH = ROOT / "phases" / "index.json"
SIWE_PHASE_INDEX_PATH = ROOT / "phases" / "18-siwe-erc1271-auth" / "index.json"


def test_docs_freeze_public_wallet_verification_scope() -> None:
    api_spec = API_SPEC_PATH.read_text(encoding="utf-8")
    domain_model = DOMAIN_MODEL_PATH.read_text(encoding="utf-8")
    sequences = SEQUENCES_PATH.read_text(encoding="utf-8")
    readmes = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (README_PATH, APP_README_PATH)
    )
    combined = "\n".join((api_spec, domain_model, sequences, readmes))

    for required in (
        "SIWE v1",
        "EOA",
        "deployed ERC-1271 smart wallet",
        "DEPLOYED_SMART_WALLET",
        "eth_getCode",
        "isValidSignature(bytes32,bytes)",
        "0x1626ba7e",
        "requiresDeployedCode",
        "Unsupported ERC-6492/counterfactual accounts are future scope",
        "linked wallets are not implemented",
    ):
        assert required in combined

    for forbidden in (
        "smart wallet recovery service",
        "bundler/paymaster is implemented",
        "ERC-6492 is supported",
    ):
        assert forbidden not in combined


def test_auth_tests_cover_siwe_eoa_and_erc1271_outcomes() -> None:
    siwe_contract = (ROOT / "scripts" / "test_siwe_message_contract.py").read_text(encoding="utf-8")
    verifier_port = (ROOT / "scripts" / "test_wallet_signature_verifier_port.py").read_text(encoding="utf-8")
    erc1271_contract = (ROOT / "scripts" / "test_erc1271_smart_wallet_auth.py").read_text(encoding="utf-8")
    api_public_contract = (ROOT / "scripts" / "test_siwe_auth_api_public_contract.py").read_text(
        encoding="utf-8"
    )

    for required in (
        "test_challenge_response_contains_siwe_required_fields_and_message",
        "test_login_rejects_siwe_message_context_mismatch",
        "SIWE_MESSAGE_MISMATCH",
        "domain",
        "uri",
        "chainId",
        "issuedAt",
        "expirationTime",
    ):
        assert required in siwe_contract

    for required in (
        "test_eoa_verifier_compares_recovered_wallet_to_requested_wallet",
        "test_eoa_verifier_maps_invalid_signature_to_bounded_failure",
        "test_eoa_verifier_maps_recovered_wallet_mismatch_to_bounded_failure",
        "test_eoa_verifier_maps_unsupported_chain_without_recovering_signature",
        "recover_address",
        "WALLET_MISMATCH",
        "UNSUPPORTED_CHAIN",
    ):
        assert required in verifier_port

    for required in (
        "test_contract_wallet_verification_checks_code_and_calls_erc1271_with_digest_and_signature",
        "test_contract_wallet_accepts_only_erc1271_success_magic_value",
        "test_contract_wallet_revert_maps_to_bounded_invalid_signature_without_eoa_fallback",
        "test_contract_wallet_timeout_maps_to_bounded_invalid_signature",
        "test_chain_mismatch_is_rejected_before_contract_lookup",
        "get_code",
        "call_contract",
        "TimeoutError",
    ):
        assert required in erc1271_contract

    for required in (
        "test_auth_api_challenge_and_session_payloads_expose_siwe_metadata_without_secret_values",
        "test_api_spec_documents_siwe_challenge_session_erc1271_and_cookie_first_runtime_contract",
        "test_postman_fixtures_capture_siwe_fields_and_smart_wallet_metadata_without_raw_signed_material",
    ):
        assert required in api_public_contract


def test_runtime_config_and_env_docs_cover_rpc_timeout_redaction_and_chain_mismatch() -> None:
    api_spec = API_SPEC_PATH.read_text(encoding="utf-8")
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    readmes = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (README_PATH, APP_README_PATH)
    )
    combined = "\n".join((api_spec, env_example, readmes))

    for required in (
        "ADAPTER_AUTH_WALLET_SIGNATURE_RPC_URL",
        "ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID",
        "ADAPTER_AUTH_WALLET_SIGNATURE_TIMEOUT_SECONDS",
        "ADAPTER_AUTH_WALLET_SIGNATURE_TIMEOUT_SECONDS bounds ERC-1271 RPC calls",
        "ADAPTER_AUTH_WALLET_SIGNATURE_CHAIN_ID mismatch rejects before signature recovery or contract lookup",
        "walletSignature.rpcUrl is redacted in runtime/debug output",
        "Access logs must not include raw SIWE messages, signatures, RPC response bodies, or contract call data",
    ):
        assert required in combined


def test_phase_metadata_records_public_verification_completion() -> None:
    phase_index = json.loads(PHASE_INDEX_PATH.read_text(encoding="utf-8"))
    siwe_phase = json.loads(SIWE_PHASE_INDEX_PATH.read_text(encoding="utf-8"))

    steps = {step["step"]: step for step in siwe_phase["steps"]}
    assert set(steps) == {0, 1, 2, 3, 4}
    assert all(step["status"] == "completed" for step in steps.values())
    assert all(step.get("summary") for step in steps.values())
    assert "public verification" in steps[4]["summary"]
    assert "SIWE" in steps[4]["summary"]
    assert "ERC-1271" in steps[4]["summary"]

    top_level = {phase["dir"]: phase for phase in phase_index["phases"]}
    assert top_level["18-siwe-erc1271-auth"]["status"] == "completed"
    assert top_level["18-siwe-erc1271-auth"].get("completed_at")

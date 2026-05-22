from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_multi_wallet_public_docs_distinguish_login_linked_payer_and_store_wallets() -> None:
    api_spec = (ROOT / "docs/API_SPEC.md").read_text(encoding="utf-8")

    for phrase in (
        "login wallet",
        "linked wallet",
        "payer wallet",
        "settlement wallet",
        "wallet revocation does not recover assets",
    ):
        assert phrase in api_spec

    assert "wallet address is the canonical user identity" not in api_spec.lower()

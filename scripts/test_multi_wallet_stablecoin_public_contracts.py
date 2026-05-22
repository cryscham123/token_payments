from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_verification_mentions_stablecoin_scope_and_future_exclusions() -> None:
    api_spec = (ROOT / "docs/API_SPEC.md").read_text(encoding="utf-8")
    sequences = (ROOT / "docs/SEQUENCES.md").read_text(encoding="utf-8")

    for phrase in ("USDC", "USDT", "registry-driven", "permit", "gas sponsorship", "swap"):
        assert phrase in api_spec or phrase in sequences

    assert "arbitrary ERC-20" in api_spec

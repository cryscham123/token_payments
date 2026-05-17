from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_phases import VALID_STATUSES, validate


ROOT = Path(__file__).resolve().parents[1]


def test_public_docs_cover_phase_16_architecture_contracts() -> None:
    combined = "\n".join(
        _read(path)
        for path in (
            "docs/ARCHITECTURE.md",
            "docs/DOMAIN_MODEL.md",
            "docs/API_SPEC.md",
            "docs/SEQUENCES.md",
            "README.md",
            "app/README.md",
        )
    )

    for phrase in (
        "Checkout Process is a separate saga/process context, not an order context submodule",
        "`order.Store` and `store_approval.Store` are not the same aggregate",
        "Adapter type: Kafka/message",
        "PostgreSQL is the source of truth for auth users, login challenges, and sessions",
        "live/prod startup rejects committed placeholder signing values",
    ):
        assert phrase in combined


def test_phase_16_metadata_is_completed_with_specific_summaries() -> None:
    phase_index = json.loads((ROOT / "phases/16-architecture-contract-alignment/index.json").read_text("utf-8"))
    top_index = json.loads((ROOT / "phases/index.json").read_text("utf-8"))
    top_phase = next(phase for phase in top_index["phases"] if phase["dir"] == "16-architecture-contract-alignment")

    assert validate(ROOT) == []
    assert top_phase["status"] == "completed"
    assert phase_index["completed_at"]
    assert all(step["status"] in VALID_STATUSES for step in phase_index["steps"])
    assert all(step["status"] == "completed" for step in phase_index["steps"])
    for step in phase_index["steps"]:
        assert len(step.get("summary", "")) >= 80


def test_manual_order_approval_does_not_return_as_active_roadmap() -> None:
    combined = "\n".join(_read(path) for path in ("docs/API_SPEC.md", "README.md", "app/README.md"))

    assert "store owner manual order approval HTTP API is not in current scope" in combined
    assert "manual order approval HTTP API is not an active roadmap item" in combined
    assert "ERC-20/USDC/USDT payment support is not an immediate roadmap phase" in combined


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")

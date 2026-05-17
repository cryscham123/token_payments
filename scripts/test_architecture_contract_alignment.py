from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_checkout_process_boundary_docs_follow_code_package_layout() -> None:
    architecture = _read("docs/ARCHITECTURE.md")
    domain_model = _read("docs/DOMAIN_MODEL.md")
    sequences = _read("docs/SEQUENCES.md")

    assert "Checkout Process is a separate saga/process context, not an order context submodule" in architecture
    assert "contexts/checkout/application/process_manager.py" in domain_model
    assert "CheckoutProcessManager consumes checkout events from the checkout context adapter" in sequences
    assert (ROOT / "app/token_payments/contexts/checkout/application/process_manager.py").is_file()


def test_checkout_process_responsibilities_are_limited_to_saga_decisions() -> None:
    architecture = _read("docs/ARCHITECTURE.md")

    for phrase in (
        "orchestration",
        "compensation command decision",
        "idempotent saga decision",
    ):
        assert phrase in architecture

    assert "Order context owns order creation, status projection, and checkout tracking" in architecture


def test_store_models_are_documented_as_context_specific_projections() -> None:
    architecture = _read("docs/ARCHITECTURE.md")
    domain_model = _read("docs/DOMAIN_MODEL.md")
    combined = f"{architecture}\n{domain_model}"

    assert "`order.Store`" in combined
    assert "`store_approval.Store`" in combined
    assert "not the same aggregate" in combined
    assert "must not share persistence or DTOs by default" in combined


def test_docs_state_code_package_layout_wins_over_diagram_conflicts() -> None:
    architecture = _read("docs/ARCHITECTURE.md")
    domain_model = _read("docs/DOMAIN_MODEL.md")
    combined = f"{architecture}\n{domain_model}"

    assert "When diagram/DDD.drawio conflicts with code package layout, code package layout wins" in combined


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")

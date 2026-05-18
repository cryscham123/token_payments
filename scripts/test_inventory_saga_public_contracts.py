from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from token_payments.api import http_route_manifest  # noqa: E402


def test_docs_describe_inventory_reserve_release_confirm_saga_flow() -> None:
    sequences = (ROOT / "docs/SEQUENCES.md").read_text(encoding="utf-8")
    domain = (ROOT / "docs/DOMAIN_MODEL.md").read_text(encoding="utf-8")
    api_spec = (ROOT / "docs/API_SPEC.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    app_readme = (ROOT / "app/README.md").read_text(encoding="utf-8")

    for text in (sequences, domain, api_spec, readme, app_readme):
        assert "ConfirmInventoryCommand" in text
        assert "InventoryConfirmedEvent" in text
    assert "OrderApprovedEvent` | CheckoutProcessManager가 `ConfirmInventoryCommand`" in sequences
    assert "PaymentFailedEvent` | CheckoutProcessManager가 `ReleaseInventoryCommand`" in sequences
    assert "PaymentExpiredEvent` | CheckoutProcessManager가 `ReleaseInventoryCommand`" in sequences
    assert "OrderRejectedEvent` | CheckoutProcessManager가 `RefundPaymentCommand`, `ReleaseInventoryCommand`" in sequences


def test_confirm_inventory_is_not_a_public_http_route() -> None:
    manifest = tuple(http_route_manifest())
    encoded = json.dumps(manifest, sort_keys=True)

    assert "ConfirmInventoryCommand" not in encoded
    assert "confirmInventory" not in encoded
    assert all("confirm" not in route["operationId"].lower() for route in manifest)


def test_phase_metadata_reflects_completed_inventory_saga_finalization() -> None:
    phase = json.loads((ROOT / "phases/19-inventory-saga-finalization/index.json").read_text(encoding="utf-8"))
    top = json.loads((ROOT / "phases/index.json").read_text(encoding="utf-8"))

    assert all(step["status"] == "completed" for step in phase["steps"])
    assert all(step.get("summary") for step in phase["steps"])
    top_entry = next(item for item in top["phases"] if item["dir"] == "19-inventory-saga-finalization")
    assert top_entry["status"] == "completed"
    assert top_entry.get("completed_at")

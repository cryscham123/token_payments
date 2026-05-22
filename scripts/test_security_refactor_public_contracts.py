from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_api_spec_documents_tracking_id_payment_submit_without_internal_order_id() -> None:
    payment_section = _section(_read("docs/API_SPEC.md"), "### `POST /payments/transaction-hashes`", "## Operator Observability")

    assert '"trackingId": "tracking-001"' in payment_section
    assert '"txHash": "0xtransactionhash"' in payment_section
    assert "payment.submit_tx:{trackingId}" in payment_section
    assert '"orderId"' not in payment_section
    assert '"paymentId"' not in payment_section


def test_public_security_contract_documents_fail_closed_membership_and_boundary_rules() -> None:
    combined = "\n".join(
        _read(path)
        for path in (
            "docs/API_SPEC.md",
            "docs/ARCHITECTURE.md",
            "docs/ADR.md",
            "docs/SEQUENCES.md",
            "docs/DOMAIN_MODEL.md",
        )
    )

    required_phrases = (
        "Phase 26 public security contract",
        "external payment submission uses `trackingId`",
        "`inventory:write` and canonical store membership",
        "`product:write` at the API boundary and canonical store membership in the service boundary",
        "fail-closed",
        "bounded contexts exchange ports, DTOs, ACLs, snapshots, or shared-kernel value objects",
        "`store_catalog_store_memberships` is the canonical membership source",
        "`auth_group_memberships` is an RBAC projection",
        "transactional outbox",
        "projection lag never authorizes writes",
        "rebuild/replay",
        "runtime composition facade",
        "no-server-start dry-run boundary",
    )

    for phrase in required_phrases:
        assert phrase in combined


def test_postman_payment_submit_public_fixture_uses_tracking_id_only() -> None:
    expected = json.loads(_read("postman/expected/token-payments.api.expected.json"))
    route = next(route for route in expected["routes"] if route["operationId"] == "submitTransactionHash")
    encoded = json.dumps(route, ensure_ascii=True, sort_keys=True)

    assert route["body"] == {
        "payment": {
            "trackingId": "<tracking-id>",
            "status": "TX_SUBMITTED",
            "currentStep": "RECEIPT_PENDING",
            "pendingAction": "WAIT_FOR_RECEIPT",
            "txHash": "<local-test-network-transaction-hash>",
            "updatedAt": "<timestamp>",
        }
    }
    assert "orderId" not in encoded
    assert "paymentId" not in encoded


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]

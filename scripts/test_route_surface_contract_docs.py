from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_api_spec_documents_current_public_http_route_manifest() -> None:
    from token_payments.api import http_route_manifest

    api_spec = _read("docs/API_SPEC.md")
    manifest = list(http_route_manifest())

    assert len(manifest) == 57
    assert "Public HTTP route surface is exactly the current 57-route manifest" in api_spec
    for entry in manifest:
        assert f"`{entry['operationId']}`" in api_spec
        assert f"`{entry['path']}`" in api_spec


def test_api_spec_separates_http_message_and_internal_inputs() -> None:
    api_spec = _read("docs/API_SPEC.md")

    for heading in (
        "Public HTTP route surface",
        "Message listener input surface",
        "Internal application port surface",
        "Store owner inventory API surface",
        "Admin store catalog provisioning API surface",
        "Externally exposed RBAC and membership API surface",
    ):
        assert heading in api_spec

    for phrase in (
        "`approveOrder`/`request_store_approval` are Kafka/message listener inputs",
        "store owner manual order approval HTTP API is not in current scope",
        "`ReserveInventoryCommand`, `ReleaseInventoryCommand`, and `ConfirmInventoryCommand` are checkout saga internal commands",
        "Operator action APIs require explicit platform permissions such as `operator:read`, `operator:action`, and `outbox:retry`",
        "Store owners can query or mutate only own store inventory",
        "platform sessions need explicit inventory/operator policy permission for cross-store access",
        "`POST /admin/store-users`, `POST /admin/stores`, and `POST /admin/stores/{storeId}/memberships` require `admin:provision` or `rbac:manage` policy checks",
        "store ownership/membership, not a global STORE_OWNER account role",
        "MERCHANT_OWNER assignment or transfer is not merchant-facing",
    ):
        assert phrase in api_spec


def test_domain_model_marks_input_ports_with_adapter_type() -> None:
    domain_model = _read("docs/DOMAIN_MODEL.md")

    for phrase in (
        "Adapter type: HTTP",
        "Adapter type: Kafka/message",
        "Adapter type: internal application",
    ):
        assert phrase in domain_model


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_root_summary_exposes_docs_for_gitbook_repository_imports() -> None:
    summary = _read("SUMMARY.md")

    assert "# 목차" in summary
    for label, link in (
        ("PRD", "docs/PRD.md"),
        ("아키텍처", "docs/ARCHITECTURE.md"),
        ("API 명세", "docs/API_SPEC.md"),
        ("API 개요", "docs/api/README.md"),
    ):
        assert label in summary
        assert f"]({link})" in summary


def test_gitbook_summary_exposes_korean_api_spec_pages() -> None:
    summary = _read("docs/SUMMARY.md")

    assert "# 목차" in summary
    for label, link in (
        ("API 명세", "API_SPEC.md"),
        ("API 개요", "api/README.md"),
        ("인증과 OAuth", "api/auth.md"),
        ("주문, 체크아웃, 결제", "api/orders-checkout-payments.md"),
        ("상점과 상품 카탈로그", "api/catalog-inventory.md"),
        ("머천트, 관리자, RBAC", "api/merchant-admin-rbac.md"),
        ("운영자와 런타임", "api/operator-runtime.md"),
    ):
        assert label in summary
        assert f"]({link})" in summary


def test_api_spec_is_gitbook_ready_without_losing_route_manifest_contract() -> None:
    from token_payments.api import http_route_manifest

    api_spec = _read("docs/API_SPEC.md")

    assert api_spec.startswith("---\n")
    assert "# Token Payments API 명세" in api_spec
    assert "## GitBook 탐색" in api_spec
    for link in (
        "api/README.md",
        "api/auth.md",
        "api/orders-checkout-payments.md",
        "api/catalog-inventory.md",
        "api/merchant-admin-rbac.md",
        "api/operator-runtime.md",
    ):
        assert f"]({link})" in api_spec

    assert "Public HTTP route surface is exactly the current 54-route manifest" in api_spec
    for entry in http_route_manifest():
        route_row = f"| `{entry['operationId']}` | `{entry['method']}` | `{entry['path']}` |"
        assert route_row in api_spec


def test_korean_gitbook_api_pages_cover_public_route_groups() -> None:
    required_phrases_by_page = {
        "docs/api/auth.md": (
            "인증",
            "`POST /auth/oauth/{provider}/authorize`",
            "`DELETE /auth/oauth/identities/{oauthIdentityId}`",
            "providerSubject",
        ),
        "docs/api/orders-checkout-payments.md": (
            "주문",
            "`POST /orders`",
            "`GET /checkouts/tracking/{trackingId}`",
            "`POST /payments/transaction-hashes`",
        ),
        "docs/api/catalog-inventory.md": (
            "카탈로그",
            "`GET /stores`",
            "`POST /merchant/stores/{publicStoreId}/products`",
            "`POST /store-owner/stores/{storeId}/inventory/{productId}/intake`",
        ),
        "docs/api/merchant-admin-rbac.md": (
            "RBAC",
            "`POST /admin/stores`",
            "`GET /merchant/role-catalog`",
            "`POST /merchant/stores/{storeId}/invitations`",
        ),
        "docs/api/operator-runtime.md": (
            "운영자",
            "`GET /operator/dashboard`",
            "`POST /operator/outbox/{messageId}/retry`",
            "no-server-start",
        ),
    }

    for relative_path, phrases in required_phrases_by_page.items():
        text = _read(relative_path)
        assert text.startswith("# ")
        assert "요청" in text or "권한" in text
        for phrase in phrases:
            assert phrase in text


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")

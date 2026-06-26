from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_http_adapter_public_exports_cover_router_routes_wsgi_and_manifest_helpers() -> None:
    import token_payments.api as api

    expected_exports = {
        "ADMIN_STORE_CATALOG_HTTP_ROUTES",
        "AUTH_HTTP_ROUTES",
        "CHECKOUT_HTTP_ROUTES",
        "ORDER_HTTP_ROUTES",
        "OPERATOR_ACTION_HTTP_ROUTES",
        "OPERATOR_HTTP_ROUTES",
        "PAYMENT_HTTP_ROUTES",
        "MERCHANT_MEMBERSHIP_HTTP_ROUTES",
        "MerchantMembershipApi",
        "STORE_OWNER_CATALOG_HTTP_ROUTES",
        "STORE_OWNER_INVENTORY_HTTP_ROUTES",
        "StoreCatalogApi",
        "HttpRequest",
        "HttpResponse",
        "HttpRoute",
        "HttpRouteSpec",
        "HttpRouter",
        "build_wsgi_app",
        "describe_http_routes",
        "http_route_manifest",
        "list_http_route_specs",
        "register_auth_routes",
        "register_checkout_routes",
        "register_merchant_membership_routes",
        "register_order_routes",
        "register_operator_action_routes",
        "register_operator_routes",
        "register_payment_routes",
        "register_store_catalog_routes",
        "register_store_owner_inventory_routes",
    }

    assert expected_exports <= set(api.__all__)
    assert all(hasattr(api, name) for name in expected_exports)


def test_http_route_manifest_includes_every_phase_7_route_family() -> None:
    from token_payments.api import describe_http_routes, http_route_manifest

    manifest = list(http_route_manifest())
    described = list(describe_http_routes())

    assert described == manifest
    assert len(manifest) == 62
    assert {entry["operationId"] for entry in manifest} == {
        "requestLoginChallenge",
        "loginWithMetaMask",
        "requestOAuthAuthorization",
        "completeOAuthSession",
        "linkOAuthIdentity",
        "listOAuthIdentities",
        "revokeOAuthIdentity",
        "requestWalletLinkChallenge",
        "linkWallet",
        "listWallets",
        "setPrimaryWallet",
            "revokeWallet",
            "refreshSession",
            "switchSession",
            "logout",
        "getCurrentUser",
        "getCurrentUserProfile",
        "updateCurrentUserProfile",
        "createOrder",
        "getCheckoutTrackingByTrackingId",
        "getCheckoutTrackingByOrderId",
        "listUserPayments",
        "submitTransactionHash",
        "cancelPayment",
        "listPublicStores",
        "getStoreProfile",
        "listAllPublicProducts",
        "listPublicProducts",
        "getPublicProduct",
        "getProductAsset",
        "listMerchantStores",
        "updateStoreProfile",
        "createOrReuseStoreUser",
        "createStore",
        "grantStoreMembership",
        "listMerchantProducts",
        "getMerchantProduct",
        "uploadMerchantProductAsset",
        "registerStoreProduct",
        "updateStoreProduct",
        "listStoreOwnerInventory",
        "increaseStoreOwnerInventoryStock",
        "correctStoreOwnerInventoryStock",
        "pauseStoreOwnerInventorySales",
        "resumeStoreOwnerInventorySales",
        "listMerchantStoreMembers",
        "listMerchantStoreInvitations",
        "listMerchantUserInvitations",
        "createMerchantStoreInvitation",
        "acceptMerchantInvitation",
        "revokeMerchantInvitation",
        "updateMerchantStoreMemberRole",
        "removeMerchantStoreMember",
        "getMerchantRoleCatalog",
        "searchMerchantUsers",
        "getOperatorDashboard",
        "getOperatorOrderDetail",
        "getOperatorPaymentDetail",
        "getOperatorOutboxDetail",
        "cancelOperatorOrder",
        "retryOperatorOutboxMessage",
        "replayOperatorMessage",
    }
    assert {entry["path"].split("/")[1] for entry in manifest} == {
        "auth",
        "orders",
        "checkouts",
        "payments",
        "stores",
        "products",
        "product-assets",
        "admin",
        "store-owner",
        "merchant",
        "operator",
    }


def test_existing_api_runtime_and_e2e_public_contract_imports_still_resolve() -> None:
    modules = (
        "token_payments.api",
        "token_payments.api.auth",
        "token_payments.api.checkout",
        "token_payments.api.operator",
        "token_payments.api.orders",
        "token_payments.api.payments",
        "token_payments.runtime",
        "token_payments.runtime.smoke",
    )

    for module_name in modules:
        module = importlib.import_module(module_name)
        assert module is not None


def test_readmes_document_http_adapter_preview_and_next_phase_candidates() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    app_readme = (ROOT / "app/README.md").read_text(encoding="utf-8")

    assert "app/README.md" in readme
    assert "serve-api" in readme

    for text in (
        "scripts/test_wsgi_runtime_preview.py",
        "scripts/test_http_adapter_public_contracts.py",
        "PYTHONPATH=app python3 -m token_payments api",
        "PYTHONPATH=app python3 -m token_payments serve-api",
        "bounded HTTP adapter preview",
        "long-running server",
        "real docker compose integration",
        "ASGI/FastAPI thin adapter",
        "operator lifecycle action endpoints",
    ):
        assert text in app_readme

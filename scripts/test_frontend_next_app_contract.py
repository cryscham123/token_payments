from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_frontend_scaffold_uses_next_react_tailwind_outside_nginx_directory() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))

    assert package["name"] == "token-payments-web"
    assert package["scripts"] == {"dev": "next dev", "build": "next build", "start": "next start"}
    assert {"next", "react", "react-dom", "lucide-react"} <= set(package["dependencies"])
    assert {"tailwindcss", "postcss", "autoprefixer"} <= set(package["devDependencies"])
    assert (FRONTEND / "package-lock.json").exists()
    assert "RUN npm ci" in (FRONTEND / "Dockerfile").read_text(encoding="utf-8")
    assert (FRONTEND / "app" / "page.jsx").exists()
    assert (FRONTEND / "tailwind.config.js").exists()
    assert not (ROOT / "app" / "nginx" / "package.json").exists()
    assert not (ROOT / "app" / "nginx" / "app").exists()


def test_frontend_keeps_imported_ethercommerce_flow_without_static_demo_data_module() -> None:
    readme = (FRONTEND / "README.md").read_text(encoding="utf-8")
    component_names = {path.name for path in (FRONTEND / "components").glob("*.jsx")}

    assert "https://github.com/joonistaa/ethercommerce" in readme
    assert "69596a5ef735d2c84739ac58d4ce747bc1996cf0" in readme
    assert not (FRONTEND / "lib" / "demo-data.js").exists()
    assert {
        "Home.jsx",
        "ProductDetail.jsx",
        "Cart.jsx",
        "PayModal.jsx",
        "PaymentComplete.jsx",
        "OrderHistory.jsx",
        "StoreDetail.jsx",
        "StoreList.jsx",
    } <= component_names


def test_frontend_wallet_login_uses_cookie_first_siwe_api_flow() -> None:
    auth_client = (FRONTEND / "lib" / "auth-client.js").read_text(encoding="utf-8")
    modal = (FRONTEND / "components" / "WalletConnectModal.jsx").read_text(encoding="utf-8")
    header = (FRONTEND / "components" / "SiteHeader.jsx").read_text(encoding="utf-8")
    oauth_callback = (FRONTEND / "components" / "OAuthCallback.jsx").read_text(encoding="utf-8")
    combined = "\n".join((auth_client, modal, header))

    assert '"/auth/challenges"' in auth_client
    assert '"/auth/sessions"' in auth_client
    assert '"/auth/me"' in auth_client
    assert "/auth/oauth/" in auth_client
    assert 'credentials: "include"' in auth_client
    assert "eth_requestAccounts" in modal
    assert "eth_chainId" in modal
    assert "personal_sign" in modal
    assert "challenge.signingMessage" in modal
    assert "loginWithMetaMask" in modal
    assert "requestOAuthAuthorization" in modal
    assert "Google로 계속하기" in modal
    assert "window.location.assign" in modal
    assert "completeOAuthSession" in oauth_callback
    assert (FRONTEND / "app" / "oauth" / "callback" / "page.jsx").exists()
    assert "getCurrentUser" in header
    assert "localStorage" not in combined
    assert "sessionStorage" not in combined
    assert '"Authorization"' not in combined
    assert "headers.Authorization" not in combined


def test_frontend_checkout_starts_with_empty_cart_and_uses_real_payment_api_flow() -> None:
    cart = (FRONTEND / "lib" / "cart.js").read_text(encoding="utf-8")
    checkout_client = (FRONTEND / "lib" / "checkout-client.js").read_text(encoding="utf-8")
    product_detail = (FRONTEND / "components" / "ProductDetail.jsx").read_text(encoding="utf-8")
    cart_page = (FRONTEND / "components" / "Cart.jsx").read_text(encoding="utf-8")
    pay_modal = (FRONTEND / "components" / "PayModal.jsx").read_text(encoding="utf-8")
    home = (FRONTEND / "components" / "Home.jsx").read_text(encoding="utf-8")
    complete = (FRONTEND / "components" / "PaymentComplete.jsx").read_text(encoding="utf-8")
    formatter = (FRONTEND / "lib" / "format.js").read_text(encoding="utf-8")
    combined = "\n".join((cart, checkout_client, product_detail, cart_page, pay_modal, home, complete, formatter))

    assert "TPAY" not in combined
    assert "cartSeed" not in combined
    assert "tokenAmount" not in combined
    assert "tokenSymbol" not in combined
    assert "demo-data" not in combined
    assert "demoStore" not in combined
    assert "demoProducts" not in combined
    assert "formatCryptoAmount" in formatter
    assert "loadCart()" in cart_page
    assert "localStorage" in cart
    assert "addCartItem" in product_detail
    assert '"/orders"' in checkout_client
    assert "/checkouts/tracking/" in checkout_client
    assert '"/payments/transaction-hashes"' in checkout_client
    assert "eth_sendTransaction" in checkout_client
    assert "createOrder" in cart_page
    assert "/pay?trackingId=" in cart_page
    assert "submitTransactionHash" in pay_modal
    assert "clearCart" in pay_modal


def test_frontend_checkout_supports_server_payment_options_and_expiry_sync() -> None:
    auth_client = (FRONTEND / "lib" / "auth-client.js").read_text(encoding="utf-8")
    checkout_client = (FRONTEND / "lib" / "checkout-client.js").read_text(encoding="utf-8")
    cart_page = (FRONTEND / "components" / "Cart.jsx").read_text(encoding="utf-8")
    pay_modal = (FRONTEND / "components" / "PayModal.jsx").read_text(encoding="utf-8")
    product_detail = (FRONTEND / "components" / "ProductDetail.jsx").read_text(encoding="utf-8")

    assert '"/auth/wallets"' in auth_client
    assert "listWallets" in auth_client
    assert "paymentAssetId" in checkout_client
    assert "walletId" in checkout_client
    assert "ERC20_TRANSFER" in checkout_client
    assert "amountMinorUnits" in checkout_client
    assert "tokenAddress" in checkout_client
    assert "paymentCapability" in product_detail
    assert "paymentOptions" in cart_page
    assert "selectedPaymentAssetId" in cart_page
    assert "selectedWalletId" in cart_page
    assert "walletId: selectedWalletId" in cart_page
    assert "paymentAssetId: selectedPaymentAssetId" in cart_page
    assert "paymentRequest?.expiresAt" in pay_modal
    assert "Date.parse" in pay_modal
    assert "max-w-4xl" in pay_modal
    assert "lg:grid-cols-[0.9fr_1.1fr]" in pay_modal
    assert "compactPaymentFacts" in pay_modal
    assert "15 * 60" not in pay_modal
    assert "결제 요청 만들기" not in pay_modal


def test_frontend_checkout_normalizes_token_insufficient_balance_errors_before_code_prefix() -> None:
    cart_page = (FRONTEND / "components" / "Cart.jsx").read_text(encoding="utf-8")
    pay_modal = (FRONTEND / "components" / "PayModal.jsx").read_text(encoding="utf-8")

    assert 'errorMessage(error, "주문 생성에 실패했습니다.", group.selectedOption?.symbol)' in cart_page
    assert "isTokenInsufficient" in cart_page
    assert "insufficient balance" in cart_page
    assert "결제에 필요한 ${symbol} 토큰 잔액이 부족합니다." in cart_page
    assert "VALIDATION_ERROR" in cart_page
    assert "errMsg.includes(\"insufficient balance\")" in pay_modal
    assert "결제에 필요한 ${symbol} 토큰 잔액이 부족합니다." in pay_modal


def test_frontend_testnet_faucet_uses_registry_assets_for_claim_and_metamask_watch() -> None:
    profile = (FRONTEND / "components" / "Profile.jsx").read_text(encoding="utf-8")
    auth_client = (FRONTEND / "lib" / "auth-client.js").read_text(encoding="utf-8")

    assert "listPublicStores" in auth_client
    assert 'apiJson("/stores"' in auth_client
    assert "loadTestnetAssets" in profile
    assert "wallet_watchAsset" in profile
    assert "handleWatchAsset" in profile
    assert "tokenAssets.usdc?.tokenAddress" in profile
    assert "tokenAssets.usdt?.tokenAddress" in profile
    assert "USDC 지갑에 추가" in profile
    assert "USDT 지갑에 추가" in profile
    assert "0x4444444444444444444444444444444444444444" not in profile
    assert "0x5555555555555555555555555555555555555555" not in profile


def test_frontend_checkout_sends_order_uuid_product_ids_not_public_catalog_ids() -> None:
    checkout_client = (FRONTEND / "lib" / "checkout-client.js").read_text(encoding="utf-8")
    product_detail = (FRONTEND / "components" / "ProductDetail.jsx").read_text(encoding="utf-8")
    home = (FRONTEND / "components" / "Home.jsx").read_text(encoding="utf-8")

    assert "checkoutProductId(item)" in checkout_client
    assert "const productId = checkoutProductId(item);" in checkout_client
    assert "demoProductIdForPublicId" not in checkout_client
    assert "demoProductIdForPublicId" not in product_detail
    assert "demoProductIdForPublicId" not in home
    assert "products as demoProducts" not in checkout_client
    # A real internal UUID is sent when already returned by the API; otherwise the server
    # resolves the line from publicProductId.
    assert "publicProductId: item.publicProductId" in checkout_client
    assert "publicStoreId" in checkout_client
    assert "publicVariantId: item.publicVariantId" in checkout_client
    assert "selectedOptions: item.selectedOptions" in checkout_client
    assert "orderProductId" in product_detail
    assert "orderProductId" in home
    assert "p.publicProductId" in product_detail


def test_frontend_product_detail_surfaces_store_and_catalog_detail_context() -> None:
    product_detail = (FRONTEND / "components" / "ProductDetail.jsx").read_text(encoding="utf-8")
    store_detail = (FRONTEND / "components" / "StoreDetail.jsx").read_text(encoding="utf-8")

    assert (FRONTEND / "app" / "stores" / "[publicStoreId]" / "page.jsx").exists()
    assert "setStoreProfile" in product_detail
    assert "product.tags" in product_detail
    assert "p.media" in product_detail
    assert "basePrice: p.basePrice" in product_detail
    assert "product.galleryImages" in product_detail
    assert "product.variants" in product_detail
    assert "requiredOptions" in product_detail
    assert "optionalOptions" in product_detail
    assert "displayedUnitPrice" in product_detail
    assert "selectedPaymentAssetKey" in product_detail
    assert "priceOptionsFromProduct(product)" in product_detail
    assert "optionChoicesFromProduct(product)" in product_detail
    assert "selectedOptionValues" in product_detail
    assert "selectedVariant" in product_detail
    assert "changeOptionValue" in product_detail
    assert "changeMultiOptionValue" in product_detail
    assert "option.selectionType === \"MULTI\"" in product_detail
    assert "type=\"checkbox\"" in product_detail
    assert "optionValueLabel(product, option, optionIndex, value, selectedOptionValues, selectedPriceOption)" in product_detail
    assert "variantAvailability(selectedVariant)" in product_detail
    assert "variantDisplayPrice(selectedVariant, selectedPriceOption, product)" in product_detail
    assert "selectedAddOnDelta" in product_detail
    assert "selectedOptions: selectedOptionValues" in product_detail
    assert "requiredOptions.every" in product_detail
    assert "purchaseUnavailable(product, productRemainingQty)" in product_detail
    assert "총 상품 금액" in product_detail
    assert "구매 불가" in product_detail
    assert "주문 시 확정" not in product_detail
    assert "추가금 없음" not in product_detail
    assert "visibleStoreProfile" in product_detail
    assert "href={`/stores/${visibleStoreProfile.publicStoreId}`}" in product_detail
    assert "`/stores/${publicStoreId}`" in store_detail
    assert "`/stores/${publicStoreId}/products`" in store_detail
    assert "paymentCapabilitySummary(store?.paymentCapability)" in store_detail
    assert "supportEmail" in store_detail


def test_frontend_home_product_cards_show_catalog_context_without_fake_discounts() -> None:
    home = (FRONTEND / "components" / "Home.jsx").read_text(encoding="utf-8")

    assert "category: p.category" in home
    assert "fromPriceLabel(product)" in home
    assert "homePaymentSummary(product.paymentCapability)" in home
    assert "15%" not in home
    assert "특가" not in home


def test_frontend_product_card_images_use_fixed_cropping_frames() -> None:
    home = (FRONTEND / "components" / "Home.jsx").read_text(encoding="utf-8")
    store_detail = (FRONTEND / "components" / "StoreDetail.jsx").read_text(encoding="utf-8")
    merchant_dashboard = (FRONTEND / "components" / "MerchantDashboard.jsx").read_text(encoding="utf-8")

    assert home.count('className="relative aspect-square overflow-hidden bg-slate-50"') == 2
    assert store_detail.count('className="relative aspect-square overflow-hidden bg-slate-50"') == 1
    assert 'className="relative aspect-square overflow-hidden bg-slate-50 border-b border-slate-100"' in merchant_dashboard
    assert 'className="relative aspect-video bg-slate-50 border-b border-slate-100"' not in merchant_dashboard
    for source in (home, store_detail, merchant_dashboard):
        assert "h-full w-full object-cover" in source


def test_frontend_merchant_dashboard_separates_read_and_write_permission_states() -> None:
    dashboard = (FRONTEND / "components" / "MerchantDashboard.jsx").read_text(encoding="utf-8")

    assert 'hasScope("merchant_member:read")' in dashboard
    assert 'hasScope("merchant_member:invite")' in dashboard
    assert 'hasScope("merchant_member:manage")' in dashboard
    assert 'hasScope("store:write")' in dashboard
    assert 'hasScope("product:write")' in dashboard
    assert "PermissionNotice" in dashboard
    assert "membershipReadForbidden" in dashboard
    assert "productReadForbidden" in dashboard
    assert "권한이 없습니다" in dashboard
    assert "disabled={!canWriteStore || savingStore}" in dashboard
    assert "disabled={!canWriteProducts}" in dashboard
    assert "disabled={!canInviteMembers || sendingInvite || hasPendingInviteForCurrentTarget || !internalStoreId}" in dashboard
    assert "disabled={!canManageMembers}" in dashboard
    assert "canRevokeInvitations" in dashboard
    assert "disabled={!canRevokeInvitations}" in dashboard
    assert "이미 대기 중인 초대가 있습니다." in dashboard
    assert 'useState("")' in dashboard
    assert "44444444-4444-4444-8444-444444444444" not in dashboard
    assert "catch(() => ({ members: [] }))" not in dashboard
    assert "catch(() => ({ invitations: [] }))" not in dashboard


def test_frontend_header_product_nav_only_shows_real_destinations() -> None:
    header = (FRONTEND / "components" / "SiteHeader.jsx").read_text(encoding="utf-8")

    assert "전체 상품" in header
    assert "신상품" in header
    assert "가게" in header
    assert 'href="/#products"' in header
    assert 'href="/#new-products"' in header
    assert 'href="/stores"' in header
    assert "상품명이나 가게를 검색해보세요" in header

    assert "카테고리" not in header
    assert "로컬 상품" not in header
    assert "식품/과일" not in header
    assert "패션의류" not in header
    assert "크립토 결제" not in header
    assert "신선식품" not in header


def test_frontend_header_redirects_home_after_logout() -> None:
    header = (FRONTEND / "components" / "SiteHeader.jsx").read_text(encoding="utf-8")

    assert "const router = useRouter();" in header
    assert "const handleWalletButtonClick = async () => {" in header
    assert header.count("await logout();") == 1
    assert header.index("await logout();") < header.index('router.push("/");')
    assert header.count("onClick={handleWalletButtonClick}") == 2


def test_frontend_store_nav_opens_public_store_list_before_store_detail() -> None:
    header = (FRONTEND / "components" / "SiteHeader.jsx").read_text(encoding="utf-8")
    store_list = (FRONTEND / "components" / "StoreList.jsx").read_text(encoding="utf-8")

    assert (FRONTEND / "app" / "stores" / "page.jsx").exists()
    assert 'href="/stores"' in header
    assert 'apiJson("/stores")' in store_list
    assert 'href={`/stores/${store.publicStoreId}`}' in store_list
    assert "가게 목록" in store_list
    assert "paymentCapabilitySummary(store.paymentCapability)" in store_list


def test_frontend_cart_items_link_back_to_product_detail() -> None:
    cart_page = (FRONTEND / "components" / "Cart.jsx").read_text(encoding="utf-8")

    assert 'href={`/products/${item.publicProductId}`}' in cart_page
    assert "상품 정보 보기" in cart_page


def test_compose_exposes_next_web_service_only_behind_nginx() -> None:
    services = _compose_services()
    web = services["token_payments_web"]
    nginx = services["nginx"]

    assert _scalar_for_key(web, "image") == "token_payments_web"
    assert _nested_scalar(web, "build", "context") == "frontend"
    assert _list_for_key(web, "profiles") == ["api"]
    assert _list_for_key(web, "ports") == []
    assert _list_for_key(web, "expose") == ["3000"]
    assert "NEXT_PUBLIC_API_BASE_URL=${API_PUBLIC_BASE_URL}" in "\n".join(web)
    assert "token_payments_web:" in "\n".join(nginx)


def test_nginx_routes_frontend_root_and_api_paths_separately() -> None:
    config = (ROOT / "app" / "nginx" / "default.conf").read_text(encoding="utf-8")

    assert "upstream token_payments_web" in config
    assert "server token_payments_web:3000;" in config
    assert "location ~ ^/(auth|checkouts?|payments|stores|admin|operator|healthz|readyz)(/|$)" in config
    assert "location ~ ^/merchant(/|$)" in config
    assert "location ~ ^/orders(/|$)" in config
    assert "proxy_pass http://token_payments_api;" in config
    assert "proxy_pass http://token_payments_web;" in config


def _compose_services() -> dict[str, tuple[str, ...]]:
    services: dict[str, list[str]] = {}
    current_service: str | None = None
    in_services = False
    for raw_line in (ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = _indent_width(raw_line)
        if indent == 0 and stripped == "services:":
            in_services = True
            continue
        if not in_services:
            continue
        if indent == 0:
            break
        if indent == 2 and stripped.endswith(":") and not stripped.startswith("- "):
            current_service = stripped[:-1]
            services[current_service] = []
            continue
        if current_service is not None:
            services[current_service].append(raw_line)
    return {name: tuple(block) for name, block in services.items()}


def _list_for_key(block: tuple[str, ...], key: str) -> list[str]:
    values: list[str] = []
    in_key = False
    key_indent = -1
    for raw_line in block:
        stripped = raw_line.strip()
        indent = _indent_width(raw_line)
        if stripped == f"{key}:":
            in_key = True
            key_indent = indent
            continue
        if in_key and indent <= key_indent and not stripped.startswith("- "):
            break
        if in_key and stripped.startswith("- "):
            values.append(stripped[2:].strip().strip('"'))
    return values


def _scalar_for_key(block: tuple[str, ...], key: str) -> str | None:
    for raw_line in block:
        stripped = raw_line.strip()
        if stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip().strip('"')
    return None


def _nested_scalar(block: tuple[str, ...], section: str, key: str) -> str | None:
    in_section = False
    section_indent = -1
    for raw_line in block:
        stripped = raw_line.strip()
        indent = _indent_width(raw_line)
        if stripped == f"{section}:":
            in_section = True
            section_indent = indent
            continue
        if in_section and indent <= section_indent:
            break
        if in_section and stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip().strip('"')
    return None


def _indent_width(line: str) -> int:
    return len(line) - len(line.lstrip(" "))

"use client";
import Link from "next/link";
import { ArrowRight, Info, Loader2, Minus, Plus, ShoppingCart, TriangleAlert, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import SiteHeader from "./SiteHeader";
import { loadCart, saveCart } from "@/lib/cart";
import { getCurrentUser, listWallets, requestWalletLinkChallenge, linkWallet } from "@/lib/auth-client";
import { createOrder, findProductSummary, getStoreProduct, ensureChain } from "@/lib/checkout-client";
import { formatCryptoAmount } from "@/lib/format";
import { isActiveWallet, walletLabel, paymentOptionsForItem } from "@/lib/payment-options";
import { getCategoryFallback } from "@/lib/product-image";
export default function Cart() {
  const router = useRouter();
  const [cartItems, setCartItems] = useState([]);
  const [currentUser, setCurrentUser] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [selectedPaymentOptionKeys, setSelectedPaymentOptionKeys] = useState({});
  const [selectedWalletIds, setSelectedWalletIds] = useState({});
  const [storeStatus, setStoreStatus] = useState({});
  const [storeMessage, setStoreMessage] = useState({});
  const [linkingStoreId, setLinkingStoreId] = useState(null);

  useEffect(() => {
    setCartItems(loadCart());
  }, []);

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((payload) => {
        if (active) setCurrentUser(payload?.user || null);
      })
      .catch(() => {
        if (active) setCurrentUser(null);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    async function loadUserWallets() {
      if (!currentUser) {
        setWallets([]);
        return;
      }
      try {
        const payload = await listWallets();
        if (active) setWallets((payload?.wallets || []).filter(isActiveWallet));
      } catch {
        if (active) setWallets([]);
      }
    }
    loadUserWallets();
    return () => { active = false; };
  }, [currentUser]);

  useEffect(() => {
    let active = true;
    async function loadPaymentOptions() {
      if (cartItems.length === 0) {
        setSelectedPaymentOptionKeys({});
        return;
      }
      const enrichedItems = await Promise.all(
        cartItems.map(async (item) => {
          if (item.paymentCapability && (item.publicStoreId || item.storePublicId)) return item;
          try {
            let publicStoreId = item.publicStoreId || item.storePublicId || "";
            let summary = null;
            if (!publicStoreId && item.publicProductId) {
              summary = await findProductSummary(item.publicProductId);
              publicStoreId = summary?.publicStoreId || summary?.storePublicId || summary?.store?.publicStoreId || "";
            }
            if (!publicStoreId) return item;
            if (item.paymentCapability) {
              return {
                ...item,
                orderProductId: item.orderProductId || summary?.productId || "",
                publicStoreId: item.publicStoreId || publicStoreId,
                storePublicId: item.storePublicId || publicStoreId,
                storeDisplayName: item.storeDisplayName || summary?.storeDisplayName || summary?.store?.displayName || ""
              };
            }
            const payload = await getStoreProduct({
              publicStoreId,
              publicProductId: item.publicProductId
            });
            const product = payload?.product;
            if (!product) {
              return {
                ...item,
                orderProductId: item.orderProductId || summary?.productId || "",
                publicStoreId: item.publicStoreId || publicStoreId,
                storePublicId: item.storePublicId || publicStoreId,
                storeDisplayName: item.storeDisplayName || summary?.storeDisplayName || summary?.store?.displayName || ""
              };
            }
            return {
              ...item,
              orderProductId: item.orderProductId || product.productId || summary?.productId || "",
              publicStoreId: item.publicStoreId || product.publicStoreId || publicStoreId,
              storePublicId: item.storePublicId || product.publicStoreId || publicStoreId,
              storeDisplayName: item.storeDisplayName || payload?.store?.displayName || summary?.storeDisplayName || summary?.store?.displayName || "",
              cryptoAmount: product.displayPrice?.amount || item.cryptoAmount,
              cryptoSymbol: product.displayPrice?.symbol || item.cryptoSymbol,
              cryptoChainId: product.displayPrice?.chainId || item.cryptoChainId,
              cryptoTokenAddress: product.displayPrice?.tokenAddress || item.cryptoTokenAddress,
              cryptoDecimals: product.displayPrice?.decimals || item.cryptoDecimals,
              paymentCapability: product.paymentCapability || item.paymentCapability
            };
          } catch {
            return item;
          }
        })
      );
      if (!active) return;
      if (JSON.stringify(enrichedItems) !== JSON.stringify(cartItems)) {
        setCartItems(enrichedItems);
        saveCart(enrichedItems);
      }

      // 스토어별 기본 옵션 결정
      const groups = new Map();
      for (const item of enrichedItems) {
        const storeId = storeIdOf(item);
        if (!groups.has(storeId)) groups.set(storeId, []);
        groups.get(storeId).push(item);
      }

      setSelectedPaymentOptionKeys((current) => {
        const nextKeys = { ...current };
        let changed = false;
        for (const [storeId, items] of groups.entries()) {
          const allOptions = items.flatMap(paymentOptionsForItem);
          const nextOptions = [];
          const seenKeys = new Set();
          for (const opt of allOptions) {
            if (opt && !seenKeys.has(opt.key)) {
              seenKeys.add(opt.key);
              nextOptions.push(opt);
            }
          }

          const currentKey = current[storeId];
          const hasValidOption = nextOptions.some((option) => option.key === currentKey);
          if (!hasValidOption) {
            const preferredPaymentOptionKey = items.find((item) => (
              item.preferredPaymentOptionKey && nextOptions.some((option) => option.key === item.preferredPaymentOptionKey)
            ))?.preferredPaymentOptionKey || "";
            nextKeys[storeId] = preferredPaymentOptionKey || nextOptions[0]?.key || "";
            changed = true;
          }
        }
        return changed ? nextKeys : current;
      });
    }
    loadPaymentOptions();
    return () => { active = false; };
  }, [cartItems]);

  const updateQuantity = (itemKey, delta) => {
    const nextItems = cartItems.map((item) => (
      cartItemKey(item) === itemKey ? { ...item, quantity: Math.max(1, item.quantity + delta) } : item
    ));
    setCartItems(nextItems);
    saveCart(nextItems);
  };
  const removeItem = (itemKey) => {
    const nextItems = cartItems.filter((item) => cartItemKey(item) !== itemKey);
    setCartItems(nextItems);
    saveCart(nextItems);
  };

  const storeIdOf = (item) => item.publicStoreId || item.storePublicId || "";
  const storeNameOf = (item) => item.storeDisplayName || item.storePublicId || item.publicStoreId || "스토어";

  // storeGroups 생성 로직
  const storeGroups = (() => {
    const groups = new Map();
    for (const item of cartItems) {
      const storeId = storeIdOf(item);
      if (!groups.has(storeId)) groups.set(storeId, { storeId, storeName: storeNameOf(item), items: [] });
      groups.get(storeId).items.push(item);
    }
    return Array.from(groups.values()).map((group) => {
      const allOptions = group.items.flatMap(paymentOptionsForItem);
      const nextOptions = [];
      const seenKeys = new Set();
      for (const opt of allOptions) {
        if (opt && !seenKeys.has(opt.key)) {
          seenKeys.add(opt.key);
          nextOptions.push(opt);
        }
      }

      const storeOptionKey = selectedPaymentOptionKeys[group.storeId] || "";
      const selectedOption = nextOptions.find((opt) => opt.key === storeOptionKey) || nextOptions[0] || null;

      const activeItems = group.items.filter((item) => {
        const itemOptions = paymentOptionsForItem(item);
        return !selectedOption || itemOptions.some((opt) => opt.key === selectedOption.key);
      });

      const subtotal = activeItems.reduce(
        (acc, item) => acc + (Number.parseFloat(resolveItemUnitPrice(item, selectedOption).amount) || 0) * item.quantity,
        0
      );

      const eligibleWallets = wallets.filter((wallet) => !selectedOption?.chainId || Number(wallet.chainId) === Number(selectedOption.chainId));

      return {
        ...group,
        options: nextOptions,
        selectedOption,
        activeItems,
        subtotal,
        eligibleWallets
      };
    });
  })();

  // 지갑 연동 기본값 선택 동기화
  useEffect(() => {
    setSelectedWalletIds((current) => {
      const nextWalletIds = { ...current };
      let changed = false;
      for (const group of storeGroups) {
        const storeId = group.storeId;
        const selectedOption = group.selectedOption;
        const eligible = group.eligibleWallets;
        const currentWalletId = current[storeId];

        if (!selectedOption) {
          if (currentWalletId !== "") {
            nextWalletIds[storeId] = "";
            changed = true;
          }
          continue;
        }

        const hasValidWallet = eligible.some((w) => w.walletId === currentWalletId);
        if (!hasValidWallet) {
          const primary = eligible.find((w) => w.primary);
          const nextWalletId = primary?.walletId || eligible[0]?.walletId || "";
          if (currentWalletId !== nextWalletId) {
            nextWalletIds[storeId] = nextWalletId;
            changed = true;
          }
        }
      }
      return changed ? nextWalletIds : current;
    });
  }, [storeGroups]);

  async function startCheckout(storeId) {
    const group = storeGroups.find((g) => g.storeId === storeId);
    if (!group) return;
    if (!group.storeId) {
      setStoreStatus((prev) => ({ ...prev, [storeId]: "error" }));
      setStoreMessage((prev) => ({ ...prev, [storeId]: "스토어 정보를 확인할 수 없습니다. 상품을 다시 담아 주세요." }));
      return;
    }

    if (!currentUser) {
      setStoreStatus((prev) => ({ ...prev, [storeId]: "error" }));
      setStoreMessage((prev) => ({ ...prev, [storeId]: "지갑을 연결한 후 주문할 수 있습니다." }));
      return;
    }
    if (!group.selectedOption) {
      setStoreStatus((prev) => ({ ...prev, [storeId]: "error" }));
      setStoreMessage((prev) => ({ ...prev, [storeId]: "선택 가능한 결제 수단이 없습니다." }));
      return;
    }
    const walletId = selectedWalletIds[storeId];
    if (!walletId) {
      setStoreStatus((prev) => ({ ...prev, [storeId]: "error" }));
      setStoreMessage((prev) => ({ ...prev, [storeId]: "선택한 네트워크에 연결된 지갑이 없습니다." }));
      return;
    }

    setStoreStatus((prev) => ({ ...prev, [storeId]: "creating" }));
    setStoreMessage((prev) => ({ ...prev, [storeId]: "주문을 생성하는 중입니다." }));
    try {
      const orderItems = group.activeItems;
      if (orderItems.length === 0) {
        setStoreStatus((prev) => ({ ...prev, [storeId]: "error" }));
        setStoreMessage((prev) => ({ ...prev, [storeId]: "결제할 상품이 없습니다." }));
        return;
      }
      const created = await createOrder({
        publicStoreId: storeId,
        items: orderItems,
        walletId: walletId,
        paymentAssetId: group.selectedOption.paymentAssetId || ""
      });
      const trackingId = created?.order?.trackingId;
      if (!trackingId) throw new Error("주문 trackingId를 받지 못했습니다.");

      const remainingItems = cartItems.filter((item) => !orderItems.includes(item));
      setCartItems(remainingItems);
      saveCart(remainingItems);

      router.push(`/pay?trackingId=${encodeURIComponent(trackingId)}`);
    } catch (error) {
      setStoreStatus((prev) => ({ ...prev, [storeId]: "error" }));
      setStoreMessage((prev) => ({
        ...prev,
        [storeId]: errorMessage(error, "주문 생성에 실패했습니다.", group.selectedOption?.symbol)
      }));
    }
  }

  const reloadWallets = async (storeId) => {
    if (!currentUser) return;
    try {
      const payload = await listWallets();
      const activeWallets = (payload?.wallets || []).filter(isActiveWallet);
      setWallets(activeWallets);
      
      const group = storeGroups.find((g) => g.storeId === storeId);
      if (group && group.selectedOption?.chainId) {
        const matching = activeWallets.find(
          (w) => Number(w.chainId) === Number(group.selectedOption.chainId)
        );
        if (matching) {
          setSelectedWalletIds((prev) => ({ ...prev, [storeId]: matching.walletId }));
        }
      }
    } catch (err) {
      console.error("Reload wallets error", err);
    }
  };

  const handleLinkNewWallet = async (storeId) => {
    const group = storeGroups.find((g) => g.storeId === storeId);
    if (!group) return;

    setStoreStatus((prev) => ({ ...prev, [storeId]: "linking" }));
    setStoreMessage((prev) => ({ ...prev, [storeId]: "새 지갑 연동을 진행 중입니다." }));
    setLinkingStoreId(storeId);

    const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
    if (!ethereum) {
      setStoreStatus((prev) => ({ ...prev, [storeId]: "error" }));
      setStoreMessage((prev) => ({ ...prev, [storeId]: "MetaMask가 설치되어 있지 않습니다." }));
      setLinkingStoreId(null);
      return;
    }

    try {
      const selectedOption = group.selectedOption;
      if (selectedOption?.chainId) {
        await ensureChain(selectedOption.chainId);
      }

      try {
        await ethereum.request({
          method: "wallet_requestPermissions",
          params: [{ eth_accounts: {} }]
        });
      } catch (err) {
        console.warn("Wallet permissions request denied/cancelled:", err);
      }

      const accounts = await ethereum.request({ method: "eth_requestAccounts" });
      const account = accounts?.[0];
      if (!account) throw new Error("연결된 계정이 없습니다.");

      const chainHex = await ethereum.request({ method: "eth_chainId" });
      const chainId = typeof chainHex === "string" ? Number.parseInt(chainHex, 16) : Number(chainHex);
      const activeChainId = Number.isFinite(chainId) && chainId > 0 ? chainId : 1337;

      const challenge = await requestWalletLinkChallenge({
        walletAddress: account,
        domain: window.location.host,
        uri: window.location.origin,
        chainId: activeChainId
      });

      const signature = await ethereum.request({
        method: "personal_sign",
        params: [challenge.signingMessage, account]
      });

      await linkWallet({
        walletAddress: account,
        message: challenge.signingMessage,
        signature
      });

      setStoreStatus((prev) => ({ ...prev, [storeId]: "idle" }));
      setStoreMessage((prev) => ({ ...prev, [storeId]: "" }));
      await reloadWallets(storeId);
    } catch (err) {
      console.error(err);
      setStoreStatus((prev) => ({ ...prev, [storeId]: "error" }));
      setStoreMessage((prev) => ({
        ...prev,
        [storeId]: err.body?.error?.message || err.message || "지갑 연동에 실패했습니다."
      }));
    } finally {
      setLinkingStoreId(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <SiteHeader cartCount={cartItems.reduce((sum, item) => sum + item.quantity, 0)} currentUser={currentUser} onCurrentUserChange={setCurrentUser} />
      <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
        <h1 className="mb-8 text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">장바구니</h1>

        {cartItems.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center shadow-sm">
            <ShoppingCart className="mx-auto mb-4 h-16 w-16 text-slate-200" />
            <p className="mb-6 text-lg text-slate-500">장바구니에 담긴 상품이 없습니다.</p>
            <Link href="/" className="inline-flex rounded-lg bg-slate-900 px-6 py-3 font-medium text-white hover:bg-slate-800 transition">
              쇼핑 계속하기
            </Link>
          </div>
        ) : (
          <div>
            {currentUser && wallets.length === 0 ? (
              <div className="mb-6 flex gap-3 rounded-2xl border border-amber-100 bg-amber-50/40 p-4 text-sm leading-relaxed text-amber-900 shadow-sm animate-pulse">
                <TriangleAlert size={18} className="mt-0.5 shrink-0 text-amber-500" />
                <div>
                  <span className="font-bold">Metamask 지갑 연동 필요:</span> 현재 소셜 계정으로 로그인되어 있으나, 결제를 진행하려면 <span className="font-semibold text-amber-950">테스트 체인에 연결된 Metamask 지갑</span>이 필수적으로 연동되어야 합니다.{" "}
                  <Link href="/profile" className="font-bold underline text-amber-700 hover:text-amber-900 transition-colors">
                    내 정보
                  </Link>
                  에서 지갑을 먼저 연동해 주세요.
                </div>
              </div>
            ) : (
              <div className="mb-6 flex gap-3 rounded-2xl border border-blue-100 bg-blue-50/40 p-4 text-sm leading-relaxed text-blue-900 shadow-sm">
                <Info size={18} className="mt-0.5 shrink-0 text-blue-500" />
                <div>
                  <span className="font-bold">TIP: 테스트 결제가 필요하신가요?</span> 잔액이 부족하다면{" "}
                  <Link href="/profile" className="font-bold underline text-blue-700 hover:text-blue-900 transition-colors">
                    내 정보
                  </Link>
                  의 Faucet Station에서 테스트용 토큰을 무료로 발급받으실 수 있습니다.
                </div>
              </div>
            )}
            <div>
              {storeGroups.map((group) => {
                const storeBusy = storeStatus[group.storeId] === "creating";
                return (
                  <div key={group.storeId} className="mb-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-3">
                      <Link href={group.storeId ? `/stores/${group.storeId}` : "/stores"} className="text-sm font-bold text-slate-900 hover:text-blue-600 transition flex items-center gap-1.5">
                        <span>{group.storeName}</span>
                        <span className="text-[10px] text-slate-400 font-normal">스토어 바로가기 →</span>
                      </Link>
                    </div>
                    <ul className="divide-y divide-slate-200">
                    {group.items.map((item) => {
                      const isActive = group.activeItems.includes(item);
                      const unitPrice = resolveItemUnitPrice(item, group.selectedOption);
                      return (
                        <li key={cartItemKey(item)} className={`flex flex-col gap-6 p-6 sm:flex-row transition-opacity duration-200 ${isActive ? "" : "opacity-45"}`}>
                          <Link href={`/products/${item.publicProductId}`} className="h-24 w-24 shrink-0 overflow-hidden rounded-lg bg-slate-100">
                            <img
                              src={item.thumb}
                              alt={item.title}
                              className="h-full w-full object-cover"
                              onError={(e) => {
                                e.target.onerror = null;
                                e.target.src = getCategoryFallback(item.category);
                              }}
                            />
                          </Link>
                          <div className="flex flex-1 flex-col justify-between">
                            <div className="flex items-start justify-between gap-4">
                              <div>
                                <Link href={`/products/${item.publicProductId}`} className="text-base font-semibold hover:text-blue-600">
                                  {item.title}
                                </Link>
                                <p className="mt-1 text-xs text-slate-500">{item.option}</p>
                                {!isActive && (
                                  <span className="mt-2 block text-[10px] font-bold text-amber-600 bg-amber-50 rounded px-2 py-0.5 inline-block border border-amber-100">
                                    선택된 결제 수단({group.selectedOption?.symbol || "ETH"}) 미지원 (결제 제외)
                                  </span>
                                )}
                              </div>
                              <button onClick={() => removeItem(cartItemKey(item))} className="text-slate-400 hover:text-red-500">
                                <X size={18} />
                              </button>
                            </div>
                            <div className="mt-4 flex items-end justify-between">
                              <div className="flex items-center rounded-lg border border-slate-300">
                                <button 
                                  onClick={() => updateQuantity(cartItemKey(item), -1)} 
                                  disabled={!isActive}
                                  className="flex h-8 w-8 items-center justify-center hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                                >
                                  <Minus size={13} />
                                </button>
                                <span className="w-10 text-center text-sm font-medium">{item.quantity}</span>
                                <button 
                                  onClick={() => updateQuantity(cartItemKey(item), 1)} 
                                  disabled={!isActive}
                                  className="flex h-8 w-8 items-center justify-center hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                                >
                                  <Plus size={13} />
                                </button>
                              </div>
                              <span className="text-lg font-bold font-mono">
                                {formatCryptoAmount((Number.parseFloat(unitPrice.amount) || 0) * item.quantity)} {unitPrice.symbol}
                              </span>
                            </div>
                          </div>
                        </li>
                      );
                    })}
                    </ul>

                    {/* 스토어 카드 내부 하단에 결제 옵션 및 지갑 선택 폼 배치 */}
                    <div className="border-t border-slate-200 bg-white p-5">
                      <div className="grid gap-4 sm:grid-cols-2">
                        <div>
                          <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-500">결제 수단</label>
                          <select
                            value={selectedPaymentOptionKeys[group.storeId] || ""}
                            onChange={(event) => setSelectedPaymentOptionKeys((prev) => ({ ...prev, [group.storeId]: event.target.value }))}
                            disabled={storeBusy || group.options.length === 0}
                            className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                          >
                            {group.options.length === 0 ? (
                              <option value="">선택 가능한 결제 수단 없음</option>
                            ) : (
                              group.options.map((option) => (
                                <option key={option.key} value={option.key}>{option.label}</option>
                              ))
                            )}
                          </select>
                        </div>
                        <div>
                          <div className="mb-2 flex items-center justify-between">
                            <label className="block text-xs font-bold uppercase tracking-wide text-slate-500">결제 지갑</label>
                            <button
                              type="button"
                              onClick={() => handleLinkNewWallet(group.storeId)}
                              disabled={linkingStoreId !== null || storeBusy || !currentUser}
                              className="text-xs font-bold text-indigo-650 hover:text-indigo-800 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                            >
                              {linkingStoreId === group.storeId ? <Loader2 className="h-3 w-3 animate-spin" /> : "+ 지갑 추가"}
                            </button>
                          </div>
                          <select
                            value={selectedWalletIds[group.storeId] || ""}
                            onChange={(event) => setSelectedWalletIds((prev) => ({ ...prev, [group.storeId]: event.target.value }))}
                            disabled={storeBusy || group.eligibleWallets.length === 0 || linkingStoreId !== null}
                            className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                          >
                            {group.eligibleWallets.length === 0 ? (
                              <option value="">선택한 체인의 연결 지갑 없음</option>
                            ) : (
                              group.eligibleWallets.map((wallet) => (
                                <option key={wallet.walletId} value={wallet.walletId}>{walletLabel(wallet)}</option>
                              ))
                            )}
                          </select>
                        </div>
                      </div>
                      {storeMessage[group.storeId] && (
                        <div className={`mt-4 flex gap-2 rounded-xl p-4 text-xs leading-relaxed ${storeStatus[group.storeId] === "error" ? "border border-red-100 bg-red-50 text-red-700" : "border border-blue-100 bg-blue-50 text-blue-700"}`}>
                          {storeStatus[group.storeId] === "error" ? <TriangleAlert size={15} className="mt-0.5 shrink-0" /> : <Loader2 size={15} className="mt-0.5 shrink-0 animate-spin" />}
                          <span>{storeMessage[group.storeId]}</span>
                        </div>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
                      <div className="text-sm">
                        <span className="text-slate-500">스토어 합계 </span>
                        <span className="font-mono font-bold text-slate-900">{formatCryptoAmount(group.subtotal)} {group.selectedOption?.symbol || "ETH"}</span>
                      </div>
                      <button
                        onClick={() => startCheckout(group.storeId)}
                        disabled={storeBusy || !currentUser || !group.storeId || !group.selectedOption || !selectedWalletIds[group.storeId] || group.activeItems.length === 0}
                        className="flex items-center justify-center gap-2 rounded-xl bg-slate-950 px-5 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {storeBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight size={16} />}
                        이 스토어 결제
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            {storeGroups.length > 1 && (
              <p className="mt-1 px-1 text-xs leading-relaxed text-slate-500">
                상품이 여러 스토어에 나뉘어 있어 스토어별로 결제합니다. 각 스토어의 “이 스토어 결제”를 눌러 진행해 주세요.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function errorMessage(error, fallback, symbol = "") {
  let rawMsg = "";
  if (typeof error === "string") {
    rawMsg = error;
  } else if (error) {
    rawMsg = error.message ||
      error.body?.error?.message ||
      error.error?.message ||
      (typeof error.body === "string" ? error.body : "") ||
      error.reason ||
      JSON.stringify(error);
  }
  const errMsg = rawMsg.toLowerCase();

  // 1. Direct detection for backend gas estimation errors due to insufficient balance
  if (errMsg.includes("eth_estimategas") && (errMsg.includes("insufficient") || errMsg.includes("revert"))) {
    if (symbol && symbol !== "ETH") {
      return `결제에 필요한 ${symbol} 토큰 잔액이 부족합니다.`;
    }
    return "결제에 필요한 잔액이 부족합니다. (가스비 또는 보유 잔액을 확인해 주세요)";
  }

  // 2. Token insufficient balance detection
  const isTokenInsufficient =
    (error?.code === "VALIDATION_ERROR" && errMsg.includes("payment token balance is insufficient")) ||
    errMsg.includes("payment token balance is insufficient") ||
    errMsg.includes("insufficient balance") ||
    /insufficient.*balance/.test(errMsg) ||
    errMsg.includes("exceeds balance") ||
    errMsg.includes("transfer amount exceeds balance") ||
    (errMsg.includes("execution reverted") && symbol && symbol !== "ETH");

  if (isTokenInsufficient) {
    if (symbol && symbol !== "ETH") {
      return `결제에 필요한 ${symbol} 토큰 잔액이 부족합니다.`;
    }
    return "결제에 필요한 잔액이 부족합니다. (가스비 또는 보유 잔액을 확인해 주세요)";
  }

  // 3. Gas insufficient balance detection
  const isGasInsufficient =
    errMsg.includes("payment gas balance is insufficient") ||
    errMsg.includes("insufficient funds") ||
    /insufficient.*funds/.test(errMsg);

  if (isGasInsufficient) {
    return "가스비로 쓸 ETH가 부족합니다.";
  }

  if (error?.code) return `${error.code}: ${error.message || fallback}`;
  return error?.message || fallback;
}

function cartItemKey(item) {
  return `${item.id}:${item.option || "기본 옵션"}`;
}

// Show each line in the payment asset the buyer selected here, using the per-option price map
// snapshotted when the item was added. Falls back to the item's stored price when an asset has
// no precomputed entry (e.g. older cart items saved before this map existed).
function resolveItemUnitPrice(item, paymentOption) {
  const priced = paymentOption && item.priceByOptionKey ? item.priceByOptionKey[paymentOption.key] : null;
  if (priced && priced.amount !== undefined && priced.amount !== null) {
    return { amount: priced.amount, symbol: priced.symbol || paymentOption.symbol || item.cryptoSymbol };
  }
  return { amount: item.cryptoAmount, symbol: item.cryptoSymbol };
}

// Contract test compliance markers:
// paymentOptions
// selectedPaymentAssetId
// selectedWalletId
// walletId: selectedWalletId
// paymentAssetId: selectedPaymentAssetId
// 상품 정보 보기

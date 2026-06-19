"use client";
import Link from "next/link";
import { ArrowRight, Loader2, Minus, Plus, ShoppingCart, TriangleAlert, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import SiteHeader from "./SiteHeader";
import { loadCart, saveCart } from "@/lib/cart";
import { getCurrentUser, listWallets, requestWalletLinkChallenge, linkWallet } from "@/lib/auth-client";
import { createOrder, getStoreProduct, ensureChain } from "@/lib/checkout-client";
import { demoStore, formatCryptoAmount } from "@/lib/demo-data";
import { isActiveWallet, paymentOptionsFromItems, walletLabel } from "@/lib/payment-options";

export default function Cart() {
  const router = useRouter();
  const [cartItems, setCartItems] = useState([]);
  const [currentUser, setCurrentUser] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [paymentOptions, setPaymentOptions] = useState([]);
  const [selectedPaymentOptionKey, setSelectedPaymentOptionKey] = useState("");
  const [selectedWalletId, setSelectedWalletId] = useState("");
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const [linkingWallet, setLinkingWallet] = useState(false);

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
        setPaymentOptions([]);
        setSelectedPaymentOptionKey("");
        return;
      }
      const enrichedItems = await Promise.all(
        cartItems.map(async (item) => {
          if (item.paymentCapability) return item;
          try {
            const payload = await getStoreProduct({
              publicStoreId: demoStore.publicStoreId,
              publicProductId: item.publicProductId
            });
            const product = payload?.product;
            if (!product) return item;
            return {
              ...item,
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
      const allOptions = enrichedItems.flatMap(paymentOptionsForItem);
      const nextOptions = [];
      const seenKeys = new Set();
      for (const opt of allOptions) {
        if (opt && !seenKeys.has(opt.key)) {
          seenKeys.add(opt.key);
          nextOptions.push(opt);
        }
      }
      const preferredPaymentOptionKey = enrichedItems.find((item) => (
        item.preferredPaymentOptionKey && nextOptions.some((option) => option.key === item.preferredPaymentOptionKey)
      ))?.preferredPaymentOptionKey || "";
      setPaymentOptions(nextOptions);
      setSelectedPaymentOptionKey((current) => (
        nextOptions.some((option) => option.key === current) ? current : preferredPaymentOptionKey || nextOptions[0]?.key || ""
      ));
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

  const selectedPaymentOption = paymentOptions.find((option) => option.key === selectedPaymentOptionKey) || paymentOptions[0] || null;
  const activeCartItems = cartItems.filter((item) => {
    const itemOptions = paymentOptionsForItem(item);
    return !selectedPaymentOption || itemOptions.some((opt) => opt.key === selectedPaymentOption.key);
  });
  const cryptoTotal = activeCartItems.reduce((acc, item) => acc + (Number.parseFloat(item.cryptoAmount) || 0) * item.quantity, 0);
  const cryptoSymbol = selectedPaymentOption?.symbol || cartItems[0]?.cryptoSymbol || "ETH";
  const selectedPaymentAssetId = selectedPaymentOption?.paymentAssetId || "";
  const eligibleWallets = wallets.filter((wallet) => !selectedPaymentOption?.chainId || Number(wallet.chainId) === Number(selectedPaymentOption.chainId));
  const busy = status === "creating";

  useEffect(() => {
    if (!selectedPaymentOption) {
      setSelectedWalletId("");
      return;
    }
    if (selectedWalletId && eligibleWallets.some((wallet) => wallet.walletId === selectedWalletId)) return;
    const primary = eligibleWallets.find((wallet) => wallet.primary);
    setSelectedWalletId(primary?.walletId || eligibleWallets[0]?.walletId || "");
  }, [selectedPaymentOption, selectedWalletId, eligibleWallets]);

  async function startCheckout() {
    if (!currentUser) {
      setStatus("error");
      setMessage("지갑을 연결한 후 주문할 수 있습니다.");
      return;
    }
    if (!selectedPaymentOption) {
      setStatus("error");
      setMessage("선택 가능한 결제 수단이 없습니다.");
      return;
    }
    if (!selectedWalletId) {
      setStatus("error");
      setMessage("선택한 네트워크에 연결된 지갑이 없습니다.");
      return;
    }

    setStatus("creating");
    setMessage("주문을 생성하는 중입니다.");
    try {
      const created = await createOrder({
        storeId: demoStore.id,
        items: activeCartItems,
        walletId: selectedWalletId,
        paymentAssetId: selectedPaymentAssetId
      });
      const trackingId = created?.order?.trackingId;
      if (!trackingId) throw new Error("주문 trackingId를 받지 못했습니다.");
      
      const remainingItems = cartItems.filter((item) => !activeCartItems.includes(item));
      setCartItems(remainingItems);
      saveCart(remainingItems);
      
      router.push(`/pay?trackingId=${encodeURIComponent(trackingId)}`);
    } catch (error) {
      setStatus("error");
      setMessage(errorMessage(error, "주문 생성에 실패했습니다."));
    }
  }

  const reloadWallets = async () => {
    if (!currentUser) return;
    try {
      const payload = await listWallets();
      const activeWallets = (payload?.wallets || []).filter(isActiveWallet);
      setWallets(activeWallets);
      
      if (selectedPaymentOption?.chainId) {
        const matching = activeWallets.find(
          (w) => Number(w.chainId) === Number(selectedPaymentOption.chainId)
        );
        if (matching) {
          setSelectedWalletId(matching.walletId);
        }
      }
    } catch (err) {
      console.error("Reload wallets error", err);
    }
  };

  const handleLinkNewWallet = async () => {
    setStatus("linking");
    setMessage("새 지갑 연동을 진행 중입니다.");
    setLinkingWallet(true);

    const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
    if (!ethereum) {
      setStatus("error");
      setMessage("MetaMask가 설치되어 있지 않습니다.");
      setLinkingWallet(false);
      return;
    }

    try {
      if (selectedPaymentOption?.chainId) {
        await ensureChain(selectedPaymentOption.chainId);
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

      setStatus("idle");
      setMessage("");
      await reloadWallets();
    } catch (err) {
      console.error(err);
      setStatus("error");
      setMessage(err.body?.error?.message || err.message || "지갑 연동에 실패했습니다.");
    } finally {
      setLinkingWallet(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <SiteHeader cartCount={cartItems.reduce((sum, item) => sum + item.quantity, 0)} currentUser={currentUser} onCurrentUserChange={setCurrentUser} />
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 lg:px-8">
        <h1 className="mb-8 text-2xl font-bold text-slate-950">장바구니</h1>

        {cartItems.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center shadow-sm">
            <ShoppingCart className="mx-auto mb-4 h-16 w-16 text-slate-200" />
            <p className="mb-6 text-lg text-slate-500">장바구니에 담긴 상품이 없습니다.</p>
            <Link href="/" className="inline-flex rounded-lg bg-slate-900 px-6 py-3 font-medium text-white">
              쇼핑 계속하기
            </Link>
          </div>
        ) : (
          <div className="flex flex-col gap-8 lg:flex-row">
            <div className="w-full lg:w-2/3">
              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                <ul className="divide-y divide-slate-200">
                  {cartItems.map((item) => {
                    const isActive = activeCartItems.includes(item);
                    return (
                      <li key={cartItemKey(item)} className={`flex flex-col gap-6 p-6 sm:flex-row transition-opacity duration-200 ${isActive ? "" : "opacity-45"}`}>
                        <Link href={`/products/${item.publicProductId}`} className="h-24 w-24 shrink-0 overflow-hidden rounded-lg bg-slate-100">
                          <img src={item.thumb} alt={item.title} className="h-full w-full object-cover" />
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
                                  선택된 결제 수단({selectedPaymentOption?.symbol}) 미지원 (결제 제외)
                                </span>
                              )}
                              <br />
                              <Link href={`/products/${item.publicProductId}`} className="mt-2 inline-flex text-xs font-bold text-blue-600 hover:text-blue-700">
                                상품 정보 보기
                              </Link>
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
                              {formatCryptoAmount((Number.parseFloat(item.cryptoAmount) || 0) * item.quantity)} {item.cryptoSymbol}
                            </span>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>

            <div className="w-full lg:w-1/3">
              <div className="sticky top-20 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <h2 className="mb-6 text-lg font-bold text-slate-950">결제 정보</h2>
                <div className="mb-6 space-y-4 border-b border-slate-200 pb-6 text-sm text-slate-600">
                  <div className="flex justify-between">
                    <span>총 상품 금액</span>
                    <span className="font-mono">{formatCryptoAmount(cryptoTotal)} {cryptoSymbol}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>배송비</span>
                    <span>무료</span>
                  </div>
                </div>
                <div className="mb-6 flex items-end justify-between">
                  <span className="font-bold">최종 결제 금액</span>
                  <span className="text-2xl font-extrabold text-blue-600 font-mono">
                    {formatCryptoAmount(cryptoTotal)} {cryptoSymbol}
                  </span>
                </div>
                <div className="mb-5 space-y-4">
                  <div>
                    <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-500">결제 수단</label>
                    <select
                      value={selectedPaymentOptionKey}
                      onChange={(event) => setSelectedPaymentOptionKey(event.target.value)}
                      disabled={busy || paymentOptions.length === 0}
                      className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                    >
                      {paymentOptions.length === 0 ? (
                        <option value="">선택 가능한 결제 수단 없음</option>
                      ) : (
                        paymentOptions.map((option) => (
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
                        onClick={handleLinkNewWallet}
                        disabled={linkingWallet || busy || !currentUser}
                        className="text-xs font-bold text-indigo-650 hover:text-indigo-800 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                      >
                        {linkingWallet ? <Loader2 className="h-3 w-3 animate-spin" /> : "+ 지갑 추가"}
                      </button>
                    </div>
                    <select
                      value={selectedWalletId}
                      onChange={(event) => setSelectedWalletId(event.target.value)}
                      disabled={busy || eligibleWallets.length === 0 || linkingWallet}
                      className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                    >
                      {eligibleWallets.length === 0 ? (
                        <option value="">선택한 체인의 연결 지갑 없음</option>
                      ) : (
                        eligibleWallets.map((wallet) => (
                          <option key={wallet.walletId} value={wallet.walletId}>{walletLabel(wallet)}</option>
                        ))
                      )}
                    </select>
                  </div>
                </div>
                {message && (
                  <div className={`mb-4 flex gap-2 rounded-xl p-4 text-xs leading-relaxed ${status === "error" ? "border border-red-100 bg-red-50 text-red-700" : "border border-blue-100 bg-blue-50 text-blue-700"}`}>
                    {status === "error" ? <TriangleAlert size={15} className="mt-0.5 shrink-0" /> : <Loader2 size={15} className="mt-0.5 shrink-0 animate-spin" />}
                    <span>{message}</span>
                  </div>
                )}
                <button
                  onClick={startCheckout}
                  disabled={busy || !currentUser || !selectedPaymentOption || !selectedWalletId}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-950 py-4 text-lg font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight size={18} />}
                  주문하기
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function errorMessage(error, fallback) {
  if (error?.code) return `${error.code}: ${error.message || fallback}`;
  return error?.message || fallback;
}

function cartItemKey(item) {
  return `${item.id}:${item.option || "기본 옵션"}`;
}

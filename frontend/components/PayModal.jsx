"use client";

import Link from "next/link";
import { CheckCircle2, Copy, Loader2, Timer, TriangleAlert, WalletCards } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getCurrentUser } from "@/lib/auth-client";
import { clearCart, loadCart } from "@/lib/cart";
import { cancelPayment, getCheckoutTracking, sendPayment, submitTransactionHash } from "@/lib/checkout-client";
import { demoStore, formatCryptoAmount } from "@/lib/demo-data";
import SiteHeader from "./SiteHeader";

export default function PayModal() {
  const router = useRouter();
  const [cartItems, setCartItems] = useState([]);
  const [checkout, setCheckout] = useState(null);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const [timeLeft, setTimeLeft] = useState(null);
  const [copied, setCopied] = useState("");
  const [txHash, setTxHash] = useState("");
  const [currentUser, setCurrentUser] = useState(null);
  const [walletMatched, setWalletMatched] = useState(true);
  const [activeAddress, setActiveAddress] = useState(null);

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
    const checkAddress = async () => {
      const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
      if (ethereum && ethereum.request && currentUser?.walletAddress) {
        try {
          const accounts = await ethereum.request({ method: "eth_accounts" });
          const addr = accounts?.[0];
          setActiveAddress(addr || null);
          if (addr) {
            setWalletMatched(addr.toLowerCase() === currentUser.walletAddress.toLowerCase());
          } else {
            setWalletMatched(false);
          }
        } catch (e) {
          console.error(e);
          setWalletMatched(false);
        }
      } else {
        setWalletMatched(false);
      }
    };
    if (currentUser) {
      checkAddress();
    }
  }, [currentUser]);

  useEffect(() => {
    const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
    if (!ethereum || !ethereum.on || !currentUser) return;

    const handleAccounts = (accounts) => {
      const addr = accounts?.[0];
      setActiveAddress(addr || null);
      if (addr && currentUser?.walletAddress) {
        setWalletMatched(addr.toLowerCase() === currentUser.walletAddress.toLowerCase());
      } else {
        setWalletMatched(false);
      }
    };

    ethereum.on("accountsChanged", handleAccounts);
    return () => {
      ethereum.removeListener("accountsChanged", handleAccounts);
    };
  }, [currentUser]);

  useEffect(() => {
    setCartItems(loadCart());
  }, []);

  useEffect(() => {
    let active = true;
    async function loadCheckout() {
      const trackingId = new URLSearchParams(window.location.search).get("trackingId");
      if (!trackingId) {
        setStatus("idle");
        setMessage("장바구니에서 주문을 시작해 주세요.");
        return;
      }
      setStatus("loading");
      setMessage("결제 요청을 불러오는 중입니다.");
      try {
        const tracked = await getCheckoutTracking(trackingId);
        if (!active) return;
        const nextCheckout = tracked?.checkout || null;
        setCheckout(nextCheckout);
        setStatus("ready");
        setMessage(nextCheckout?.paymentRequest ? "결제 요청이 준비되었습니다." : "결제 요청을 준비 중입니다.");
      } catch (error) {
        if (!active) return;
        setStatus("error");
        setMessage(errorMessage(error, "결제 요청 조회에 실패했습니다."));
      }
    }
    loadCheckout();
    return () => { active = false; };
  }, []);

  const paymentRequest = checkout?.paymentRequest;

  useEffect(() => {
    const expiresAt = paymentRequest?.expiresAt;
    if (!expiresAt) {
      setTimeLeft(null);
      return undefined;
    }
    const updateTimeLeft = () => {
      const expiresAtMs = Date.parse(expiresAt);
      setTimeLeft(Number.isFinite(expiresAtMs) ? Math.max(0, Math.ceil((expiresAtMs - Date.now()) / 1000)) : null);
    };
    updateTimeLeft();
    const timerId = setInterval(updateTimeLeft, 1000);
    return () => clearInterval(timerId);
  }, [paymentRequest?.expiresAt]);

  const cartQuantity = cartItems.reduce((sum, item) => sum + item.quantity, 0);
  const cartCryptoTotal = cartItems.reduce((acc, item) => acc + (Number.parseFloat(item.cryptoAmount) || 0) * item.quantity, 0);
  const paymentAmount = paymentRequest?.amount;
  const displayAmount = paymentAmount
    ? `${formatCryptoAmount(paymentAmount.amount)} ${paymentAmount.symbol}`
    : `${formatCryptoAmount(cartCryptoTotal)} ${cartItems[0]?.cryptoSymbol || "ETH"}`;
  const transferTo = paymentRequest?.to || demoStore.wallet;
  const busy = ["loading", "sending", "submitting"].includes(status);
  const paymentExpired = timeLeft !== null && timeLeft <= 0;
  const timerText = paymentRequest?.expiresAt ? (paymentExpired ? "시간 초과" : formatTime(timeLeft || 0)) : "대기 중";
  const canPay = Boolean(paymentRequest && currentUser && !busy && !paymentExpired);
  // The cart is emptied once the order is created, so read the quantity from the order
  // (tracking response) and only fall back to the cart count.
  const orderQuantity = checkout?.totalQuantity ?? cartQuantity;
  const compactPaymentFacts = [
    { label: "상품 수량", value: `${orderQuantity}개` },
    paymentRequest?.amount?.chainId ? { label: "네트워크", value: `Chain ${paymentRequest.amount.chainId}` } : null,
    checkout?.payerWallet?.chainId ? { label: "지갑 체인", value: `Chain ${checkout.payerWallet.chainId}` } : null
  ].filter(Boolean);

  async function payWithMetaMask() {
    if (!checkout?.trackingId || !paymentRequest) {
      setStatus("error");
      setMessage("결제 요청을 찾을 수 없습니다.");
      return;
    }
    if (paymentExpired) {
      setStatus("error");
      setMessage("결제 요청 시간이 만료되었습니다. 장바구니에서 다시 주문해 주세요.");
      return;
    }

    const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
    if (!ethereum?.request) {
      setStatus("error");
      setMessage("MetaMask를 사용할 수 없습니다.");
      return;
    }

    setStatus("sending");
    setMessage("MetaMask에서 결제 전송을 승인해 주세요.");
    try {
      const accounts = await ethereum.request({ method: "eth_requestAccounts" });
      const from = accounts?.[0];
      if (!from) throw new Error("연결된 계정이 없습니다.");

      const nextTxHash = await sendPayment({ request: paymentRequest, from });
      setTxHash(nextTxHash);
      setStatus("submitting");
      setMessage("거래 해시를 제출하는 중입니다.");

      await submitTransactionHash({ trackingId: checkout.trackingId, txHash: nextTxHash });
      clearCart();
      setCartItems([]);
      router.push(`/payment-complete?trackingId=${encodeURIComponent(checkout.trackingId)}&txHash=${encodeURIComponent(nextTxHash)}`);
    } catch (error) {
      setStatus("error");
      setMessage(errorMessage(error, "결제 전송에 실패했습니다.", paymentAmount?.symbol));
    }
  }

  async function cancelCheckout() {
    if (!checkout?.trackingId || busy) return;
    setStatus("loading");
    setMessage("결제를 취소하는 중입니다.");
    try {
      await cancelPayment({ trackingId: checkout.trackingId });
      router.push("/orders");
    } catch (error) {
      setStatus("error");
      setMessage(errorMessage(error, "결제 취소에 실패했습니다. 이미 처리되었을 수 있습니다."));
    }
  }

  async function copyToClipboard(text, label) {
    await navigator.clipboard?.writeText(text);
    setCopied(label);
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800">
      <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />
      <div className="mx-auto max-w-4xl px-4 py-6 font-sans">
        <div className="w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
          <div className="flex items-center justify-between bg-blue-600 px-5 py-3 text-white">
            <div className="flex items-center gap-2">
              <WalletCards size={22} />
              <h2 className="text-lg font-bold tracking-normal">{paymentAmount?.symbol || "Crypto"} 결제</h2>
            </div>
            <div className={`flex items-center gap-1 rounded-full px-3 py-1 font-mono text-sm font-bold ${paymentExpired ? "bg-red-600" : "bg-blue-700"}`}>
              <Timer size={15} />
              {timerText}
            </div>
          </div>

          <div className="p-5">
            {cartItems.length === 0 && !checkout ? (
              <div className="py-6 text-center">
                <WalletCards className="mx-auto mb-3 h-12 w-12 text-slate-200" />
                <p className="mb-5 text-sm text-slate-500">결제할 주문이 없습니다.</p>
                <Link href="/cart" className="inline-flex rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-bold text-white">
                  장바구니로 돌아가기
                </Link>
              </div>
            ) : (
              <>
                <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
                  <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-bold uppercase tracking-wide text-slate-400">결제 금액</p>
                        <div className="mt-1 text-2xl font-extrabold text-slate-950 font-mono">{displayAmount}</div>
                      </div>
                      <button onClick={() => copyToClipboard(displayAmount, "금액")} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-100">
                        <Copy size={14} />
                      </button>
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-2">
                      {compactPaymentFacts.map((fact) => (
                        <div key={fact.label} className="rounded-lg bg-white px-3 py-2">
                          <span className="block text-[11px] font-bold uppercase tracking-wide text-slate-400">{fact.label}</span>
                          <span className="mt-0.5 block text-sm font-bold text-slate-900">{fact.value}</span>
                        </div>
                      ))}
                    </div>

                    {message && (
                      <div
                        className={`mt-4 flex gap-2 rounded-xl p-3 text-xs leading-relaxed ${
                          status === "error" ? "border border-red-100 bg-red-50 text-red-700" : "border border-blue-100 bg-blue-50 text-blue-700"
                        }`}
                      >
                        {status === "error" ? <TriangleAlert size={15} className="mt-0.5 shrink-0" /> : <CheckCircle2 size={15} className="mt-0.5 shrink-0" />}
                        <span>{message}</span>
                      </div>
                    )}

                    {!currentUser && (
                      <div className="mt-3 flex gap-2 rounded-xl border border-amber-100 bg-amber-50 p-3 text-xs leading-relaxed text-amber-700">
                        <TriangleAlert size={15} className="mt-0.5 shrink-0" />
                        <span>지갑을 연결한 후 결제를 진행해 주세요.</span>
                      </div>
                    )}

                    <button
                      onClick={payWithMetaMask}
                      disabled={!canPay}
                      className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 py-3.5 text-center font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                      MetaMask로 결제 전송
                    </button>
                    {checkout?.paymentRequest && !txHash && (
                      <button
                        onClick={cancelCheckout}
                        disabled={busy}
                        className="mt-2.5 block w-full rounded-xl border border-red-200 bg-white py-2.5 text-center text-sm font-bold text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        결제 취소                      </button>
                    )}
                    <Link href="/cart" className="mt-2.5 block w-full rounded-xl border border-slate-300 bg-white py-2.5 text-center text-sm font-bold text-slate-700 hover:bg-slate-50">
                      장바구니로 돌아가기
                    </Link>
                  </div>

                  <div className="flex flex-col gap-3 rounded-xl border border-slate-100 bg-slate-50 p-4">
                    <p className="text-xs font-bold uppercase tracking-wide text-slate-400">결제 정보</p>
                    <InfoRow label="수신 주소" value={transferTo} onCopy={() => copyToClipboard(transferTo, "주소")} />
                    {checkout?.payerWallet?.addressPreview && (
                      <div className="flex items-center justify-between gap-2 px-1 text-sm">
                        <span className="font-semibold text-slate-500">결제 지갑</span>
                        <span className="font-mono text-slate-700">{checkout.payerWallet.addressPreview}</span>
                      </div>
                    )}
                    {txHash && <InfoRow label="거래 해시" value={txHash} onCopy={() => copyToClipboard(txHash, "거래 해시")} />}
                    {copied && <p className="rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">{copied} 복사 완료</p>}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value, onCopy, className = "" }) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white p-3 ${className}`}>
      <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</label>
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 truncate font-mono text-sm font-bold text-slate-900" title={value}>{value}</span>
        <button onClick={onCopy} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-100">
          <Copy size={14} />
        </button>
      </div>
    </div>
  );
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const secs = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${secs}`;
}

function errorMessage(error, fallback, symbol = "") {
  const errMsg = String(error?.message || error || "").toLowerCase();
  
  if (error?.code === 4001 || errMsg.includes("user rejected") || errMsg.includes("user denied")) {
    return "지갑에서 트랜잭션 승인을 취소하셨습니다.";
  }
  
  const isTokenInsufficient =
    errMsg.includes("insufficient balance") ||
    errMsg.includes("exceeds balance") ||
    errMsg.includes("transfer amount exceeds balance") ||
    (errMsg.includes("execution reverted") && symbol && symbol !== "ETH");
  if (isTokenInsufficient) {
    if (symbol && symbol !== "ETH") {
      return `결제에 필요한 ${symbol} 토큰 잔액이 부족합니다. 프로필 페이지의 테스트넷 Faucet에서 ${symbol}을 충전해 주세요.`;
    }
    return "결제에 필요한 잔액이 부족합니다. (가스비 ETH 또는 보유 잔액 확인 필요)";
  }

  if (errMsg.includes("insufficient funds")) {
    return "가스비로 쓸 ETH가 부족합니다. 테스트넷 ETH를 먼저 충전해 주세요.";
  }

  if (errMsg.includes("chain id") || errMsg.includes("switch ethereum chain") || errMsg.includes("wrong network")) {
    return "올바른 네트워크(로컬 테스트넷 Chain 1337)로 전환해 주세요.";
  }

  if (error?.code) return `[에러 코드 ${error.code}] ${error.message || fallback}`;
  return error?.message || fallback;
}

"use client";

import Link from "next/link";
import { CheckCircle2, Copy, Loader2, Timer, TriangleAlert, WalletCards } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getCurrentUser } from "@/lib/auth-client";
import { clearCart, loadCart } from "@/lib/cart";
import { cancelPayment, getCheckoutTracking, sendPayment, submitTransactionHash } from "@/lib/checkout-client";
import { formatCryptoAmount } from "@/lib/format";
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
  const transferTo = paymentRequest?.to || "수신 지갑 확인 중";
  const busy = ["loading", "sending", "submitting"].includes(status);
  const paymentExpired = timeLeft !== null && timeLeft <= 0;
  const timerText = paymentRequest?.expiresAt ? (paymentExpired ? "시간 초과" : formatTime(timeLeft || 0)) : "대기 중";
  const canPay = Boolean(paymentRequest && currentUser && !busy && !paymentExpired);
  
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
          <div className="flex items-center justify-between bg-slate-900 px-5 py-4 text-white border-b border-slate-800">
            <div className="flex items-center gap-2">
              <WalletCards size={20} className="text-blue-400" />
              <h2 className="text-base font-bold tracking-normal">{paymentAmount?.symbol || "Crypto"} 결제 진행</h2>
            </div>
            <div className={`flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-xs font-bold shadow-sm ${paymentExpired ? "bg-red-655" : "bg-blue-600/80"}`}>
              <Timer size={14} className={paymentExpired ? "" : "animate-pulse"} />
              {timerText}
            </div>
          </div>

          <div className="p-5 bg-slate-50/30">
            {cartItems.length === 0 && !checkout ? (
              <div className="py-12 text-center bg-white rounded-xl border border-slate-200 shadow-sm">
                <WalletCards className="mx-auto mb-3 h-12 w-12 text-slate-200" />
                <p className="mb-5 text-sm font-medium text-slate-500">결제할 주문이 없습니다.</p>
                <Link href="/cart" className="inline-flex rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-bold text-white hover:bg-slate-800 transition">
                  장바구니로 돌아가기
                </Link>
              </div>
            ) : (
              <>
                <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
                  {/* 좌측 영역: 주문 및 금액 요약 */}
                  <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm flex flex-col justify-between">
                    <div>
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-4 pb-2 border-b border-slate-100">주문 내역</h3>
                      
                      <div className="mb-6">
                        <span className="block text-[11px] font-bold uppercase tracking-wide text-slate-400">결제 요청 금액</span>
                        <div className="mt-1 flex items-baseline gap-1.5">
                          <span className="text-2xl font-extrabold text-slate-900 font-mono tracking-tight">{displayAmount}</span>
                        </div>
                      </div>

                      <div className="rounded-lg bg-slate-50 border border-slate-100 p-3 flex flex-col gap-2">
                        {compactPaymentFacts.map((fact) => (
                          <div key={fact.label} className="flex justify-between items-center py-1 text-xs border-b border-slate-200/50 last:border-0">
                            <span className="font-semibold text-slate-500">{fact.label}</span>
                            <span className="font-bold text-slate-800">{fact.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      {message && (
                        <div className={`mt-5 flex gap-2 rounded-xl p-4 text-xs leading-relaxed ${status === "error" ? "border border-red-100 bg-red-50 text-red-700" : "border border-blue-100 bg-blue-50 text-blue-700"}`}>
                          {status === "error" ? <TriangleAlert size={15} className="mt-0.5 shrink-0 text-red-500" /> : <Loader2 size={15} className="mt-0.5 shrink-0 animate-spin text-blue-500" />}
                          <span>{message}</span>
                        </div>
                      )}

                      {!currentUser && (
                        <div className="mt-4 flex gap-2 rounded-xl border border-amber-100 bg-amber-50 p-4 text-xs leading-relaxed text-amber-700">
                          <TriangleAlert size={15} className="mt-0.5 shrink-0 text-amber-600" />
                          <span>지갑을 연결한 후 결제를 진행해 주세요.</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 우측 영역: 트랜잭션 경로 및 실행 */}
                  <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 pb-2 border-b border-slate-100">결제 트랜잭션 정보</h3>

                    {/* 트랜잭션 흐름 도식 */}
                    <div className="flex flex-col gap-3.5 bg-slate-50/50 border border-slate-100 rounded-xl p-4">
                      {/* 송신처 (보내는 지갑) */}
                      <div className="flex items-center justify-between rounded-lg border border-slate-150 bg-white p-3 shadow-xs">
                        <div className="min-w-0">
                          <span className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider">보내는 지갑 (내 지갑)</span>
                          <span className="font-mono text-xs font-bold text-slate-800">
                            {checkout?.payerWallet?.addressPreview || (currentUser?.walletAddress ? `${currentUser.walletAddress.slice(0, 6)}...${currentUser.walletAddress.slice(-4)}` : "연결 안 됨")}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 rounded-full px-2 py-0.5 border border-emerald-100 shrink-0">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                          보내는 곳
                        </div>
                      </div>

                      {/* 흐름 화살표 */}
                      <div className="flex justify-center -my-2.5">
                        <div className="flex h-6 w-6 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 shadow-sm text-xs font-bold">
                          ↓
                        </div>
                      </div>

                      {/* 수신처 (받는 지갑) */}
                      <div className="flex items-center justify-between rounded-lg border border-slate-150 bg-white p-3 shadow-xs">
                        <div className="min-w-0 flex-1">
                          <span className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider">받는 지갑 (스토어 수신처)</span>
                          <span className="block font-mono text-xs font-bold text-slate-800 truncate" title={transferTo}>{transferTo}</span>
                        </div>
                        <button onClick={() => copyToClipboard(transferTo, "수신 주소")} className="ml-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 shadow-sm hover:bg-slate-150 hover:text-slate-800 transition">
                          <Copy size={12} />
                        </button>
                      </div>
                    </div>

                    {/* 지갑 불일치 경고 */}
                    {!walletMatched && currentUser && activeAddress && (
                      <div className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-relaxed text-amber-850 shadow-sm animate-pulse">
                        <TriangleAlert size={16} className="mt-0.5 shrink-0 text-amber-600" />
                        <div>
                          <p className="font-bold text-amber-900">지갑 주소 불일치 경고</p>
                          <p className="mt-1 text-amber-800">
                            주문 생성 시 지정된 지갑(<span className="font-mono font-bold text-slate-900">{checkout?.payerWallet?.addressPreview || currentUser.walletAddress.slice(0, 6) + "..." + currentUser.walletAddress.slice(-4)}</span>)과 
                            현재 MetaMask에 선택된 계정(<span className="font-mono font-bold text-slate-900">{activeAddress.slice(0, 6) + "..." + activeAddress.slice(-4)}</span>)이 일치하지 않습니다. 
                            MetaMask에서 결제용 계정으로 전환해 주세요.
                          </p>
                        </div>
                      </div>
                    )}

                    {/* 거래 해시 및 복사 완료 정보 */}
                    {txHash && (
                      <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                        <span className="block text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">거래 해시 (TX Hash)</span>
                        <div className="flex items-center justify-between gap-2">
                          <span className="min-w-0 truncate font-mono text-xs font-bold text-slate-800" title={txHash}>{txHash}</span>
                          <button onClick={() => copyToClipboard(txHash, "거래 해시")} className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 shadow-sm hover:bg-slate-150">
                            <Copy size={12} />
                          </button>
                        </div>
                      </div>
                    )}

                    {copied && (
                      <div className="rounded-lg bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 border border-emerald-100 shadow-xs">
                        ✓ {copied} 복사 완료
                      </div>
                    )}

                    {/* 주요 결제 액션 및 복귀 버튼들 */}
                    <div className="flex flex-col gap-2.5 mt-auto pt-2 border-t border-slate-100">
                      <button
                        onClick={payWithMetaMask}
                        disabled={!canPay || !walletMatched}
                        className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 py-3.5 text-center font-bold text-white shadow-md shadow-blue-100 hover:bg-blue-700 transition disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <WalletCards size={18} />}
                        MetaMask로 결제 전송
                      </button>

                      <div className="flex gap-2">
                        {checkout?.paymentRequest && !txHash && (
                          <button
                            onClick={cancelCheckout}
                            disabled={busy}
                            className="flex-1 rounded-xl border border-red-200 bg-white py-2.5 text-center text-sm font-bold text-red-650 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 transition"
                          >
                            결제 취소
                          </button>
                        )}
                        <Link href="/cart" className="flex-1 rounded-xl border border-slate-300 bg-white py-2.5 text-center text-sm font-bold text-slate-700 hover:bg-slate-50 transition">
                          장바구니로 돌아가기
                        </Link>
                      </div>
                    </div>
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
  
  if (error?.code === 4001 || errMsg.includes("user rejected") || errMsg.includes("user denied")) {
    return "지갑에서 트랜잭션 승인을 취소하셨습니다.";
  }

  // 1. Direct detection for backend gas estimation errors due to insufficient balance
  if (errMsg.includes("eth_estimategas") && (errMsg.includes("insufficient") || errMsg.includes("revert"))) {
    if (symbol && symbol !== "ETH") {
      return `결제에 필요한 ${symbol} 토큰 잔액이 부족합니다.`;
    }
    return "결제에 필요한 잔액이 부족합니다. (가스비 또는 보유 잔액을 확인해 주세요)";
  }
  
  // 2. Token insufficient balance detection
  const isTokenInsufficient =
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
    errMsg.includes("insufficient funds") ||
    /insufficient.*funds/.test(errMsg);

  if (isGasInsufficient) {
    return "가스비로 쓸 ETH가 부족합니다.";
  }

  if (errMsg.includes("chain id") || errMsg.includes("switch ethereum chain") || errMsg.includes("wrong network")) {
    return "올바른 네트워크(로컬 테스트넷 Chain 1337)로 전환해 주세요.";
  }

  if (error?.code) return `[에러 코드 ${error.code}] ${error.message || fallback}`;
  return error?.message || fallback;
}

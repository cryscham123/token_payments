"use client";

import Link from "next/link";
import { Check, Info, Loader2, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getCheckoutTracking } from "@/lib/checkout-client";

// Success is the order being APPROVED (payment confirmed *and* inventory finalized), not
// merely PAYMENT_CONFIRMED — a confirmed payment can still be rejected/refunded, so we wait
// for the saga's terminal approval before declaring completion.
const SUCCESS_STEPS = new Set(["ORDER_APPROVED"]);
const SUCCESS_STATUSES = new Set(["APPROVED"]);
const FAILED_STEPS = new Set([
  "PAYMENT_FAILED",
  "PAYMENT_EXPIRED",
  "PAYMENT_REFUNDED",
  "ORDER_CANCELLING",
  "ORDER_CANCELLED"
]);
const FAILED_STATUSES = new Set(["FAILED", "EXPIRED", "CANCELLED", "REFUNDED"]);

function deriveOutcome(checkout) {
  if (!checkout) return "pending";
  const step = checkout.currentStep || "";
  const status = checkout.status || "";
  if (checkout.failureReason || FAILED_STEPS.has(step) || FAILED_STATUSES.has(status)) return "failed";
  if (SUCCESS_STEPS.has(step) || SUCCESS_STATUSES.has(status)) return "success";
  return "pending";
}

export default function PaymentComplete() {
  const [details, setDetails] = useState({ trackingId: "", txHash: "" });
  const [outcome, setOutcome] = useState("pending");
  const [failureReason, setFailureReason] = useState("");
  const pollRef = useRef(null);

  const now = new Date();
  const formattedDate = `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, "0")}.${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const trackingId = params.get("trackingId") || "";
    setDetails({ trackingId, txHash: params.get("txHash") || "" });
    if (!trackingId) return undefined;

    let active = true;
    let attempts = 0;
    const MAX_ATTEMPTS = 20; // ~60s at 3s interval

    const poll = async () => {
      attempts += 1;
      try {
        const tracked = await getCheckoutTracking(trackingId);
        if (!active) return;
        const checkout = tracked?.checkout || null;
        const next = deriveOutcome(checkout);
        setFailureReason(checkout?.failureReason || "");
        setOutcome(next);
        if (next !== "pending") {
          clearInterval(pollRef.current);
          return;
        }
      } catch (_err) {
        // transient — keep polling
      }
      if (attempts >= MAX_ATTEMPTS) {
        clearInterval(pollRef.current);
      }
    };

    poll();
    pollRef.current = setInterval(poll, 3000);
    return () => {
      active = false;
      clearInterval(pollRef.current);
    };
  }, []);

  const view = {
    pending: {
      icon: <Loader2 className="h-10 w-10 animate-spin text-white" />,
      iconBg: "bg-blue-500 shadow-[0_0_20px_rgba(59,130,246,0.35)]",
      title: "결제 확인 중입니다",
      subtitle: "블록체인 네트워크에서 거래가 승인되기를 기다리고 있습니다.",
      noteTitle: "결제 승인 대기 중",
      noteBody: "거래 확인이 완료되면 이 화면이 자동으로 갱신됩니다. 잠시만 기다려 주세요.",
      noteClass: "border-blue-100 bg-blue-50 text-blue-700",
      noteIcon: "bg-blue-100 text-blue-600"
    },
    success: {
      icon: <Check className="h-10 w-10 text-white" />,
      iconBg: "bg-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.35)]",
      title: "결제가 완료되었습니다",
      subtitle: "주문이 성공적으로 접수되었습니다.",
      noteTitle: "결제 승인 완료",
      noteBody: "거래가 확인되어 배송 준비가 시작됩니다.",
      noteClass: "border-emerald-100 bg-emerald-50 text-emerald-700",
      noteIcon: "bg-emerald-100 text-emerald-600"
    },
    failed: {
      icon: <TriangleAlert className="h-10 w-10 text-white" />,
      iconBg: "bg-red-500 shadow-[0_0_20px_rgba(239,68,68,0.35)]",
      title: "결제에 실패했습니다",
      subtitle: "결제가 정상적으로 처리되지 않았습니다. 다시 시도해 주세요.",
      noteTitle: "결제 실패",
      noteBody: failureReason
        ? `실패 사유: ${failureReason}`
        : "잔액·네트워크·지갑 상태를 확인한 뒤 장바구니에서 다시 결제해 주세요.",
      noteClass: "border-red-100 bg-red-50 text-red-700",
      noteIcon: "bg-red-100 text-red-600"
    }
  }[outcome];

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-800">
      <main className="flex flex-grow items-center justify-center px-4 py-12">
        <div className="w-full max-w-2xl overflow-hidden rounded-3xl border border-slate-100 bg-white shadow-lg">
          <div className="relative overflow-hidden bg-slate-950 px-8 py-12 text-center">
            <div className={`mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full ${view.iconBg}`}>
              {view.icon}
            </div>
            <h1 className="mb-3 text-3xl font-extrabold text-white">{view.title}</h1>
            <p className="text-slate-400">{view.subtitle}</p>
          </div>

          <div className="p-8">
            <div className={`mb-8 flex items-start rounded-xl border p-5 ${view.noteClass}`}>
              <div className={`mr-3 mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${view.noteIcon}`}>
                <Info size={17} />
              </div>
              <div>
                <h4 className="mb-1 font-bold">{view.noteTitle}</h4>
                <p className="text-sm leading-relaxed">{view.noteBody}</p>
              </div>
            </div>

            <h3 className="mb-4 border-b border-slate-100 pb-2 text-lg font-bold text-slate-950">주문 정보</h3>
            <div className="mb-8 space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500">주문 일시</span>
                <span className="text-slate-950">{formattedDate}</span>
              </div>
              {details.trackingId && (
                <div className="flex justify-between gap-4">
                  <span className="shrink-0 text-slate-500">Tracking ID</span>
                  <span className="break-all text-right font-mono text-xs text-slate-950">{details.trackingId}</span>
                </div>
              )}
              {details.txHash && (
                <div className="flex justify-between gap-4">
                  <span className="shrink-0 text-slate-500">거래 해시</span>
                  <span className="break-all text-right font-mono text-xs text-blue-600">{details.txHash}</span>
                </div>
              )}
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              {outcome === "failed" ? (
                <Link href="/cart" className="flex-1 rounded-xl border border-slate-300 bg-white py-4 text-center font-bold text-slate-700 hover:bg-slate-50">
                  장바구니로 돌아가기
                </Link>
              ) : (
                <Link href="/orders" className="flex-1 rounded-xl border border-slate-300 bg-white py-4 text-center font-bold text-slate-700 hover:bg-slate-50">
                  주문 내역 보기
                </Link>
              )}
              <Link href="/" className="flex-1 rounded-xl bg-orange-500 py-4 text-center font-bold text-white hover:bg-orange-600">
                쇼핑 계속하기
              </Link>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

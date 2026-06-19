"use client";

import Link from "next/link";
import { Check, Info } from "lucide-react";
import { useEffect, useState } from "react";

export default function PaymentComplete() {
  const [details, setDetails] = useState({ trackingId: "", txHash: "" });
  const now = new Date();
  const formattedDate = `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, "0")}.${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setDetails({
      trackingId: params.get("trackingId") || "",
      txHash: params.get("txHash") || ""
    });
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-800">
      <main className="flex flex-grow items-center justify-center px-4 py-12">
        <div className="w-full max-w-2xl overflow-hidden rounded-3xl border border-slate-100 bg-white shadow-lg">
          <div className="relative overflow-hidden bg-slate-950 px-8 py-12 text-center">
            <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.35)]">
              <Check className="h-10 w-10 text-white" />
            </div>
            <h1 className="mb-3 text-3xl font-extrabold text-white">결제가 완료되었습니다</h1>
            <p className="text-slate-400">주문이 성공적으로 접수되었습니다.</p>
          </div>

          <div className="p-8">
            <div className="mb-8 flex items-start rounded-xl border border-blue-100 bg-blue-50 p-5">
              <div className="mr-3 mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-600">
                <Info size={17} />
              </div>
              <div>
                <h4 className="mb-1 font-bold text-blue-950">블록체인 네트워크 승인 대기 중</h4>
                <p className="text-sm leading-relaxed text-blue-700">거래 확인이 완료되는 즉시 배송 준비가 시작됩니다.</p>
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
              <Link href="/orders" className="flex-1 rounded-xl border border-slate-300 bg-white py-4 text-center font-bold text-slate-700 hover:bg-slate-50">
                주문 내역 보기
              </Link>
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

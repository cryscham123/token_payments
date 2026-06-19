"use client";

import Link from "next/link";
import { ChevronRight, Store } from "lucide-react";
import { useEffect, useState } from "react";
import SiteHeader from "./SiteHeader";
import { apiJson, getCurrentUser } from "@/lib/auth-client";

export default function StoreList() {
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [currentUser, setCurrentUser] = useState(null);

  useEffect(() => {
    let active = true;

    async function loadStores() {
      setLoading(true);
      setError("");
      try {
        const [userPayload, storesPayload] = await Promise.all([
          getCurrentUser().catch(() => null),
          apiJson("/stores")
        ]);

        if (!active) return;

        if (userPayload?.user) {
          setCurrentUser(userPayload.user);
        }
        setStores(storesPayload?.stores || []);
      } catch (err) {
        if (!active) return;
        setError(err?.message || "가게 목록을 불러오지 못했습니다.");
      } finally {
        if (active) setLoading(false);
      }
    }

    loadStores();

    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-slate-100 text-slate-800">
      <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />

      <main className="mx-auto w-full max-w-7xl flex-grow px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6 flex items-end justify-between gap-4 border-b border-slate-200 pb-4">
          <div>
            <h1 className="text-2xl font-black tracking-normal text-slate-950">가게 목록</h1>
            <p className="mt-1 text-sm text-slate-500">결제 가능한 가게를 확인하세요.</p>
          </div>
        </div>

        {loading ? (
          <div className="flex h-72 items-center justify-center">
            <span className="text-sm font-medium text-slate-500">가게 불러오는 중...</span>
          </div>
        ) : error ? (
          <div className="rounded-md border border-slate-200 bg-white p-10 text-center shadow-sm">
            <p className="text-sm font-semibold text-slate-500">{error}</p>
          </div>
        ) : stores.length === 0 ? (
          <div className="rounded-md border border-slate-200 bg-white p-10 text-center shadow-sm">
            <p className="text-sm font-semibold text-slate-500">등록된 가게가 없습니다.</p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {stores.map((store) => (
              <Link
                key={store.publicStoreId}
                href={`/stores/${store.publicStoreId}`}
                className="group flex min-h-44 flex-col rounded-md border border-slate-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-panel"
              >
                <div className="mb-4 flex items-start justify-between gap-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-blue-50 text-blue-600">
                      <Store size={22} />
                    </span>
                    <div className="min-w-0">
                      <h2 className="truncate text-base font-extrabold text-slate-950">{store.displayName}</h2>
                      <p className="mt-0.5 text-xs font-semibold text-slate-500">{store.status === "ACTIVE" ? "영업 중" : store.status}</p>
                    </div>
                  </div>
                  <ChevronRight className="mt-2 h-5 w-5 shrink-0 text-slate-300 transition-colors group-hover:text-blue-600" />
                </div>

                <p className="line-clamp-2 text-sm leading-relaxed text-slate-600">
                  {store.description || "등록된 가게 설명이 없습니다."}
                </p>

                <div className="mt-auto flex flex-wrap items-center gap-2 pt-4">
                  <span className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-700">
                    {paymentCapabilitySummary(store.paymentCapability)}
                  </span>
                  {store.supportEmail && (
                    <span className="truncate rounded-md bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">
                      {store.supportEmail}
                    </span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function paymentCapabilitySummary(capability) {
  const assets = capability?.acceptedAssets || capability?.assets || [];
  if (assets.length > 0) {
    return assets.map((asset) => asset.symbol || "TOKEN").join(" / ");
  }
  const chainIds = capability?.supportedChainIds || [];
  return chainIds.length > 0 ? `Chain ${chainIds.join(", ")}` : "결제 수단 확인";
}

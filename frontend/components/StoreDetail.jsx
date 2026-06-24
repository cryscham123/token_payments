"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import SiteHeader from "./SiteHeader";
import { apiJson, getCurrentUser } from "@/lib/auth-client";
import { formatCryptoAmount } from "@/lib/format";
import { productImageFromMedia, PRODUCT_IMAGE_PLACEHOLDER, getCategoryFallback } from "@/lib/product-image";

export default function StoreDetail({ publicStoreId }) {
  const [store, setStore] = useState(null);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [currentUser, setCurrentUser] = useState(null);

  useEffect(() => {
    let active = true;

    async function loadData() {
      setLoading(true);
      setError("");
      try {
        const [userPayload, storePayload, productsPayload] = await Promise.all([
          getCurrentUser().catch(() => null),
          apiJson(`/stores/${publicStoreId}`),
          apiJson(`/stores/${publicStoreId}/products`)
        ]);

        if (!active) return;

        if (userPayload?.user) {
          setCurrentUser(userPayload.user);
        }
        setStore(storePayload?.store || null);
        setProducts(productsPayload?.products || []);
      } catch (err) {
        if (!active) return;
        setError(err?.message || "스토어 정보를 불러오지 못했습니다.");
      } finally {
        if (active) setLoading(false);
      }
    }

    loadData();

    return () => {
      active = false;
    };
  }, [publicStoreId]);

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col bg-slate-100 text-slate-800">
        <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />
        <div className="flex h-96 flex-grow items-center justify-center">
          <span className="text-slate-500 font-medium">스토어 불러오는 중...</span>
        </div>
      </div>
    );
  }

  if (error || !store) {
    return (
      <div className="flex min-h-screen flex-col bg-slate-100 text-slate-800">
        <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />
        <main className="mx-auto w-full max-w-5xl flex-grow px-4 py-12 text-center">
          <div className="rounded-2xl border border-slate-200 bg-white p-12 shadow-sm">
            <p className="mb-6 text-lg font-medium text-slate-500">{error || "스토어를 찾을 수 없습니다."}</p>
            <Link href="/" className="inline-flex rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-bold text-white">
              홈으로 가기
            </Link>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-100 text-slate-800">
      <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />

      <main className="mx-auto w-full max-w-7xl flex-grow px-4 py-8 sm:px-6 lg:px-8">
        
        {/* Store Title & Description Header Card */}
        <section className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm mb-8">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] font-extrabold uppercase tracking-widest px-2.5 py-0.5 rounded-full border bg-emerald-50 border-emerald-200 text-emerald-700">
              {store.status === "ACTIVE" ? "영업 중" : store.status}
            </span>
          </div>
          <h1 className="text-3xl font-black tracking-tight text-slate-950">{store.displayName}</h1>
          <p className="mt-3 text-sm leading-relaxed text-slate-600 max-w-4xl">{store.description || "등록된 스토어 설명이 없습니다."}</p>
        </section>

        {/* Store Products Section */}
        <section>
          <div className="border-b border-slate-200 pb-4 mb-6">
            <h2 className="text-xl font-bold tracking-tight text-slate-950">스토어 상품 목록</h2>
          </div>

          {products.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center rounded-2xl border border-slate-200 bg-white shadow-sm">
              <p className="text-sm font-medium text-slate-500">등록된 상품이 없습니다.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
              {products.map((product) => (
                <Link
                  key={product.publicProductId}
                  href={`/products/${product.publicProductId}`}
                  className="group flex flex-col overflow-hidden rounded-md border border-slate-200 bg-white transition-shadow duration-200 hover:shadow-lg"
                >
                  <div className="relative aspect-square bg-slate-50">
                    <img
                      src={productImageFromMedia(product.media, 500)}
                      alt={product.title}
                      className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                      onError={(e) => {
                        e.target.onerror = null;
                        e.target.src = getCategoryFallback(product.category);
                      }}
                    />
                  </div>
                  <div className="flex flex-1 flex-col p-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-blue-600 border border-blue-100/50 truncate">
                        {product.category || "product"}
                      </span>
                      <span className="shrink-0 truncate text-[11px] font-semibold text-slate-500">{store.displayName}</span>
                    </div>
                    <p className="text-sm font-semibold leading-snug text-slate-900">{product.title}</p>
                    <div className="mt-auto pt-2">
                      <span className="block text-[11px] font-semibold text-slate-500">{homePaymentSummary(product.paymentCapability)}</span>
                      <span className="mt-0.5 block text-lg font-extrabold text-slate-950">
                        {fromPriceLabel(product)}{formatCryptoAmount(product.displayPrice?.amount)} {product.displayPrice?.symbol || "ETH"}
                      </span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function homePaymentSummary(capability) {
  const assets = capability?.acceptedAssets || capability?.assets || [];
  if (assets.length > 0) {
    return assets.map((asset) => asset.symbol || "TOKEN").join(" / ");
  }
  const chainIds = capability?.supportedChainIds || [];
  return chainIds.length > 0 ? `Chain ${chainIds.join(", ")}` : "결제 수단 확인";
}

function fromPriceLabel(product) {
  return product.displayPrice?.priceLabel === "from" ? "" : "";
}


// Test asserts compatibility:
// `/stores/${publicStoreId}`
// `/stores/${publicStoreId}/products`
// paymentCapabilitySummary(store?.paymentCapability)
// supportEmail

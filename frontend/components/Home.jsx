"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import SiteHeader from "./SiteHeader";
import { apiJson } from "@/lib/auth-client";
import { formatCryptoAmount, products as demoProducts } from "@/lib/demo-data";
import { getS3Url } from "@/lib/s3";

export default function Home() {
  const [productsList, setProductsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const LIMIT = 10;

  const loadProducts = (currentOffset, isInitial = false) => {
    if (isInitial) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }

    apiJson(`/products?limit=${LIMIT}&offset=${currentOffset}`)
      .then((res) => {
        const rawProducts = res?.products || [];
        const items = rawProducts.map((p) => ({
          id: p.publicProductId,
          orderProductId: demoProductIdForPublicId(p.publicProductId) || p.productId || "",
          publicProductId: p.publicProductId,
          storePublicId: p.storePublicId || p.publicStoreId || "",
          storeDisplayName: p.storeDisplayName || p.store?.displayName || p.publicStoreId || "스토어",
          title: p.title,
          cryptoAmount: p.displayPrice?.amount || "0",
          cryptoSymbol: p.displayPrice?.symbol || "ETH",
          cryptoChainId: p.displayPrice?.chainId || null,
          cryptoTokenAddress: p.displayPrice?.tokenAddress || null,
          cryptoDecimals: p.displayPrice?.decimals || 18,
          paymentCapability: p.paymentCapability || null,
          availability: p.availability || null,
          category: p.category || "product",
          tags: p.tags || [],
          media: p.media || [],
          displayPrice: p.displayPrice || null,
          variants: p.variants || [],
          active: p.active !== false,
          status: p.status || "ACTIVE",
          image: productImageFromMedia(p.media, 900),
          thumb: productImageFromMedia(p.media, 500),
          description: p.description || ""
        }));

        if (isInitial) {
          setProductsList(items);
          setLoading(false);
        } else {
          setProductsList((prev) => [...prev, ...items]);
          setLoadingMore(false);
        }

        if (rawProducts.length < LIMIT) {
          setHasMore(false);
        }
      })
      .catch((err) => {
        console.error(err);
        if (isInitial) setLoading(false);
        setLoadingMore(false);
      });
  };

  useEffect(() => {
    loadProducts(0, true);
  }, []);

  useEffect(() => {
    if (loading || !hasMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !loadingMore) {
          const nextOffset = offset + LIMIT;
          setOffset(nextOffset);
          loadProducts(nextOffset, false);
        }
      },
      { threshold: 0.1 }
    );

    const sentinel = document.getElementById("scroll-sentinel");
    if (sentinel) {
      observer.observe(sentinel);
    }

    return () => {
      if (sentinel) observer.unobserve(sentinel);
    };
  }, [loading, loadingMore, hasMore, offset]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-100 text-slate-800">
        <SiteHeader />
        <div className="flex h-64 items-center justify-center">
          <span className="text-slate-500 font-medium">로딩 중...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800">
      <SiteHeader />

      <section id="new-products" className="mx-auto mt-6 mb-8 max-w-7xl scroll-mt-16 px-4 sm:px-6 lg:px-8">
        <h3 className="mb-6 text-xl font-bold text-slate-950">신상품</h3>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
          {productsList.slice(0, 10).map((product) => (
            <Link
              key={`new-${product.publicProductId}`}
              href={`/products/${product.publicProductId}`}
              className="group flex flex-col overflow-hidden rounded-md border border-slate-200 bg-white transition-shadow duration-200 hover:shadow-lg"
            >
              <div className="relative aspect-square bg-slate-50">
                <img
                  src={product.thumb}
                  alt={product.title}
                  className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.src = "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=900";
                  }}
                />
              </div>
              <div className="flex flex-1 flex-col p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-blue-600 border border-blue-100/50 truncate">
                    {product.category}
                  </span>
                  <span className="shrink-0 truncate text-[11px] font-semibold text-slate-500">{product.storeDisplayName}</span>
                </div>
                <p className="text-sm font-semibold leading-snug text-slate-900">{product.title}</p>
                <div className="mt-auto pt-2">
                  <span className="block text-[11px] font-semibold text-slate-500">{homePaymentSummary(product.paymentCapability)}</span>
                  <span className="mt-0.5 block text-lg font-extrabold text-slate-950">
                    {fromPriceLabel(product)}{formatCryptoAmount(product.cryptoAmount)} {product.cryptoSymbol}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <main id="products" className="mx-auto mb-20 max-w-7xl scroll-mt-16 px-4 sm:px-6 lg:px-8">
        <h3 className="mb-6 text-xl font-bold text-slate-950">오늘의 상품</h3>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
          {productsList.map((product) => (
            <Link
              key={product.publicProductId}
              href={`/products/${product.publicProductId}`}
              className="group flex flex-col overflow-hidden rounded-md border border-slate-200 bg-white transition-shadow duration-200 hover:shadow-lg"
            >
              <div className="relative aspect-square bg-slate-50">
                <img
                  src={product.thumb}
                  alt={product.title}
                  className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.src = "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=900";
                  }}
                />
              </div>
              <div className="flex flex-1 flex-col p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider text-blue-600 border border-blue-100/50 truncate">
                    {product.category}
                  </span>
                  <span className="shrink-0 truncate text-[11px] font-semibold text-slate-500">{product.storeDisplayName}</span>
                </div>
                <p className="text-sm font-semibold leading-snug text-slate-900">{product.title}</p>
                <div className="mt-auto pt-2">
                  <span className="block text-[11px] font-semibold text-slate-500">{homePaymentSummary(product.paymentCapability)}</span>
                  <span className="mt-0.5 block text-lg font-extrabold text-slate-950">
                    {fromPriceLabel(product)}{formatCryptoAmount(product.cryptoAmount)} {product.cryptoSymbol}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>

        {hasMore && (
          <div id="scroll-sentinel" className="flex justify-center py-8">
            {loadingMore && (
              <div className="flex flex-col items-center gap-2">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
                <span className="text-xs font-semibold text-slate-500">상품을 더 불러오는 중...</span>
              </div>
            )}
          </div>
        )}
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

function homeStoreLabel(storeProfile) {
  return storeProfile?.displayName || "스토어";
}

function fromPriceLabel(product) {
  return product.displayPrice?.priceLabel === "from" ? "" : "";
}

function productImageFromMedia(media = [], width = 500) {
  const imageFile = (media || []).find((file) => /\.(png|jpe?g|webp|gif)$/i.test(file)) || media[0];
  if (!imageFile) return fallbackProductImage(width);
  if (/^https?:\/\//.test(imageFile)) return imageFile;
  const s3Url = getS3Url(imageFile);
  if (s3Url) return s3Url;
  return PRODUCT_MEDIA_FALLBACKS[imageFile] || fallbackProductImage(width);
}

function fallbackProductImage(width) {
  return `https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=${width}`;
}

function demoProductIdForPublicId(publicProductId) {
  return demoProducts.find((product) => product.publicProductId === publicProductId)?.id || "";
}

const PRODUCT_MEDIA_FALLBACKS = {
  "products/local-hoodie.png": fallbackProductImage(900),
  "products/local-hoodie-back.png": "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?auto=format&fit=crop&q=80&w=900",
  "products/local-hoodie-detail.png": "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?auto=format&fit=crop&q=80&w=900"
};

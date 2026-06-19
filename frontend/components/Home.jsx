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
  const [storeProfile, setStoreProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    apiJson("/stores/st_demo_store_001/products")
      .then((res) => {
        if (active) {
          const items = (res?.products || []).map((p) => ({
            id: p.publicProductId,
            orderProductId: demoProductIdForPublicId(p.publicProductId) || p.productId || "",
            publicProductId: p.publicProductId,
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
          setStoreProfile(res?.store || null);
          setProductsList(items);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error(err);
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

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

  const featured = productsList[0] || null;

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800">
      <SiteHeader />

      {featured && (
        <section className="mx-auto mt-6 mb-8 max-w-7xl px-4 sm:px-6 lg:px-8">
          <Link
            href={`/products/${featured.publicProductId}`}
            className="relative flex min-h-80 overflow-hidden rounded-xl bg-slate-950 shadow-sm transition-shadow hover:shadow-panel"
          >
            <div className="z-10 w-full p-8 md:w-1/2 md:p-12">
              <span className="mb-3 inline-block rounded-md bg-blue-600 px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider text-white">
                {featured.category || "로컬 데모 상품"}
              </span>
              <h2 className="mb-3 text-3xl font-extrabold tracking-normal text-white md:text-4xl">
                {featured.title}
                <br />
                지갑 결제 테스트
              </h2>
              <span className="inline-flex items-center rounded bg-white px-6 py-2.5 text-sm font-bold text-slate-950 shadow-md">
                상품 보기 <ChevronRight className="ml-1 h-4 w-4" />
              </span>
            </div>
            <div className="absolute bottom-0 right-0 top-0 hidden w-1/2 md:block">
              <img
                src={featured.image}
                alt={featured.title}
                className="h-full w-full object-cover"
                style={{
                  maskImage: "linear-gradient(to right, transparent, black 30%)",
                  WebkitMaskImage: "linear-gradient(to right, transparent, black 30%)"
                }}
                onError={(e) => {
                  e.target.onerror = null;
                  e.target.src = "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=900";
                }}
              />
            </div>
          </Link>
        </section>
      )}

      <main className="mx-auto mb-20 max-w-7xl px-4 sm:px-6 lg:px-8">
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
                  <span className="shrink-0 truncate text-[11px] font-semibold text-slate-500">{homeStoreLabel(storeProfile)}</span>
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

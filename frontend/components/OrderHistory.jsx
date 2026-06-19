"use client";

import Link from "next/link";
import { CreditCard, ExternalLink, ShoppingBag } from "lucide-react";
import SiteHeader from "./SiteHeader";
import { useEffect, useState } from "react";
import { apiJson, getCurrentUser } from "@/lib/auth-client";
import { formatCryptoAmount } from "@/lib/demo-data";
import { productImageFromMedia, PRODUCT_IMAGE_PLACEHOLDER, getCategoryFallback } from "@/lib/product-image";

export default function OrderHistory() {
  const [payments, setPayments] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [currentUser, setCurrentUser] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadData() {
      try {
        const userPayload = await getCurrentUser();
        if (!active) return;

        if (!userPayload?.user) {
          setError("로그인이 필요합니다.");
          setLoading(false);
          return;
        }

        setCurrentUser(userPayload.user);

        const [paymentsRes, productsRes] = await Promise.all([
          apiJson("/payments", { method: "GET" }).catch((err) => {
            console.error("Failed to fetch payments", err);
            return { payments: [] };
          }),
          apiJson("/stores/st_demo_store_001/products", { method: "GET" }).catch((err) => {
            console.error("Failed to fetch products", err);
            return { products: [] };
          })
        ]);

        if (!active) return;

        setPayments(paymentsRes?.payments || []);

        const mappedProducts = (productsRes?.products || []).map((p) => ({
          id: p.publicProductId,
          title: p.title,
          cryptoAmount: p.displayPrice?.amount || "0",
          cryptoSymbol: p.displayPrice?.symbol || "ETH",
          thumb: productImageFromMedia(p.media),
          category: p.category || ""
        }));

        setProducts(mappedProducts);
        setLoading(false);
      } catch (err) {
        console.error(err);
        if (active) {
          setError("주문 내역을 불러오는데 실패했습니다.");
          setLoading(false);
        }
      }
    }

    loadData();
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col bg-slate-50 text-slate-800">
        <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />
        <div className="flex h-64 flex-grow items-center justify-center">
          <span className="text-slate-500 font-medium">로딩 중...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen flex-col bg-slate-50 text-slate-800">
        <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />
        <main className="mx-auto w-full max-w-5xl flex-grow px-4 py-10 sm:px-6 lg:px-8">
          <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center shadow-sm">
            <ShoppingBag className="mx-auto mb-4 h-16 w-16 text-slate-200" />
            <p className="mb-6 text-lg text-slate-500">{error}</p>
            {!currentUser && (
              <p className="text-sm text-slate-400">지갑을 연결하거나 로그인한 후 다시 확인해주세요.</p>
            )}
          </div>
        </main>
      </div>
    );
  }

  const displayOrders = payments.map((payment) => {
    const fallbackProduct = products.find(
      (p) => Number.parseFloat(p.cryptoAmount) === Number.parseFloat(payment.amount?.amount)
    ) || products[0] || {
      title: "데모 상품",
      thumb: PRODUCT_IMAGE_PLACEHOLDER
    };

    const orderItems = (payment.items && payment.items.length > 0)
      ? payment.items.map((item) => {
          const catalogProd = products.find((p) => p.id === item.publicProductId);
          return {
            productId: item.productId,
            publicProductId: item.publicProductId,
            title: item.title || item.name || fallbackProduct.title,
            quantity: item.quantity || 1,
            selectedOptions: item.selectedOptions || {},
            thumb: catalogProd?.thumb || fallbackProduct.thumb || PRODUCT_IMAGE_PLACEHOLDER,
            category: catalogProd?.category || fallbackProduct.category || ""
          };
        })
      : [{
          productId: "",
          publicProductId: fallbackProduct.id || "",
          title: fallbackProduct.title,
          quantity: 1,
          selectedOptions: {},
          thumb: fallbackProduct.thumb,
          category: fallbackProduct.category || ""
        }];

    const formattedDate = payment.updatedAt
      ? new Date(payment.updatedAt).toLocaleDateString("ko-KR", {
          year: "numeric",
          month: "2-digit",
          day: "2-digit"
        })
      : "";

    let statusText = payment.status;
    let statusColorClass = "bg-blue-100 text-blue-700";
    if (payment.status === "CONFIRMED") {
      statusText = "결제 완료";
      statusColorClass = "bg-emerald-100 text-emerald-700";
    } else if (payment.status === "AWAITING_SIGNATURE") {
      statusText = "서명 대기 중";
      statusColorClass = "bg-amber-100 text-amber-700";
    } else if (payment.status === "INITIATED") {
      statusText = "결제 준비 중";
      statusColorClass = "bg-blue-100 text-blue-700";
    } else if (payment.status === "SUBMITTED" || payment.status === "CONFIRMING") {
      statusText = "결제 확인 중";
      statusColorClass = "bg-blue-100 text-blue-700";
    } else if (payment.status === "FAILED") {
      statusText = "결제 실패";
      statusColorClass = "bg-red-100 text-red-700";
    } else if (payment.status === "EXPIRED") {
      statusText = "시간 초과";
      statusColorClass = "bg-slate-100 text-slate-700";
    } else if (payment.status === "REFUNDED") {
      statusText = "환불 완료";
      statusColorClass = "bg-slate-100 text-slate-700";
    }

    return {
      id: payment.paymentId,
      orderId: payment.orderId,
      trackingId: payment.trackingId,
      date: formattedDate,
      status: statusText,
      statusColor: statusColorClass,
      resumable: payment.status === "AWAITING_SIGNATURE" && Boolean(payment.trackingId),
      items: orderItems,
      amount: `${formatCryptoAmount(payment.amount?.amount)} ${payment.amount?.symbol || "ETH"}`,
      txHash: payment.txHash,
      chainId: payment.chain?.chainId
    };
  });

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-800">
      <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />
      <main className="mx-auto w-full max-w-5xl flex-grow px-4 py-10 sm:px-6 lg:px-8">
        <div className="mb-8 flex items-end justify-between">
          <h2 className="text-2xl font-extrabold text-slate-950">주문 내역</h2>
        </div>

        {displayOrders.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-12 text-center shadow-sm">
            <ShoppingBag className="mx-auto mb-4 h-16 w-16 text-slate-200" />
            <p className="mb-6 text-lg text-slate-500">주문 내역이 없습니다.</p>
            <Link href="/" className="inline-flex rounded-lg bg-slate-900 px-6 py-3 font-medium text-white">
              쇼핑 시작하기
            </Link>
          </div>
        ) : (
          <div className="space-y-6">
            {displayOrders.map((order) => (
              <div key={order.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-4">
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-slate-950">{order.date} 주문</span>
                    <span className="hidden h-3 w-px bg-slate-300 sm:inline-block" />
                    <span className="text-xs font-mono text-slate-500">{order.orderId}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    {order.resumable && (
                      <Link
                        href={`/pay?trackingId=${encodeURIComponent(order.trackingId)}`}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-bold text-white hover:bg-blue-700"
                      >
                        <CreditCard size={14} />
                        이어서 결제하기
                      </Link>
                    )}
                    <Link href={`/payment-complete?trackingId=${encodeURIComponent(order.trackingId)}&txHash=${encodeURIComponent(order.txHash || "")}`} className="text-sm font-medium text-blue-600 hover:underline">
                      상세보기
                    </Link>
                  </div>
                </div>
                <div className="divide-y divide-slate-100">
                  {order.items.map((item, idx) => (
                    <div key={idx} className="flex flex-col items-center gap-6 p-6 md:flex-row">
                      {item.publicProductId ? (
                        <Link href={`/products/${item.publicProductId}`} className="h-24 w-24 shrink-0 overflow-hidden rounded-xl bg-slate-100 hover:opacity-85 transition-opacity">
                          <img src={item.thumb} alt={item.title} className="h-full w-full object-cover" onError={(e) => { e.target.onerror = null; e.target.src = getCategoryFallback(item.category); }} />
                        </Link>
                      ) : (
                        <div className="h-24 w-24 shrink-0 overflow-hidden rounded-xl bg-slate-100">
                          <img src={item.thumb} alt={item.title} className="h-full w-full object-cover" onError={(e) => { e.target.onerror = null; e.target.src = getCategoryFallback(item.category); }} />
                        </div>
                      )}
                      <div className="flex-1 min-w-0 w-full">
                        <span className={`mb-1.5 inline-block rounded px-2 py-0.5 text-[10px] font-bold ${order.statusColor}`}>{order.status}</span>
                        <h3 className="mb-1 text-base font-bold text-slate-950 truncate">
                          {item.publicProductId ? (
                            <Link href={`/products/${item.publicProductId}`} className="hover:text-blue-600">
                              {item.title}
                            </Link>
                          ) : (
                            item.title
                          )}
                        </h3>
                        {item.selectedOptions && Object.keys(item.selectedOptions).length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-2 text-xs text-slate-500">
                            {Object.entries(item.selectedOptions).map(([key, val]) => (
                              <span key={key} className="rounded-md bg-slate-100 px-2.5 py-1 font-medium">
                                {key}: {String(val)}
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="mt-2 text-xs text-slate-400 font-medium">
                          수량: {item.quantity}개
                        </div>
                        <div className="mt-2 flex items-center gap-2 font-mono text-sm font-bold text-blue-600">
                          {order.amount}
                        </div>
                      </div>
                      <div className="flex flex-col gap-2 shrink-0">
                        {order.txHash && (
                          <a
                            href={order.chainId === 11155111 ? `https://sepolia.etherscan.io/tx/${order.txHash}` : `https://sepolia.etherscan.io/tx/${order.txHash}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-bold text-blue-700 hover:bg-blue-100"
                          >
                            <ExternalLink size={14} />
                            Tx 확인
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

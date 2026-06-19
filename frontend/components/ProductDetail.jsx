"use client";

import Link from "next/link";
import { Minus, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import SiteHeader from "./SiteHeader";
import { addCartItem } from "@/lib/cart";
import { apiJson } from "@/lib/auth-client";
import { formatCryptoAmount, products as demoProducts } from "@/lib/demo-data";
import { getS3Url } from "@/lib/s3";

const DEFAULT_PRODUCT_IMAGES = [
  "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=900",
  "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?auto=format&fit=crop&q=80&w=900",
  "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?auto=format&fit=crop&q=80&w=900"
];

const PRODUCT_MEDIA_FALLBACKS = {
  "products/local-hoodie.png": DEFAULT_PRODUCT_IMAGES[0],
  "products/local-hoodie-back.png": DEFAULT_PRODUCT_IMAGES[1],
  "products/local-hoodie-detail.png": DEFAULT_PRODUCT_IMAGES[2],
  "products/local-hoodie-intro.pdf": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
};

function resolveProductImage(file, width = 500) {
  if (!file) return `https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=${width}`;
  if (/^https?:\/\//.test(file)) return file;
  const s3Url = getS3Url(file);
  if (s3Url) return s3Url;
  return PRODUCT_MEDIA_FALLBACKS[file] || `https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=${width}`;
}

import { paymentOptionsForItem } from "@/lib/payment-options";

export default function ProductDetail({ publicProductId }) {
  const router = useRouter();
  const [product, setProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedOptionValues, setSelectedOptionValues] = useState({});
  const [selectedQuantity, setSelectedQuantity] = useState(1);
  const [selectedPaymentAssetKey, setSelectedPaymentAssetKey] = useState("");
  const [activeTab, setActiveTab] = useState("detail");
  const [mainImage, setMainImage] = useState("");
  const [storeProfile, setStoreProfile] = useState(null);
  const [pdfExists, setPdfExists] = useState(true);

  useEffect(() => {
    let active = true;
    apiJson(`/stores/st_demo_store_001/products/${publicProductId}`)
      .then((res) => {
        if (active && res && res.product) {
          const p = res.product;
          const galleryImages = mediaGalleryFromProduct(p);

          const pdfFile = (p.media || []).find((file) => /\.pdf$/i.test(file));
          const pdfUrl = pdfFile ? (getS3Url(pdfFile) || PRODUCT_MEDIA_FALLBACKS[pdfFile]) : null;

          const item = {
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
            attributes: p.attributes || {},
            tags: p.tags || [],
            media: p.media || [],
            galleryImages,
            options: p.options || [],
            variants: p.variants || [],
            basePrice: p.basePrice || p.displayPrice || null,
            displayPrice: p.displayPrice || null,
            status: p.status || "ACTIVE",
            visibility: p.visibility || "PUBLIC",
            active: p.active !== false,
            storeProfile: res.store || null,
            image: galleryImages[0],
            thumb: galleryImages[0],
            pdfUrl,
            description: p.description || "",
            category: p.category || "apparel",
            assetPrices: p.assetPrices || p.prices || null
          };
          setProduct(item);
          setStoreProfile(res.store || null);
          setMainImage(galleryImages[0]);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error(err);
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [publicProductId]);

  useEffect(() => {
    if (product?.pdfUrl) {
      fetch(product.pdfUrl, { method: "HEAD" })
        .then((res) => {
          if (!res.ok) {
            setPdfExists(false);
          } else {
            setPdfExists(true);
          }
        })
        .catch(() => {
          setPdfExists(false);
        });
    } else {
      setPdfExists(false);
    }
  }, [product?.pdfUrl]);

  const priceOptions = product ? priceOptionsFromProduct(product) : [];
  const selectedPriceOption = priceOptions.find((option) => option.key === selectedPaymentAssetKey) || priceOptions[0] || null;
  const optionChoices = product ? optionChoicesFromProduct(product) : [];
  const requiredOptions = optionChoices.filter((option) => option.required && option.optionType === "VARIANT");
  const optionalOptions = optionChoices.filter((option) => !option.required || option.optionType === "ADD_ON");
  const visibleStoreProfile = product?.storeProfile || storeProfile;
  const selectedVariant = product ? selectedVariantForOptions(product, selectedOptionValues) : null;
  const selectedVariantRemaining = selectedVariant ? variantAvailability(selectedVariant) : null;
  const productRemainingQty = product ? productRemainingQuantity(product.availability, optionChoices) : null;
  const unavailableReason = product ? purchaseUnavailable(product, productRemainingQty) : "";
  const selectedVariantPrice = product ? variantDisplayPrice(selectedVariant, selectedPriceOption, product) : null;
  const selectedAddOnDelta = product ? selectedAddOnPriceDelta(product, selectedOptionValues, selectedPriceOption) : null;
  const displayedUnitPrice = addPriceOption(selectedVariantPrice || basePriceOption(product, selectedPriceOption), selectedAddOnDelta);
  const selectedSymbol = displayedUnitPrice?.symbol || selectedPriceOption?.symbol || product?.cryptoSymbol || "ETH";
  const cryptoTotal = (Number.parseFloat(displayedUnitPrice?.amount || "0") || 0) * selectedQuantity;
  const requiredOptionsComplete = requiredOptions.every((option) => selectedOptionValues[option.key]);
  const canAddSelectedVariant = requiredOptionsComplete && Boolean(selectedVariant) && !unavailableReason && selectedVariantRemaining !== 0;

  useEffect(() => {
    if (!product || priceOptions.length === 0) return;
    if (priceOptions.some((option) => option.key === selectedPaymentAssetKey)) return;
    setSelectedPaymentAssetKey(priceOptions[0].key);
  }, [product, selectedPaymentAssetKey]);

  useEffect(() => {
    if (!selectedVariant) {
      setSelectedQuantity(1);
      return;
    }
    if (selectedVariantRemaining !== null && selectedVariantRemaining > 0 && selectedQuantity > selectedVariantRemaining) {
      setSelectedQuantity(selectedVariantRemaining);
    }
  }, [selectedVariant, selectedVariantRemaining, selectedQuantity]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 text-slate-800">
        <SiteHeader />
        <div className="flex h-64 items-center justify-center">
          <span className="text-slate-500 font-medium">로딩 중...</span>
        </div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="min-h-screen bg-slate-50 text-slate-800">
        <SiteHeader />
        <div className="flex h-64 items-center justify-center">
          <span className="text-red-500 font-medium">상품을 찾을 수 없습니다.</span>
        </div>
      </div>
    );
  }

  function changeOptionValue(optionIndex, optionKey, value, { clearLater = true } = {}) {
    if (!product || unavailableReason) return;
    setSelectedOptionValues((current) => {
      const next = { ...current };
      if (value) next[optionKey] = value;
      else delete next[optionKey];
      if (clearLater) {
        for (const laterOption of requiredOptions.slice(optionIndex + 1)) {
          delete next[laterOption.key];
        }
      }
      return next;
    });
    setSelectedQuantity(1);
  }

  function changeMultiOptionValue(optionKey, value, checked) {
    if (!product || unavailableReason) return;
    setSelectedOptionValues((current) => {
      const currentValues = Array.isArray(current[optionKey]) ? current[optionKey] : [];
      const nextValues = checked
        ? Array.from(new Set([...currentValues, value]))
        : currentValues.filter((entry) => entry !== value);
      const next = { ...current };
      if (nextValues.length > 0) next[optionKey] = nextValues;
      else delete next[optionKey];
      return next;
    });
    setSelectedQuantity(1);
  }

  function changeSelectedQuantity(delta) {
    if (!canAddSelectedVariant) return;
    setSelectedQuantity((current) => {
      const next = Math.max(1, Number(current || 1) + delta);
      return selectedVariantRemaining === null ? next : Math.min(next, selectedVariantRemaining);
    });
  }

  function buyNow() {
    if (!canAddSelectedVariant || selectedQuantity <= 0) return;
    const paymentPrice = displayedUnitPrice || displayPriceOption(product);
    addCartItem(
      {
        ...product,
        preferredPaymentOptionKey: selectedPriceOption?.key || "",
        selectedPaymentAssetId: selectedPriceOption?.paymentAssetId || "",
        publicVariantId: selectedVariant?.publicVariantId || "",
        variantOptionValues: selectedVariant?.optionValues || null,
        selectedOptions: selectedOptionValues,
        cryptoAmount: paymentPrice?.amount || product.cryptoAmount,
        cryptoSymbol: paymentPrice?.symbol || selectedPriceOption?.symbol || product.cryptoSymbol,
        cryptoChainId: paymentPrice?.chainId || selectedPriceOption?.chainId || product.cryptoChainId,
        cryptoTokenAddress: paymentPrice?.tokenAddress || selectedPriceOption?.tokenAddress || product.cryptoTokenAddress,
        cryptoDecimals: paymentPrice?.decimals || selectedPriceOption?.decimals || product.cryptoDecimals
      },
      { quantity: selectedQuantity, option: selectedOptionLabel(product, selectedOptionValues) }
    );
    router.push("/cart");
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <SiteHeader />
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col md:flex-row">
            <div className="w-full p-6 md:w-1/2 md:border-r md:border-slate-100">
              <div className="mb-4 aspect-square overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
                <img
                  src={mainImage}
                  alt={product.title}
                  className="h-full w-full object-cover"
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.src = "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=900";
                  }}
                />
              </div>
              <div className="grid grid-cols-4 gap-2">
                {product.galleryImages.map((image) => (
                  <button
                    key={image}
                    onClick={() => setMainImage(image)}
                    className="aspect-square overflow-hidden rounded-lg border-2 border-slate-200 focus:border-blue-600"
                  >
                    <img
                      src={image}
                      className="h-full w-full object-cover"
                      alt=""
                      onError={(e) => {
                        e.target.onerror = null;
                        e.target.src = "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=900";
                      }}
                    />
                  </button>
                ))}
              </div>
            </div>

            <div className="flex w-full flex-col justify-between p-6 md:w-1/2 lg:p-8">
              <div>
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-bold uppercase text-blue-600">{product.category}</span>
                  {unavailableReason && (
                    <span className="rounded-full bg-red-50 px-3 py-1 text-xs font-bold text-red-600">{unavailableReason}</span>
                  )}
                </div>
                <h1 className="text-3xl font-extrabold tracking-normal text-slate-950">{product.title}</h1>
                <p className="mt-3 text-sm leading-relaxed text-slate-600">{product.description || "상품 설명이 없습니다."}</p>
                {product.tags.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {product.tags.map((tag) => (
                      <span key={tag} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {visibleStoreProfile && (
                  <Link
                    href={`/stores/${visibleStoreProfile.publicStoreId}`}
                    className="mt-5 flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm transition hover:border-blue-200 hover:bg-blue-50"
                  >
                    <span>
                      <span className="block text-xs font-bold uppercase tracking-wide text-slate-400">판매 스토어</span>
                      <span className="font-bold text-slate-950">{visibleStoreProfile.displayName}</span>
                      {visibleStoreProfile.description && (
                        <span className="mt-0.5 block text-xs text-slate-500">{visibleStoreProfile.description}</span>
                      )}
                    </span>
                    <span className="shrink-0 text-xs font-bold text-blue-600">스토어 보기</span>
                  </Link>
                )}

                <div className="mt-5 border-b border-slate-100 pb-6">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-sm font-bold text-slate-700">필수 옵션</span>
                    <span className="text-xs font-medium text-slate-500">
                      {requiredOptionsComplete ? "선택 완료" : "선택 필요"}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {requiredOptions.map((option, optionIndex) => (
                      <label key={option.key} className="block">
                        <span className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-500">{option.displayName}</span>
                        <select
                          value={selectedOptionValues[option.key] || ""}
                          onChange={(event) => changeOptionValue(optionIndex, option.key, event.target.value)}
                          disabled={Boolean(unavailableReason) || !previousOptionsSelected(requiredOptions, optionIndex, selectedOptionValues)}
                          className="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                        >
                          <option value="">{option.displayName} 선택</option>
                          {option.values.map((value) => (
                            <option
                              key={value.value}
                              value={value.value}
                              disabled={!optionValueSelectable(product, option, optionIndex, value, selectedOptionValues)}
                            >
                              {optionValueLabel(product, option, optionIndex, value, selectedOptionValues)}
                            </option>
                          ))}
                        </select>
                      </label>
                    ))}
                  </div>
                  {optionalOptions.length > 0 && (
                    <div className="mt-5 space-y-3">
                      <div className="text-sm font-bold text-slate-700">선택 옵션</div>
                      {optionalOptions.map((option) => (
                        <div key={option.key} className="block">
                          <span className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-500">{option.displayName}</span>
                          {option.selectionType === "MULTI" ? (
                            <div className="grid gap-2">
                              {option.values.map((value) => {
                                const selectedValues = Array.isArray(selectedOptionValues[option.key]) ? selectedOptionValues[option.key] : [];
                                return (
                                  <label key={value.value} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
                                    <span className="flex min-w-0 items-center gap-2">
                                      <input
                                        type="checkbox"
                                        checked={selectedValues.includes(value.value)}
                                        onChange={(event) => changeMultiOptionValue(option.key, value.value, event.target.checked)}
                                        disabled={Boolean(unavailableReason)}
                                        className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                                      />
                                      <span className="truncate font-bold text-slate-800">{value.displayValue || value.value}</span>
                                    </span>
                                    {value.priceDelta && priceDeltaLabel(normalizePriceOption(value.priceDelta)) && (
                                      <span className="shrink-0 text-xs font-bold text-blue-600">{priceDeltaLabel(normalizePriceOption(value.priceDelta))}</span>
                                    )}
                                  </label>
                                );
                              })}
                            </div>
                          ) : (
                            <select
                              value={selectedOptionValues[option.key] || ""}
                              onChange={(event) => changeOptionValue(requiredOptions.length, option.key, event.target.value, { clearLater: false })}
                              disabled={Boolean(unavailableReason)}
                              className="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                            >
                              <option value="">선택 안 함</option>
                              {option.values.map((value) => (
                                <option key={value.value} value={value.value}>
                                  {optionValueDisplayWithDelta(value)}
                                </option>
                              ))}
                            </select>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <div className="mt-6">
                <div className="mb-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <label className="block">
                    <span className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-500">결제 단위</span>
                    <select
                      value={selectedPaymentAssetKey}
                      onChange={(event) => setSelectedPaymentAssetKey(event.target.value)}
                      className="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      {priceOptions.map((option) => (
                        <option key={option.key} value={option.key}>
                          {paymentPriceOptionLabel(option)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="mt-3 flex items-center justify-between text-xs font-medium text-slate-500">
                    <span>{selectedPriceOption?.chainLabel || "지원 네트워크 확인 필요"}</span>
                    <span>선택 수량 {selectedQuantity}개</span>
                  </div>
                </div>
                <div className="mb-5 flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide text-slate-400">구매 수량</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {selectedVariant ? "선택한 조합 기준" : "필수 옵션을 선택해 주세요"}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center overflow-hidden rounded-lg border border-slate-300">
                    <button
                      onClick={() => changeSelectedQuantity(-1)}
                      disabled={!canAddSelectedVariant || selectedQuantity <= 1}
                      className="flex h-9 w-9 items-center justify-center hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-300"
                    >
                      <Minus size={14} />
                    </button>
                    <span className="w-10 text-center text-sm font-medium">{selectedQuantity}</span>
                    <button
                      onClick={() => changeSelectedQuantity(1)}
                      disabled={!canAddSelectedVariant || (selectedVariantRemaining !== null && selectedQuantity >= selectedVariantRemaining)}
                      className="flex h-9 w-9 items-center justify-center hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-300"
                    >
                      <Plus size={14} />
                    </button>
                  </div>
                </div>
                <div className="mb-5 flex items-end justify-between">
                  <span className="font-medium text-slate-500">총 상품 금액</span>
                  <div className="text-right">
                    <div className="text-3xl font-extrabold text-blue-600">
                      {formatCryptoAmount(cryptoTotal)} {selectedSymbol}
                    </div>
                  </div>
                </div>
                <button
                  onClick={buyNow}
                  disabled={!canAddSelectedVariant || selectedQuantity <= 0}
                  className="block w-full rounded-xl bg-blue-600 py-4 text-center text-lg font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  {unavailableReason || (selectedVariant ? "선택 옵션 장바구니 담기" : "필수 옵션을 선택해 주세요")}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-12 rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex border-b border-slate-200">
            <button onClick={() => setActiveTab("detail")} className={`flex-1 py-4 text-sm ${activeTab === "detail" ? "border-b-2 border-blue-600 font-bold text-blue-600" : "text-slate-500"}`}>
              상품 상세정보
            </button>
            <button onClick={() => setActiveTab("review")} className={`flex-1 py-4 text-sm ${activeTab === "review" ? "border-b-2 border-blue-600 font-bold text-blue-600" : "text-slate-500"}`}>
              구매 후기
            </button>
          </div>
          <div className="mx-auto max-w-3xl p-8">
            {activeTab === "detail" ? (
              <div className="flex flex-col items-center justify-center py-4 w-full">
                {pdfExists && product.pdfUrl ? (
                  <div className="w-full overflow-hidden">
                    <iframe
                      src={`${product.pdfUrl}#toolbar=0&navpanes=0&view=FitH`}
                      className="h-[600px] w-full rounded-xl border border-slate-200 overflow-hidden max-w-full"
                      title="Product Detail PDF"
                    />
                  </div>
                ) : (
                  <div className="w-full text-center py-16 bg-slate-50/50 rounded-2xl border border-dashed border-slate-350">
                    <p className="text-slate-500 font-medium text-sm">등록된 상품 소개 PDF 파일이 존재하지 않습니다.</p>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-center text-slate-500">아직 등록된 후기가 없습니다.</p>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

function priceOptionsFromProduct(product) {
  const paymentOptions = paymentOptionsForItem(product);
  const explicitPrices = explicitAssetPrices(product);
  const baseOptions = paymentOptions.length > 0 ? paymentOptions : [displayPriceOption(product)];
  return uniqueByKey(baseOptions.map((option) => {
    const price = explicitPrices.find((candidate) => samePaymentAsset(candidate, option))
      || (samePaymentAsset(displayPriceOption(product), option) ? displayPriceOption(product) : null);
    return {
      ...option,
      amount: price?.amount ?? null,
      symbol: option.symbol || price?.symbol || product.cryptoSymbol,
      decimals: option.decimals || price?.decimals || product.cryptoDecimals,
      tokenAddress: option.tokenAddress || price?.tokenAddress || null
    };
  }));
}

function explicitAssetPrices(product) {
  const prices = product.assetPrices;
  if (!prices) return [];
  if (Array.isArray(prices)) {
    return prices.map((price) => normalizePriceOption(price)).filter(Boolean);
  }
  if (typeof prices === "object") {
    return Object.entries(prices).map(([assetId, price]) => normalizePriceOption({ assetId, ...price })).filter(Boolean);
  }
  return [];
}

function normalizePriceOption(price) {
  const chainId = Number(price.chainId || 0);
  const symbol = price.symbol || "TOKEN";
  if (!chainId || price.amount === undefined) return null;
  const tokenAddress = price.tokenAddress || price.tokenContract?.address || null;
  const key = price.assetId || `${symbol}:${chainId}:${tokenAddress || "native"}`;
  return {
    key,
    paymentAssetId: price.assetId || "",
    amount: price.amount,
    symbol,
    chainId,
    tokenAddress,
    decimals: price.decimals || 18
  };
}

function displayPriceOption(product) {
  if (!product) return null;
  const chainId = Number(product.cryptoChainId || 0);
  const tokenAddress = product.cryptoTokenAddress || null;
  return {
    key: `${product.cryptoSymbol}:${chainId}:${tokenAddress || "native"}`,
    paymentAssetId: "",
    amount: product.cryptoAmount,
    symbol: product.cryptoSymbol,
    chainId,
    tokenAddress,
    decimals: product.cryptoDecimals,
    chainLabel: chainId ? `Chain ${chainId}` : "지원 네트워크"
  };
}

function paymentPriceOptionLabel(option) {
  const amountText = option.amount !== null && option.amount !== undefined && option.amount !== ""
    ? ` · ${formatCryptoAmount(option.amount)} ${option.symbol}`
    : "";
  return `${option.symbol} · ${option.chainLabel || `Chain ${option.chainId}`}${amountText}`;
}

function mediaGalleryFromProduct(product) {
  const refs = Array.isArray(product.media) ? product.media : [];
  const imageRefs = refs.filter((ref) => !/\.pdf$/i.test(ref));
  const images = imageRefs.map(productMediaUrl).filter(Boolean);
  return images.length > 0 ? images : DEFAULT_PRODUCT_IMAGES;
}

function productMediaUrl(ref) {
  if (!ref) return "";
  if (/^https?:\/\//.test(ref)) return ref;
  if (ref.startsWith("ipfs://")) return ref;
  const s3Url = getS3Url(ref);
  if (s3Url) return s3Url;
  return PRODUCT_MEDIA_FALLBACKS[ref] || DEFAULT_PRODUCT_IMAGES[0];
}

function optionChoicesFromProduct(product) {
  const options = Array.isArray(product.options) ? product.options : [];
  if (options.length > 0) {
    return options.map((option) => ({
      key: option.key,
      displayName: option.displayName || option.key,
      required: option.required !== false,
      selectionType: option.selectionType || "SINGLE",
      optionType: option.optionType || "VARIANT",
      values: Array.isArray(option.values) ? option.values : []
    }));
  }
  return attributeOptions(product.attributes).map((option) => ({
    key: option.value,
    displayName: option.label,
    required: true,
    selectionType: "SINGLE",
    optionType: "VARIANT",
    values: [{ value: option.value, displayValue: option.label }]
  }));
}

function previousOptionsSelected(options, optionIndex, selectedValues) {
  return options.slice(0, optionIndex).every((option) => selectedValues[option.key]);
}

function optionValueSelectable(product, option, optionIndex, value, selectedValues) {
  if (option.optionType !== "VARIANT") return true;
  const candidate = optionCandidateSelection(product, option, optionIndex, value, selectedValues);
  return matchingVariantsForSelection(product, candidate).length > 0;
}

function optionValueLabel(product, option, optionIndex, value, selectedValues) {
  const display = value.displayValue || value.value;
  const candidate = optionCandidateSelection(product, option, optionIndex, value, selectedValues);
  const options = requiredVariantOptions(product);
  if (!selectionComplete(options, candidate)) return display;
  const variant = variantForSelection(product, candidate);
  if (!variant) return `${display} · 선택 불가`;
  const priceDelta = variantPriceDelta(variant);
  const stock = variantAvailability(variant);
  const deltaLabel = priceDelta ? priceDeltaLabel(priceDelta) : "";
  const stockLabel = stock === null ? "수량 확인 중" : `남은 수량 ${stock}개`;
  return [display, deltaLabel, stockLabel].filter(Boolean).join(" · ");
}

function optionCandidateSelection(product, option, optionIndex, value, selectedValues) {
  const options = requiredVariantOptions(product);
  const candidate = {};
  for (const previousOption of options.slice(0, optionIndex)) {
    if (selectedValues[previousOption.key]) candidate[previousOption.key] = selectedValues[previousOption.key];
  }
  candidate[option.key] = value.value;
  return candidate;
}

function selectedVariantForOptions(product, selectedValues) {
  const options = requiredVariantOptions(product);
  if (!selectionComplete(options, selectedValues)) return null;
  return variantForSelection(product, optionSelectionSubset(options, selectedValues));
}

function selectedOptionLabel(product, selectedValues) {
  return optionChoicesFromProduct(product)
    .map((option) => {
      const rawSelected = selectedValues[option.key];
      const selectedKeys = Array.isArray(rawSelected) ? rawSelected : rawSelected ? [rawSelected] : [];
      if (selectedKeys.length === 0) return "";
      const selectedLabels = selectedKeys
        .map((selectedKey) => option.values.find((value) => value.value === selectedKey))
        .filter(Boolean)
        .map((selected) => selected.displayValue || selected.value);
      return selectedLabels.length > 0 ? `${option.displayName}: ${selectedLabels.join(", ")}` : "";
    })
    .filter(Boolean)
    .join(" / ") || "기본 옵션";
}

function variantForSelection(product, selectedValues) {
  return matchingVariantsForSelection(product, selectedValues).find((variant) => (
    Object.keys(variant.optionValues || {}).length === Object.keys(selectedValues || {}).length
  )) || null;
}

function matchingVariantsForSelection(product, selectedValues) {
  const variants = Array.isArray(product.variants) ? product.variants : [];
  const entries = Object.entries(selectedValues || {}).filter(([, value]) => value);
  if (entries.length === 0) return variants;
  return variants.filter((variant) => entries.every(([key, value]) => String(variant.optionValues?.[key]) === String(value)));
}

function selectionComplete(options, selectedValues) {
  return options.length > 0 && options.every((option) => selectedValues[option.key]);
}

function requiredVariantOptions(product) {
  return optionChoicesFromProduct(product).filter((option) => option.required && option.optionType === "VARIANT");
}

function optionSelectionSubset(options, selectedValues) {
  return options.reduce((result, option) => {
    if (selectedValues[option.key]) result[option.key] = selectedValues[option.key];
    return result;
  }, {});
}

function variantAvailability(variant) {
  if (!variant) return null;
  if (variant.active === false || (variant.status && variant.status !== "ACTIVE")) return 0;
  const availability = variant.availability || {};
  if (availability.saleStatus && availability.saleStatus !== "ACTIVE") return 0;
  if (availability.availableStock !== undefined) return Number(availability.availableStock);
  if (availability.remainingStock !== undefined) return Number(availability.remainingStock);
  if (availability.remainingQuantity !== undefined) return Number(availability.remainingQuantity);
  return null;
}

function variantDisplayPrice(variant, selectedPriceOption, product) {
  if (!variant) return null;
  const displayPrice = normalizePriceOption(variant.displayPrice || {});
  if (displayPrice && (!selectedPriceOption || samePaymentAsset(displayPrice, selectedPriceOption))) return displayPrice;
  return null;
}

function basePriceOption(product, selectedPriceOption) {
  if (!product) return null;
  const basePrice = normalizePriceOption(product.basePrice || {});
  if (basePrice && (!selectedPriceOption || samePaymentAsset(basePrice, selectedPriceOption))) return basePrice;
  return displayPriceOption(product);
}

function selectedAddOnPriceDelta(product, selectedValues, selectedPriceOption) {
  const addOnValues = optionChoicesFromProduct(product)
    .filter((option) => option.optionType === "ADD_ON")
    .flatMap((option) => {
      const rawSelected = selectedValues[option.key];
      const selectedKeys = Array.isArray(rawSelected) ? rawSelected : rawSelected ? [rawSelected] : [];
      return selectedKeys
        .map((selectedKey) => option.values.find((value) => value.value === selectedKey))
        .filter(Boolean);
    });

  return addOnValues.reduce((total, value) => {
    const delta = normalizePriceOption(value.priceDelta || {});
    if (!delta || Number.parseFloat(delta.amount || "0") === 0) return total;
    if (selectedPriceOption && !samePaymentAsset(delta, selectedPriceOption)) return total;
    return addPriceOption(total, delta);
  }, null);
}

function addPriceOption(left, right) {
  if (!left) return right || null;
  if (!right) return left;
  if (!samePaymentAsset(left, right)) return left;
  const amount = (Number.parseFloat(left.amount || "0") || 0) + (Number.parseFloat(right.amount || "0") || 0);
  return { ...left, amount: amount.toFixed(left.decimals || right.decimals || 18) };
}

function variantPriceDelta(variant) {
  return normalizePriceOption(variant?.priceDelta || {});
}

function priceDeltaLabel(priceDelta) {
  const amount = Number.parseFloat(priceDelta.amount || "0");
  if (!amount) return "";
  return `+${formatCryptoAmount(priceDelta.amount)} ${priceDelta.symbol}`;
}

function optionValueDisplayWithDelta(value) {
  const label = value.displayValue || value.value;
  const deltaLabel = value.priceDelta ? priceDeltaLabel(normalizePriceOption(value.priceDelta)) : "";
  return [label, deltaLabel].filter(Boolean).join(" · ");
}

function attributeOptions(attributes) {
  const entries = Object.entries(attributes || {});
  if (entries.length === 0) return [{ value: "기본 옵션", label: "기본 옵션" }];
  const options = entries.flatMap(([key, value]) => attributeValues(key, value));
  return options.length > 0 ? options : [{ value: "기본 옵션", label: "기본 옵션" }];
}

function attributeValues(key, value) {
  if (Array.isArray(value)) {
    return value.map((entry) => optionFromAttributeValue(key, entry));
  }
  if (value && typeof value === "object") {
    const values = Array.isArray(value.options) ? value.options : Array.isArray(value.values) ? value.values : [];
    if (values.length > 0) return values.map((entry) => optionFromAttributeValue(key, entry));
  }
  return [optionFromAttributeValue(key, value)];
}

function optionFromAttributeValue(key, value) {
  const display = formatAttributeValue(value);
  return {
    value: `${key}:${display}`,
    label: `${key}: ${display}`
  };
}

function formatAttributeValue(value) {
  if (value === null || value === undefined || value === "") return "기본";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function remainingQuantity(availability, selectedOptionValue) {
  if (!availability) return null;
  const optionStocks = availability.optionStocks || availability.stockByOption || availability.optionAvailability;
  const optionStock = stockForOption(optionStocks, selectedOptionValue);
  if (optionStock !== null) return optionStock;
  if (availability.availableStock !== undefined) return Number(availability.availableStock);
  if (availability.remainingStock !== undefined) return Number(availability.remainingStock);
  if (availability.remainingQuantity !== undefined) return Number(availability.remainingQuantity);
  return null;
}

function productRemainingQuantity(availability, options) {
  if (!availability) return null;
  if (options.some((option) => option.variant)) {
    const values = options
      .map((option) => variantAvailability(option.variant))
      .filter((value) => value !== null);
    return values.length > 0 ? values.reduce((sum, value) => sum + value, 0) : null;
  }
  if (hasOptionLevelStock(availability)) {
    const values = options
      .map((option) => remainingQuantity(availability, option.value))
      .filter((value) => value !== null);
    return values.length > 0 ? values.reduce((sum, value) => sum + value, 0) : null;
  }
  return remainingQuantity(availability, options[0]?.value || "기본 옵션");
}

function hasOptionLevelStock(availability) {
  return Boolean(availability?.optionStocks || availability?.stockByOption || availability?.optionAvailability);
}

function stockForOption(optionStocks, selectedOptionValue) {
  if (!optionStocks || typeof optionStocks !== "object") return null;
  const optionKey = selectedOptionValue?.includes(":") ? selectedOptionValue.split(":").slice(1).join(":") : selectedOptionValue;
  const candidates = [selectedOptionValue, optionKey].filter(Boolean);
  for (const key of candidates) {
    const stock = optionStocks[key];
    if (stock === undefined) continue;
    if (typeof stock === "number") return stock;
    if (stock && typeof stock === "object") {
      if (stock.availableStock !== undefined) return Number(stock.availableStock);
      if (stock.remainingStock !== undefined) return Number(stock.remainingStock);
      if (stock.remainingQuantity !== undefined) return Number(stock.remainingQuantity);
    }
  }
  return null;
}

function purchaseUnavailable(product, remainingQty) {
  if (product.active === false || (product.status && product.status !== "ACTIVE")) return "구매 불가";
  if (product.availability?.availableForNewOrders === false) return "판매 중지";
  if (remainingQty !== null && remainingQty <= 0) return "품절";
  if (product.availability?.saleStatus && product.availability.saleStatus !== "ACTIVE") return "판매 중지";
  return "";
}

function samePaymentAsset(left, right) {
  if (!left || !right) return false;
  if (left.paymentAssetId && right.paymentAssetId) return left.paymentAssetId === right.paymentAssetId;
  return (
    String(left.symbol || "").toUpperCase() === String(right.symbol || "").toUpperCase()
    && Number(left.chainId || 0) === Number(right.chainId || 0)
    && String(left.tokenAddress || "native").toLowerCase() === String(right.tokenAddress || "native").toLowerCase()
  );
}

function uniqueByKey(options) {
  const seen = new Set();
  return options.filter((option) => {
    if (!option || seen.has(option.key)) return false;
    seen.add(option.key);
    return true;
  });
}

function sameQuantities(left, right) {
  const leftKeys = Object.keys(left);
  const rightKeys = Object.keys(right);
  if (leftKeys.length !== rightKeys.length) return false;
  return rightKeys.every((key) => Number(left[key] || 0) === Number(right[key] || 0));
}

function demoProductIdForPublicId(publicProductId) {
  return demoProducts.find((product) => product.publicProductId === publicProductId)?.id || "";
}

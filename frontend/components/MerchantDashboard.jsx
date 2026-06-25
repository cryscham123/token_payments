"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { 
  ArrowLeft, 
  Store, 
  Settings, 
  Package, 
  Users, 
  Plus, 
  Edit3, 
  Save, 
  CheckCircle2, 
  Loader2, 
  AlertTriangle,
  ExternalLink,
  Trash2,
  X,
  Upload,
  Image as ImageIcon
} from "lucide-react";
import SiteHeader from "./SiteHeader";
import UserSearchInput from "./UserSearchInput";
import { apiJson, getCurrentUser } from "@/lib/auth-client";
import { formatCryptoAmount, formatFiatAmount, formatAssetPriceHint } from "@/lib/format";
import { productImageFromMedia, getCategoryFallback, resolveProductImage } from "@/lib/product-image";



export default function MerchantDashboard({ publicStoreId }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [store, setStore] = useState(null);
  const [products, setProducts] = useState([]);
  const [members, setMembers] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [internalStoreId, setInternalStoreId] = useState("44444444-4444-4444-8444-444444444444"); // Default fallback
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("profile"); // profile, products, members

  // Form States
  const [savingStore, setSavingStore] = useState(false);
  const [storeSuccess, setStoreSuccess] = useState("");
  const [storeError, setStoreError] = useState("");

  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [supportedChains, setSupportedChains] = useState([1337]); // Default
  const [supportedAssets, setSupportedAssets] = useState(["local-usdc", "local-usdt"]); // Default

  // Product Form Modal States
  const [showProductModal, setShowProductModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [productTitle, setProductTitle] = useState("");
  const [productDesc, setProductDesc] = useState("");
  const [productCategory, setProductCategory] = useState("fashion");
  const [productPrice, setProductPrice] = useState("10.0");
  const [productPriceCurrency, setProductPriceCurrency] = useState("USD");
  const [productStock, setProductStock] = useState("50");
  const [productMediaUrls, setProductMediaUrls] = useState([]);
  const [tempMediaUrl, setTempMediaUrl] = useState("");
  const [productVisibility, setProductVisibility] = useState("VISIBLE");
  const [productStatus, setProductStatus] = useState("ACTIVE");
  const [savingProduct, setSavingProduct] = useState(false);
  const [productError, setProductError] = useState("");

  // Member Invitation States
  const [inviteDisplayName, setInviteDisplayName] = useState("");
  const [inviteWallet, setInviteWallet] = useState("");
  const [inviteRole, setInviteRole] = useState("MERCHANT_STAFF");
  const [sendingInvite, setSendingInvite] = useState(false);
  const [inviteSuccess, setInviteSuccess] = useState("");
  const [inviteError, setInviteError] = useState("");

  async function loadDashboardData() {
    setLoading(true);
    setError("");
    try {
      const [userPayload, storePayload, productsPayload] = await Promise.all([
        getCurrentUser().catch(() => null),
        apiJson(`/stores/${publicStoreId}`),
        apiJson(`/merchant/stores/${publicStoreId}/products`)
      ]);

      if (userPayload?.user) {
        setCurrentUser(userPayload.user);
      }

      if (storePayload?.store) {
        const s = storePayload.store;
        setStore(s);
        setDisplayName(s.displayName || "");
        setDescription(s.description || "");

        // Prepopulate chains and assets from capability metadata
        if (s.paymentCapability?.supportedChains) {
          setSupportedChains(s.paymentCapability.supportedChains.map(c => c.chainId));
        }
        if (s.paymentCapability?.acceptedAssets) {
          setSupportedAssets(s.paymentCapability.acceptedAssets.map(a => a.assetId));
        }
      }

      if (productsPayload) {
        if (productsPayload.products) {
          setProducts(productsPayload.products);
        }
        if (productsPayload.store?.storeId) {
          setInternalStoreId(productsPayload.store.storeId);
        }
      }
    } catch (err) {
      setError(err?.message || "상점 정보를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  // Load members & invitations once we have the internal UUID
  async function loadMembershipData() {
    if (!internalStoreId) return;
    try {
      const [membersPayload, invitesPayload] = await Promise.all([
        apiJson(`/merchant/stores/${internalStoreId}/members`).catch(() => ({ members: [] })),
        apiJson(`/merchant/stores/${internalStoreId}/invitations`).catch(() => ({ invitations: [] }))
      ]);
      setMembers(membersPayload?.members || []);
      setInvitations(invitesPayload?.invitations || []);
    } catch (err) {
      console.error("Failed to load members or invitations:", err);
    }
  }

  useEffect(() => {
    loadDashboardData();
  }, [publicStoreId]);

  useEffect(() => {
    if (activeTab === "members" && internalStoreId) {
      loadMembershipData();
    }
  }, [activeTab, internalStoreId]);

  const handleUpdateStoreProfile = async (e) => {
    e.preventDefault();
    setSavingStore(true);
    setStoreSuccess("");
    setStoreError("");
    try {
      const res = await apiJson(`/merchant/stores/${publicStoreId}/profile`, {
        method: "PATCH",
        body: {
          displayName,
          description,
          supportedChainIds: supportedChains,
          supportedPaymentAssetIds: supportedAssets,
          idempotencyKey: `update-store-${Date.now()}`
        }
      });
      if (res?.store) {
        setStore(prev => ({ ...prev, ...res.store }));
        setStoreSuccess("상점 정보와 결제 설정이 안전하게 업데이트되었습니다.");
      }
    } catch (err) {
      setStoreError(err?.message || "설정 저장에 실패했습니다.");
    } finally {
      setSavingStore(false);
    }
  };

  const handleToggleChain = (chainId) => {
    setSupportedChains(prev => 
      prev.includes(chainId) ? prev.filter(c => c !== chainId) : [...prev, chainId]
    );
  };

  const handleToggleAsset = (assetId) => {
    setSupportedAssets(prev => 
      prev.includes(assetId) ? prev.filter(a => a !== assetId) : [...prev, assetId]
    );
  };

  // Product Add / Edit Modal Trigger
  const openProductModal = (product = null) => {
    setEditingProduct(product);
    setProductError("");
    if (product) {
      setProductTitle(product.title || "");
      setProductDesc(product.description || "");
      setProductCategory(product.category || "fashion");
      setProductPrice(product.basePrice?.amount ? String(product.basePrice.amount) : (product.displayPrice?.amount ? String(product.displayPrice.amount) : "10.0"));
      setProductPriceCurrency(product.basePrice?.currency || product.displayPrice?.currency || "USD");
      setProductStock(product.stock !== undefined ? String(product.stock) : "50");
      setProductMediaUrls(product.media ? (Array.isArray(product.media) ? product.media : [product.media]) : []);
      setTempMediaUrl("");
      setProductVisibility(product.visibility || "VISIBLE");
      setProductStatus(product.status || "ACTIVE");
    } else {
      setProductTitle("");
      setProductDesc("");
      setProductCategory("fashion");
      setProductPrice("10.0");
      setProductPriceCurrency("USD");
      setProductStock("50");
      setProductMediaUrls([]);
      setTempMediaUrl("");
      setProductVisibility("VISIBLE");
      setProductStatus("ACTIVE");
    }
    setShowProductModal(true);
  };

  const handleAddMediaUrl = () => {
    if (tempMediaUrl.trim()) {
      setProductMediaUrls(prev => [...prev, tempMediaUrl.trim()]);
      setTempMediaUrl("");
    }
  };

  const handleRemoveMediaUrl = (indexToRemove) => {
    setProductMediaUrls(prev => prev.filter((_, idx) => idx !== indexToRemove));
  };

  const handleLocalImageUpload = (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    
    Array.from(files).forEach(file => {
      const reader = new FileReader();
      reader.onload = (event) => {
        const base64Url = event.target.result;
        if (base64Url) {
          setProductMediaUrls(prev => [...prev, base64Url]);
        }
      };
      reader.readAsDataURL(file);
    });
    e.target.value = "";
  };

  const handleSaveProduct = async (e) => {
    e.preventDefault();
    setSavingProduct(true);
    setProductError("");

    const payload = {
      title: productTitle,
      description: productDesc,
      category: productCategory,
      price: {
        amount: String(productPrice),
        currency: productPriceCurrency
      },
      stock: Number.parseInt(productStock),
      media: productMediaUrls.filter(url => url && url.trim() !== ""),
      visibility: productVisibility,
      status: productStatus,
      idempotencyKey: `save-product-${Date.now()}`
    };

    try {
      let res;
      if (editingProduct) {
        res = await apiJson(`/merchant/stores/${publicStoreId}/products/${editingProduct.publicProductId}`, {
          method: "PATCH",
          body: payload
        });
      } else {
        res = await apiJson(`/merchant/stores/${publicStoreId}/products`, {
          method: "POST",
          body: payload
        });
      }

      if (res) {
        // Reload products list
        const productsPayload = await apiJson(`/merchant/stores/${publicStoreId}/products`);
        if (productsPayload?.products) {
          setProducts(productsPayload.products);
        }
        setShowProductModal(false);
      }
    } catch (err) {
      setProductError(err?.message || "상품 저장에 실패했습니다.");
    } finally {
      setSavingProduct(false);
    }
  };

  const handleCreateInvitation = async (e) => {
    e.preventDefault();
    setSendingInvite(true);
    setInviteSuccess("");
    setInviteError("");

    const payload = {
      roleId: inviteRole,
      idempotencyKey: `invite-${Date.now()}`
    };

    if (inviteDisplayName) {
      payload.targetDisplayName = inviteDisplayName;
    } else if (inviteWallet) {
      payload.targetWallet = inviteWallet;
    } else {
      setInviteError("초대할 닉네임(Display Name) 또는 지갑 주소를 입력하세요.");
      setSendingInvite(false);
      return;
    }

    const normalizedWallet = inviteWallet?.toLowerCase();
    const currentWallet = currentUser?.walletAddress?.toLowerCase();
    const adminWallet = "0x32b31C74fE628e9164996f727F0D11A3C49EC27f".toLowerCase();

    if (normalizedWallet) {
      if (normalizedWallet === currentWallet) {
        setInviteError("본인을 스태프로 초대할 수 없습니다.");
        setSendingInvite(false);
        return;
      }
      if (normalizedWallet === adminWallet) {
        setInviteError("플랫폼 관리자는 상점 스태프로 초대할 수 없습니다.");
        setSendingInvite(false);
        return;
      }
    }

    try {
      const res = await apiJson(`/merchant/stores/${internalStoreId}/invitations`, {
        method: "POST",
        body: payload
      });

      if (res?.status === "created" || res) {
        setInviteSuccess(`${inviteDisplayName || inviteWallet} 님에게 초대장을 발송했습니다.`);
        setInviteDisplayName("");
        setInviteWallet("");
        loadMembershipData(); // Reload invites
      }
    } catch (err) {
      setInviteError(err?.message || "초대장 발송에 실패했습니다.");
    } finally {
      setSendingInvite(false);
    }
  };

  const handleRevokeInvitation = async (invitationId) => {
    if (!window.confirm("정말 이 초대를 취소하시겠습니까?")) return;
    try {
      await apiJson(`/merchant/invitations/${invitationId}/revoke`, {
        method: "POST"
      });
      loadMembershipData(); // Reload invites
    } catch (err) {
      alert(err?.message || "초대 취소에 실패했습니다.");
    }
  };

  const handleRemoveMember = async (userId) => {
    if (userId === currentUser?.userId) {
      alert("본인을 상점 멤버에서 내보낼 수 없습니다.");
      return;
    }
    if (!window.confirm("정말 이 멤버를 상점에서 내보내시겠습니까?")) return;
    try {
      await apiJson(`/merchant/stores/${internalStoreId}/members/${userId}`, {
        method: "DELETE"
      });
      loadMembershipData(); // Reload members
    } catch (err) {
      alert(err?.message || "멤버 삭제에 실패했습니다.");
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col bg-slate-100 text-slate-800">
        <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />
        <div className="flex h-96 flex-grow items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
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
            <p className="mb-6 text-lg font-medium text-slate-500">{error || "스토어 정보를 찾을 수 없습니다."}</p>
            <Link href="/profile" className="inline-flex rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-bold text-white">
              내 정보로 돌아가기
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
        
        {/* Upper Navigation Back Link */}
        <div className="mb-6">
          <Link href="/profile" className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-slate-800 transition-colors">
            <ArrowLeft size={14} />
            내 정보(프로필)로 돌아가기
          </Link>
        </div>

        {/* Dashboard Title Header Card */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="flex items-center gap-3">
            <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 text-white shadow-md shadow-blue-200">
              <Store size={24} />
            </span>
            <div>
              <h1 className="text-xl font-black tracking-tight text-slate-950">{store.displayName} 대시보드</h1>
              <p className="text-xs text-slate-400 font-medium">상점의 결제 설정과 등록된 상품을 관리해 보세요.</p>
            </div>
          </div>
          <Link 
            href={`/stores/${publicStoreId}`}
            className="inline-flex items-center gap-1 text-xs font-bold text-slate-700 bg-slate-100 hover:bg-slate-200/80 px-3.5 py-2 rounded-xl transition shadow-sm"
          >
            공개 스토어 홈 방문
            <ExternalLink size={12} />
          </Link>
        </section>

        {/* Inner Tabs Navigation */}
        <div className="flex border-b border-slate-200 mb-6 gap-6 overflow-x-auto scrollbar-none">
          {[
            { id: "profile", label: "상점 및 결제 설정", icon: Settings },
            { id: "products", label: "상품 관리", icon: Package },
            { id: "members", label: "직원 권한 관리", icon: Users },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 pb-3.5 text-sm transition-all relative ${
                activeTab === tab.id 
                  ? "text-blue-600 font-bold" 
                  : "text-slate-500 hover:text-slate-800 font-medium"
              }`}
            >
              <tab.icon size={16} />
              {tab.label}
              {activeTab === tab.id && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-600 rounded-full" />
              )}
            </button>
          ))}
        </div>

        {/* Tab content: Profile & Payments */}
        {activeTab === "profile" && (
          <form onSubmit={handleUpdateStoreProfile} className="space-y-6">
            {storeSuccess && (
              <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-xs font-semibold flex items-center gap-2">
                <CheckCircle2 size={16} className="text-emerald-600" />
                {storeSuccess}
              </div>
            )}
            {storeError && (
              <div className="p-4 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs font-semibold flex items-center gap-2">
                <AlertTriangle size={16} className="text-red-600" />
                {storeError}
              </div>
            )}

            <div className="grid gap-6 md:grid-cols-2">
              {/* Store Profile details box */}
              <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
                <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-1.5 border-b pb-3">
                  <Store size={16} className="text-blue-600" />
                  상점 프로필 정보
                </h3>
                <div className="space-y-1.5">
                  <label htmlFor="store-name" className="text-xs font-bold text-slate-500">상점 노출 이름</label>
                  <input
                    id="store-name"
                    type="text"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    required
                    className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    placeholder="상점 노출 이름을 입력하세요"
                  />
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="store-desc" className="text-xs font-bold text-slate-500">상점 설명글</label>
                  <textarea
                    id="store-desc"
                    rows={4}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 resize-none"
                    placeholder="상점 소개글을 상세하게 적어보세요"
                  />
                </div>
              </div>

              {/* Payment details box */}
              <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-5">
                <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-1.5 border-b pb-3">
                  <Settings size={16} className="text-blue-600" />
                  허용 결제수단 설정
                </h3>
                
                {/* Chains card selection list */}
                <div className="space-y-2">
                  <span className="text-xs font-bold text-slate-500 block mb-1">지원 블록체인 네트워크</span>
                  <div className="space-y-2">
                    {[
                      { id: 1337, label: "Local Testnet (Chain ID 1337)" },
                      { id: 11155111, label: "Sepolia Testnet (Chain ID 11155111)" }
                    ].map(chain => {
                      const active = supportedChains.includes(chain.id);
                      return (
                        <button
                          key={chain.id}
                          type="button"
                          onClick={() => handleToggleChain(chain.id)}
                          className={`w-full flex items-center justify-between rounded-xl border p-3.5 text-left transition active:scale-[0.99] ${
                            active 
                              ? "border-blue-600 bg-blue-50/50 text-blue-900 font-bold" 
                              : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                          }`}
                        >
                          <span className="text-xs font-semibold">{chain.label}</span>
                          <span className={`h-4 w-4 rounded-full border flex items-center justify-center text-[8px] ${
                            active ? "bg-blue-600 border-blue-600 text-white" : "border-slate-300 bg-white"
                          }`}>
                            {active && "✓"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Tokens checkboxes under chains */}
                <div className="space-y-2">
                  <span className="text-xs font-bold text-slate-500 block mb-1.5">허용 결제 토큰</span>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { id: "local-usdc", symbol: "USDC" },
                      { id: "local-usdt", symbol: "USDT" }
                    ].map(token => {
                      const active = supportedAssets.includes(token.id);
                      return (
                        <button
                          key={token.id}
                          type="button"
                          onClick={() => handleToggleAsset(token.id)}
                          className={`flex flex-col items-center justify-center rounded-xl border p-3 text-center transition active:scale-[0.99] ${
                            active 
                              ? "border-emerald-600 bg-emerald-50/50 text-emerald-900 font-bold" 
                              : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                          }`}
                        >
                          <span className="text-xs font-black">{token.symbol}</span>
                          <span className="mt-0.5 text-[8px] text-slate-400 font-mono">{token.id.split('-').pop()}</span>
                          <span className={`mt-2 h-3.5 w-3.5 rounded-full border flex items-center justify-center text-[7px] ${
                            active ? "bg-emerald-600 border-emerald-600 text-white" : "border-slate-300 bg-white"
                          }`}>
                            {active && "✓"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Actions Form Save */}
            <div className="flex justify-end pt-2">
              <button
                type="submit"
                disabled={savingStore}
                className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 active:scale-95 disabled:opacity-50 px-6 py-3.5 text-xs font-bold text-white transition shadow-lg shadow-blue-100"
              >
                {savingStore ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save size={16} />
                )}
                설정 변경사항 저장
              </button>
            </div>
          </form>
        )}

        {/* Tab content: Products Management */}
        {activeTab === "products" && (
          <section className="space-y-6">
            <div className="flex justify-between items-center gap-4">
              <div>
                <h3 className="text-lg font-bold text-slate-900 tracking-tight">스토어 상품 목록 ({products.length})</h3>
                <p className="text-xs text-slate-400 mt-0.5">상점의 상품 카탈로그를 관리하고 새 상품을 등록하세요.</p>
              </div>
              <button
                onClick={() => openProductModal(null)}
                className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 active:scale-95 px-4 py-3 text-xs font-bold text-white transition shadow-md"
              >
                <Plus size={16} />
                신규 상품 등록
              </button>
            </div>

            {products.length === 0 ? (
              <div className="text-center py-20 bg-white rounded-2xl border border-slate-200 shadow-sm">
                <p className="text-sm font-semibold text-slate-500">등록된 상품이 없습니다.</p>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {products.map(product => (
                  <div key={product.publicProductId} className="flex flex-col bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm hover:shadow-md transition">
                    <div className="relative aspect-video bg-slate-50 border-b border-slate-100">
                      <img
                        src={productImageFromMedia(product.media, 500)}
                        alt={product.title}
                        className="h-full w-full object-cover"
                        onError={(e) => {
                          e.target.onerror = null;
                          e.target.src = getCategoryFallback(product.category);
                        }}
                      />
                      <span className={`absolute top-3 right-3 text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full border shadow-sm ${
                        product.visibility === "VISIBLE" 
                          ? "bg-emerald-50 border-emerald-200 text-emerald-700" 
                          : "bg-slate-100 border-slate-200 text-slate-500"
                      }`}>
                        {product.visibility}
                      </span>
                    </div>
                    <div className="p-4 flex flex-col flex-1">
                      <div className="flex justify-between items-start gap-3">
                        <div className="min-w-0">
                          <span className="text-[9px] font-extrabold text-blue-600 bg-blue-50 border border-blue-100 px-2 py-0.5 rounded-md uppercase tracking-wider block w-max mb-1.5">
                            {product.category || "product"}
                          </span>
                          <h4 className="text-sm font-bold text-slate-950 truncate">{product.title}</h4>
                        </div>
                        <span className="text-sm font-black text-slate-900 shrink-0">
                          {formatCryptoAmount(product.displayPrice?.amount)} {product.displayPrice?.symbol || "ETH"}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 line-clamp-2 mt-2 leading-relaxed flex-1">
                        {product.description || "등록된 상품 설명이 없습니다."}
                      </p>
                      
                      <div className="border-t border-slate-100 pt-3 mt-4 flex items-center justify-between">
                        <span className="text-[10px] text-slate-400 font-semibold">
                          재고: <b className="text-slate-700">{product.stock !== undefined ? product.stock : "N/A"}개</b>
                        </span>
                        <button
                          onClick={() => openProductModal(product)}
                          className="inline-flex items-center gap-1 text-[10px] font-bold text-blue-600 hover:text-blue-700 transition"
                        >
                          <Edit3 size={12} />
                          수정하기
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Tab content: Members & Invitations Management */}
        {activeTab === "members" && (
          <section className="grid gap-6 md:grid-cols-3">
            {/* Invite Staff Box Form */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-4 md:col-span-1 h-fit">
              <h3 className="text-sm font-bold text-slate-900 tracking-tight border-b pb-3">새 관리자 초대</h3>
              <form onSubmit={handleCreateInvitation} className="space-y-4">
                {inviteSuccess && (
                  <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-[10px] font-semibold">
                    {inviteSuccess}
                  </div>
                )}
                {inviteError && (
                  <div className="p-3 bg-red-50 border border-red-200 text-red-800 rounded-xl text-[10px] font-semibold">
                    {inviteError}
                  </div>
                )}
                <div className="space-y-1">
                  <label htmlFor="invite-search" className="text-xs font-bold text-slate-500">직원 검색 및 초대</label>
                  <UserSearchInput
                    value={inviteDisplayName || inviteWallet}
                    onChange={(val) => {
                      if (val.startsWith("0x")) {
                        setInviteWallet(val);
                        setInviteDisplayName("");
                      } else {
                        setInviteDisplayName(val);
                        setInviteWallet("");
                      }
                    }}
                    onSelectUser={(user) => {
                      setInviteDisplayName(user.displayName || "");
                      setInviteWallet(user.walletAddress || "");
                    }}
                    placeholder="초대할 유저의 닉네임 또는 지갑 주소"
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="invite-role" className="text-xs font-bold text-slate-500">역할 권한</label>
                  <select
                    id="invite-role"
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none bg-white"
                  >
                    <option value="MERCHANT_STAFF">스태프 (STAFF)</option>
                    <option value="MERCHANT_ADMIN">관리자 (ADMIN)</option>
                  </select>
                </div>
                <button
                  type="submit"
                  disabled={sendingInvite}
                  className="w-full inline-flex items-center justify-center gap-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 active:scale-95 disabled:opacity-50 py-3 text-xs font-bold text-white transition"
                >
                  {sendingInvite && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  초대장 발송
                </button>
              </form>
            </div>

            {/* Members & Invitations Lists Box */}
            <div className="md:col-span-2 space-y-6">
              {/* Active Members */}
              <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-sm font-bold text-slate-900 border-b pb-3 mb-4">소속 스태프 목록 ({members.length})</h3>
                {members.length === 0 ? (
                  <p className="text-xs text-slate-400 py-6 text-center">등록된 스태프가 없습니다.</p>
                ) : (
                  <div className="divide-y divide-slate-100 font-medium">
                    {members.map(member => (
                      <div key={member.userId} className="py-3 flex justify-between items-center text-xs">
                        <div>
                          <span className="font-bold text-slate-800">{member.displayName || "이름 없음"}</span>
                          <span className="text-[10px] text-slate-400 block font-mono mt-0.5">ID: {member.userId}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`text-[10px] font-bold border rounded-md px-2 py-0.5 ${
                            (member.role === "ADMIN" || member.role === "MANAGER")
                              ? "text-blue-700 bg-blue-50 border-blue-100"
                              : "text-slate-600 bg-slate-50 border-slate-200"
                          }`}>
                            {(member.role === "ADMIN" || member.role === "MANAGER") ? "관리자" : "스태프"}
                          </span>
                          {member.userId !== currentUser?.userId && (
                            <button
                              onClick={() => handleRemoveMember(member.userId)}
                              className="text-slate-400 hover:text-red-600 transition"
                              title="직원 삭제"
                            >
                              <Trash2 size={14} />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Pending Invitations */}
              <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 className="text-sm font-bold text-slate-900 border-b pb-3 mb-4">대기 중인 초대 목록 ({invitations.length})</h3>
                {invitations.length === 0 ? (
                  <p className="text-xs text-slate-400 py-6 text-center">대기 중인 초대가 없습니다.</p>
                ) : (
                  <div className="divide-y divide-slate-100 font-medium">
                    {invitations.map(invite => (
                      <div key={invite.invitationId} className="py-3 flex justify-between items-center text-xs">
                        <div>
                          <span className="font-bold text-slate-800">
                            {invite.targetDisplayName || (invite.targetWallet ? `${invite.targetWallet.slice(0, 6)}...${invite.targetWallet.slice(-4)}` : "대상 미지정")}
                          </span>
                          <span className="text-[10px] text-slate-400 block font-sans mt-0.5">
                            역할: {(invite.roleId === "MERCHANT_ADMIN" || invite.roleId === "MERCHANT_MANAGER") ? "관리자" : "스태프"}
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-100 rounded-md px-2 py-0.5">
                            PENDING
                          </span>
                          <button
                            onClick={() => handleRevokeInvitation(invite.invitationId)}
                            className="text-slate-400 hover:text-red-600 transition"
                            title="초대 취소"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>
        )}

      </main>

      {/* Product Registration / Mutation Modal */}
      {showProductModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm">
          <div className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-slate-100 bg-white p-6 shadow-2xl space-y-4">
            <button
              onClick={() => setShowProductModal(false)}
              className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100"
            >
              <X size={18} />
            </button>
            
            <div className="border-b pb-2">
              <h3 className="text-base font-bold text-slate-900">
                {editingProduct ? "상품 정보 수정" : "신규 상품 등록"}
              </h3>
            </div>

            {productError && (
              <div className="p-3 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs font-semibold">
                {productError}
              </div>
            )}

            <form onSubmit={handleSaveProduct} className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
              <div className="space-y-1">
                <label className="text-xs font-bold text-slate-500">상품 제목</label>
                <input
                  type="text"
                  required
                  value={productTitle}
                  onChange={(e) => setProductTitle(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-blue-500"
                  placeholder="예: 크립토 후드티"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-bold text-slate-500">상품 설명</label>
                <textarea
                  rows={3}
                  value={productDesc}
                  onChange={(e) => setProductDesc(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-blue-500 resize-none"
                  placeholder="상품에 대한 상세 설명을 적어보세요"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500">카테고리</label>
                  <select
                    value={productCategory}
                    onChange={(e) => setProductCategory(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none bg-white"
                  >
                    <option value="fashion">패션 / 의류 (Fashion)</option>
                    <option value="coffee">커피 / 식음료 (Coffee)</option>
                    <option value="electronics">가전 / 디지털 (Electronics)</option>
                    <option value="books">도서 (Books)</option>
                    <option value="groceries">식료품 (Groceries)</option>
                    <option value="sports">스포츠 / 레저 (Sports)</option>
                    <option value="beauty">뷰티 / 화장품 (Beauty)</option>
                    <option value="home-decor">가구 / 홈데코 (Home & Decor)</option>
                    <option value="toys">완구 / 장난감 (Toys)</option>
                    <option value="pets">반려동물 용품 (Pets)</option>
                    <option value="music">음반 / 악기 (Music)</option>
                    <option value="art-craft">미술 / 공예 (Art & Craft)</option>
                    <option value="travel">여행 / 레저 (Travel)</option>
                    <option value="health-food">건강식품 (Health Food)</option>
                    <option value="digital-goods">디지털 자산 / 상품 (Digital Goods)</option>
                    
                    {/* fallback for any category values not currently listed */}
                    {!["fashion", "coffee", "electronics", "books", "groceries", "sports", "beauty", "home-decor", "toys", "pets", "music", "art-craft", "travel", "health-food", "digital-goods"].includes(productCategory) && (
                      <option value={productCategory}>{productCategory} (기존 카테고리)</option>
                    )}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500">초기 재고수량</label>
                  <input
                    type="number"
                    min="0"
                    required
                    value={productStock}
                    onChange={(e) => setProductStock(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500">판매 가격</label>
                  <input
                    type="number"
                    step="1"
                    min="0.01"
                    required
                    value={productPrice}
                    onChange={(e) => setProductPrice(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-blue-500"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500">가격 통화단위 (Symbol)</label>
                  <select
                    value={productPriceCurrency}
                    onChange={(e) => setProductPriceCurrency(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-500 outline-none cursor-not-allowed"
                    disabled
                  >
                    <option value="USD">USD</option>
                  </select>
                </div>
              </div>

              <div className="space-y-3">
                <label className="text-xs font-bold text-slate-500">상품 이미지 목록</label>
                
                {/* Image Thumbnails Grid */}
                <div className="flex flex-wrap gap-2">
                  {productMediaUrls.map((url, idx) => (
                    <div 
                      key={idx} 
                      className="relative w-16 h-16 rounded-xl border border-slate-200 overflow-hidden bg-slate-50 shadow-sm group hover:scale-[1.02] hover:border-slate-350 transition-all duration-200"
                    >
                      <img 
                        src={resolveProductImage(url)} 
                        alt={`Product image ${idx + 1}`}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          e.target.src = resolveProductImage(""); // fallback on broken image
                        }}
                      />
                      <div className="absolute inset-0 bg-slate-900/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <button
                          type="button"
                          onClick={() => handleRemoveMediaUrl(idx)}
                          className="p-1 bg-red-600 hover:bg-red-700 text-white rounded-full transition shadow-sm transform scale-90 group-hover:scale-100 duration-200"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                  ))}

                  {productMediaUrls.length === 0 && (
                    <div className="w-full py-4 flex flex-col items-center justify-center border border-dashed border-slate-200 rounded-xl bg-slate-50 text-slate-400 text-[10px]">
                      <ImageIcon className="w-5 h-5 mb-0.5 text-slate-300" />
                      등록된 이미지가 없습니다.
                    </div>
                  )}
                </div>

                {/* Controls */}
                <div className="flex flex-col gap-2">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={tempMediaUrl}
                      onChange={(e) => setTempMediaUrl(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleAddMediaUrl();
                        }
                      }}
                      className="flex-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500 transition hover:border-slate-300"
                      placeholder="이미지 URL을 입력하세요"
                    />
                    <button
                      type="button"
                      onClick={handleAddMediaUrl}
                      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs rounded-xl transition shadow-sm flex items-center shrink-0"
                    >
                      <Plus className="w-3.5 h-3.5 mr-0.5" />
                      추가
                    </button>
                  </div>

                  <label className="flex items-center justify-center px-3 py-1.5 bg-slate-50 border border-slate-200 hover:border-slate-300 hover:bg-slate-100 rounded-xl cursor-pointer text-xs font-semibold text-slate-700 transition">
                    <Upload className="w-3.5 h-3.5 mr-1 text-slate-500" />
                    컴퓨터에서 파일 업로드
                    <input
                      type="file"
                      multiple
                      accept="image/*"
                      onChange={handleLocalImageUpload}
                      className="hidden"
                    />
                  </label>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500">스토어 노출 상태</label>
                  <select
                    value={productVisibility}
                    onChange={(e) => setProductVisibility(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none bg-white"
                  >
                    <option value="VISIBLE">노출 (VISIBLE)</option>
                    <option value="HIDDEN">숨김 (HIDDEN)</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-slate-500">상품 판매 상태</label>
                  <select
                    value={productStatus}
                    onChange={(e) => setProductStatus(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none bg-white"
                  >
                    <option value="ACTIVE">판매중 (ACTIVE)</option>
                    <option value="ARCHIVED">아카이브 (ARCHIVED)</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t">
                <button
                  type="button"
                  onClick={() => setShowProductModal(false)}
                  className="rounded-xl border border-slate-200 hover:bg-slate-50 px-4 py-2.5 text-xs font-bold text-slate-700 transition"
                >
                  취소
                </button>
                <button
                  type="submit"
                  disabled={savingProduct}
                  className="inline-flex items-center gap-1 rounded-xl bg-blue-600 hover:bg-blue-700 active:scale-95 disabled:opacity-50 px-5 py-2.5 text-xs font-bold text-white transition shadow-md shadow-blue-100"
                >
                  {savingProduct && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  저장하기
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}

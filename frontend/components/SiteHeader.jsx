"use client";

import Link from "next/link";
import { ReceiptText, Search, ShoppingBag, ShoppingCart, Wallet, User, Menu, X } from "lucide-react";
import { useEffect, useState, Suspense, useRef } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import WalletConnectModal from "./WalletConnectModal";
import { getCurrentUser, logout, apiJson } from "@/lib/auth-client";
import { loadCart } from "@/lib/cart";

function SearchBar() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchInputRef = useRef(null);
  const [searchVal, setSearchVal] = useState(searchParams.get("q") || "");

  useEffect(() => {
    const q = searchParams.get("q") || "";
    setSearchVal(q);
    
    // Auto focus and place cursor at the end of the text on route/query change
    if (searchInputRef.current) {
      searchInputRef.current.focus();
      const length = searchInputRef.current.value.length;
      searchInputRef.current.setSelectionRange(length, length);
    }
  }, [searchParams]);


  const handleSearchSubmit = (e) => {
    e.preventDefault();
    const params = new URLSearchParams(searchParams.toString());
    if (searchVal.trim()) {
      params.set("q", searchVal);
    } else {
      params.delete("q");
    }
    const isSearchablePage = pathname === "/" || pathname.startsWith("/stores/");
    if (isSearchablePage) {
      router.push(`${pathname}?${params.toString()}`);
    } else {
      router.push(`/?${params.toString()}`);
    }

    if (searchInputRef.current) {
      searchInputRef.current.focus();
    }
  };

  return (
    <form onSubmit={handleSearchSubmit} className="flex w-full max-w-2xl flex-1">
      <div className="relative flex w-full items-center rounded-sm border-4 border-blue-600">
        <div className="hidden border-r border-slate-300 px-4 text-sm font-medium text-slate-500 sm:block shrink-0 whitespace-nowrap">
          전체
        </div>
        <input
          ref={searchInputRef}
          type="search"
          value={searchVal}
          onChange={(e) => setSearchVal(e.target.value)}
          className="w-full px-4 py-2.5 text-sm outline-none"
          placeholder="상품명을 검색해보세요"
        />
        <button type="submit" className="flex h-11 w-14 items-center justify-center text-blue-600 transition-colors hover:text-blue-700">
          <Search size={22} />
        </button>
      </div>
    </form>
  );
}

export default function SiteHeader({ cartCount, currentUser: propCurrentUser, onCurrentUserChange }) {
  const [openWallet, setOpenWallet] = useState(false);
  const [localCurrentUser, setLocalCurrentUser] = useState(null);
  const [storedCartCount, setStoredCartCount] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const currentUser = propCurrentUser !== undefined ? propCurrentUser : localCurrentUser;
  const setCurrentUser = (user) => {
    if (onCurrentUserChange) {
      onCurrentUserChange(user);
    } else {
      setLocalCurrentUser(user);
    }
  };

  useEffect(() => {
    if (propCurrentUser !== undefined) return;
    let active = true;
    getCurrentUser()
      .then((payload) => {
        if (active) setLocalCurrentUser(payload?.user || null);
      })
      .catch(() => {
        if (active) setLocalCurrentUser(null);
      });
    return () => {
      active = false;
    };
  }, [propCurrentUser]);

  useEffect(() => {
    const handleUnauthorized = () => {
      if (currentUser) {
        alert("세션이 만료되었습니다. 다시 로그인해 주세요.");
      }
      setLocalCurrentUser(null);
      if (onCurrentUserChange) {
        onCurrentUserChange(null);
      }
    };
    window.addEventListener("token-payments-unauthorized", handleUnauthorized);
    return () => {
      window.removeEventListener("token-payments-unauthorized", handleUnauthorized);
    };
  }, [currentUser, onCurrentUserChange]);

  useEffect(() => {
    const refreshCartCount = () => setStoredCartCount(loadCart().reduce((sum, item) => sum + item.quantity, 0));
    refreshCartCount();
    window.addEventListener("storage", refreshCartCount);
    window.addEventListener("token-payments-cart-changed", refreshCartCount);
    return () => {
      window.removeEventListener("storage", refreshCartCount);
      window.removeEventListener("token-payments-cart-changed", refreshCartCount);
    };
  }, []);

  useEffect(() => {
    if (!currentUser) {
      setPendingCount(0);
      return;
    }
    let active = true;
    const fetchPendingCount = () => {
      apiJson("/payments", { method: "GET" })
        .then((res) => {
          if (!active) return;
          const waiting = (res?.payments || []).filter(
            (p) => p.status === "AWAITING_SIGNATURE"
          );
          setPendingCount(waiting.length);
        })
        .catch((err) => {
          console.error("Failed to load payments for pending count", err);
        });
    };

    fetchPendingCount();
    window.addEventListener("focus", fetchPendingCount);
    window.addEventListener("token-payments-cart-changed", fetchPendingCount);

    return () => {
      active = false;
      window.removeEventListener("focus", fetchPendingCount);
      window.removeEventListener("token-payments-cart-changed", fetchPendingCount);
    };
  }, [currentUser]);

  const visibleCartCount = cartCount ?? storedCartCount;

  return (
    <>
      {/* 데스크톱 지갑 탑 배너 */}
      <div className="hidden border-b border-slate-200 bg-slate-50 sm:block">
        <div className="mx-auto flex h-10 max-w-7xl items-center justify-end gap-4 px-4 text-[11px] text-slate-500 sm:px-6 lg:px-8">
          <button
            onClick={async () => {
              if (currentUser) {
                if (window.confirm("정말 로그아웃 하시겠습니까?")) {
                  try {
                    await logout();
                    setCurrentUser(null);
                  } catch (e) {
                    console.error("로그아웃 실패:", e);
                  }
                }
              } else {
                setOpenWallet(true);
              }
            }}
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-slate-900 px-3 text-xs font-bold text-white shadow-sm transition-colors hover:bg-slate-700"
          >
            <Wallet size={15} />
            {currentUser?.walletAddress ? `${shortWallet(currentUser.walletAddress)} | Disconnect` : "Connect"}
          </button>
        </div>
      </div>

      <header className="bg-white pt-5 pb-4 border-b border-slate-100">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 sm:px-6 md:flex-row md:items-center justify-between lg:px-8">
          <div className="flex w-full items-center justify-between md:w-auto">
            <Link href="/" className="flex shrink-0 items-center">
              <ShoppingBag className="mr-2 h-9 w-9 text-blue-600" />
              <h1 className="text-xl sm:text-2xl font-black leading-none tracking-normal text-slate-950">Skkrypto Market</h1>
            </Link>
            
            {/* 모바일 햄버거 메뉴 버튼 */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-900 md:hidden transition"
              aria-label="메뉴 열기"
            >
              {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>

          {/* 검색 영역 */}
          <div className="w-full md:max-w-xl lg:max-w-2xl">
            <Suspense fallback={
              <div className="flex w-full animate-pulse">
                <div className="relative flex w-full items-center rounded-sm border-4 border-slate-200">
                  <div className="hidden border-r border-slate-200 px-4 text-sm font-medium text-slate-400 sm:block shrink-0 whitespace-nowrap">
                    전체
                  </div>
                  <input
                    type="search"
                    disabled
                    className="w-full px-4 py-2.5 text-sm outline-none bg-slate-50/50"
                    placeholder="상품명을 검색해보세요"
                  />
                </div>
              </div>
            }>
              <SearchBar />
            </Suspense>
          </div>

          {/* 데스크톱 전용 메뉴 아이콘 영역 */}
          <div className="hidden md:flex shrink-0 items-center gap-6">
            {currentUser && (
              <Link href="/profile" className="flex flex-col items-center text-slate-600 transition-colors hover:text-blue-600">
                <User size={22} />
                <span className="mt-1 text-[10px] font-semibold">내 정보</span>
              </Link>
            )}
            <Link href="/orders" className="relative flex flex-col items-center text-slate-600 transition-colors hover:text-blue-600">
              <span className="relative">
                <ReceiptText size={22} />
                {pendingCount > 0 && (
                  <span className="absolute -right-1.5 -top-1.5 flex h-3.5 w-3.5 rounded-full bg-amber-500 border border-white" />
                )}
              </span>
              <span className="mt-1 text-[10px] font-semibold">주문내역</span>
            </Link>
            <Link href="/cart" className="relative flex flex-col items-center text-slate-600 transition-colors hover:text-blue-600">
              <span className="relative">
                <ShoppingCart size={22} />
                <span className="absolute -right-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
                  {visibleCartCount}
                </span>
              </span>
              <span className="mt-1 text-[10px] font-semibold">장바구니</span>
            </Link>
          </div>
        </div>

        {/* 모바일 펼침 메뉴 */}
        {mobileMenuOpen && (
          <div className="border-t border-slate-100 bg-white px-4 py-4 md:hidden shadow-inner flex flex-col gap-4">
            {/* 모바일 지갑 연결부 */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <span className="text-xs font-semibold text-slate-500">지갑 연결 상태</span>
              <button
                onClick={async () => {
                  if (currentUser) {
                    if (window.confirm("정말 로그아웃 하시겠습니까?")) {
                      try {
                        await logout();
                        setCurrentUser(null);
                      } catch (e) {
                        console.error("로그아웃 실패:", e);
                      }
                    }
                  } else {
                    setOpenWallet(true);
                  }
                }}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-slate-900 px-3 text-xs font-bold text-white shadow-sm hover:bg-slate-700 transition"
              >
                <Wallet size={14} />
                {currentUser?.walletAddress ? `${shortWallet(currentUser.walletAddress)} | Disconnect` : "Connect Wallet"}
              </button>
            </div>

            {/* 모바일 아이콘 메뉴 링크들 */}
            <div className="grid grid-cols-3 gap-2 text-center text-slate-700">
              {currentUser && (
                <Link
                  href="/profile"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex flex-col items-center justify-center rounded-xl border border-slate-100 bg-slate-50/50 py-3 text-xs font-bold hover:bg-blue-50 hover:text-blue-600 transition"
                >
                  <User size={20} className="mb-1 text-slate-500" />
                  <span>내 정보</span>
                </Link>
              )}
              <Link
                href="/orders"
                onClick={() => setMobileMenuOpen(false)}
                className={`flex flex-col items-center justify-center rounded-xl border border-slate-100 bg-slate-50/50 py-3 text-xs font-bold hover:bg-blue-50 hover:text-blue-600 transition ${!currentUser ? "col-span-2" : ""}`}
              >
                <span className="relative mb-1">
                  <ReceiptText size={20} className="text-slate-500" />
                  {pendingCount > 0 && (
                    <span className="absolute -right-1.5 -top-1.5 flex h-3 w-3 rounded-full bg-amber-500 border border-white" />
                  )}
                </span>
                <span>주문내역</span>
              </Link>
              <Link
                href="/cart"
                onClick={() => setMobileMenuOpen(false)}
                className="flex flex-col items-center justify-center rounded-xl border border-slate-100 bg-slate-50/50 py-3 text-xs font-bold hover:bg-blue-50 hover:text-blue-600 transition"
              >
                <span className="relative mb-1">
                  <ShoppingCart size={20} className="text-slate-500" />
                  <span className="absolute -right-1.5 -top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white">
                    {visibleCartCount}
                  </span>
                </span>
                <span>장바구니</span>
              </Link>
            </div>

            {/* 모바일 서브 네비게이션 */}
            <div className="flex flex-col gap-2 pt-2 border-t border-slate-100">
              <Link
                href="/#products"
                onClick={() => setMobileMenuOpen(false)}
                className="flex items-center justify-between rounded-lg px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
              >
                <span>전체 상품</span>
                <span className="text-[10px] text-slate-400">→</span>
              </Link>
              <Link
                href="/#new-products"
                onClick={() => setMobileMenuOpen(false)}
                className="flex items-center justify-between rounded-lg px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
              >
                <span>신상품</span>
                <span className="text-[10px] text-slate-400">→</span>
              </Link>
              <Link
                href="/stores"
                onClick={() => setMobileMenuOpen(false)}
                className="flex items-center justify-between rounded-lg px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
              >
                <span>가게 목록</span>
                <span className="text-[10px] text-slate-400">→</span>
              </Link>
            </div>
          </div>
        )}
      </header>

      {/* 데스크톱 전용 하단 sticky nav */}
      <nav className="hidden md:block sticky top-0 z-40 border-y border-slate-200 bg-white shadow-sm">
        <div className="mx-auto flex h-12 max-w-7xl items-center px-4 text-sm font-medium sm:px-6 lg:px-8">
          <div className="flex gap-6 overflow-x-auto whitespace-nowrap text-slate-700">
            <Link href="/#products" className="font-bold text-blue-600 hover:text-blue-800">
              전체 상품
            </Link>
            <Link href="/#new-products" className="hover:text-blue-600">
              신상품
            </Link>
            <Link href="/stores" className="hover:text-blue-600">
              가게
            </Link>
          </div>
        </div>
      </nav>

      {openWallet && (
        <WalletConnectModal
          onClose={() => setOpenWallet(false)}
          onSignedIn={(user) => {
            setCurrentUser(user);
            setOpenWallet(false);
          }}
        />
      )}
    </>
  );
}

function shortWallet(value = "") {
  return value.length > 12 ? `${value.slice(0, 6)}...${value.slice(-4)}` : value;
}

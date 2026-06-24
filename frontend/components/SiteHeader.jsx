"use client";

import Link from "next/link";
import { ReceiptText, Search, ShoppingBag, ShoppingCart, Wallet, User } from "lucide-react";
import { useEffect, useState } from "react";
import WalletConnectModal from "./WalletConnectModal";
import { getCurrentUser, logout, apiJson } from "@/lib/auth-client";
import { loadCart } from "@/lib/cart";

export default function SiteHeader({ cartCount, currentUser: propCurrentUser, onCurrentUserChange }) {
  const [openWallet, setOpenWallet] = useState(false);
  const [localCurrentUser, setLocalCurrentUser] = useState(null);
  const [storedCartCount, setStoredCartCount] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);

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

      <header className="bg-white pt-5 pb-4">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-4 sm:px-6 md:flex-row lg:px-8">
          <Link href="/" className="flex shrink-0 items-center">
            <ShoppingBag className="mr-2 h-10 w-10 text-blue-600" />
            <div>
              <h1 className="text-2xl font-black leading-none tracking-normal text-slate-950">Skkrypto Market</h1>
            </div>
          </Link>

          <div className="flex w-full max-w-2xl flex-1">
            <div className="relative flex w-full items-center rounded-sm border-4 border-blue-600">
              <div className="hidden border-r border-slate-300 px-4 text-sm font-medium text-slate-500 sm:block">
                전체
              </div>
              <input
                type="search"
                className="w-full px-4 py-2.5 text-sm outline-none"
                placeholder="상품명이나 가게를 검색해보세요"
              />
              <button className="flex h-11 w-14 items-center justify-center text-blue-600 transition-colors hover:text-blue-700">
                <Search size={22} />
              </button>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-5">
            {currentUser && (
              <Link href="/profile" className="flex flex-col items-center text-slate-600 transition-colors hover:text-blue-600">
                <User size={25} />
                <span className="mt-1 text-[11px]">내 정보</span>
              </Link>
            )}
            <Link href="/orders" className="relative flex flex-col items-center text-slate-600 transition-colors hover:text-blue-600">
              <span className="relative">
                <ReceiptText size={25} />
                {pendingCount > 0 && (
                  <span className="absolute -right-2 -top-2 flex h-4 w-4 rounded-full bg-amber-500 border border-white" />
                )}
              </span>
              <span className="mt-1 text-[11px]">주문내역</span>
            </Link>
            <Link href="/cart" className="relative flex flex-col items-center text-slate-600 transition-colors hover:text-blue-600">
              <span className="relative">
                <ShoppingCart size={25} />
                <span className="absolute -right-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
                  {visibleCartCount}
                </span>
              </span>
              <span className="mt-1 text-[11px]">장바구니</span>
            </Link>
          </div>
        </div>
      </header>

      <nav className="sticky top-0 z-40 border-y border-slate-200 bg-white shadow-sm">
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

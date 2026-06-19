"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Check,
  CheckCircle2,
  Copy,
  Coins,
  Store,
  User,
  Wallet,
  ShieldAlert,
  Loader2,
  Star,
  Trash2,
  Plus,
  ExternalLink
} from "lucide-react";
import SiteHeader from "./SiteHeader";
import {
  getCurrentUser,
  getCurrentUserProfile,
  updateCurrentUserProfile,
  listMerchantStores,
  listWallets,
  requestWalletLinkChallenge,
  linkWallet,
  setPrimaryWallet,
  revokeWallet,
  listOAuthIdentities,
  requestOAuthAuthorization,
  revokeOAuthIdentity
} from "@/lib/auth-client";
import { ensureChain } from "@/lib/checkout-client";
import { isActiveWallet } from "@/lib/payment-options";

export default function Profile() {
  const [currentUser, setCurrentUser] = useState(null);
  const [profile, setProfile] = useState(null);
  const [stores, setStores] = useState([]);
  const [wallets, setWallets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [linkingWallet, setLinkingWallet] = useState(false);
  const [displayNameInput, setDisplayNameInput] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [copiedWallet, setCopiedWallet] = useState(null); // stores address of copied wallet
  const [isGoogleLinked, setIsGoogleLinked] = useState(false);
  const [googleIdentityId, setGoogleIdentityId] = useState(null);

  const [claimingState, setClaimingState] = useState({
    eth: false,
    usdc: false,
    usdt: false
  });

  const loadProfileData = async () => {
    setErrorMsg("");
    setSuccessMsg("");
    try {
      let userPayload = null;
      try {
        userPayload = await getCurrentUser();
      } catch (err) {
        console.log("User session not found or expired:", err);
      }

      if (!userPayload?.user) {
        setLoading(false);
        return;
      }

      setCurrentUser(userPayload.user);

      const [profileRes, storesRes, walletsRes, oauthRes] = await Promise.all([
        getCurrentUserProfile().catch((err) => {
          if (err.status !== 404 && err.body?.error?.code !== "USER_PROFILE_NOT_FOUND") {
            console.error("Profile fetch failed:", err);
          } else {
            console.log("No profile created yet for this user.");
          }
          return null;
        }),
        listMerchantStores().catch((err) => {
          console.error("Stores fetch failed:", err);
          return { stores: [] };
        }),
        listWallets().catch((err) => {
          console.error("Wallets fetch failed:", err);
          return { wallets: [] };
        }),
        listOAuthIdentities().catch((err) => {
          console.error("OAuth identities fetch failed:", err);
          return { oauthIdentities: [] };
        })
      ]);

      if (profileRes?.profile) {
        setProfile(profileRes.profile);
        setDisplayNameInput(profileRes.profile.displayName || "");
      }
      setStores(storesRes?.stores || []);
      setWallets((walletsRes?.wallets || []).filter(isActiveWallet));

      const googleIdentity = (oauthRes?.oauthIdentities || []).find(
        (identity) => identity.provider === "google" && !identity.revokedAt
      );
      setIsGoogleLinked(!!googleIdentity);
      setGoogleIdentityId(googleIdentity ? googleIdentity.oauthIdentityId : null);

      setLoading(false);
    } catch (err) {
      console.error("loadProfileData error:", err);
      setErrorMsg("프로필 정보를 불러오는 도중 오류가 발생했습니다.");
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfileData();
  }, []);

  const reloadWallets = async () => {
    try {
      const walletsRes = await listWallets();
      setWallets((walletsRes?.wallets || []).filter(isActiveWallet));
    } catch (err) {
      console.error("Failed to reload wallets:", err);
    }
  };

  const handleCopyWallet = (address) => {
    if (!address) return;
    navigator.clipboard.writeText(address);
    setCopiedWallet(address);
    setTimeout(() => setCopiedWallet(null), 2000);
  };

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    setErrorMsg("");
    setSuccessMsg("");
    setSaving(true);

    try {
      const trimmed = displayNameInput.trim();
      const updated = await updateCurrentUserProfile(trimmed);
      if (updated?.profile) {
        setProfile(updated.profile);
        setDisplayNameInput(updated.profile.displayName || "");
        setSuccessMsg("닉네임이 성공적으로 변경되었습니다.");
      }
    } catch (err) {
      console.warn("Update profile failed:", err);
      setErrorMsg(err.body?.error?.message || err.message || "프로필 저장 중 오류가 발생했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const handleSetPrimary = async (walletId) => {
    setErrorMsg("");
    setSuccessMsg("");
    try {
      await setPrimaryWallet(walletId);
      setSuccessMsg("대표 지갑이 설정되었습니다.");
      await reloadWallets();
      const userPayload = await getCurrentUser().catch(() => null);
      if (userPayload?.user) {
        setCurrentUser(userPayload.user);
      }
    } catch (err) {
      console.warn("Set primary wallet failed:", err);
      setErrorMsg(err.body?.error?.message || err.message || "대표 지갑 설정에 실패했습니다.");
    }
  };

  const handleRevoke = async (walletId, walletAddress) => {
    setErrorMsg("");
    setSuccessMsg("");
    if (wallets.length <= 1) {
      setErrorMsg("최소한 하나의 지갑은 연동되어 있어야 합니다.");
      return;
    }
    if (!confirm(`지갑(${shortWallet(walletAddress)}) 연동을 해제하시겠습니까?`)) {
      return;
    }
    try {
      await revokeWallet(walletId);
      setSuccessMsg("지갑 연동이 해제되었습니다.");
      await reloadWallets();
      const userPayload = await getCurrentUser().catch(() => null);
      if (userPayload?.user) {
        setCurrentUser(userPayload.user);
      }
    } catch (err) {
      console.warn("Revoke wallet failed:", err);
      setErrorMsg(err.body?.error?.message || err.message || "지갑 연동 해제에 실패했습니다.");
    }
  };

  const handleLinkNewWallet = async () => {
    setErrorMsg("");
    setSuccessMsg("");
    setLinkingWallet(true);

    const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
    if (!ethereum) {
      setErrorMsg("MetaMask가 설치되어 있지 않거나 브라우저 환경이 아닙니다.");
      setLinkingWallet(false);
      return;
    }

    try {
      try {
        await ethereum.request({
          method: "wallet_requestPermissions",
          params: [{ eth_accounts: {} }]
        });
      } catch (err) {
        console.warn("Wallet permissions request denied/cancelled:", err);
      }

      const accounts = await ethereum.request({ method: "eth_requestAccounts" });
      const account = accounts?.[0];
      if (!account) throw new Error("연결된 계정이 없습니다.");

      const alreadyLinked = wallets.some(
        (w) => w.walletAddress.toLowerCase() === account.toLowerCase()
      );
      if (alreadyLinked) {
        throw new Error("이미 이 계정에 연동된 지갑입니다.");
      }

      const chainHex = await ethereum.request({ method: "eth_chainId" });
      const chainId = parseChainId(chainHex);

      const challenge = await requestWalletLinkChallenge({
        walletAddress: account,
        domain: window.location.host,
        uri: window.location.origin,
        chainId
      });

      const signature = await ethereum.request({
        method: "personal_sign",
        params: [challenge.signingMessage, account]
      });

      await linkWallet({
        walletAddress: account,
        message: challenge.signingMessage,
        signature
      });

      setSuccessMsg("지갑이 성공적으로 추가되었습니다.");
      await reloadWallets();
      const userPayload = await getCurrentUser().catch(() => null);
      if (userPayload?.user) {
        setCurrentUser(userPayload.user);
      }
    } catch (err) {
      console.warn("Link wallet failed:", err);
      setErrorMsg(err.body?.error?.message || err.message || "지갑 추가에 실패했습니다.");
    } finally {
      setLinkingWallet(false);
    }
  };

  const handleLinkGoogle = async () => {
    setErrorMsg("");
    setSuccessMsg("");
    try {
      if (typeof document !== "undefined") {
        document.cookie = "oauth_mode=link; path=/; max-age=300;";
      }
      const payload = await requestOAuthAuthorization({
        provider: "google",
        redirectUri: `${window.location.origin}/oauth/callback`,
        mode: "link"
      });
      const authorizationUrl = payload?.oauthAuthorization?.authorizationUrl;
      if (authorizationUrl) {
        window.location.assign(authorizationUrl);
      } else {
        throw new Error("Google 연동 URL 생성 실패");
      }
    } catch (err) {
      console.warn("Link Google failed:", err);
      setErrorMsg(err.body?.error?.message || err.message || "Google 인증 요청에 실패했습니다.");
    }
  };

  const handleUnlinkGoogle = async () => {
    if (!googleIdentityId) return;
    setErrorMsg("");
    setSuccessMsg("");
    if (!confirm("Google 계정 연동을 해제하시겠습니까?")) {
      return;
    }
    try {
      await revokeOAuthIdentity(googleIdentityId);
      setSuccessMsg("Google 계정 연동이 해제되었습니다.");
      setIsGoogleLinked(false);
      setGoogleIdentityId(null);
      await loadProfileData();
    } catch (err) {
      console.warn("Unlink Google failed:", err);
      setErrorMsg(err.body?.error?.message || err.message || "Google 연동 해제에 실패했습니다.");
    }
  };

  const erc20TransferData = (to, amountMinorUnits) => {
    const address = String(to || "").toLowerCase().replace(/^0x/, "");
    const amount = BigInt(amountMinorUnits);
    const paddedAddress = address.padStart(64, "0");
    const paddedAmount = amount.toString(16).padStart(64, "0");
    return `0xa9059cbb${paddedAddress}${paddedAmount}`;
  };

  const handleFaucetClaim = async (type) => {
    setErrorMsg("");
    setSuccessMsg("");

    const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
    if (!ethereum) {
      setErrorMsg("MetaMask가 설치되어 있지 않거나 브라우저 환경이 아닙니다.");
      return;
    }

    setClaimingState((prev) => ({ ...prev, [type]: true }));

    try {
      await ensureChain(1337);

      const accounts = await ethereum.request({ method: "eth_requestAccounts" });
      const userAddress = accounts?.[0] || currentUser?.walletAddress;
      if (!userAddress) {
        throw new Error("연결된 지갑 주소를 찾을 수 없습니다.");
      }

      let txHash = "";
      const rpcUrl = "/testnet-rpc";
      const deployer = "0x32b31C74fE628e9164996f727F0D11A3C49EC27f";

      if (type === "eth") {
        const res = await fetch(rpcUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            method: "eth_sendTransaction",
            params: [
              {
                from: deployer,
                to: userAddress,
                value: "0x8ac7230489e80000", // 10 ETH in Wei
                gas: "0x21000"
              }
            ]
          })
        });
        const payload = await res.json();
        if (payload.error) throw new Error(payload.error.message || "ETH claim failed");
        txHash = payload.result;
      } else if (type === "usdc") {
        const usdcAddress = "0x4444444444444444444444444444444444444444";
        const data = erc20TransferData(userAddress, 100000000n); // 100 USDC (6 decimals)
        const res = await fetch(rpcUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            method: "eth_sendTransaction",
            params: [
              {
                from: deployer,
                to: usdcAddress,
                value: "0x0",
                data,
                gas: "0x186a0"
              }
            ]
          })
        });
        const payload = await res.json();
        if (payload.error) throw new Error(payload.error.message || "USDC claim failed");
        txHash = payload.result;
      } else if (type === "usdt") {
        const usdtAddress = "0x5555555555555555555555555555555555555555";
        const data = erc20TransferData(userAddress, 100000000n); // 100 USDT (6 decimals)
        const res = await fetch(rpcUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jsonrpc: "2.0",
            id: 1,
            method: "eth_sendTransaction",
            params: [
              {
                from: deployer,
                to: usdtAddress,
                value: "0x0",
                data,
                gas: "0x186a0"
              }
            ]
          })
        });
        const payload = await res.json();
        if (payload.error) throw new Error(payload.error.message || "USDT claim failed");
        txHash = payload.result;
      }

      setSuccessMsg(`${type.toUpperCase()} 테스트넷 코인이 정상적으로 지급되었습니다! (Tx: ${txHash.slice(0, 10)}...)`);
    } catch (err) {
      console.warn("Faucet claim failed:", err);
      setErrorMsg(err.message || `${type.toUpperCase()} 지급에 실패했습니다. Local Test Network(Ganache)를 확인하세요.`);
    } finally {
      setClaimingState((prev) => ({ ...prev, [type]: false }));
    }
  };

  const shortWallet = (value = "") => {
    return value.length > 12 ? `${value.slice(0, 6)}...${value.slice(-4)}` : value;
  };

  const getChainName = (chainId) => {
    const cid = Number(chainId);
    if (cid === 1) return "Ethereum Mainnet";
    if (cid === 11155111) return "Sepolia Testnet";
    if (cid === 137) return "Polygon";
    if (cid === 80001 || cid === 80002) return "Polygon Amoy";
    if (cid === 1337 || cid === 31337) return "Local Testnet";
    return `Chain ${chainId}`;
  };

  const getChainColor = (chainId) => {
    const cid = Number(chainId);
    if (cid === 1) return "bg-blue-50 text-blue-700 border-blue-100";
    if (cid === 137) return "bg-purple-50 text-purple-700 border-purple-100";
    if (cid === 1337 || cid === 31337) return "bg-amber-50 text-amber-700 border-amber-100";
    return "bg-slate-50 text-slate-700 border-slate-100";
  };

  function parseChainId(value) {
    const parsed = typeof value === "string" ? Number.parseInt(value, 16) : Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 1337;
  }

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col bg-slate-50 text-slate-800">
        <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />
        <div className="flex h-96 flex-grow flex-col items-center justify-center">
          <Loader2 className="h-10 w-10 animate-spin text-slate-650" />
          <span className="mt-4 text-slate-500 font-medium text-sm">프로필을 불러오는 중...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-800">
      <SiteHeader currentUser={currentUser} onCurrentUserChange={setCurrentUser} />

      <main className="flex-grow">
        {/* Simple & Premium Page Title */}
        <div className="border-b border-slate-200 bg-white px-6 py-8 shadow-sm">
          <div className="mx-auto max-w-6xl flex flex-col md:flex-row md:items-center md:justify-between gap-6">
            <div>
              <div className="flex items-center gap-3">
                <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
                  {profile?.displayName || "사용자 정보"}
                </h2>
                {isGoogleLinked ? (
                  <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 border border-emerald-100">
                    Google 인증 완료
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded-full bg-slate-150 px-2.5 py-0.5 text-xs font-semibold text-slate-500 border border-slate-200">
                    Google 미인증
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-sm text-slate-500">지갑 연동 관리 및 개인 설정을 단일 대시보드에서 제어합니다.</p>
            </div>

            <div className="flex gap-4 self-start md:self-auto text-sm">
              <div className="rounded-xl border border-slate-200 px-4 py-2 bg-slate-50/50">
                <div className="text-xs text-slate-400 font-medium">연동 지갑</div>
                <div className="text-base font-bold font-mono text-slate-800">{wallets.length}</div>
              </div>
              <div className="rounded-xl border border-slate-200 px-4 py-2 bg-slate-50/50">
                <div className="text-xs text-slate-400 font-medium">관리 상점</div>
                <div className="text-base font-bold font-mono text-slate-800">{stores.length}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Unified Profile Setting Layout */}
        <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
          
          {/* Notifications */}
          {errorMsg && (
            <div className="mb-6 flex items-start rounded-xl border border-red-200 bg-red-50 p-4 text-red-800 shadow-sm transition-all duration-300">
              <ShieldAlert className="mr-3 h-5 w-5 shrink-0 text-red-600" />
              <div>
                <p className="text-sm font-bold">오류</p>
                <p className="mt-1 text-xs text-red-700 leading-normal">{errorMsg}</p>
              </div>
            </div>
          )}
          {successMsg && (
            <div className="mb-6 flex items-start rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-800 shadow-sm transition-all duration-300">
              <CheckCircle2 className="mr-3 h-5 w-5 shrink-0 text-emerald-600" />
              <div>
                <p className="text-sm font-bold">성공</p>
                <p className="mt-1 text-xs text-emerald-700 leading-normal">{successMsg}</p>
              </div>
            </div>
          )}

          {!currentUser ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-16 text-center shadow-sm max-w-lg mx-auto mt-8">
              <Wallet className="mx-auto mb-5 h-16 w-16 text-slate-300" />
              <p className="mb-6 text-lg font-semibold text-slate-700">로그인이 필요합니다.</p>
              <p className="text-sm text-slate-400 mb-8 leading-relaxed">우측 상단의 [Connect] 버튼을 눌러 지갑을 연결한 뒤 세션을 발급받으세요.</p>
            </div>
          ) : (
            <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
              {/* Left Column: Combined Block (Profile, Google Verification, Wallet Management) */}
              <div>
                <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden divide-y divide-slate-100">
                  
                  {/* Part 1: Profile Nickname & Google Settings */}
                  <div className="p-6 sm:p-8">
                    <h3 className="text-lg font-bold text-slate-900 mb-6">계정 설정</h3>
                    
                    <div className="space-y-6">
                      {/* Nickname modification row */}
                      <form onSubmit={handleUpdateProfile} className="space-y-2 max-w-md">
                        <label htmlFor="displayName" className="block text-xs font-bold uppercase tracking-wider text-slate-400">
                          표시 닉네임
                        </label>
                        <div className="flex gap-2">
                          <input
                            id="displayName"
                            type="text"
                            className="flex-1 rounded-xl border border-slate-200 px-4 py-2.5 text-sm text-slate-800 placeholder-slate-400 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all bg-slate-50/50"
                            placeholder="표시할 이름을 입력해주세요"
                            value={displayNameInput}
                            onChange={(e) => setDisplayNameInput(e.target.value)}
                          />
                          <button
                            type="submit"
                            disabled={saving}
                            className="rounded-xl bg-slate-900 hover:bg-slate-800 disabled:bg-slate-350 px-5 py-2.5 text-xs font-bold text-white shadow-sm transition-all"
                          >
                            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "저장"}
                          </button>
                        </div>
                      </form>

                      {/* Google verification status row */}
                      <div className="pt-5 border-t border-slate-100 flex items-center justify-between flex-wrap gap-4">
                        <div>
                          <span className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-1">
                            Google 소셜 계정 연동
                          </span>
                          <div className="flex items-center gap-2">
                            {isGoogleLinked ? (
                              <>
                                <span className="text-sm font-semibold text-slate-700">Google 계정이 정상 연동되었습니다.</span>
                                <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] font-bold text-emerald-700 border border-emerald-100">
                                  연결됨
                                </span>
                              </>
                            ) : (
                              <>
                                <span className="text-sm font-medium text-slate-500">연결된 소셜 계정이 없습니다.</span>
                                <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-bold text-slate-500 border border-slate-200">
                                  미연결
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                        {isGoogleLinked ? (
                          <button
                            onClick={handleUnlinkGoogle}
                            className="text-xs font-bold text-red-650 bg-red-50 hover:bg-red-100 border border-red-200/50 px-4 py-2 rounded-xl transition-all"
                          >
                            연동 해제
                          </button>
                        ) : (
                          <button
                            onClick={handleLinkGoogle}
                            className="text-xs font-bold text-indigo-650 bg-indigo-50 hover:bg-indigo-100 border border-indigo-150/30 px-4 py-2 rounded-xl transition-all"
                          >
                            구글 연동하기
                          </button>
                        )}
                      </div>



                    </div>
                  </div>

                  {/* Part 2: Linked Wallets Management list */}
                  <div className="p-6 sm:p-8">
                    <div className="flex items-center justify-between mb-6">
                      <div>
                        <h3 className="text-lg font-bold text-slate-900">연동된 지갑 목록</h3>
                        <p className="text-xs text-slate-450 mt-1">결제 및 세션에 사용할 계정 지갑들을 관리합니다.</p>
                      </div>
                      <button
                        onClick={handleLinkNewWallet}
                        disabled={linkingWallet}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 px-4 py-2.5 text-xs font-bold text-white shadow-sm transition-all"
                      >
                        {linkingWallet ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Plus className="h-3.5 w-3.5" />
                        )}
                        지갑 추가
                      </button>
                    </div>

                    {wallets.length === 0 ? (
                      <div className="text-center py-10 rounded-xl border border-dashed border-slate-200 bg-slate-50/20">
                        <Wallet className="mx-auto mb-2 h-8 w-8 text-slate-300" />
                        <p className="text-xs font-semibold text-slate-550">연동된 계정 지갑이 없습니다.</p>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {wallets.map((wallet) => (
                          <div
                            key={wallet.walletId}
                            className={`flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border p-4 transition-all hover:bg-slate-50/30 ${
                              wallet.primary ? "border-slate-300 bg-slate-50/30" : "border-slate-200"
                            }`}
                          >
                            <div className="flex items-start gap-3">
                              <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500 font-mono text-[10px] font-bold">
                                W
                              </div>
                              <div className="space-y-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="font-mono text-sm font-bold text-slate-800">
                                    {shortWallet(wallet.walletAddress)}
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() => handleCopyWallet(wallet.walletAddress)}
                                    className="text-slate-400 hover:text-slate-600 transition-colors"
                                    title="주소 복사"
                                  >
                                    {copiedWallet === wallet.walletAddress ? (
                                      <Check className="h-3.5 w-3.5 text-emerald-500" />
                                    ) : (
                                      <Copy className="h-3.5 w-3.5" />
                                    )}
                                  </button>
                                  
                                  {wallet.primary && (
                                    <span className="inline-flex items-center gap-0.5 rounded-full bg-amber-500/10 px-2 py-0.5 text-[9px] font-bold text-amber-700 border border-amber-500/20">
                                      대표
                                    </span>
                                  )}
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className={`inline-block rounded-md border px-1.5 py-0.5 text-[9px] font-bold font-mono ${getChainColor(wallet.chainId)}`}>
                                    {getChainName(wallet.chainId)}
                                  </span>
                                </div>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 sm:self-center">
                              {!wallet.primary && (
                                <button
                                  onClick={() => handleSetPrimary(wallet.walletId)}
                                  className="text-[10px] font-bold text-slate-500 hover:text-indigo-650 bg-slate-100 hover:bg-indigo-50 border border-slate-200 hover:border-indigo-100 px-2.5 py-1.5 rounded-lg transition-all"
                                >
                                  대표 지정
                                </button>
                              )}
                              <button
                                onClick={() => handleRevoke(wallet.walletId, wallet.walletAddress)}
                                className="inline-flex items-center justify-center p-1.5 text-slate-400 hover:text-red-650 hover:bg-red-50 rounded-lg border border-transparent hover:border-red-100 transition-all"
                                title="연동 해제"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Part 3: Developer Tools - Testnet Faucet */}
                  <div className="p-6 sm:p-8 bg-slate-50/20">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="block text-xs font-bold uppercase tracking-wider text-indigo-750 bg-indigo-50 border border-indigo-100 px-2.5 py-0.5 rounded-md">
                        테스트넷 Faucet                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mb-4 leading-relaxed">
                      로컬 검증 네트워크(Ganache)용 가상 자산(ETH, USDC, USDT)을 대표 지갑에 청구합니다.
                    </p>
                    <div className="flex flex-wrap gap-3">
                      {/* ETH claim */}
                      <button
                        type="button"
                        onClick={() => handleFaucetClaim("eth")}
                        disabled={claimingState.eth}
                        className="inline-flex items-center gap-2 rounded-xl bg-indigo-50 hover:bg-indigo-100 border border-indigo-200/50 px-4 py-2 hover:border-indigo-300/50 transition-all text-xs font-bold text-indigo-700 disabled:opacity-50 shadow-sm"
                      >
                        {claimingState.eth ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-500" />
                        ) : (
                          <Coins className="h-3.5 w-3.5 text-indigo-500" />
                        )}
                        <span>10 ETH 청구</span>
                      </button>

                      {/* USDC claim */}
                      <button
                        type="button"
                        onClick={() => handleFaucetClaim("usdc")}
                        disabled={claimingState.usdc}
                        className="inline-flex items-center gap-2 rounded-xl bg-blue-50 hover:bg-blue-100 border border-blue-200/50 px-4 py-2 hover:border-blue-300/50 transition-all text-xs font-bold text-blue-700 disabled:opacity-50 shadow-sm"
                      >
                        {claimingState.usdc ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
                        ) : (
                          <Coins className="h-3.5 w-3.5 text-blue-500" />
                        )}
                        <span>100 USDC 청구</span>
                      </button>

                      {/* USDT claim */}
                      <button
                        type="button"
                        onClick={() => handleFaucetClaim("usdt")}
                        disabled={claimingState.usdt}
                        className="inline-flex items-center gap-2 rounded-xl bg-teal-50 hover:bg-teal-100 border border-teal-200/50 px-4 py-2 hover:border-teal-300/50 transition-all text-xs font-bold text-teal-700 disabled:opacity-50 shadow-sm"
                      >
                        {claimingState.usdt ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-teal-500" />
                        ) : (
                          <Coins className="h-3.5 w-3.5 text-teal-500" />
                        )}
                        <span>100 USDT 청구</span>
                      </button>
                    </div>
                  </div>

                </div>
              </div>

              {/* Right Column: Auxiliary Widgets (Shop Permissions) */}
              <div className="space-y-6">
                
                {/* Belongs to Stores Permissions */}
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center gap-2 border-b border-slate-100 pb-3 mb-4">
                    <Store className="h-4.5 w-4.5 text-slate-550" />
                    <h4 className="font-bold text-slate-900 text-sm">소속 상점 목록</h4>
                  </div>

                  {stores.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-6 text-center border border-dashed border-slate-200 rounded-xl">
                      <p className="text-[10px] font-semibold text-slate-455">속한 상점이 없습니다.</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-100">
                      {stores.map((store) => (
                        <div key={store.publicStoreId} className="py-3 first:pt-0 last:pb-0 flex items-center justify-between gap-2">
                          <div className="truncate">
                            <h5 className="font-bold text-slate-800 text-xs truncate">{store.displayName}</h5>
                            <span className="text-[9px] text-slate-400 block font-mono mt-0.5">ID: {store.publicStoreId}</span>
                          </div>
                          <Link
                            href={`/stores/${store.publicStoreId}`}
                            className="shrink-0 inline-flex items-center gap-0.5 text-[9px] font-bold text-indigo-650 bg-indigo-50/50 hover:bg-indigo-100/50 px-2.5 py-1.5 rounded-lg transition-colors border border-indigo-100/50"
                          >
                            이동
                            <ExternalLink className="h-2.5 w-2.5" />
                          </Link>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

              </div>
            </div>
          )}

        </div>
      </main>
    </div>
  );
}

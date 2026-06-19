"use client";

import { CheckCircle2, Chrome, Loader2, TriangleAlert, X } from "lucide-react";
import { useState } from "react";
import {
  browserSiweContext,
  ensureLocalTestnet,
  loginWithMetaMask,
  newBrowserDeviceId,
  requestLoginChallenge,
  requestOAuthAuthorization
} from "@/lib/auth-client";

export default function WalletConnectModal({ onClose, onSignedIn }) {
  const [wallet, setWallet] = useState("");
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const [user, setUser] = useState(null);
  const [availableAccounts, setAvailableAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState("");
  const metaMaskBusy = ["connecting", "challenge", "signing", "session"].includes(status);

  async function connect() {
    const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
    if (!ethereum?.request) {
      setStatus("error");
      setMessage("MetaMask를 사용할 수 없습니다.");
      return;
    }

    setStatus("connecting");
    setMessage("네트워크 및 지갑 연결을 설정하는 중입니다.");
    try {
      await ensureLocalTestnet();

      try {
        await ethereum.request({
          method: "wallet_requestPermissions",
          params: [{ eth_accounts: {} }]
        });
      } catch (permissionError) {
        console.warn("지갑 권한 요청 거부됨:", permissionError);
      }
      const accounts = await ethereum.request({ method: "eth_requestAccounts" });
      if (!accounts || accounts.length === 0) {
        throw new Error("연결된 계정이 없습니다.");
      }

      setAvailableAccounts(accounts);
      setSelectedAccount(accounts[0]);
      setStatus("select-account");
      setMessage("로그인에 사용할 지갑을 선택해 주세요.");
    } catch (error) {
      setStatus("error");
      setMessage(error?.code ? `${error.code}: ${error.message}` : error?.message || "지갑 연결에 실패했습니다.");
    }
  }

  async function proceedLogin() {
    const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
    if (!ethereum?.request) {
      setStatus("error");
      setMessage("MetaMask를 사용할 수 없습니다.");
      return;
    }
    if (!selectedAccount) {
      setStatus("error");
      setMessage("선택된 지갑 계정이 없습니다.");
      return;
    }

    setWallet(selectedAccount);
    setStatus("challenge");
    setMessage("로그인 메시지를 발급하는 중입니다.");
    try {
      const chainHex = await ethereum.request({ method: "eth_chainId" });
      const chainId = parseChainId(chainHex);
      const challenge = await requestLoginChallenge({
        walletAddress: selectedAccount,
        ...browserSiweContext(chainId)
      });

      setStatus("signing");
      setMessage("MetaMask에서 로그인 메시지에 서명해 주세요.");
      const signature = await ethereum.request({
        method: "personal_sign",
        params: [challenge.signingMessage, selectedAccount]
      });

      setStatus("session");
      setMessage("서비스 세션을 생성하는 중입니다.");
      const login = await loginWithMetaMask({
        walletAddress: selectedAccount,
        message: challenge.signingMessage,
        signature,
        deviceId: newBrowserDeviceId()
      });

      setStatus("signed-in");
      setUser(login.user);
      setMessage("로그인되었습니다.");
      onSignedIn?.(login.user);
    } catch (error) {
      setStatus("error");
      setMessage(error?.code ? `${error.code}: ${error.message}` : error?.message || "로그인 서명에 실패했습니다.");
    }
  }

  async function startGoogleOAuth() {
    if (typeof window === "undefined") return;
    setStatus("oauth");
    setMessage("Google 로그인 페이지로 이동하는 중입니다.");
    try {
      if (typeof document !== "undefined") {
        document.cookie = "oauth_mode=login; path=/; max-age=300;";
      }
      const payload = await requestOAuthAuthorization({
        provider: "google",
        redirectUri: `${window.location.origin}/oauth/callback`,
        mode: "login"
      });
      const authorizationUrl = payload?.oauthAuthorization?.authorizationUrl;
      if (!authorizationUrl) throw new Error("Google authorization URL을 받지 못했습니다.");
      window.location.assign(authorizationUrl);
    } catch (error) {
      setStatus("error");
      setMessage(error?.code ? `${error.code}: ${error.message}` : error?.message || "Google 로그인 시작에 실패했습니다.");
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 backdrop-blur-sm"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-sm overflow-hidden rounded-2xl border border-slate-100 bg-white p-6 shadow-2xl">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
        >
          <X size={18} />
        </button>
        <div className="mt-2 mb-8 text-center">
          <h2 className="mt-3 text-xl font-bold tracking-normal text-slate-950">서비스 연결하기</h2>
          <p className="mt-1.5 text-xs leading-relaxed text-slate-500">디지털 지갑을 연동하거나 간편하게 로그인하세요.</p>
        </div>
        <button
          onClick={connect}
          disabled={status !== "idle" && status !== "error" && status !== "signed-in"}
          className="flex w-full items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-4 py-3.5 font-bold text-slate-950 transition active:scale-[0.99] disabled:cursor-wait disabled:opacity-75"
        >
          <span className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-orange-500 text-xs font-black text-white">M</span>
            <span className="text-sm">{status === "signed-in" ? "MetaMask 로그인 완료" : "MetaMask 지갑 로그인"}</span>
          </span>
          {metaMaskBusy && <Loader2 className="h-4 w-4 animate-spin" />}
        </button>
        <button
          onClick={startGoogleOAuth}
          disabled={status !== "idle" && status !== "error" && status !== "signed-in"}
          className="mt-3 flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3.5 font-bold text-slate-950 shadow-sm transition active:scale-[0.99] disabled:cursor-wait disabled:opacity-75"
        >
          <span className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-white">
              <Chrome size={16} />
            </span>
            <span className="text-sm">Google로 계속하기</span>
          </span>
          {status === "oauth" && <Loader2 className="h-4 w-4 animate-spin" />}
        </button>
        {status === "select-account" && availableAccounts.length > 0 && (
          <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 p-4">
            <p className="mb-2 text-left text-xs font-bold text-slate-500">로그인할 지갑 선택</p>
            <div className="max-h-40 overflow-y-auto space-y-2">
              {availableAccounts.map((acc) => (
                <button
                  key={acc}
                  onClick={() => setSelectedAccount(acc)}
                  className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-xs font-mono transition ${
                    selectedAccount === acc
                      ? "border-blue-600 bg-blue-50 text-blue-900 font-bold"
                      : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <span className="truncate">{shortWallet(acc)}</span>
                  {selectedAccount === acc && <span className="text-blue-600 font-extrabold">✓</span>}
                </button>
              ))}
            </div>
            <button
              onClick={proceedLogin}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 py-3 text-center text-sm font-bold text-white transition active:scale-[0.99]"
            >
              선택한 지갑으로 로그인
            </button>
          </div>
        )}
        {message && (
          <div
            className={`mt-4 flex gap-2 rounded-lg p-3 text-xs ${
              status === "error" ? "bg-red-50 text-red-700" : "bg-slate-50 text-slate-600"
            }`}
          >
            {status === "signed-in" ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            ) : status === "error" ? (
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
            ) : (
              <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin" />
            )}
            <span>{message}</span>
          </div>
        )}
        {user && (
          <p className="mt-3 rounded-lg bg-emerald-50 p-3 text-xs font-medium text-emerald-700">
            {shortWallet(user.walletAddress)} 계정으로 로그인됨
          </p>
        )}
      </div>
    </div>
  );
}

function shortWallet(value = "") {
  return value.length > 12 ? `${value.slice(0, 6)}...${value.slice(-4)}` : value;
}

function parseChainId(value) {
  const parsed = typeof value === "string" ? Number.parseInt(value, 16) : Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1337;
}

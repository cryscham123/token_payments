"use client";

import Link from "next/link";
import { CheckCircle2, Loader2, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { linkOAuthIdentity } from "@/lib/auth-client";
import { completeOAuthSession } from "@/lib/checkout-client";

export default function OAuthCallback() {
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("로그인을 완료하는 중입니다.");

  useEffect(() => {
    async function complete() {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");
      const state = params.get("state");
      const error = params.get("error");

      if (error) {
        setStatus("error");
        setMessage(error);
        return;
      }
      if (!code || !state) {
        setStatus("error");
        setMessage("OAuth callback code 또는 state가 없습니다.");
        return;
      }

      try {
        const oauthMode = typeof document !== "undefined"
          ? document.cookie.split("; ").find(row => row.startsWith("oauth_mode="))?.split("=")[1] || "login"
          : "login";

        if (oauthMode === "link") {
          await linkOAuthIdentity({
            provider: "google",
            code,
            state,
            redirectUri: `${window.location.origin}/oauth/callback`
          });
          setStatus("success");
          setMessage("소셜 계정이 성공적으로 연동되었습니다.");
          window.setTimeout(() => window.location.assign("/profile"), 600);
        } else {
          await completeOAuthSession({
            provider: "google",
            code,
            state,
            redirectUri: `${window.location.origin}/oauth/callback`
          });
          setStatus("success");
          setMessage("로그인되었습니다.");
          window.setTimeout(() => window.location.assign("/"), 600);
        }
      } catch (requestError) {
        setStatus("error");
        setMessage(requestError?.code ? `${requestError.code}: ${requestError.message}` : requestError?.message || "OAuth 처리 중 오류가 발생했습니다.");
      }
    }

    complete();
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-xl">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100">
          {status === "loading" ? (
            <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
          ) : status === "success" ? (
            <CheckCircle2 className="h-6 w-6 text-emerald-600" />
          ) : (
            <TriangleAlert className="h-6 w-6 text-red-600" />
          )}
        </div>
        <h1 className="mb-2 text-xl font-bold text-slate-950">Google 로그인</h1>
        <p className={`mb-6 break-words text-sm ${status === "error" ? "text-red-700" : "text-slate-500"}`}>{message}</p>
        <Link href="/" className="inline-flex rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white">
          홈으로 이동
        </Link>
      </div>
    </main>
  );
}

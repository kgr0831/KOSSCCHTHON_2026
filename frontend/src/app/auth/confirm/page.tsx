"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useAppNavigation } from "@/components/app-navigation";
import { useAuth } from "@/components/providers";
import { api, jsonBody } from "@/lib/api";
import { clearAuthLocation } from "@/lib/auth-location";
import { ErrorMessage, Loading, PageHeading } from "@/components/ui";

export default function Confirm() {
  const started = useRef(false), saved = useRef<{ token: string | null; purpose: string | null } | null>(null);
  const { login, user, ready } = useAuth(), client = useQueryClient();
  const { finishLogin } = useAppNavigation();
  const [error, setError] = useState<unknown>(), [needsLogin, setNeedsLogin] = useState(false);
  useEffect(() => {
    if (!saved.current) {
      const fragment = new URLSearchParams(window.location.hash.slice(1));
      saved.current = { token: fragment.get("token"), purpose: fragment.get("purpose") };
      clearAuthLocation("/auth/confirm");
    }
    if (!ready || started.current) return;
    const { token, purpose } = saved.current;
    const paths: Record<string, string> = { school: "/auth/school-email-verifications", login: "/auth/login-links", company: "/auth/company-email-verifications", school_attach: "/me/school-email-verifications" };
    if (!token || !purpose || !paths[purpose]) { started.current = true; setError(new Error("유효한 인증 링크를 열어 주세요.")); return; }
    if ((purpose === "school_attach" || purpose === "company") && !user) { setNeedsLogin(true); return; }
    started.current = true; setNeedsLogin(false);
    api<{ access_token?: string }>(`${paths[purpose]}/confirm`, { method: "POST", body: jsonBody({ token }) })
      .then(async result => { if (result.access_token) await login(result.access_token); await client.invalidateQueries(); finishLogin(); }).catch(setError);
  }, [login, user, ready, finishLogin, client]);
  return <><PageHeading title="이메일을 확인하고 있어요" description="인증을 요청한 계정으로 로그인해 주세요." />{error ? <ErrorMessage error={error} /> : needsLogin ? <div className="panel stack"><p>인증을 요청한 계정으로 로그인한 다음, 이메일의 링크를 다시 열어 주세요.</p><Link className="button primary" href="/auth">로그인하기</Link></div> : <Loading />}</>;
}

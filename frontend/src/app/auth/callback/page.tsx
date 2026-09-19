"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers";
import { useAppNavigation } from "@/components/app-navigation";
import { ErrorMessage, Loading, PageHeading } from "@/components/ui";
import { api, jsonBody } from "@/lib/api";
import { clearAuthLocation } from "@/lib/auth-location";

export default function Callback() {
  const saved = useRef<{ code: string | null; failed: boolean } | null>(null), started = useRef(false);
  const { login, ready } = useAuth(), { finishLogin } = useAppNavigation();
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    if (!saved.current) {
      const params = new URLSearchParams(window.location.search);
      saved.current = { code: params.get("code"), failed: params.has("error") };
      clearAuthLocation("/auth/callback");
    }
    if (!ready || started.current) return;
    started.current = true;
    const { code, failed } = saved.current;
    if (!code || failed) { setError(new Error("Google 로그인이 완료되지 않았어요. 다시 시도해 주세요.")); return; }
    api<{ access_token: string }>("/auth/google/callback", { method: "POST", body: jsonBody({ code }) })
      .then(async result => { await login(result.access_token); finishLogin(); }).catch(setError);
  }, [login, ready, finishLogin]);
  return <><PageHeading title="Google 로그인을 확인하고 있어요" description="로그인을 시작한 브라우저에서 잠시 기다려 주세요." />{error ? <><ErrorMessage error={error} /><Link className="button" href="/auth">로그인 다시 시도</Link></> : <Loading />}</>;
}

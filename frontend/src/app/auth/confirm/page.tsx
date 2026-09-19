"use client";

import { useEffect, useRef, useState } from "react";
import { useAppNavigation } from "@/components/app-navigation";
import { useAuth } from "@/components/providers";
import { api, jsonBody } from "@/lib/api";
import { ErrorMessage, Loading, PageHeading } from "@/components/ui";

export default function Confirm() {
  const started = useRef(false);
  const { login } = useAuth();
  const { finishLogin } = useAppNavigation();
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const token = fragment.get("token");
    const purpose = fragment.get("purpose");
    window.history.replaceState({ ...window.history.state }, "", "/auth/confirm");
    const paths: Record<string, string> = { school: "school-email-verifications", login: "login-links", company: "company-email-verifications" };
    if (!token || !purpose || !paths[purpose]) { setError(new Error("유효한 인증 링크를 열어 주세요.")); return; }
    api<{ access_token?: string }>(`/auth/${paths[purpose]}/confirm`, { method: "POST", body: jsonBody({ token }) })
      .then(async result => { if (result.access_token) await login(result.access_token); finishLogin(); }).catch(setError);
  }, [login, finishLogin]);
  return <><PageHeading title="이메일을 확인하고 있어요" description="잠시만 기다려 주세요. 인증을 마치면 프로필로 이동합니다." />{error ? <ErrorMessage error={error} /> : <Loading />}</>;
}

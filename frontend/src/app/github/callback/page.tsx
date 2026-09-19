"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "@/components/app-navigation";
import { useAuth } from "@/components/providers";
import { ErrorMessage, Loading, PageHeading } from "@/components/ui";
import { api, jsonBody } from "@/lib/api";
import { clearAuthLocation } from "@/lib/auth-location";

type CallbackValues = { code: string | null; state: string | null; failed: boolean };

export default function GithubCallbackPage() {
  const saved = useRef<CallbackValues | null>(null);
  const started = useRef(false);
  const { ready, user } = useAuth();
  const router = useRouter();
  const client = useQueryClient();
  const [error, setError] = useState<unknown>();

  const exchange = async () => {
    const values = saved.current;
    if (!values?.code || !values.state || values.failed) {
      setError(new Error("GitHub 연결을 완료하지 못했어요. 자료 화면에서 다시 연결해 주세요."));
      return;
    }
    setError(null);
    try {
      await api("/auth/github/callback", { method: "POST", body: jsonBody({ code: values.code, state: values.state }) });
      await Promise.all([
        client.invalidateQueries({ queryKey: ["external-accounts"] }),
        client.invalidateQueries({ queryKey: ["materials"] }),
      ]);
      router.replace("/materials");
    } catch (reason) {
      setError(reason);
    }
  };

  useEffect(() => {
    if (!saved.current) {
      const params = new URLSearchParams(window.location.search);
      saved.current = { code: params.get("code"), state: params.get("state"), failed: params.has("error") };
      clearAuthLocation("/github/callback");
    }
    if (!ready || started.current) return;
    started.current = true;
    if (!user) {
      setError(new Error("GitHub 연결을 시작한 계정으로 다시 로그인한 뒤, 자료 화면에서 연결해 주세요."));
      return;
    }
    void exchange();
  }, [ready, user]); // The one-time values intentionally stay only in the ref above.

  return <><PageHeading title="GitHub 연결을 확인하고 있어요" description="연결 정보를 안전하게 확인한 뒤 자료 화면으로 이동합니다." />{error ? <div className="panel stack"><ErrorMessage error={error} /><button className="button primary" type="button" onClick={() => void exchange()}>다시 시도</button></div> : <Loading />}</>;
}

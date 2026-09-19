"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "./providers";
import { ErrorMessage } from "./ui";

export function GoogleSignIn({ link = false }: { link?: boolean }) {
  const { ready } = useAuth();
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>();
  async function start() {
    setBusy(true); setError(undefined);
    try {
      const result = await api<{ url: string }>(link ? "/auth/google/link" : "/auth/google", { method: "POST" });
      window.location.assign(result.url);
    } catch (failure) { setError(failure); setBusy(false); }
  }
  return <div className="stack"><button className="button primary" disabled={busy || !ready} onClick={start}>{busy ? "Google로 이동하고 있어요…" : link ? "이 계정에 Google 연결" : "Google로 시작하기"}</button><ErrorMessage error={error} /></div>;
}

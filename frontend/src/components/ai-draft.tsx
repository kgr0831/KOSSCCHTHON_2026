"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useRouter } from "@/components/app-navigation";
import { api, jsonBody, type Subscription } from "@/lib/api";
import { ErrorMessage } from "./ui";

export default function AIDraft({ kind, text, onApply }: { kind: "profile" | "experience" | "recruitment" | "career"; text: string; onApply: (value: { title: string; text: string }) => void }) {
  const router = useRouter();
  const subscription = useQuery({ queryKey: ["subscription"], queryFn: () => api<Subscription>("/me/subscription") });
  const [busy, setBusy] = useState(false), [consent, setConsent] = useState(false), [error, setError] = useState<unknown>();
  const [draft, setDraft] = useState<{ title: string; text: string; questions: string[] }>();
  async function generate() { if (subscription.data?.plan !== "premium") { router.push("/pricing"); return; } setBusy(true); setError(null); try { setDraft(await api("/ai/writing-drafts", { method: "POST", body: jsonBody({ kind, text }) })); } catch (e) { setError(e); } finally { setBusy(false); } }
  return <div className="ai-draft"><details><summary><Sparkles size={16} /> AI로 문장 다듬기</summary><div className="stack tight"><p className="muted">작성한 내용과 공개 프로필을 연결한 AI에 전달해요. 직접 적용한 다음 저장할 수 있어요.</p><label className="check-row"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> AI 전송에 동의합니다.</label><div className="card-actions"><button type="button" className="button subtle" disabled={busy || !consent || !text.trim()} onClick={generate}>{busy ? "초안 작성 중…" : "초안 만들기"}</button><Link className="text-link" href="/settings/ai">AI 연결</Link></div><ErrorMessage error={error} />{draft && <div className="ai-proposal"><strong>{draft.title}</strong><p data-selectable>{draft.text}</p>{draft.questions.map((q, i) => <p className="muted" key={i}>{q}</p>)}<button type="button" className="button primary" onClick={() => { onApply(draft); setDraft(undefined); }}>이 초안을 편집창에 적용</button></div>}</div></details></div>;
}

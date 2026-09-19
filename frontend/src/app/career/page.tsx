"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowRight, Flag, Route, Sparkles } from "lucide-react";
import { api, jsonBody, type Career } from "@/lib/api";
import { useAuth } from "@/components/providers";
import { AuthGate, ErrorMessage, Field } from "@/components/ui";

type Plan = { id: string; goal: string; content: { headline: string; insight: string; steps: { title: string; description: string; actions: string[] }[] } };
export default function CareerPage() { return <AuthGate><CareerMap /></AuthGate>; }
function CareerMap() {
  const { user } = useAuth(), client = useQueryClient();
  const [goal, setGoal] = useState(""), [consent, setConsent] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>();
  const [selected, setSelected] = useState("");
  const careers = useQuery({ queryKey: ["career-events"], queryFn: () => api<{ items: Career[] }>("/me/career-events") });
  const plans = useQuery({ queryKey: ["career-plans"], queryFn: () => api<{ items: Plan[] }>("/me/career-plans") });
  const plan = plans.data?.items.find(x => x.id === selected) || plans.data?.items[0];
  async function generate() { setBusy(true); setError(null); try { const row = await api<Plan>("/me/career-plans", { method: "POST", body: jsonBody({ goal, consent }) }); setSelected(row.id); await client.invalidateQueries({ queryKey: ["career-plans"] }); } catch (e) { setError(e); } finally { setBusy(false); } }
  return <div className="career-page"><section className="career-hero gradient-card"><div><span className="eyebrow">MY CAREER MAP</span><h1>커리어맵</h1><p>{user?.profile.display_name}님의 경험에서 시작하는<br />다음 가능성을 그려보세요.</p></div><Route size={76} strokeWidth={1.2} /></section><div className="career-layout"><div className="stack"><section className="panel"><div className="section-title"><h2>지금까지 걸어온 길</h2><Link className="text-link" href="/profile#experience">경험 기록 <ArrowRight size={15} /></Link></div><div className="career-route"><span className="route-start">나의 시작</span>{careers.data?.items.map(x => <div className="route-step" key={x.id}><span className="route-dot" /><small>{x.started_on || "날짜 미입력"}</small><h3>{x.title}</h3><p>{x.description}</p></div>)}{!careers.data?.items.length && <p className="muted">첫 경험을 기록하면 이곳에서 나의 길을 볼 수 있어요.</p>}<span className="route-next"><Flag size={16} /> 나의 다음 단계</span></div></section>{plan && <><section className="panel"><span className="badge purple">AI가 제안한 미래 계획</span><h2>{plan.content.headline}</h2><p className="muted">목표: {plan.goal}</p><div className="career-plan-steps">{plan.content.steps.map((step, i) => <article key={i}><span className="step-number">{String(i + 1).padStart(2, "0")}</span><div><h3>{step.title}</h3><p>{step.description}</p><ul>{step.actions.map((x, n) => <li key={n}>{x}</li>)}</ul></div></article>)}</div></section><section className="ai-insight"><Sparkles size={23} /><div><h2>다음 한 걸음을 위한 AI 인사이트</h2><p>{plan.content.insight}</p><Link className="text-link" href="/explore">함께 성장할 동문 찾기 <ArrowRight size={16} /></Link></div></section></>}</div><aside className="stack"><section className="panel stack"><h2>어디로 나아가고 싶나요?</h2><Field label="나의 목표"><textarea rows={5} value={goal} maxLength={3000} onChange={e => setGoal(e.target.value)} placeholder="예: 이번 학기에 프론트엔드 프로젝트를 완성하고 인턴 지원을 준비하고 싶어요." /></Field><label className="check-row"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> 공개 프로필과 목표를 AI에 전송하는 데 동의합니다.</label><button className="button primary" disabled={busy || !goal.trim() || !consent} onClick={generate}><Sparkles size={17} />{busy ? "계획을 구성하는 중…" : "Claude와 커리어맵 만들기"}</button><Link className="text-link" href="/settings/ai">AI 연결 설정</Link><p className="muted">완료된 계획은 DB에 저장돼요. 미래 제안은 이미 이룬 경력에 추가되지 않습니다.</p></section>{!!plans.data?.items.length && <section className="panel stack"><h2>저장된 계획</h2>{plans.data.items.map(x => <button key={x.id} className={`history-item ${plan?.id === x.id ? "selected" : ""}`} onClick={() => setSelected(x.id)}>{x.goal}</button>)}</section>}</aside></div><ErrorMessage error={error || careers.error || plans.error} /></div>;
}

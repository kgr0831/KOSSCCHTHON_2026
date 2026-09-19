"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Sparkles } from "lucide-react";
import { AuthGate, ErrorMessage, Loading, PageHeading } from "@/components/ui";
import { api, jsonBody, type Subscription, type SubscriptionPlan } from "@/lib/api";

const plans: { id: SubscriptionPlan; name: string; price: string; description: string; features: string[] }[] = [
  { id: "free", name: "Free", price: "월간 기회 5회", description: "자료 연결과 직접 작성으로 이야기를 정리해요.", features: ["GitHub·LinkedIn·파일 자료 연결", "프로필·경험 직접 편집", "커피챗 요청·모집 게시·참여 지원 월 5회"] },
  { id: "premium", name: "Premium", price: "월간 기회 20회", description: "개인 AI 생성 도구와 더 넉넉한 연결 기회를 사용할 수 있어요.", features: ["포트폴리오 AI 생성", "CV·프로필·커버레터 AI 생성", "커피챗 요청·모집 게시·참여 지원 월 20회"] },
];

export default function PricingPage() {
  return <><PageHeading eyebrow="PLANS FOR YOUR NEXT CHAPTER" title="요금제와 AI 생성 범위" description="필요한 AI 생성 범위와 월간 연결 기회를 선택하세요. 결제 수단을 입력하거나 실제 결제를 처리하지는 않아요." /><AuthGate><Pricing /></AuthGate></>;
}

function Pricing() {
  const client = useQueryClient();
  const subscription = useQuery({ queryKey: ["subscription"], queryFn: () => api<Subscription>("/me/subscription") });
  const [busy, setBusy] = useState<SubscriptionPlan | null>(null);
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  const currentPlan = subscription.data?.plan;

  async function selectPlan(plan: SubscriptionPlan) {
    if (busy || currentPlan === plan) return;
    setBusy(plan); setError(null); setMessage("");
    try {
      const next = await api<Subscription>("/me/subscription", { method: "PUT", body: jsonBody({ plan }) });
      client.setQueryData(["subscription"], next);
      await client.invalidateQueries({ queryKey: ["subscription"] });
      await client.invalidateQueries({ queryKey: ["rewards"] });
      setMessage(`${plans.find(item => item.id === next.plan)?.name || next.plan} 플랜을 선택했어요. 결제는 처리되지 않았어요.`);
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(null);
    }
  }

  return <section className="stack">
    <p className="notice info"><strong>결제 처리 없음</strong> 현재 이 화면은 기능 플랜을 선택하는 용도이며, 카드나 계좌 정보는 입력·저장·결제되지 않아요.</p>
    {subscription.isPending ? <Loading /> : <div className="grid-2" aria-label="요금제 선택">
      {plans.map(plan => {
        const current = currentPlan === plan.id;
        return <article className="panel stack" key={plan.id} aria-label={`${plan.name} 플랜${current ? ", 현재 이용 중" : ""}`}>
          <div className="subheading"><h2>{plan.name}</h2>{current && <span className="badge purple"><Check size={12} /> 현재 이용 중</span>}</div>
          <p><strong>{plan.price}</strong></p>
          <p className="muted">{plan.description}</p>
          <ul>{plan.features.map(feature => <li key={feature}>{feature}</li>)}</ul>
          <button className={current ? "button subtle" : "button primary"} type="button" disabled={Boolean(busy) || current} onClick={() => void selectPlan(plan.id)}>{busy === plan.id ? "선택 중…" : current ? "현재 플랜" : `${plan.name} 선택`}</button>
        </article>;
      })}
    </div>}
    <ErrorMessage error={error || subscription.error} />
    {message && <p className="notice" role="status">{message}</p>}
    <p className="muted">Premium에서는 포트폴리오, CV, 프로필, 커버레터 AI 생성을 사용할 수 있고, 커피챗 요청·모집 게시·참여 지원은 합산 월 20회까지 할 수 있어요.</p>
  </section>;
}

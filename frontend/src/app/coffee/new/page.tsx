"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "@/components/app-navigation";
import { useQuery } from "@tanstack/react-query";
import { Plus, Sparkles, Trash2 } from "lucide-react";
import { api, timezone, type Coffee, type UserPublic } from "@/lib/api";
import { useCommand } from "@/lib/hooks";
import { AuthGate, ErrorMessage, Field, Loading, PageHeading, Submit } from "@/components/ui";

function Content() {
  const params = useSearchParams();
  const recipient = params.get("recipient");
  const router = useRouter();
  const user = useQuery({ queryKey: ["user", recipient], queryFn: () => api<UserPublic>(`/users/${recipient}`), enabled: !!recipient, staleTime: 0 });
  const command = useCommand<Coffee>();
  const draft = useCommand<{ questions: string; introduction: string }>();
  const [purpose, setPurpose] = useState("");
  const [intro, setIntro] = useState("");
  const [questions, setQuestions] = useState("");
  const [aiConsent, setAiConsent] = useState(false);
  const [slots, setSlots] = useState([{ starts_at: "", ends_at: "" }]);
  if (!recipient) return <p className="notice">동문의 공개 프로필에서 커피챗 요청을 시작해 주세요.</p>;
  if (user.isPending) return <Loading />;
  if (user.error) return <ErrorMessage error={user.error} />;
  if (!user.data?.can_request_coffee_chat) return <p className="notice">지금은 이 동문에게 커피챗을 요청할 수 없어요.</p>;
  return <><PageHeading eyebrow="SAY HELLO" title={`${user.data?.display_name || "동문"}님께 커피챗 요청`} description="직접 작성한 질문을 그대로 보낼 수 있어요. AI 도움은 선택 사항입니다." /><form className="stack" onSubmit={e => { e.preventDefault(); command.mutate({ path: "/coffee-chats", idempotent: true, body: { recipient_id: recipient, purpose, introduction: intro, questions, proposed_slots: slots.map(x => ({ starts_at: new Date(x.starts_at).toISOString(), ends_at: new Date(x.ends_at).toISOString() })) } }, { onSuccess: x => router.push(`/coffee/${x.id}`) }); }}><section className="panel stack"><h2>나누고 싶은 이야기</h2><Field label="만남의 목적"><input required value={purpose} maxLength={200} onChange={e => setPurpose(e.target.value)} placeholder="첫 백엔드 직무를 선택한 경험이 궁금해요" /></Field><Field label="간단한 자기소개"><textarea value={intro} maxLength={3000} onChange={e => setIntro(e.target.value)} /></Field><Field label="나누고 싶은 질문"><textarea required value={questions} maxLength={5000} onChange={e => setQuestions(e.target.value)} /></Field><div><label className="check-row"><input type="checkbox" checked={aiConsent} onChange={e => setAiConsent(e.target.checked)} /> 공개 프로필·만남 목적을 AI에 전송하는 데 동의합니다.</label><button className="button subtle" type="button" disabled={!purpose || !aiConsent || draft.isPending} onClick={() => draft.mutate({ path: "/coffee-chat-drafts", body: { recipient_id: recipient, purpose } })}><Sparkles size={16} /> 질문 아이디어 받기</button><ErrorMessage error={draft.error} />{draft.data && <div className="notice"><p>{draft.data.questions}</p><button type="button" className="button subtle" onClick={() => { setQuestions(draft.data!.questions); setIntro(draft.data!.introduction); }}>초안을 입력창에 적용</button></div>}</div></section><section className="panel stack"><h2>가능한 시간을 알려주세요</h2><p className="muted">입력 시간대: {timezone()}. 상대방이 후보 중 하나를 골라 예약을 확정합니다.</p>{slots.map((slot, i) => <div className="form-grid" key={i}><Field label={`후보 ${i + 1} 시작`}><input type="datetime-local" required value={slot.starts_at} onChange={e => setSlots(slots.map((x, n) => n === i ? { ...x, starts_at: e.target.value } : x))} /></Field><div className="inline"><Field label={`후보 ${i + 1} 종료`}><input type="datetime-local" required value={slot.ends_at} onChange={e => setSlots(slots.map((x, n) => n === i ? { ...x, ends_at: e.target.value } : x))} /></Field>{slots.length > 1 && <button type="button" className="icon-button" aria-label={`후보 ${i + 1} 삭제`} onClick={() => setSlots(slots.filter((_, n) => n !== i))}><Trash2 size={16} /></button>}</div></div>)}<div><button type="button" className="button subtle" disabled={slots.length >= 10} onClick={() => setSlots([...slots, { starts_at: "", ends_at: "" }])}><Plus size={16} /> 시간 후보 추가</button></div></section><ErrorMessage error={command.error || user.error} /><div className="form-actions"><Submit pending={command.isPending}>커피챗 요청 보내기</Submit></div></form></>;
}
export default function NewCoffee() { return <AuthGate><Suspense fallback={<Loading />}><Content /></Suspense></AuthGate>; }

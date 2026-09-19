"use client";

import Link from "next/link";
import { useParams, useRouter } from "@/components/app-navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/components/providers";
import { api, localDate, statusText, timezone, type Coffee } from "@/lib/api";
import { useCommand } from "@/lib/hooks";
import { AuthGate, Badge, ErrorMessage, Field, Loading, PageHeading, Submit } from "@/components/ui";

function Content({ id }: { id: string }) {
  const { user } = useAuth();
  const router = useRouter();
  const query = useQuery({ queryKey: ["coffee-detail", id], queryFn: () => api<Coffee>(`/coffee-chats/${id}`) });
  const decide = useCommand();
  const book = useCommand<{ id: string }>();
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorMessage error={query.error} />;
  const item = query.data;
  const recipient = item.recipient_id === user?.id;
  return <><PageHeading eyebrow="COFFEE CHAT" title={item.purpose} action={<Badge>{statusText[item.status]}</Badge>} /><div className="split"><section className="panel"><h2>함께 나누고 싶은 이야기</h2><p className="card-description">{item.questions}</p><div className="section-divider" /><h3>자기소개</h3><p className="card-description">{item.introduction || "별도 소개가 없어요."}</p><div className="card-actions"><Link className="button subtle" href={`/users/${recipient ? item.requester_id : item.recipient_id}`}>상대방 프로필 보기</Link></div><ErrorMessage error={decide.error} />{recipient && item.status === "pending" && <div className="form-actions"><button className="button subtle" disabled={decide.isPending} onClick={() => decide.mutate({ path: `/coffee-chats/${id}/decision`, body: { decision: "rejected", revision: item.revision } })}>거절</button><button className="button primary" disabled={decide.isPending} onClick={() => decide.mutate({ path: `/coffee-chats/${id}/decision`, body: { decision: "accepted", revision: item.revision } })}>요청 수락</button></div>}</section><section className="panel"><h2>희망 일정</h2><p className="muted">시간대: {timezone()}</p>{item.proposed_slots.map(x => <div className="list-row" key={x.id}><div><strong>{localDate(x.starts_at)}</strong><p className="muted">~ {localDate(x.ends_at)}</p></div></div>)}{item.booking_id ? <Link className="button primary wide" href={`/bookings/${item.booking_id}`}>확정된 예약 보기</Link> : recipient && item.status === "accepted" ? <form className="stack" style={{ marginTop: 20 }} onSubmit={e => { e.preventDefault(); const fd = new FormData(e.currentTarget); book.mutate({ path: `/coffee-chats/${id}/booking`, idempotent: true, body: { slot_id: fd.get("slot"), meeting_mode: fd.get("mode"), meeting_location: fd.get("location") } }, { onSuccess: result => router.push(`/bookings/${result.id}`) }); }}><Field label="확정할 후보"><select name="slot" required>{item.proposed_slots.map(x => <option key={x.id} value={x.id}>{localDate(x.starts_at)}</option>)}</select></Field><Field label="만남 방식"><select name="mode"><option value="online">온라인</option><option value="offline">오프라인</option></select></Field><Field label="장소 또는 접속 안내"><input name="location" required maxLength={1000} placeholder="장소명 또는 화상회의 링크" /></Field><ErrorMessage error={book.error} /><Submit pending={book.isPending}>일정 확정</Submit></form> : <p className="notice">수락 후 요청을 받은 사람이 일정을 확정할 수 있어요.</p>}</section></div></>;
}
export default function CoffeeDetail() { const { id } = useParams<{ id: string }>(); return <AuthGate><Content id={id} /></AuthGate>; }

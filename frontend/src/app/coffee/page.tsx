"use client";

import Link from "next/link";
import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ArrowUpRight, CalendarDays, Coffee as CoffeeIcon } from "lucide-react";
import { api, localDate, statusText, type Booking, type Coffee, type Page } from "@/lib/api";
import { useBookings } from "@/lib/bookings";
import Calendar from "@/components/calendar";
import { AuthGate, Badge, Empty, ErrorMessage, Loading, PageHeading } from "@/components/ui";

function BookingCard({ booking }: { booking: Booking }) {
  return <Link href={`/bookings/${booking.id}`} className="booking-summary coffee-upcoming-card">
    <div className="person-header"><span className="action-symbol teal"><CalendarDays size={20} /></span><div><h3>{localDate(booking.starts_at)}</h3><p className="muted">{booking.meeting_location}</p></div></div>
    <div className="card-actions"><Badge>{statusText[booking.status]}</Badge><span className="text-link">일정 보기 <ArrowUpRight size={16} /></span></div>
  </Link>;
}

function Content() {
  const [box, setBox] = useState("received");
  const [tab, setTab] = useState<"requests" | "past">("requests");
  const requests = useInfiniteQuery({
    queryKey: ["coffee", box], initialPageParam: "",
    queryFn: ({ pageParam }) => api<Page<Coffee>>(`/coffee-chats?box=${box}${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`),
    getNextPageParam: page => page.next_cursor ?? undefined,
  });
  const bookings = useBookings();
  const items = requests.data?.pages.flatMap(page => page.items) || [];
  const upcoming = bookings.data?.filter(x => x.status === "confirmed" && new Date(x.ends_at) > new Date());
  const past = bookings.data?.filter(x => x.status === "completed" || x.status === "cancelled" || new Date(x.ends_at) <= new Date());

  return <div className="coffee-layout"><div className="coffee-main">
    <section className="panel coffee-upcoming" aria-labelledby="upcoming-coffee-title">
      <div className="section-title"><h2 id="upcoming-coffee-title">다가오는 커피챗</h2>{upcoming?.length ? <Badge color="purple">{upcoming.length}개 일정</Badge> : null}</div>
      <ErrorMessage error={bookings.error} />
      {bookings.isPending ? <div className="coffee-upcoming-loading"><Loading /></div> : upcoming?.length ? <div className="coffee-upcoming-list">{upcoming.map(booking => <BookingCard key={booking.id} booking={booking} />)}</div> : !bookings.error ? <div className="coffee-upcoming-empty"><span className="action-symbol purple"><CoffeeIcon size={20} /></span><div><h3>아직 예정된 커피챗이 없어요</h3><p className="muted">관심 있는 동문에게 먼저 인사를 건네 보세요.</p></div><Link href="/explore" className="text-link">동문 찾기 <ArrowUpRight size={15} /></Link></div> : null}
    </section>

    <div className="tabs coffee-tabs" aria-label="커피챗 분류">{[["requests", "요청"], ["past", "지난 약속"]].map(([value, label]) => <button key={value} className={tab === value ? "selected" : ""} aria-pressed={tab === value} onClick={() => setTab(value as "requests" | "past")}>{label}</button>)}</div>
    {tab === "requests" ? <><div className="request-box-tabs" aria-label="요청함"><button aria-pressed={box === "received"} onClick={() => setBox("received")}>받은 요청</button><button aria-pressed={box === "sent"} onClick={() => setBox("sent")}>보낸 요청</button></div><ErrorMessage error={requests.error} />{requests.isPending ? <Loading /> : !items.length && !requests.error ? <Empty title={box === "received" ? "새로운 대화를 기다리고 있어요" : "아직 보낸 요청이 없어요"} description="궁금한 이야기가 있는 동문에게 먼저 인사를 보내 보세요." action={<Link href="/explore" className="button primary">대화할 동문 찾기 <ArrowUpRight size={16} /></Link>} /> : <div className="stack">{items.map(x => <Link className="panel coffee-request" href={`/coffee/${x.id}`} key={x.id}><div className="person-header"><span className="action-symbol purple"><CoffeeIcon size={20} /></span><div style={{ flex: 1 }}><h3>{x.purpose}</h3><p className="muted">{box === "received" ? "동문에게 받은 요청" : "동문에게 보낸 요청"}</p></div><Badge color={x.status === "pending" ? "peach" : "green"}>{statusText[x.status]}</Badge></div>{x.questions && <div className="question-preview"><small>나누고 싶은 이야기</small><p>{x.questions}</p></div>}<div className="card-meta"><span className="muted">후보 일정 {x.proposed_slots.length}개</span>{x.booking_id && <Badge>일정 확정</Badge>}</div><span className="card-link">요청 자세히 보기 <ArrowUpRight size={16} /></span></Link>)}</div>}{requests.hasNextPage && <div className="form-actions"><button className="button subtle" disabled={requests.isFetchingNextPage} onClick={() => requests.fetchNextPage()}>{requests.isFetchingNextPage ? "불러오는 중…" : "이전 요청 더 보기"}</button></div>}</> : <><ErrorMessage error={bookings.error} />{bookings.isPending ? <Loading /> : past?.length === 0 ? <Empty title="아직 지난 대화가 없어요" description="대화를 나누기로 했다면 서로 편한 시간을 정해 보세요." /> : <div className="stack">{past?.map(booking => <BookingCard key={booking.id} booking={booking} />)}</div>}</>}
  </div><aside className="coffee-aside stack">{bookings.data ? <Calendar bookings={bookings.data} /> : bookings.error ? <ErrorMessage error={bookings.error} /> : <Loading />}<div className="gentle-note"><CalendarDays size={18} /><p>월별 달력과 주간 일정으로 약속을 확인하세요.<br />시간을 바꾸려면 상대방에게 변경을 제안해 주세요.</p></div></aside></div>;
}

export default function CoffeePage() {
  return <><PageHeading title="커피챗" description="서로의 경험을 한 걸음 가까워지는 시간." action={<Link href="/explore" className="button subtle">동문 탐색 <ArrowUpRight size={16} /></Link>} /><AuthGate><Content /></AuthGate></>;
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { type Booking, statusText, timezone } from "@/lib/api";
import { clockTime, dateKey } from "@/lib/bookings";

const weekdays = ["일", "월", "화", "수", "목", "금", "토"];
const dayLabel = (day: Date) => day.toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "long" });
const coversDay = (booking: Booking, day: Date) => {
  const end = new Date(day); end.setDate(end.getDate() + 1);
  return new Date(booking.starts_at) < end && new Date(booking.ends_at) > day;
};

const localDay = () => { const day = new Date(); day.setHours(0, 0, 0, 0); return day; };
const appointmentTime = (booking: Booking) => {
  const start = new Date(booking.starts_at), end = new Date(booking.ends_at);
  if (dateKey(start) === dateKey(end)) return `${clockTime(booking.starts_at)}–${clockTime(booking.ends_at)}`;
  return `${start.getMonth() + 1}/${start.getDate()} ${clockTime(booking.starts_at)}–${end.getMonth() + 1}/${end.getDate()} ${clockTime(booking.ends_at)}`;
};

export default function Calendar({ bookings, guest = false }: { bookings: Booking[]; guest?: boolean }) {
  const [today, setToday] = useState(localDay);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const refreshDay = () => {
      const day = localDay();
      setToday(previous => dateKey(previous) === dateKey(day) ? previous : day);
      const next = new Date(day); next.setDate(next.getDate() + 1);
      clearTimeout(timer);
      timer = setTimeout(refreshDay, next.getTime() - Date.now() + 50);
    };
    refreshDay();
    document.addEventListener("visibilitychange", refreshDay);
    window.addEventListener("focus", refreshDay);
    return () => { clearTimeout(timer); document.removeEventListener("visibilitychange", refreshDay); window.removeEventListener("focus", refreshDay); };
  }, []);
  const [selected, setSelected] = useState(today);
  const [month, setMonth] = useState(() => new Date(today.getFullYear(), today.getMonth(), 1));
  const [view, setView] = useState<"month" | "week">("month");
  const visibleBookings = bookings.filter(x => x.status !== "cancelled");
  const first = new Date(month); first.setDate(1 - first.getDay());
  const days = Array.from({ length: Math.ceil((month.getDay() + new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()) / 7) * 7 }, (_, i) => new Date(first.getFullYear(), first.getMonth(), first.getDate() + i));
  const week = Array.from({ length: 7 }, (_, i) => new Date(selected.getFullYear(), selected.getMonth(), selected.getDate() - selected.getDay() + i));
  const selectedBookings = visibleBookings.filter(x => coversDay(x, selected));
  const shift = (direction: number) => {
    if (view === "month") { const next = new Date(month.getFullYear(), month.getMonth() + direction, 1); setMonth(next); setSelected(next); }
    else { const next = new Date(selected.getFullYear(), selected.getMonth(), selected.getDate() + direction * 7); setSelected(next); setMonth(new Date(next.getFullYear(), next.getMonth(), 1)); }
  };
  return <section className="panel calendar" aria-label="커피챗 캘린더">
    <div className="subheading"><h2><CalendarDays size={18} /> 나의 캘린더</h2><div className="segmented compact" aria-label="캘린더 보기"><button aria-pressed={view === "month"} onClick={() => setView("month")}>월</button><button aria-pressed={view === "week"} onClick={() => setView("week")}>주</button></div></div>
    <div className="calendar-toolbar"><strong aria-live="polite">{month.getFullYear()}년 {month.getMonth() + 1}월</strong><div className="inline"><button className="text-link" onClick={() => { setSelected(today); setMonth(new Date(today.getFullYear(), today.getMonth(), 1)); }}>오늘</button><button className="icon-button" onClick={() => shift(-1)} aria-label={view === "month" ? "이전 달" : "이전 주"}><ChevronLeft size={17} /></button><button className="icon-button" onClick={() => shift(1)} aria-label={view === "month" ? "다음 달" : "다음 주"}><ChevronRight size={17} /></button></div></div>
    {view === "month" ? <><div className="calendar-weekdays">{weekdays.map(x => <span key={x}>{x}</span>)}</div><div className="calendar-grid">{days.map(day => { const events = visibleBookings.filter(x => coversDay(x, day)); return <button key={dateKey(day)} className={`calendar-day ${day.getMonth() !== month.getMonth() ? "outside" : ""} ${dateKey(day) === dateKey(today) ? "today" : ""}`} aria-pressed={dateKey(day) === dateKey(selected)} aria-label={`${dayLabel(day)}${events.length ? `, 일정 ${events.length}개` : ""}`} onClick={() => { setSelected(day); if (day.getMonth() !== month.getMonth()) setMonth(new Date(day.getFullYear(), day.getMonth(), 1)); }}><span>{day.getDate()}</span>{events.length > 0 && <i aria-hidden="true" />}</button>; })}</div></> : <div className="week-agenda">{week.map(day => { const events = visibleBookings.filter(x => coversDay(x, day)); return <div key={dateKey(day)} className="week-day"><button aria-pressed={dateKey(day) === dateKey(selected)} className="week-date" onClick={() => { setSelected(day); setMonth(new Date(day.getFullYear(), day.getMonth(), 1)); }}><small>{weekdays[day.getDay()]}</small><strong>{day.getDate()}</strong></button><div>{events.length ? events.map(x => <Link key={x.id} className="week-event" href={`/bookings/${x.id}`}><strong>{appointmentTime(x)}</strong><span>{x.meeting_location || "커피챗"}</span></Link>) : <span className="muted">일정 없음</span>}</div></div>; })}</div>}
    <div className="calendar-selected" aria-live="polite"><div className="subheading"><strong>{dayLabel(selected)}</strong><span className="calendar-legend"><i /> 커피챗</span></div>{selectedBookings.length ? selectedBookings.map(x => <Link href={`/bookings/${x.id}`} className="agenda-card" key={x.id}><span className="agenda-time">{appointmentTime(x)}</span><div><strong>{x.meeting_location || "커피챗 약속"}</strong><small>{statusText[x.meeting_mode]} · {statusText[x.status]}</small></div><ChevronRight size={16} /></Link>) : <p className="calendar-empty">{guest ? "로그인하면 나의 약속을 모아 볼 수 있어요." : "이날은 예정된 약속이 없어요."}</p>}</div>
    <p className="calendar-timezone">{timezone()} 기준</p>
  </section>;
}

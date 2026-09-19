"use client";

import Link from "next/link";
import { ArrowRight, CalendarDays, ChevronRight, Coffee, Compass, FilePenLine } from "lucide-react";
import { useAuth } from "@/components/providers";
import { ErrorMessage, Loading } from "@/components/ui";
import { Mascot } from "@/components/brand";
import Calendar from "@/components/calendar";
import Recommendations from "@/components/recommendations";
import { useBookings } from "@/lib/bookings";
import { localDate } from "@/lib/api";

export default function Home() {
  const { user, ready } = useAuth();
  const bookings = useBookings(!!user);
  if (!ready) return <Loading />;
  const fields = user ? [!!user.profile.display_name, !!user.profile.bio, !!user.school_affiliations.length, !!user.tags.length, !!user.preferences.activity_goal] : [];
  const completed = fields.filter(Boolean).length;
  const progress = user ? Math.round(completed / fields.length * 100) : 0;
  const next = bookings.data?.find(x => x.status === "confirmed" && new Date(x.ends_at) > new Date());
  return <div className="home">
    <div className="home-greeting"><div><span className="eyebrow">MY NEXT CHAPTER</span><h1>{user ? `안녕하세요, ${user.profile.display_name}님` : "우리의 다음 이야기, 두드리"}</h1>{user?.school_affiliations[0] ? <span className="school-pill"><span className="live-dot" />{user.school_affiliations[0].university_name}</span> : <p>작은 관심사 하나로, 새로운 연결을 시작해요.</p>}</div><span className="greeting-date">{new Date().toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "long" })}</span></div>
    <div className="dashboard-grid"><div className="dashboard-main">
      <section className="panel completion-card"><div className="subheading"><h2>{user ? "프로필 완성도" : "나를 소개하는 첫걸음"}</h2>{user && <strong className="progress-value">{progress}%</strong>}</div>{user ? <><div className="progress-track" role="progressbar" aria-label="프로필 완성도" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress}%` }} /></div><div className="completion-bottom"><p>이름·소개·학교·관심사·활동 목표<br />{completed}개 항목을 채웠어요</p><Link className="button primary" href="/profile">{progress === 100 ? "프로필 보기" : "완성하기"}</Link></div></> : <div className="completion-bottom"><p>학교 이메일로 시작하고<br />나의 경험과 관심사를 알려주세요.</p><Link className="button primary" href="/auth">시작하기 <ArrowRight size={15} /></Link></div>}</section>
      <section className="dashboard-section"><div className="section-title"><h2>{user ? "나의 연결을 준비해요" : "어떤 이야기를 나눠볼까요?"}</h2></div><div className="stack tight"><Link className="action-row" href="/explore"><span className="action-symbol purple"><Compass size={21} /></span><div><strong>궁금했던 길을 먼저 걸은 동문</strong><small>관심사로 대화의 시작을 찾아요</small></div><ChevronRight size={17} /></Link><Link className="action-row" href="/profile#experience"><span className="action-symbol teal"><FilePenLine size={20} /></span><div><strong>작은 경험도 나만의 이야기로</strong><small>수업, 동아리, 프로젝트를 기록해요</small></div><ChevronRight size={17} /></Link></div></section>
      <section className="dashboard-section"><div className="section-title"><h2>다가오는 커피챗</h2><Link className="text-link" href="/coffee">전체 <ChevronRight size={14} /></Link></div>{user && bookings.isPending ? <Loading /> : bookings.error ? <ErrorMessage error={bookings.error} /> : <div className="gradient-card upcoming-card"><div className="person-header"><span className="action-symbol"><Coffee size={22} /></span><div><h3>{next ? "곧 나눌 이야기가 있어요" : "새로운 대화를 기다리는 중"}</h3><p>{next ? localDate(next.starts_at) : "궁금한 이야기가 있는 동문에게 인사해 보세요."}</p></div></div>{next && <p className="upcoming-location">{next.meeting_location}</p>}<div className="card-actions"><Link className="button glass" href={next ? `/bookings/${next.id}` : "/coffee"}>{next ? "일정 자세히 보기" : "나의 커피챗"}</Link><Link className="button light" href="/explore">대화할 동문 찾기</Link></div></div>}</section>
      <Recommendations /><section className="dashboard-section"><div className="stack tight"><Link className="action-row gradient-card" href="/studio"><span className="action-symbol"><FilePenLine size={21} /></span><div><strong>AI로 만드는 나만의 포트폴리오</strong><small>디자인을 고르고, 내 경험을 한곳에</small></div><ChevronRight size={17} /></Link><Link className="action-row" href="/career"><span className="action-symbol teal"><Compass size={21} /></span><div><strong>다음 한 걸음, 나의 커리어맵</strong><small>지금까지의 경험에서 미래 계획으로</small></div><ChevronRight size={17} /></Link></div></section><section className="story-card"><Mascot /><div><span className="eyebrow">A LITTLE CONNECTION</span><h2>처음이어도, 함께라면.</h2><p>아직 경험이 없어도 괜찮아요.<br />같은 관심사를 가진 동료를 만나보세요.</p><Link href="/explore" className="text-link">나의 다음 연결 찾기 <ArrowRight size={16} /></Link></div></section>
    </div><div className="dashboard-aside">{!user || bookings.data ? <Calendar bookings={bookings.data || []} guest={!user} /> : bookings.error ? <section className="panel"><h2>나의 캘린더</h2><ErrorMessage error={bookings.error} /></section> : <Loading />}<div className="gentle-note"><CalendarDays size={18} /><p>약속은 내 시간대로 표시해요.<br />일정 변경은 상대방의 동의 후 반영돼요.</p></div></div></div>
  </div>;
}

"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronRight, LockKeyhole, LogOut, Settings2 } from "lucide-react";
import { useAuth } from "@/components/providers";
import { ErrorMessage, Loading } from "@/components/ui";

export default function MyPage() {
  const { user, ready, logout } = useAuth();
  const [error, setError] = useState<unknown>(null);
  if (!ready) return <Loading />;
  const school = user?.school_affiliations[0];
  return <div className="my-page">
    <section className="my-header"><div className="my-heading"><h1>마이</h1><Link className="icon-button" href="/profile" aria-label="프로필 설정"><Settings2 size={20} /></Link></div><div className="my-person"><div className="avatar">{user ? user.profile.display_name.slice(0, 1) : "D"}</div><div><h2>{user ? user.profile.display_name : "나의 이야기를 시작해요"}</h2><p>{school ? `${school.university_name} · ${school.department || "학과 미입력"}` : "경험과 관심사를 모아, 다음 가능성으로"}</p>{user ? <span className="badge">나의 공간</span> : <Link href="/auth" className="button glass" style={{ marginTop: 12 }}>로그인 · 회원가입</Link>}</div></div></section>
    <div className="my-body">
      <Link className="action-row" href="/profile"><span className="action-symbol purple"><span className="shape diamond" /></span><div><strong>나를 소개하는 프로필</strong><small>내가 작성하고, 공개 범위를 정해요</small></div><span className="button primary">편집</span></Link>
      <div className="my-tiles"><Link className="my-tile" href="/studio"><small>AI 스튜디오</small><strong>나만의 이야기</strong><span>포트폴리오 · 자기 PR · CV</span></Link><Link className="my-tile" href="/coffee"><small>커피챗</small><strong>나의 약속 모아보기</strong><span>일정 · 요청 확인</span></Link></div>
      <div className="my-menu"><Link href="/profile"><span className="menu-dot" /><strong>프로필 편집 · 공개 범위</strong><ChevronRight size={16} /></Link><Link href="/profile#experience"><span className="menu-dot teal" /><strong>나의 경험 · 커리어 기록</strong><ChevronRight size={16} /></Link><Link href="/materials"><span className="menu-dot teal" /><strong>연결 자료 · AI 검토</strong><ChevronRight size={16} /></Link><Link href="/projects"><span className="menu-dot pink" /><strong>내 프로젝트 · 지원 현황</strong><ChevronRight size={16} /></Link><Link href="/career"><span className="menu-dot" /><strong>커리어맵</strong><ChevronRight size={16} /></Link><Link href="/settings/ai"><span className="menu-dot" /><strong>AI 연결 설정</strong><ChevronRight size={16} /></Link><Link href="/notifications"><span className="menu-dot" /><strong>알림</strong><ChevronRight size={16} /></Link></div>
      <div className="my-privacy"><LockKeyhole size={15} /><p>현재 추천은 임의 순서로 제공돼요. 다른 동문에게는 공개한 정보만 표시됩니다.</p></div>
      <ErrorMessage error={error} />{user && <div className="my-logout"><button className="text-link" onClick={() => logout().catch(setError)}><LogOut size={15} /> 로그아웃</button></div>}
    </div>
  </div>;
}

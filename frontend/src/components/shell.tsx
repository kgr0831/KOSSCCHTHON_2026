"use client";

import Link from "next/link";
import { AppOutlet, useAppNavigation, usePathname } from "@/components/app-navigation";
import { Bell, ChevronRight, Coffee, Compass, House, LogOut, Plus, UserRound, UsersRound, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import AuthPage from "@/app/auth/page";
import { useAuth } from "./providers";
import { Brand } from "./brand";

const navigation = [
  { href: "/", title: "홈", icon: House },
  { href: "/explore", title: "탐색", icon: Compass },
  { href: "/team-building", title: "팀빌딩", icon: UsersRound },
  { href: "/coffee", title: "커피챗", icon: Coffee },
  { href: "/my", title: "마이", icon: UserRound },
];
const personal = [
  { href: "/profile", title: "프로필 · 공개 범위" }, { href: "/studio", title: "AI 스튜디오" },
  { href: "/career", title: "커리어맵" }, { href: "/projects", title: "프로젝트" }, { href: "/notifications", title: "알림" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { user, logout, ready, connectionError, reconnect } = useAuth();
  const { authOpen, closeAuth } = useAppNavigation();
  const authDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (authOpen && !authDialog.current?.open) authDialog.current?.showModal(); else if (!authOpen) authDialog.current?.close(); }, [authOpen]);
  const dialog = useRef<HTMLDialogElement>(null);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [error, setError] = useState("");
  const openRegistration = () => { dialog.current?.showModal(); setRegisterOpen(true); };
  const closeRegistration = () => { dialog.current?.close(); setRegisterOpen(false); };
  const isActive = (href: string) => href === "/" ? path === "/" : href === "/my" ? ["/my", "/profile", "/studio", "/settings", "/materials", "/career", "/projects", "/notifications"].some(x => path.startsWith(x)) : href === "/coffee" ? path.startsWith("/coffee") || path.startsWith("/bookings") : path.startsWith(href) || path.startsWith("/users");
  const currentPersonal = personal.find(x => path === x.href || path.startsWith(x.href + "/"));
  const location = currentPersonal?.title || (path === "/settings/ai" ? "AI 연결 설정" : path === "/materials" ? "내 자료" : navigation.find(x => isActive(x.href))?.title || "두드리");
  useEffect(() => { document.title = `${location} · 두드리`; }, [location]);
  const item = (nav: typeof navigation[number]) => <Link key={nav.href} href={nav.href} aria-current={isActive(nav.href) ? "page" : undefined} className={`nav-item ${isActive(nav.href) ? "active" : ""}`}><span className="nav-icon"><nav.icon size={20} /></span><span>{nav.title}</span></Link>;
  const register = (mobile = false) => <button className={mobile ? "nav-register" : "button primary register-desktop"} onClick={openRegistration} aria-haspopup="dialog" aria-expanded={registerOpen}><span className="register-symbol"><Plus size={23} /></span><span>등록{!mobile && "하기"}</span></button>;
  return <div className="app-shell" onDragStartCapture={event => {
    const target = event.target;
    if (target instanceof Element && (target.closest("img,svg") || !target.closest('input,textarea,[contenteditable="true"],[contenteditable="plaintext-only"],pre,code,.code-box,.card-description,[data-selectable]'))) event.preventDefault();
  }}>
    <aside className="sidebar">
      <Brand /><p className="sidebar-caption">새로운 연결, 나의 다음 이야기</p>
      <nav aria-label="주요 메뉴">{navigation.map(item)}</nav>
      {register()}
      <nav className="sidebar-personal" aria-label="나의 공간"><span className="nav-label">나의 공간</span>{personal.map(x => <Link key={x.href} className={`utility-link ${currentPersonal?.href === x.href ? "active" : ""}`} aria-current={currentPersonal?.href === x.href ? "page" : undefined} href={x.href}>{x.title}<ChevronRight size={15} /></Link>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><span className="mini-brand"><img src="/figma/logo.png" alt="" width="28" height="28" /></span><strong>처음이어도 괜찮아요</strong><p>작은 관심사 하나에서<br />새로운 연결이 시작돼요.</p><Link href="/explore">동문 만나보기 <ChevronRight size={14} /></Link></div>
        {!ready ? <div className="account-placeholder" aria-label="계정 확인 중" /> : user ? <div className="account"><Link href="/my" className="avatar small" aria-label="마이 페이지">{user.profile.display_name.slice(0, 1)}</Link><div><strong>{user.profile.display_name}</strong><small>나의 다음 이야기</small></div><button aria-label="로그아웃" className="icon-button" onClick={() => logout().catch(e => setError(e.message))}><LogOut size={17} /></button></div> : <Link className="button subtle wide" href="/auth">로그인 · 회원가입</Link>}
      </div>
    </aside>
    <div className="main-frame"><header className="topbar"><div className="mobile-brand"><Brand /></div><p className="topbar-context"><span className="live-dot" /> {isActive("/my") ? "나의 공간" : "두드리"}<ChevronRight size={14} /><strong>{location}</strong></p><div className="topbar-actions"><Link href="/notifications" className="icon-button notification-button" aria-label="알림"><Bell size={19} /></Link>{!ready ? <span className="avatar small account-placeholder" /> : user ? <Link href="/my" className="avatar small" aria-label="마이 페이지">{user.profile.display_name.slice(0, 1)}</Link> : <Link href="/auth" className="text-link">로그인</Link>}</div></header>
      <div className="mobile-location" aria-label="현재 화면">{isActive("/my") && <span>나의 공간 <ChevronRight size={12} /></span>}<strong>{location}</strong></div>
      <main id="main" className="main-content">{connectionError && <div role="alert" className="notice error"><p>{connectionError}</p><button className="button subtle" onClick={reconnect}>다시 연결</button></div>}{error && <p role="alert" className="notice error">{error}</p>}<AppOutlet fallback={children} /></main><footer className="footer"><span>두드리 · 서로의 경험이 다음 가능성이 되는 곳</span><span>함께, 한 걸음 더</span></footer>
    </div>
    <nav className="bottom-nav" aria-label="모바일 주요 메뉴">{navigation.slice(0, 2).map(item)}{register(true)}{navigation.slice(2).map(item)}</nav>
    <dialog ref={authDialog} className="auth-dialog" aria-labelledby="auth-dialog-title" onCancel={event => { event.preventDefault(); closeAuth(); }} onClick={event => { if (event.target === event.currentTarget) closeAuth(); }}><div className="auth-dialog-heading"><h2 id="auth-dialog-title">로그인 · 회원가입</h2><button className="icon-button" autoFocus aria-label="로그인 닫기" onClick={closeAuth}><X size={20} /></button></div>{authOpen && <AuthPage />}</dialog>
    <dialog ref={dialog} className="registration-dialog" aria-labelledby="registration-title" onClose={() => setRegisterOpen(false)} onClick={e => { if (e.target === e.currentTarget) closeRegistration(); }}>
      <div className="registration-content"><span className="sheet-handle" /><div className="subheading"><h2 id="registration-title">무엇을 시작할까요?</h2><button className="icon-button" aria-label="등록 메뉴 닫기" onClick={closeRegistration} autoFocus><X size={20} /></button></div>
        <div className="registration-options">
          <Link className="action-row" href="/projects/new" onClick={closeRegistration}><span className="action-symbol purple"><span className="shape square" /></span><div><strong>팀원 모집하기</strong><small>함께할 동료를 찾는 모집 공고</small></div><ChevronRight size={16} /></Link>
          <Link className="action-row" href="/profile#experience" onClick={closeRegistration}><span className="action-symbol teal"><span className="shape square" /></span><div><strong>경험 기록하기</strong><small>프로젝트와 활동을 나의 경험으로</small></div><ChevronRight size={16} /></Link>
          <Link className="action-row" href="/explore" onClick={closeRegistration}><span className="action-symbol purple"><span className="shape ring" /></span><div><strong>커피챗 요청하기</strong><small>대화하고 싶은 동문을 찾아요</small></div><ChevronRight size={16} /></Link>
          <Link className="action-row gradient-card" href="/studio" onClick={closeRegistration}><span className="action-symbol"><span className="shape diamond" /></span><div><strong>포트폴리오 만들기</strong><small>AI 포트폴리오 · 자기 PR · CV</small></div><ChevronRight size={16} /></Link>
        </div><p className="sheet-note">기록한 경험의 공개 범위는 직접 선택할 수 있어요.</p>
      </div>
    </dialog>
  </div>;
}

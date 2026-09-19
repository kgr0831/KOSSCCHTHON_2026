"use client";

import { useState } from "react";
import { useAppNavigation } from "@/components/app-navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Sprout } from "lucide-react";
import Link from "next/link";
import { api, type Page } from "@/lib/api";
import { useCommand } from "@/lib/hooks";
import { useAuth } from "@/components/providers";
import { ErrorMessage, Field, PageHeading, Submit } from "@/components/ui";

export default function AuthPage() {
  const { user, login, ready } = useAuth();
  const { finishLogin } = useAppNavigation();
  const [demoError, setDemoError] = useState<unknown>(), [demoBusy, setDemoBusy] = useState(false);
  const demo = useQuery({ queryKey: ["demo-accounts"], queryFn: () => api<{ items: { id: string; name: string; school: string; role: string }[] }>("/dev/accounts"), retry: false });
  const demoLogin = async (id: string) => { if (!ready) return; setDemoBusy(true); setDemoError(null); try { const result = await api<{ access_token: string }>("/dev/login", { method: "POST", body: JSON.stringify({ user_id: id }) }); await login(result.access_token); finishLogin(); } catch (e) { setDemoError(e); } finally { setDemoBusy(false); } };
  const [mode, setMode] = useState("signup");
  const [school, setSchool] = useState("");
  const universities = useQuery({ queryKey: ["universities"], queryFn: () => api<Page<{ id: string; name: string }>>("/universities") });
  const domains = useQuery({ queryKey: ["domains", school], queryFn: () => api<Page<{ domain: string }>>(`/universities/${school}/domains`), enabled: !!school });
  const command = useCommand();
  if (user) return <><PageHeading title="다시 만나 반가워요" description={`${user.profile.display_name}님으로 로그인되어 있어요.`} /><Link href="/profile" className="button primary">내 프로필 완성하기 <ArrowRight size={17} /></Link></>;
  return <div className="auth-container"><PageHeading eyebrow="YOUR NEXT CHAPTER" title="연결의 시작은, 나의 학교에서" description="학교 이메일 접근 여부만 확인해요. 재학·졸업 상태는 직접 입력한 정보로 표시됩니다." />{!!demo.data?.items.length && <section className="panel demo-accounts"><span className="badge purple">로컬 체험 · 가상 인물</span><h2>바로 시작해 보세요</h2><p className="muted">학교 인증 없이 로컬에서 기능을 확인하는 더미 계정입니다. 모든 이름과 경험은 가상 데이터예요.</p><div className="demo-grid">{demo.data.items.map(x => <button className="demo-account" key={x.id} disabled={demoBusy || !ready} onClick={() => demoLogin(x.id)}><span className="avatar small">{x.name.slice(0, 1)}</span><span><strong>{x.name}</strong><small>{x.school} · {x.role}</small></span></button>)}</div><ErrorMessage error={demoError} /></section>}<div className="grid-2"><div className="auth-story"><Sprout size={49} /><h2>작은 연결 하나가<br />다음 가능성을<br />열어줄 거예요.</h2><p>국민대학교 · 숭실대학교 · 순천향대학교<br />함께 시작하는 동문 커뮤니티, 두드리.</p></div><section className="panel"><div className="tabs" role="tablist"><button role="tab" aria-selected={mode === "signup"} className={mode === "signup" ? "selected" : ""} onClick={() => { setMode("signup"); command.reset(); }}>처음 시작해요</button><button role="tab" aria-selected={mode === "login"} className={mode === "login" ? "selected" : ""} onClick={() => { setMode("login"); command.reset(); }}>다시 왔어요</button></div>
    <form className="stack" onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); const body = mode === "signup" ? { name: form.get("name"), email: form.get("email"), university_id: school, enrollment_status: form.get("status"), department: form.get("department") } : { email: form.get("email") }; command.mutate({ path: mode === "signup" ? "/auth/school-email-verifications" : "/auth/login-links", body }); }}>
      {mode === "signup" && <><Field label="이름"><input name="name" required maxLength={100} placeholder="동문에게 소개할 이름" autoComplete="name" /></Field><Field label="학교"><select value={school} onChange={e => setSchool(e.target.value)} required><option value="">학교를 선택해 주세요</option>{universities.data?.items.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field><div className="form-grid"><Field label="학과"><input name="department" maxLength={150} placeholder="소프트웨어학부" /></Field><Field label="학적 상태 (본인 입력)"><select name="status"><option value="student">재학 중</option><option value="graduate">졸업</option><option value="leave">휴학 중</option><option value="other">기타</option></select></Field></div></>}
      <Field label="학교 이메일" hint={domains.data ? `허용 도메인: ${domains.data.items.map(x => x.domain).join(", ")}` : "인증 링크를 보내드릴게요."}><input type="email" name="email" required autoComplete="email" placeholder="name@university.ac.kr" /></Field><ErrorMessage error={command.error || universities.error} />{command.isSuccess && <p className="notice" role="status">이메일 발송을 요청했어요. 받은 편지함에서 15분 안에 인증 링크를 열어 주세요.</p>}<Submit pending={command.isPending}>이메일로 인증 링크 받기</Submit><p className="muted">학교 이메일을 사용할 수 없는 경우, 보조 인증 정책이 준비된 후 이용할 수 있어요.</p>
    </form></section></div></div>;
}

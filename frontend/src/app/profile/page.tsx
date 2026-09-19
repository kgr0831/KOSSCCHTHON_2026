"use client";

import { useState } from "react";
import { PreferencesForm } from "@/components/preferences-form";
import { GoogleSignIn } from "@/components/google-sign-in";
import { SchoolVerification } from "@/components/school-verification";
import AIDraft from "@/components/ai-draft";
import { useQuery } from "@tanstack/react-query";
import { Check, Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import { useAuth } from "@/components/providers";
import { AuthGate, Badge, Empty, ErrorMessage, Field, PageHeading, Submit, Toggle } from "@/components/ui";
import { api, type Career, type Page, type Profile, type UserTag } from "@/lib/api";
import { useCommand, useSessionDraft, useUnsavedChanges } from "@/lib/hooks";

function ProfileForm({ profile }: { profile: Profile }) {
  const [draft, setForm] = useSessionDraft<Profile>(`profile-${profile.user_id}`);
  const form = draft || profile;
  const command = useCommand();
  useUnsavedChanges(JSON.stringify(profile) !== JSON.stringify(form));
  return <section className="panel" id="introduction"><h2>나를 소개해요</h2><form className="stack" onSubmit={e => { e.preventDefault(); const { user_id: _, ...body } = form; command.mutate({ path: "/me", body, method: "PATCH" }, { onSuccess: () => setForm(null) }); }}><Field label="이름"><input required maxLength={100} value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} /></Field><Toggle label="이름 공개" checked={form.name_is_public} onChange={v => setForm({ ...form, name_is_public: v })} /><Field label="자기소개"><textarea value={form.bio} maxLength={5000} placeholder="지금 관심 있는 분야와 나누고 싶은 이야기를 적어보세요." onChange={e => setForm({ ...form, bio: e.target.value })} /></Field><AIDraft kind="profile" text={form.bio} onApply={draft => setForm({ ...form, bio: draft.text })} /><Toggle label="자기소개 공개" checked={form.bio_is_public} onChange={v => setForm({ ...form, bio_is_public: v })} /><Field label="프로필 이미지 URL"><input type="url" value={form.avatar_url || ""} placeholder="https://…" onChange={e => setForm({ ...form, avatar_url: e.target.value || null })} /></Field><Toggle label="프로필 이미지 공개" checked={form.avatar_is_public} onChange={v => setForm({ ...form, avatar_is_public: v })} /><ErrorMessage error={command.error} /><div className="form-actions">{command.isSuccess && <Badge><Check size={12} /> 저장했어요</Badge>}<Submit pending={command.isPending}>프로필 저장</Submit></div></form></section>;
}


function Careers() {
  const careers = useQuery({ queryKey: ["careers"], queryFn: () => api<Page<Career>>("/me/career-events?limit=100") });
  const command = useCommand();
  const [editing, setEditing] = useState<Career | "new" | null>(null);
  const [description, setDescription] = useState("");
  return <section className="panel" id="experience"><div className="subheading"><h2>나의 경험 타임라인</h2><button className="button subtle" onClick={() => { setDescription(""); setEditing("new"); }}><Plus size={16} /> 경험 추가</button></div><ErrorMessage error={careers.error || command.error} />{editing && <form key={typeof editing === "string" ? editing : editing.id} className="stack" onSubmit={e => { e.preventDefault(); const fd = new FormData(e.currentTarget); const body = { event_kind: fd.get("kind"), title: fd.get("title"), organization_name: fd.get("organization"), description: fd.get("description"), started_on: fd.get("start") || null, ended_on: fd.get("end") || null, is_public: fd.get("public") === "on", ...(editing !== "new" ? { revision: editing.revision } : {}) }; command.mutate({ path: editing === "new" ? "/me/career-events" : `/me/career-events/${editing.id}`, method: editing === "new" ? "POST" : "PATCH", body }, { onSuccess: () => setEditing(null) }); }}>
    <div className="form-grid"><Field label="경험 종류"><select name="kind" defaultValue={editing === "new" ? "activity" : editing.event_kind}><option value="education">교육</option><option value="activity">활동</option><option value="project">프로젝트</option><option value="internship">인턴</option><option value="employment">회사·직무</option><option value="transition">직무 전환</option></select></Field><Field label="경험 이름"><input name="title" required maxLength={200} defaultValue={editing === "new" ? "" : editing.title} /></Field></div><Field label="학교·회사·단체"><input name="organization" maxLength={200} defaultValue={editing === "new" ? "" : editing.organization_name} /></Field><div className="form-grid"><Field label="시작일 (모르면 비워두세요)"><input type="date" name="start" defaultValue={editing === "new" ? "" : editing.started_on || ""} /></Field><Field label="종료일 (선택)"><input type="date" name="end" defaultValue={editing === "new" ? "" : editing.ended_on || ""} /></Field></div><Field label="내가 실제로 맡은 역할과 기여"><textarea name="description" maxLength={10000} value={description} onChange={e => setDescription(e.target.value)} /></Field><AIDraft kind="experience" text={description} onApply={draft => setDescription(draft.text)} /><label className="toggle-row">동문에게 공개<input type="checkbox" name="public" defaultChecked={editing !== "new" && editing.is_public} /></label><div className="form-actions"><button type="button" className="button subtle" onClick={() => setEditing(null)}>닫기</button><Submit pending={command.isPending}>경험 저장</Submit></div><div className="section-divider" /></form>}
    {careers.data?.items.length === 0 && !editing && <Empty title="어떤 경험이든 좋아요" description="동아리, 수업, 작은 프로젝트도 당신만의 이야기가 됩니다." />}
    <div className="timeline">{careers.data?.items.map(item => <div className="timeline-event" key={item.id}><small>{item.started_on || "기간 미입력"} {item.ended_on && `— ${item.ended_on}`}</small><h3>{item.title}</h3><p className="muted">{item.organization_name}</p><p className="card-description">{item.description}</p><div className="card-actions"><Badge color={item.is_public ? "green" : "gray"}>{item.is_public ? <Eye size={11} /> : <EyeOff size={11} />}{item.is_public ? "공개" : "비공개"}</Badge><button className="button subtle" onClick={() => { setDescription(item.description); setEditing(item); }}>수정</button><button className="icon-button" aria-label={`${item.title} 사용 철회`} onClick={() => command.mutate({ path: `/me/career-events/${item.id}?revision=${item.revision}`, method: "DELETE" })}><Trash2 size={15} /></button></div></div>)}</div></section>;
}

function Tags() {
  const catalog = useQuery({ queryKey: ["tags"], queryFn: () => api<Page<{ id: string; name: string; kind: string }>>("/tags?limit=100") });
  const selected = useQuery({ queryKey: ["my-tags"], queryFn: () => api<Page<UserTag> & { revision: number }>("/me/tags") });
  const command = useCommand();
  const [tag, setTag] = useState("");
  const [usage, setUsage] = useState("interested");
  const save = (items: { tag_id: string; usage: string; is_public: boolean }[]) => command.mutate({ path: "/me/tags", method: "PUT", body: { revision: selected.data?.revision, items } });
  const values = selected.data?.items.map(({ tag_id, usage, is_public }) => ({ tag_id, usage, is_public })) || [];
  return <section className="panel" id="interests"><h2>기술 · 관심사 · 희망 역할</h2><div className="stack">{selected.data?.items.map((x, i) => <div className="inline" key={x.id}><Badge>{x.name}</Badge><span className="muted">{{ experienced: "경험", desired: "희망", interested: "관심" }[x.usage]}</span><button className="button subtle" onClick={() => save(values.map((v, index) => index === i ? { ...v, is_public: !v.is_public } : v))}>{x.is_public ? "공개" : "비공개"}</button><button className="icon-button" aria-label={`${x.name} 삭제`} onClick={() => save(values.filter((_, index) => index !== i))}><Trash2 size={15} /></button></div>)}<form className="stack" onSubmit={e => { e.preventDefault(); save([...values, { tag_id: tag, usage, is_public: false }]); }}><Field label="추가할 태그"><select value={tag} onChange={e => setTag(e.target.value)} required><option value="">태그 선택</option>{catalog.data?.items.map(x => <option key={x.id} value={x.id}>{x.name} · {x.kind}</option>)}</select></Field><Field label="어떤 관계인가요?"><select value={usage} onChange={e => setUsage(e.target.value)}><option value="interested">관심 있어요</option><option value="desired">맡고 싶어요</option><option value="experienced">경험했어요</option></select></Field><Submit pending={command.isPending}>태그 추가</Submit></form><ErrorMessage error={command.error || catalog.error || selected.error} /></div></section>;
}

function Content() {
  const { user } = useAuth();
  const company = useCommand();
  const verification = useQuery({ queryKey: ["verifications"], queryFn: () => api<Page<{ id: string; verification_kind: string; verified_email: string }>>("/me/verifications") });
  if (!user) return null;
  return <><nav className="profile-section-nav" aria-label="프로필 섹션"><a href="#introduction">소개</a><a href="#experience">경험</a><a href="#preferences">활동 조건</a><a href="#interests">관심사</a><a href="#verification">학교 · 인증</a></nav><p className="notice">현재 추천은 적합도 점수 없이 임의 순서로 제공됩니다. 다른 동문과 공개 문서 생성에는 공개한 정보만 사용됩니다. 공개 정보를 바꾸면 기존 사이트 게시가 중지되며, 새 내용을 확인한 후 다시 게시할 수 있어요.</p><div className="split"><div className="stack"><ProfileForm key={`profile-${user.id}`} profile={user.profile} /><Careers /></div><div className="stack"><PreferencesForm key={`pref-${user.id}`} preferences={user.preferences} userId={user.id} /><Tags /><section className="panel" id="verification"><h2>학교와 인증</h2>{!user.google_connected && <div className="stack"><GoogleSignIn link /><p className="muted">현재 프로필과 저장 자료를 유지하면서 Google 로그인을 연결할 수 있어요.</p></div>}{user.school_affiliations.map(x => <div className="list-row" key={x.id}><div><h3>{x.university_name}</h3><p className="muted">{x.department} · {x.enrollment_status === "graduate" ? "졸업" : "재학·기타"} (본인 입력)</p></div></div>)}{verification.data?.items.map(x => <div className="list-row" key={x.id}><Badge>{x.verification_kind === "school" ? "학교" : "회사"} 이메일 확인</Badge><small>{x.verified_email}</small></div>)}<div className="section-divider" /><SchoolVerification /><div className="section-divider" /><form className="stack" onSubmit={e => { e.preventDefault(); const fd = new FormData(e.currentTarget); company.mutate({ path: "/auth/company-email-verifications", body: { company_name: fd.get("company"), email: fd.get("email") } }); }}><Field label="현재 회사명"><input name="company" required maxLength={150} /></Field><Field label="회사 이메일"><input type="email" name="email" required /></Field><ErrorMessage error={company.error} />{company.isSuccess && <p className="notice">회사 이메일로 확인 링크를 보냈어요.</p>}<Submit pending={company.isPending}>회사 이메일 확인</Submit><p className="muted">이메일 접근만 확인하며 직무·직급·과거 경력을 검증하지 않아요.</p></form></section></div></div></>;
}

export default function ProfilePage() { return <><PageHeading eyebrow="MY STORY" title="내 프로필" description="완벽한 이력보다, 지금의 나를 알려주세요." /><AuthGate><Content /></AuthGate></>; }

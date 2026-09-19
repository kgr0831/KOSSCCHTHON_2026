"use client";

import { Suspense, useState } from "react";
import DesignGallery from "@/components/design-gallery";
import { useSessionDraft, useUnsavedChanges } from "@/lib/hooks";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "@/components/app-navigation";
import Link from "next/link";
import { ArrowDown, ArrowUp, Code2, Download, Eye, FileText, History, Monitor, Plus, Save, Smartphone, Sparkles, X } from "lucide-react";
import { api, jsonBody, localDate, type UserPublic } from "@/lib/api";
import { kinds, pending, versionStatus, type Code, type Document, type Site, type Style, type Version } from "@/lib/studio";
import { useAuth } from "@/components/providers";
import { AuthGate, ErrorMessage, Field, Loading, PageHeading } from "@/components/ui";

export default function StudioPage() { return <AuthGate><Suspense fallback={<Loading />}><Studio /></Suspense></AuthGate>; }

function Studio() {
  const { user } = useAuth();
  const params = useSearchParams(), router = useRouter(), client = useQueryClient();
  const kind = kinds[params.get("kind") || ""] ? params.get("kind")! : "portfolio";
  const versionId = params.get("version") || "";
  const [styleId, setStyleId] = useState("linear"), [instruction, setInstruction] = useState(""), [consent, setConsent] = useState(false);
  const [revisionStyle, setRevisionStyle] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>();
  const styles = useQuery({ queryKey: ["portfolio-styles", user?.id], queryFn: () => api<{ items: Style[] }>("/portfolio-styles"), refetchInterval: query => query.state.data?.items.some(style => style.status === "queued" || style.status === "running") ? 2000 : false });
  const sites = useQuery({ queryKey: ["sites"], queryFn: () => api<{ items: Site[] }>("/me/sites"), refetchInterval: q => q.state.data?.items.some(s => s.versions.some(v => pending(v.status))) ? 2000 : false });
  const profile = useQuery({ queryKey: ["studio-public-input", user?.id], queryFn: () => api<UserPublic>(`/users/${user!.id}`), enabled: !!user });
  const version = useQuery({ queryKey: ["site-version", versionId], queryFn: () => api<Version>(`/me/site-versions/${versionId}`), enabled: !!versionId, refetchInterval: q => q.state.data && pending(q.state.data.status) ? 2000 : false });
  const site = sites.data?.items.find(x => x.site_kind === kind);
  const navigate = (id = "", nextKind = kind) => router.replace(`/studio?kind=${nextKind}${id ? `&version=${id}` : ""}`, { scroll: false });
  async function generate(base?: Version) {
    setBusy(true); setError(null);
    try {
      const result = await api<Version>(`/me/sites/${kind}/versions`, { method: "POST", body: jsonBody({ style_id: (base && revisionStyle) || base?.style_id || styleId, instruction: instruction || base?.instruction || "", consent, revision: site?.revision || 0, base_version_id: base?.facts_current && base.code?.html ? base.id : null }) });
      await client.invalidateQueries({ queryKey: ["sites"] }); navigate(result.id);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <div className="studio-page"><PageHeading eyebrow="MY STORY STUDIO" title="나를 담는 AI 스튜디오" description="디자인을 고르고, 내 경험으로 나만의 이야기를 완성해요. 모든 초안과 수정본은 저장됩니다." action={<Link className="button subtle" href="/settings/ai"><Sparkles size={16} /> AI 연결 설정</Link>} />
    <div className="tabs studio-kinds" aria-label="문서 종류">{Object.entries(kinds).map(([id, name]) => <button key={id} className={kind === id ? "selected" : ""} aria-pressed={kind === id} onClick={() => navigate("", id)}>{name}</button>)}</div>
    <p className="kind-description">{{ portfolio: "대표 프로젝트와 내가 맡은 역할, 문제 해결 과정, 결과물을 보여주는 웹 포트폴리오를 만들어요.", cv: "경력·학력·기술을 간결하게 정리한 이력서를 만들어요. 인쇄와 PDF 보관에 맞는 문서입니다.", profile_pr: "나의 강점과 경험을 한눈에 소개하는 자기 PR 웹 프로필을 만들어요.", cover_letter: "지원 동기와 실제 경험을 연결한 문단 중심 자기소개서를 만들어요." }[kind]}</p>
    <div className="studio-layout"><div className="studio-workspace stack">
      {!versionId ? <>
        <section className="panel"><div className="section-title"><h2>01. 나에게 어울리는 디자인</h2><span className="badge purple">{styles.data?.items.length || 0}가지 스타일</span></div><p className="muted">같은 예시 프로필로 비교해 보세요. 선택한 디자인 문서를 AI에 함께 전달해요.</p><DesignGallery styles={styles.data?.items || []} selected={styleId} onSelect={setStyleId} /><ErrorMessage error={styles.error} /></section>
        <section className="panel stack"><h2>02. 어떤 이야기를 만들까요?</h2><Field label="AI에게 전달할 요청" hint="소개할 경험, 지원 분야, 강조할 강점을 알려주세요. 없는 이력을 넣지 않아요."><textarea rows={5} maxLength={15000} value={instruction} onChange={e => setInstruction(e.target.value)} placeholder={kind === "cover_letter" ? "어떤 직무에 지원하나요? 관련 경험과 지원 동기를 적어 주세요." : "누구에게 보여줄 문서인가요? 내 경험 중 강조하고 싶은 내용을 적어 주세요."} /></Field><details><summary>AI에 전달할 공개 프로필 확인</summary>{profile.data ? <div className="input-facts"><strong>{profile.data.display_name}</strong><p>{profile.data.bio || "공개된 자기소개가 없습니다."}</p>{profile.data.career_events.map(x => <p key={x.id}>{x.title} · {x.description}</p>)}<p>{profile.data.tags.map(x => x.name).join(" · ")}</p><Link className="text-link" href="/profile">프로필·공개 범위 수정</Link></div> : <Loading />}</details><label className="check-row"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> 공개 프로필과 작성 요청을 선택한 AI 제공자에게 전송하는 데 동의합니다.</label><button className="button primary" disabled={busy || !consent || !profile.data || !styles.data?.items.length} onClick={() => generate()}><Sparkles size={17} />{busy ? "작업 저장 중…" : `Claude로 ${kinds[kind]} 만들기`}</button></section>
      </> : version.isPending ? <Loading /> : version.data ? <>
        <div className="studio-version-heading"><button className="text-link" onClick={() => navigate()}>← 디자인 선택으로</button><span className="badge purple">버전 {version.data.version_number} · {versionStatus[version.data.status]}</span></div>
        {pending(version.data.status) ? <section className="panel generation-state"><Sparkles className="spin" size={36} /><h2>나만의 이야기를 만드는 중이에요</h2><p>화면을 닫아도 작업 기록은 유지돼요.<br />마이 → AI 스튜디오에서 이어서 확인할 수 있어요.</p><span className="muted">Claude · 선택한 디자인과 공개 프로필 반영</span></section> : <>
          {version.data.error && <p className="notice error" role="alert">{version.data.error}</p>}
          {version.data.code?.html && <Editor key={`${version.data.id}:${version.data.status}`} version={version.data} site={site} kind={kind} onSaved={id => navigate(id)} />}
          <section className="panel stack"><h2>{version.data.code?.html ? "AI에게 수정 요청" : "저장된 입력으로 다시 만들기"}</h2><Field label="수정본에 적용할 디자인"><select value={revisionStyle || version.data.style_id} onChange={e => setRevisionStyle(e.target.value)}>{styles.data?.items.map(style => <option key={style.id} value={style.id}>{style.name}</option>)}</select></Field><Field label="변경할 내용"><textarea value={instruction} onChange={e => setInstruction(e.target.value)} rows={3} placeholder={version.data.instruction || "예: 소개를 간결하게 하고 프로젝트를 먼저 보여주세요."} /></Field><label className="check-row"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> 공개 프로필·선택 버전·작성 요청의 AI 전송에 동의합니다.</label><button className="button subtle" disabled={busy || !consent} onClick={() => generate(version.data)}><Sparkles size={16} />새 버전 생성</button></section>
        </>}
      </> : null}<ErrorMessage error={error || version.error || sites.error} />
    </div><aside className="studio-history panel"><div className="section-title"><h2><History size={18} /> 저장된 이야기</h2><button className="icon-button" aria-label="새 문서 만들기" onClick={() => navigate()}><Plus size={18} /></button></div><p className="muted">{kinds[kind]} · {site?.versions.length || 0}개 버전</p>{site?.public_url && <a href={site.public_url} target="_blank" rel="noreferrer" className="button subtle wide">게시된 문서 열기 ↗</a>}{site?.versions.map(v => <button key={v.id} className={`history-item ${v.id === versionId ? "selected" : ""}`} onClick={() => navigate(v.id)}><FileText size={18} /><span><strong>버전 {v.version_number} {site.published_version_id === v.id && "· 게시 중"}</strong><small>{versionStatus[v.status]} · {localDate(v.created_at)}</small></span></button>)}{!site?.versions.length && <p className="history-empty">첫 문서를 만들어 보세요.<br />이전 버전도 언제든 다시 열 수 있어요.</p>}<div className="gentle-note"><Save size={18} /><p>저장된 내용은 로컬 DB에 남아요. 공개 정보가 바뀌면 기존 게시는 자동으로 중지돼요.</p></div></aside></div>

  </div>;
}

function Editor({ version, site, kind, onSaved }: { version: Version; site?: Site; kind: string; onSaved: (id: string) => void }) {
  const client = useQueryClient();
  const [documentDraft, setDocument] = useSessionDraft<Document>(`document-${version.id}`), [codeDraft, setCode] = useSessionDraft<Code>(`code-${version.id}`);
  const document = documentDraft || version.gui, code = codeDraft || version.code;
  const printable = kind === "cv" || kind === "cover_letter";
  const [tab, setTab] = useState("preview"), [width, setWidth] = useState("desktop"), [file, setFile] = useState<keyof Code>("html");
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(), [message, setMessage] = useState("");
  const dirty = JSON.stringify(document) !== JSON.stringify(version.gui) || JSON.stringify(code) !== JSON.stringify(version.code);
  useUnsavedChanges(dirty && !busy);
  const field = (name: keyof Document, value: unknown) => setDocument({ ...document, [name]: value });
  async function action(mode: "gui" | "code" | "restore" | "publish" | "revoke") {
    setBusy(true); setError(null); setMessage("");
    try {
      const revision = site?.revision || version.site_revision;
      if (mode === "publish") { await api(`/me/site-versions/${version.id}/publish`, { method: "POST", body: jsonBody({ revision }) }); setMessage("이 버전을 게시했어요."); }
      else if (mode === "revoke") { await api(`/me/sites/${version.site_id}/revoke`, { method: "POST", body: jsonBody({ revision }) }); setMessage("게시를 중지했어요. 저장된 버전은 유지됩니다."); }
      else { const next = await api<Version>(`/me/site-versions/${version.id}/revisions`, { method: "POST", body: jsonBody({ revision, mode, ...(mode === "gui" ? { document } : mode === "code" ? { code } : {}) }) }); setDocument(null); setCode(null); onSaved(next.id); }
      await client.invalidateQueries({ queryKey: ["sites"] });
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  function download() {
    // Export a static document for local printing; sandboxed JS remains in preview/publication only.
    const html = (version.preview_html || "").replace(/<script>[\s\S]*?<\/script>/g, "");
    const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
    const anchor = window.document.createElement("a"); anchor.href = url; anchor.download = `${document.title || "dudri"}-v${version.version_number}.html`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000); setMessage(printable ? "문서를 저장했어요. 파일을 브라우저로 열어 인쇄 → PDF로 저장할 수 있어요." : "포트폴리오의 정적 HTML을 저장했어요. 인터랙션이 포함된 전체 사이트는 미리보기와 게시된 페이지에서 볼 수 있어요.");
  }
  return <section className="panel studio-editor"><div className="editor-toolbar"><div className="tabs">{[["preview", "미리보기", Eye], ["gui", "내용·디자인", FileText], ["code", "코드", Code2]].map(([id, label, Icon]) => { const I = Icon as typeof Eye; return <button key={id as string} className={tab === id ? "selected" : ""} onClick={() => { if (dirty && id !== tab) { setError(new Error("편집 내용을 새 버전으로 저장한 뒤 편집 방식을 바꿔 주세요.")); return; } setTab(id as string); }}><I size={15} />{label as string}</button>; })}</div><div className="device-toggle"><button aria-label="PC 미리보기" aria-pressed={width === "desktop"} onClick={() => setWidth("desktop")}><Monitor size={18} /></button><button aria-label="모바일 미리보기" aria-pressed={width === "mobile"} onClick={() => setWidth("mobile")}><Smartphone size={18} /></button></div></div>
    {tab === "preview" && <div className={`document-preview ${width}`}><iframe title="저장된 문서 미리보기" sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={version.preview_html} /></div>}
    {tab === "gui" && <div className="stack"><p className="muted">편집 표시가 있는 영역을 바꿔요. 직접 작성한 나머지 코드는 유지됩니다.</p>{(["title", "headline", "summary"] as const).map((name, i) => <Field key={name} label={["문서 제목", "첫 소개 문구", "자기소개"][i]}><textarea value={document[name] || ""} rows={i === 2 ? 4 : 2} maxLength={i === 0 ? 200 : i === 1 ? 500 : 12000} onChange={e => field(name, e.target.value)} /></Field>)}<div className="form-grid"><Field label="강조 색상"><input type="color" value={document.accent || "#7060d9"} onChange={e => field("accent", e.target.value)} /></Field><Field label="글꼴"><select value={document.font || "sans-serif"} onChange={e => field("font", e.target.value)}><option value="sans-serif">고딕</option><option value="serif">명조</option><option value="monospace">고정폭</option></select></Field><Field label="섹션 간격"><input type="range" min={8} max={64} value={document.spacing || 24} onChange={e => field("spacing", Number(e.target.value))} /></Field></div>{document.sections?.map((section, i) => <div className="section-editor stack tight" key={section.id}><div className="section-title"><h3>섹션 {i + 1}</h3><div className="card-actions">{[-1, 1].map(delta => <button key={delta} className="icon-button" aria-label={`섹션 ${i + 1} ${delta < 0 ? "위로" : "아래로"}`} disabled={i + delta < 0 || i + delta >= document.sections.length} onClick={() => { const next = [...document.sections]; [next[i], next[i + delta]] = [next[i + delta], next[i]]; field("sections", next); }}>{delta < 0 ? <ArrowUp size={16} /> : <ArrowDown size={16} />}</button>)}<button className="icon-button" aria-label={`섹션 ${i + 1} 제거`} onClick={() => field("sections", document.sections.filter((_, index) => index !== i))}><X size={16} /></button></div></div>{(["heading", "body", "items"] as const).map(name => <Field key={name} label={name === "heading" ? "제목" : name === "body" ? "내용" : "목록 (한 줄에 하나)"}><textarea rows={name === "heading" ? 1 : 3} value={name === "items" ? section.items.join("\n") : section[name]} onChange={e => field("sections", document.sections.map((s, n) => n === i ? { ...s, [name]: name === "items" ? e.target.value.split("\n") : e.target.value } : s))} /></Field>)}</div>)}<button className="button subtle" onClick={() => field("sections", [...document.sections, { id: `section-${Date.now()}`, heading: "새 섹션", body: "", items: [] }])}><Plus size={15} />섹션 추가</button><button className="button primary" disabled={busy || !version.facts_current} onClick={() => action("gui")}><Save size={16} />변경 내용을 새 버전으로 저장</button></div>}
    {tab === "code" && <div className="stack"><div className="tabs">{(["html", "css", "javascript"] as const).map(name => <button key={name} className={file === name ? "selected" : ""} onClick={() => setFile(name)}>{name.toUpperCase()}</button>)}</div><Field label={`${file.toUpperCase()} 편집`}><textarea className="code-editor" spellCheck={false} value={code[file]} onChange={e => setCode({ ...code, [file]: e.target.value })} rows={20} /></Field><p className="muted">외부 스크립트·네트워크·폼은 제한돼요. data-field와 data-section 표시를 유지하면 내용 편집으로 돌아갈 수 있어요.</p><button className="button primary" disabled={busy || !version.facts_current} onClick={() => action("code")}><Save size={16} />코드 새 버전 저장</button></div>}
    <div className="editor-footer"><button className="button subtle" onClick={download} disabled={dirty}><Download size={15} />{printable ? "HTML 저장 · PDF 인쇄" : "포트폴리오 HTML 저장"}</button><button className="button subtle" disabled={busy || !version.facts_current || dirty} onClick={() => action("restore")}>이 버전으로 복구</button><button className="button primary" disabled={busy || dirty || version.status !== "preview_ready" || !version.facts_current} onClick={() => action("publish")}>이 버전 게시</button>{site?.published_version_id && <button className="text-link" disabled={busy} onClick={() => action("revoke")}>게시 중지</button>}</div>{dirty && <p className="notice">저장하지 않은 변경이 있어요. 새 버전으로 저장한 뒤 미리보기·다운로드·게시를 확인해 주세요.</p>}{!version.facts_current && <p className="notice">공개 프로필이 변경됐어요. 최신 정보로 새로 생성해 주세요.</p>}<ErrorMessage error={error} />{message && <p className="notice" role="status">{message}</p>}<p className="muted">{version.validation.model && `${version.validation.model} · `}저장된 버전은 자동으로 공개되지 않습니다.</p>
  </section>;
}

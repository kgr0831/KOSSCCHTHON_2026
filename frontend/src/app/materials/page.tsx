"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText, Link2, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import {
  api,
  jsonBody,
  localDate,
  type ExternalAccount,
  type GithubConnect,
  type GithubRepository,
  type SourceMaterial,
  type Subscription,
} from "@/lib/api";
import { AuthGate, ErrorMessage, Field, PageHeading } from "@/components/ui";

type Run = { id: string; status: string; error?: string };
type Suggestion = { id: string; revision: number; target_kind: string; decision: string; proposed_value: { title: string; text: string }; evidence: { quote: string }[] };

function externalHttpsUrl(value: string | null | undefined) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function repositoryId(repository: GithubRepository) { return String(repository.repository_id ?? repository.id ?? ""); }

export default function MaterialsPage() { return <AuthGate><Materials /></AuthGate>; }

function Materials() {
  const client = useQueryClient();
  const [selected, setSelected] = useState<string[]>([]);
  const [selectedRepositories, setSelectedRepositories] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  const materials = useQuery({ queryKey: ["materials"], queryFn: () => api<{ items: SourceMaterial[] }>("/me/source-materials") });
  const accounts = useQuery({ queryKey: ["external-accounts"], queryFn: () => api<{ items: ExternalAccount[] }>("/me/external-accounts") });
  const subscription = useQuery({ queryKey: ["subscription"], queryFn: () => api<Subscription>("/me/subscription") });
  const githubAccount = accounts.data?.items.find(account => account.provider === "github");
  const repositories = useQuery({
    queryKey: ["github-repositories", githubAccount?.id],
    queryFn: () => api<{ items: GithubRepository[] }>("/me/external-accounts/github/repositories"),
    enabled: Boolean(githubAccount),
  });
  const runs = useQuery({ queryKey: ["analysis-runs"], queryFn: () => api<{ items: Run[] }>("/me/analysis-runs"), refetchInterval: query => query.state.data?.items.some(item => ["queued", "running"].includes(item.status)) ? 2000 : false });
  const suggestions = useQuery({ queryKey: ["suggestions", runs.data], queryFn: () => api<{ items: Suggestion[] }>("/me/suggestions") });
  const sourceItems = materials.data?.items || [];
  const linkedInMaterial = sourceItems.find(item => ["linkedin", "linkedin_profile"].includes(item.material_kind) && item.access_status === "available");
  const analysisMaterials = sourceItems.filter(item => !["linkedin", "linkedin_profile"].includes(item.material_kind));
  const selectedMaterialIds = selected.filter(id => analysisMaterials.some(item => item.id === id && item.access_status === "available"));
  const repositoryItems = (repositories.data?.items || []).filter(repository => Boolean(repositoryId(repository)));
  const selectedRepositoryIds = selectedRepositories.filter(id => repositoryItems.some(repository => repositoryId(repository) === id));
  const analysisAllowed = subscription.data?.plan === "premium";

  async function perform(path: string, body?: unknown, method = "POST") {
    setBusy(true); setError(null); setMessage("");
    try {
      await api(path, { method, ...(body ? { body: body instanceof FormData ? body : jsonBody(body) } : {}) });
      await client.invalidateQueries();
      return true;
    } catch (reason) {
      setError(reason);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function connectGithub() {
    setBusy(true); setError(null); setMessage("");
    try {
      const result = await api<GithubConnect>("/me/external-accounts/github/connect", { method: "POST" });
      const url = externalHttpsUrl(result.url);
      if (!url) throw new Error("GitHub 연결 주소를 확인할 수 없어요. 잠시 후 다시 시도해 주세요.");
      window.location.assign(url);
      setBusy(false);
    } catch (reason) {
      setError(reason);
      setBusy(false);
    }
  }

  async function syncGithubRepositories() {
    if (!selectedRepositoryIds.length) return;
    const repositoryIds = selectedRepositoryIds.map(Number);
    if (repositoryIds.some(id => !Number.isSafeInteger(id) || id <= 0)) {
      setError(new Error("GitHub 저장소를 다시 선택해 주세요."));
      return;
    }
    if (await perform("/me/external-accounts/github/sync", { repository_ids: repositoryIds })) {
      setSelectedRepositories([]);
      setMessage("선택한 GitHub 저장소를 비공개 자료로 가져왔어요. 아직 AI 분석은 시작하지 않았어요.");
    }
  }

  return <>
    <PageHeading eyebrow="FROM EXPERIENCE TO STORY" title="내 자료와 AI 검토" description="자료를 보관하고, 필요한 것만 선택해 분석하세요. 제안은 직접 승인해야 프로필에 반영돼요." action={<Link className="button subtle" href="/studio?kind=cv">새 CV 만들기</Link>} />
    <section className="dashboard-section">
      <div className="section-title"><h2>외부 자료 연결</h2></div>
      <div className="grid-2">
        <section className="panel stack" aria-labelledby="github-connection-title">
          <h2 id="github-connection-title"><Link2 size={20} /> GitHub 연결</h2>
          {!githubAccount ? <>
            <p>GitHub가 안내하는 권한 동의 후, 공개·비공개 저장소 목록에서 가져올 자료를 직접 고를 수 있어요.</p>
            <button className="button primary" type="button" disabled={busy} onClick={() => void connectGithub()}>GitHub 연결하기</button>
          </> : <>
            <p><strong>{githubAccount.login || "GitHub"}</strong> 계정이 연결되어 있어요. 가져올 저장소를 직접 선택하세요.</p>
            {repositories.isPending ? <p className="muted" role="status">저장소 목록을 불러오는 중이에요.</p> : repositoryItems.length ? <div className="stack tight" role="group" aria-label="가져올 GitHub 저장소">
              {repositoryItems.map(repository => {
                const id = repositoryId(repository);
                const visibility = repository.private ? "비공개" : "공개";
                const repositoryUrl = externalHttpsUrl(repository.canonical_url || repository.html_url);
                return <div className="material-row" key={id}>
                  <label className="check-row"><input aria-label={`${repository.full_name} (${visibility})`} type="checkbox" disabled={busy} checked={selectedRepositoryIds.includes(id)} onChange={event => setSelectedRepositories(current => event.target.checked ? [...current, id] : current.filter(value => value !== id))} /><span><strong>{repository.full_name || repository.display_name || repository.name}</strong><small>{visibility}{repository.description ? ` · ${repository.description}` : ""}</small></span></label>
                  {repositoryUrl && <a className="text-link" href={repositoryUrl} target="_blank" rel="noopener noreferrer">저장소 열기 <ExternalLink size={12} /></a>}
                </div>;
              })}
            </div> : !repositories.isError && <p className="muted">이 권한으로 볼 수 있는 GitHub 저장소가 없어요.</p>}
            <div className="card-actions">
              <button className="button primary" type="button" disabled={busy || !selectedRepositoryIds.length} onClick={() => void syncGithubRepositories()}>선택한 저장소 {selectedRepositoryIds.length ? `${selectedRepositoryIds.length}개 ` : ""}가져오기</button>
              <button className="button subtle" type="button" disabled={busy} onClick={async () => {
                if (await perform(`/me/external-accounts/${githubAccount.id}`, undefined, "DELETE")) {
                  setSelectedRepositories([]);
                  setMessage("GitHub 연결을 해제했어요.");
                }
              }}>연결 해제</button>
            </div>
            <p className="muted">선택한 저장소만 비공개 자료로 가져오며, AI 분석은 자동으로 시작하지 않아요.</p>
          </>}
        </section>
        <section className="panel stack" aria-labelledby="linkedin-connection-title">
          <h2 id="linkedin-connection-title"><Link2 size={20} /> LinkedIn 프로필</h2>
          {linkedInMaterial ? <>
            <p>LinkedIn 프로필 링크를 저장했어요. 이 기능은 URL 등록과 외부 링크만 제공하며 자동 수집이나 OAuth 연결을 하지 않아요.</p>
            <div className="card-actions">
              {externalHttpsUrl(linkedInMaterial.canonical_url) ? <a className="button subtle" href={externalHttpsUrl(linkedInMaterial.canonical_url)!} target="_blank" rel="noopener noreferrer">LinkedIn 프로필 열기 <ExternalLink size={15} /></a> : <span className="muted">저장한 링크를 열 수 없어요.</span>}
              <button className="button subtle" type="button" disabled={busy} onClick={async () => {
                if (await perform(`/me/source-materials/${linkedInMaterial.id}`, undefined, "DELETE")) setMessage("LinkedIn 프로필 링크를 삭제했어요.");
              }}>LinkedIn 연결 해제</button>
            </div>
          </> : <form className="stack" onSubmit={async event => {
            event.preventDefault();
            const form = event.currentTarget;
            const url = String(new FormData(form).get("linkedin_url") || "");
            if (await perform("/me/source-materials/linkedin", { url })) {
              form.reset();
              setMessage("LinkedIn 프로필 링크를 저장했어요.");
            }
          }}>
            <p>LinkedIn 프로필 URL만 저장해 외부 링크로 열 수 있어요. LinkedIn 로그인이나 자동 정보 수집은 하지 않아요.</p>
            <Field label="LinkedIn 프로필 URL"><input name="linkedin_url" type="url" required maxLength={2048} placeholder="https://www.linkedin.com/in/…" disabled={busy} /></Field>
            <button className="button primary" disabled={busy}>LinkedIn 링크 저장</button>
          </form>}
        </section>
      </div>
    </section>
    <div className="grid-2">
      <section className="panel stack"><h2><Upload size={20} /> 경험 자료 등록</h2><form className="stack" onSubmit={async event => { event.preventDefault(); const form = event.currentTarget; const data = new FormData(form); if (await perform("/me/source-materials", { display_name: data.get("name"), text: data.get("text") })) { form.reset(); setMessage("자료를 비공개로 저장했어요."); } }}><Field label="자료 이름"><input name="name" required maxLength={200} placeholder="프로젝트 회고, 기존 자기소개서…" /></Field><Field label="내용"><textarea name="text" required rows={7} maxLength={100000} placeholder="직접 작성한 경험이나 CV의 텍스트를 붙여넣어 주세요." /></Field><button className="button primary" disabled={busy}>자료 저장</button></form><Field label="또는 파일에서 가져오기" hint="텍스트 PDF · UTF-8 TXT/MD, 10MB·100쪽 이하. 추출된 텍스트를 비공개 DB에 저장합니다."><input type="file" accept=".pdf,.txt,.md" disabled={busy} onChange={async event => { const file = event.target.files?.[0]; if (!file) return; const body = new FormData(); body.append("file", file); if (await perform("/me/source-materials/upload", body)) setMessage("파일 내용을 비공개로 저장했어요."); event.target.value = ""; }} /></Field></section>
      <section className="panel stack"><h2><FileText size={20} /> 저장된 자료</h2>{analysisMaterials.length ? analysisMaterials.map(item => <div className="material-row" key={item.id}><label className="check-row"><input type="checkbox" disabled={item.access_status !== "available" || busy} checked={selectedMaterialIds.includes(item.id)} onChange={event => setSelected(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))} /><span><strong>{item.display_name}</strong><small>{item.access_status === "available" ? localDate(item.created_at) : "사용 철회됨"}</small></span></label>{item.access_status === "available" && <button className="text-link" disabled={busy} onClick={async () => { if (await perform(`/me/source-materials/${item.id}`, undefined, "DELETE")) setSelected(current => current.filter(id => id !== item.id)); }}>사용 철회</button>}</div>) : <p className="muted">등록한 자료가 여기에 표시돼요.</p>}<label className="check-row"><input type="checkbox" checked={consent} disabled={busy} onChange={event => setConsent(event.target.checked)} /> 선택한 자료를 AI 제공자에게 전송하는 데 동의합니다.</label>{subscription.data?.plan === "free" ? <Link className="button primary" href="/pricing"><Sparkles size={16} />AI 분석 플랜 보기</Link> : <button className="button primary" disabled={busy || subscription.isPending || !analysisAllowed || !consent || !selectedMaterialIds.length} onClick={() => void perform("/me/analysis-runs", { material_ids: selectedMaterialIds, consent })}><Sparkles size={16} />선택 자료 분석</button>}{runs.data?.items.map(item => ["queued", "running", "failed"].includes(item.status) && <p className={`notice ${item.status === "failed" ? "error" : ""}`} key={item.id}>{item.status === "failed" ? item.error : "자료를 분석 중이에요. 화면을 닫아도 작업 기록이 남아요."}</p>)}<p className="muted">사용 철회 시 자료 원문이 삭제되고 진행 중 분석·미승인 제안은 더 이상 적용할 수 없어요. 이미 승인한 프로필은 프로필 화면에서 별도로 관리하세요.</p></section>
    </div>
    <ErrorMessage error={error || materials.error || accounts.error || subscription.error || repositories.error || suggestions.error || runs.error} />
    {message && <p className="notice" role="status">{message}</p>}
    <section className="dashboard-section"><div className="section-title"><h2>검토할 AI 제안</h2><Link className="text-link" href="/profile">확정 프로필 보기</Link></div><div className="grid-2">{suggestions.data?.items.filter(item => item.decision === "pending").map(item => <Review key={item.id} suggestion={item} onSave={body => perform(`/me/suggestions/${item.id}/decision`, body)} busy={busy} />)}</div>{!suggestions.data?.items.some(item => item.decision === "pending") && <div className="panel"><p className="muted">분석 결과가 생기면 근거와 함께 이곳에서 검토할 수 있어요.</p></div>}</section>
  </>;
}

function Review({ suggestion, onSave, busy }: { suggestion: Suggestion; onSave: (body: unknown) => Promise<boolean>; busy: boolean }) {
  const [title, setTitle] = useState(suggestion.proposed_value.title);
  const [text, setText] = useState(suggestion.proposed_value.text);
  const [isPublic, setIsPublic] = useState(false);
  return <article className="panel stack"><span className="badge purple">{suggestion.target_kind === "bio" ? "자기소개 제안" : "경험 제안"}</span><Field label="제목"><input value={title} maxLength={200} onChange={event => setTitle(event.target.value)} /></Field><Field label="승인할 내용"><textarea value={text} maxLength={5000} onChange={event => setText(event.target.value)} rows={5} /></Field><details><summary>원문 근거 확인</summary>{suggestion.evidence.map((evidence, index) => <blockquote key={index}>{evidence.quote}</blockquote>)}</details><label className="check-row"><input type="checkbox" checked={isPublic} onChange={event => setIsPublic(event.target.checked)} /> 이 내용을 프로필에 공개</label><div className="card-actions"><button className="button primary" disabled={busy || !text.trim()} onClick={() => void onSave({ decision: "accepted", revision: suggestion.revision, title, text, is_public: isPublic })}>수정한 내용 승인</button><button className="button subtle" disabled={busy} onClick={() => void onSave({ decision: "rejected", revision: suggestion.revision })}>제외</button></div></article>;
}

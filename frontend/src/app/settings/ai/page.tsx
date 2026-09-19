"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu, Terminal } from "lucide-react";
import { api, jsonBody } from "@/lib/api";
import { AuthGate, ErrorMessage, Field, Loading, PageHeading } from "@/components/ui";

type Connection = { provider: string; device_id: string; device_name: string; executable_path: string; account_email: string; status: string; models: string[]; default_model: string; checked_at: string; current_pc: boolean };
type Settings = { transport: string; easy_model: string; hard_model: string; cli_provider: string; cli_model: string; cli_connections: Connection[]; revision: number };
type Providers = { api: { configured: boolean; models: string[]; error?: string }; cli: { allowed: boolean; codex_installed: boolean; claude_installed: boolean }; consent_text: string };
const statusText: Record<string, string> = { connected: "로그인 확인됨", needs_login: "구독 계정 로그인 필요", not_installed: "설치 필요", error: "확인 실패 · 다시 확인해 주세요" };

export default function AISettingsPage() { return <AuthGate><SettingsPage /></AuthGate>; }
function SettingsPage() {
  const settings = useQuery({ queryKey: ["ai-settings"], queryFn: () => api<Settings>("/me/ai-settings") });
  const providers = useQuery({ queryKey: ["ai-providers"], queryFn: () => api<Providers>("/ai/providers"), retry: false });
  return <><PageHeading eyebrow="CONNECTED INTELLIGENCE" title="AI 연결 설정" description="서버 API 또는 PC에 로그인한 Codex·Claude CLI로 AI 기능을 사용해요." />
    <div className="ai-routing">
      <article className="panel"><Cpu /><h2>서버 API</h2><p>배포 앱과 PC에서 사용<br />가벼운 작업은 Haiku·Flash, 복잡한 작업은 Sonnet</p></article>
      <article className="panel"><Terminal /><h2>Codex · Claude CLI</h2><p>PC에서 BAT로 실행할 때만 사용<br />CLI 기본 제공자는 Codex예요.</p></article>
    </div>
    {settings.isPending ? <Loading /> : settings.data && <SettingsForm initial={settings.data} providers={providers.data} />}
    <ErrorMessage error={settings.error || providers.error} /></>;
}
function SettingsForm({ initial, providers }: { initial: Settings; providers?: Providers }) {
  const [form, setForm] = useState(initial), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(), [saved, setSaved] = useState(false);
  const client = useQueryClient();
  const allowed = providers?.cli.allowed === true;
  const connections = form.cli_connections || [];
  const current = connections.find(x => x.current_pc && x.provider === form.cli_provider);
  async function save() {
    setBusy(true); setSaved(false); setError(null);
    try {
      const { transport, easy_model, hard_model, cli_provider, cli_model, revision } = form;
      const result = await api<Settings>("/me/ai-settings", { method: "PUT", body: jsonBody({ transport, easy_model, hard_model, ...(allowed ? { cli_provider, cli_model } : {}), revision }) });
      setForm(result); setSaved(true);
      await client.invalidateQueries({ queryKey: ["ai-settings"] });
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function check(family: string) {
    setBusy(true); setSaved(false); setError(null);
    try {
      const result = await api<Settings>(`/me/ai-cli-connections/${family}/check`, { method: "POST" });
      setForm(result); client.setQueryData(["ai-settings"], result);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <section className="panel stack">
    <p className="notice"><strong>CLI는 PC 실행 전용입니다.</strong> 배포 웹에서는 서버 API를 사용해요. DB에는 실행 경로·연결 계정 이메일·연결 상태·모델·확인 PC와 시각만 저장하며, 로그인 인증 정보는 각 CLI가 PC에서 관리합니다.</p>
    <Field label="연결 방식"><select value={form.transport} disabled={busy} onChange={e => { setSaved(false); setForm({ ...form, transport: e.target.value }); }}>
      <option value="api">서버 API</option><option disabled={!allowed} value="cli">PC 전용 · 구독 CLI</option><option disabled={!allowed} value="hybrid">PC 전용 · 가벼운 작업은 API, 복잡한 작업은 CLI</option>
    </select></Field>
    {form.transport !== "cli" && <>
      <p className="notice">{providers?.api.configured ? "서버 API가 설정돼 있어요." : "서버 API 설정이 필요해요. PC 실행 시 루트 .env의 DUDRI_AI_API_KEY를 설정해 주세요."}</p>
      {providers?.api.error && <p className="notice error">{providers.api.error}</p>}
      {(["easy_model", "hard_model"] as const).filter(name => form.transport !== "hybrid" || name === "easy_model").map(name => <Field key={name} label={name === "easy_model" ? "가벼운 작업 API 모델" : "복잡한 작업 API 모델"}>
        <select value={form[name]} onChange={e => setForm({ ...form, [name]: e.target.value })}><option value="">사용 가능한 모델 자동 선택</option>{providers?.api.models.filter(x => name === "easy_model" ? (/gemini/i.test(x) && /flash/i.test(x)) || /haiku/i.test(x) : /claude/i.test(x)).map(x => <option key={x} value={x}>{x}</option>)}</select>
      </Field>)}
    </>}
    <div className="cli-guide stack">
      <h2>PC의 CLI 연결 기록</h2>
      <p className="muted">연결 상태는 마지막 확인 당시의 로그인 상태예요. 구독 만료·해지 또는 사용량 제한은 생성할 때 확인될 수 있습니다. 다른 PC에서는 그 PC에서 다시 로그인하고 연결을 확인해 주세요.</p>
      {allowed ? <>
        <p>BAT 실행 터미널에서 <kbd>X</kbd>로 Codex, <kbd>C</kbd>로 Claude에 로그인한 뒤 아래에서 확인해 주세요. 확인하면 저장하지 않은 설정은 마지막 저장 상태로 돌아갑니다.</p>
        <div className="actions">{(["codex", "claude"] as const).map(family => <button className="button" key={family} disabled={busy} onClick={() => check(family)}>{family === "codex" ? "Codex" : "Claude"} 연결 확인</button>)}</div>
      </> : <p className="notice">배포 웹에서는 저장된 기록만 볼 수 있어요. 연결 확인과 CLI 생성은 PC에서 BAT로 실행해 주세요.</p>}
      {connections.length === 0 ? <p className="muted">저장된 CLI 연결 기록이 없습니다.</p> : connections.map(x => <article className="panel" key={x.device_id + x.provider} style={{ overflowWrap: "anywhere", minWidth: 0 }}>
        <h3>{x.provider === "codex" ? "Codex" : "Claude"} · {x.device_name}{x.current_pc ? " · 이 PC" : ""}</h3>
        <p>{statusText[x.status] || "확인 필요"}<br />계정: {x.account_email || "확인되지 않음"}<br />경로: {x.executable_path || "설치되지 않음"}<br />기본 모델: {x.default_model || "확인되지 않음"}<br />확인 시각: {new Date(x.checked_at).toLocaleString("ko-KR")}</p>
      </article>)}
      {allowed && <>
        <Field label="PC CLI 제공자"><select value={form.cli_provider || "codex"} disabled={busy} onChange={e => setForm({ ...form, cli_provider: e.target.value, cli_model: "" })}><option value="codex">Codex · 기본</option><option value="claude">Claude</option></select></Field>
        <Field label="PC CLI 모델"><select value={form.cli_model || ""} disabled={busy || !current} onChange={e => setForm({ ...form, cli_model: e.target.value })}><option value="">CLI 기본 모델{current?.default_model ? ` · ${current.default_model}` : ""}</option>{current?.models.map(model => <option key={model} value={model}>{model}</option>)}</select></Field>
      </>}
    </div>
    <button className="button primary" disabled={busy || !providers} onClick={save}>{busy ? "처리 중…" : "연결 설정 저장"}</button>
    <ErrorMessage error={error} />{saved && <p className="notice" role="status">설정을 저장했어요.</p>}<p className="muted">{providers?.consent_text}</p>
  </section>;
}

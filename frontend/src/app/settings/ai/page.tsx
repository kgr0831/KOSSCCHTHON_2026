"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Cpu, Link2, Terminal, Unplug } from "lucide-react";
import { api, jsonBody } from "@/lib/api";
import { AuthGate, ErrorMessage, Field, Loading, PageHeading } from "@/components/ui";

type Connection = { provider: string; device_id: string; device_name: string; executable_path: string; account_email: string; status: string; models: string[]; default_model: string; checked_at: string; current_pc: boolean };
type Connector = { id: string; device_id: string; device_name: string; status: string; online: boolean; last_seen_at: string | null; expires_at: string | null };
type Settings = { transport: string; easy_model: string; hard_model: string; cli_provider: string; cli_model: string; cli_device_id: string; cli_connections: Connection[]; cli_connectors?: Connector[]; revision: number };
type Providers = { api: { configured: boolean; models: string[]; error?: string }; cli: { allowed: boolean; codex_installed: boolean; claude_installed: boolean; connection: string; connector_available?: boolean }; consent_text: string };
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
  const [form, setForm] = useState(initial), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(), [saved, setSaved] = useState(false), [pairing, setPairing] = useState<{ command: string; expiresAt: string }>();
  const client = useQueryClient();
  const allowed = providers?.cli.allowed === true;
  const connections = form.cli_connections || [];
  const fallbackDevice = allowed ? connections.find(x => x.current_pc && x.provider === form.cli_provider)?.device_id || "" : "";
  const selectedDevice = form.cli_device_id || fallbackDevice;
  const current = connections.find(x => x.device_id === selectedDevice && x.provider === form.cli_provider);
  const connected = current?.status === "connected";
  const connectors = form.cli_connectors || [];
  const activeConnectorDevices = new Set(connectors.filter(x => x.status === "active" && (!x.expires_at || new Date(x.expires_at).getTime() > Date.now())).map(x => x.device_id));
  const connectedConnections = connections.filter(x => x.status === "connected" && (allowed || activeConnectorDevices.has(x.device_id)));
  const installed = (family: "codex" | "claude") => family === "codex" ? providers?.cli.codex_installed === true : providers?.cli.claude_installed === true;
  async function save() {
    setBusy(true); setSaved(false); setError(null);
    try {
      const { transport, easy_model, hard_model, cli_provider, cli_model, revision } = form;
      const result = await api<Settings>("/me/ai-settings", { method: "PUT", body: jsonBody({ transport, easy_model, hard_model, cli_provider, cli_model, cli_device_id: selectedDevice || null, revision }) });
      setForm(result); setSaved(true);
      await client.invalidateQueries({ queryKey: ["ai-settings"] });
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function check(family: string) {
    setBusy(true); setSaved(false); setError(null);
    try {
      const result = await api<Settings>(`/me/ai-cli-connections/${family}/check`, { method: "POST" });
      setForm(result); client.setQueryData(["ai-settings"], result);
      await client.invalidateQueries({ queryKey: ["ai-providers"] });
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function pair() {
    setBusy(true); setSaved(false); setError(null);
    try {
      const result = await api<{ pairing_code: string; expires_at: string }>("/me/ai-cli-connectors/pairings", { method: "POST", body: jsonBody({}) });
      const apiOrigin = process.env.NEXT_PUBLIC_WS_ORIGIN || window.location.origin;
      setPairing({ command: `start-local.bat --connector "${result.pairing_code}" --api-origin "${apiOrigin}"`, expiresAt: result.expires_at });
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function copyPairing() {
    if (!pairing) return;
    try { await navigator.clipboard.writeText(pairing.command); }
    catch { setError(new Error("명령을 복사하지 못했습니다. 직접 선택해 복사해 주세요.")); }
  }
  async function revoke(connectorId: string) {
    setBusy(true); setSaved(false); setError(null);
    try {
      await api(`/me/ai-cli-connectors/${connectorId}`, { method: "DELETE" });
      await client.invalidateQueries({ queryKey: ["ai-settings"] });
      const next = await client.fetchQuery({ queryKey: ["ai-settings"], queryFn: () => api<Settings>("/me/ai-settings") });
      setForm(next);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function refreshConnections() {
    setBusy(true); setError(null);
    try {
      const next = await api<Settings>("/me/ai-settings");
      setForm(next); client.setQueryData(["ai-settings"], next);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <section className="panel stack">
    <p className="notice"><strong>CLI는 사용자의 PC에서만 실행됩니다.</strong> 배포 웹은 일회성 연결 코드로 PC 커넥터에 작업을 전달합니다. CLI 로그인 정보와 연결 토큰은 서버 DB나 브라우저에 저장하지 않습니다.</p>
    <Field label="연결 방식"><select value={form.transport} disabled={busy} onChange={e => { setSaved(false); setForm({ ...form, transport: e.target.value }); }}>
      <option value="api">서버 API</option><option disabled={!connected} value="cli">PC 전용 · 구독 CLI</option><option disabled={!connected} value="hybrid">PC 전용 · 가벼운 작업은 API, 복잡한 작업은 CLI</option>
    </select></Field>
    {!connected && <p className="notice" role="status"><strong>PC 커넥터를 연결하면 CLI·혼합 연결을 선택할 수 있어요.</strong> 아래에서 연결 코드를 만든 뒤, Codex 또는 Claude에 로그인한 PC에서 실행해 주세요.</p>}
    {form.transport !== "cli" && <>
      <p className="notice">{providers?.api.configured ? "서버 API가 설정돼 있어요." : "서버 API 설정이 필요해요. PC 실행 시 루트 .env의 DUDRI_AI_API_KEY를 설정해 주세요."}</p>
      {providers?.api.error && <p className="notice error">{providers.api.error}</p>}
      {(["easy_model", "hard_model"] as const).filter(name => form.transport !== "hybrid" || name === "easy_model").map(name => <Field key={name} label={name === "easy_model" ? "가벼운 작업 API 모델" : "복잡한 작업 API 모델"}>
        <select value={form[name]} onChange={e => setForm({ ...form, [name]: e.target.value })}><option value="">사용 가능한 모델 자동 선택</option>{providers?.api.models.filter(x => name === "easy_model" ? (/gemini/i.test(x) && /flash/i.test(x)) || /haiku/i.test(x) : /claude/i.test(x)).map(x => <option key={x} value={x}>{x}</option>)}</select>
      </Field>)}
    </>}
    <div className="cli-guide stack">
      <h2>PC CLI 커넥터</h2>
      <p className="muted">연결 코드는 10분 동안 한 번만 사용할 수 있습니다. 커넥터 창을 열어 둔 PC만 해당 PC로 요청된 문서 생성 작업을 처리합니다.</p>
      {!allowed && <div className="actions"><button className="button primary" disabled={busy} onClick={pair}><Link2 size={16} />PC 연결 코드 만들기</button><button className="button" disabled={busy} onClick={() => void refreshConnections()}>연결 상태 새로고침</button></div>}
      {pairing && <article className="notice stack" role="status"><strong>PC의 프로젝트 폴더에서 아래 명령을 실행해 주세요.</strong><code style={{ overflowWrap: "anywhere", userSelect: "text" }}>{pairing.command}</code><p className="muted">만료: {new Date(pairing.expiresAt).toLocaleString("ko-KR")}. 이 코드는 다시 표시되지 않으며, 실행 뒤에는 PC 창을 닫지 마세요.</p><button className="button" onClick={copyPairing}><Copy size={16} />명령 복사</button></article>}
      {connectors.length > 0 && <div className="stack">{connectors.map(connector => <article className="panel" key={connector.id}>
        <h3>{connector.device_name} {connector.online ? "· 연결됨" : "· 대기 중"}</h3><p>마지막 연결: {connector.last_seen_at ? new Date(connector.last_seen_at).toLocaleString("ko-KR") : "아직 없음"}</p><button className="text-link" disabled={busy} onClick={() => revoke(connector.id)}><Unplug size={15} />연결 해제</button>
      </article>)}</div>}
      <Field label="실행할 PC CLI"><select value={current ? `${current.provider}:${current.device_id}` : ""} disabled={busy || !connectedConnections.length} onChange={e => { const [provider, device] = e.target.value.split(":"); setSaved(false); setForm({ ...form, cli_provider: provider || "codex", cli_device_id: device || "", cli_model: "" }); }}><option value="">PC CLI를 선택해 주세요</option>{connectedConnections.map(connection => <option key={`${connection.provider}:${connection.device_id}`} value={`${connection.provider}:${connection.device_id}`}>{connection.provider === "codex" ? "Codex" : "Claude"} · {connection.device_name} · {connection.account_email}</option>)}</select></Field>
      {allowed ? <>
        <p>BAT 실행 터미널에서 <kbd>X</kbd>로 Codex, <kbd>C</kbd>로 Claude에 로그인한 뒤 아래에서 확인해 주세요. 확인하면 저장하지 않은 설정은 마지막 저장 상태로 돌아갑니다.</p>
        {(["codex", "claude"] as const).map(family => !installed(family) && <p className="notice" key={`${family}-install`}><strong>{family === "codex" ? "Codex" : "Claude"} CLI 설치가 필요합니다.</strong> {family === "codex" ? <><code>npm install -g @openai/codex</code>로 설치한 뒤 BAT에서 <kbd>X</kbd> 로그인을 완료해 주세요.</> : <><code>npm install -g @anthropic-ai/claude-code</code>로 설치한 뒤 <kbd>C</kbd> 로그인을 완료해 주세요.</>}</p>)}
        <div className="actions">{(["codex", "claude"] as const).map(family => <button className="button" key={family} disabled={busy || !installed(family)} onClick={() => check(family)}>{family === "codex" ? "Codex" : "Claude"} 연결 확인</button>)}</div>
      </> : <p className="notice">배포 웹에서는 위 연결 코드로 시작한 PC 커넥터가 CLI를 실행합니다. CLI 로그인은 항상 해당 PC의 공식 CLI에서만 진행됩니다.</p>}
      {connections.length === 0 ? <p className="muted">저장된 CLI 연결 기록이 없습니다.</p> : connections.map(x => <article className="panel" key={x.device_id + x.provider} style={{ overflowWrap: "anywhere", minWidth: 0 }}>
        <h3>{x.provider === "codex" ? "Codex" : "Claude"} · {x.device_name}{x.current_pc ? " · 이 PC" : ""}</h3>
        <p>{statusText[x.status] || "확인 필요"}<br />계정: {x.account_email || "확인되지 않음"}<br />경로: {x.executable_path || "설치되지 않음"}<br />기본 모델: {x.default_model || "확인되지 않음"}<br />확인 시각: {new Date(x.checked_at).toLocaleString("ko-KR")}</p>
      </article>)}
      <Field label="PC CLI 모델"><select value={form.cli_model || ""} disabled={busy || !current} onChange={e => setForm({ ...form, cli_model: e.target.value })}><option value="">CLI 기본 모델{current?.default_model ? ` · ${current.default_model}` : ""}</option>{current?.models.map(model => <option key={model} value={model}>{model}</option>)}</select></Field>
      {form.transport !== "api" && !connected && <p className="notice" role="status">PC 커넥터 연결과 CLI 로그인 확인이 완료되어야 CLI 또는 혼합 연결을 저장할 수 있습니다.</p>}
    </div>
    <button className="button primary" disabled={busy || !providers || (form.transport !== "api" && !connected)} onClick={save}>{busy ? "처리 중…" : "연결 설정 저장"}</button>
    <ErrorMessage error={error} />{saved && <p className="notice" role="status">설정을 저장했어요.</p>}<p className="muted">{providers?.consent_text}</p>
  </section>;
}

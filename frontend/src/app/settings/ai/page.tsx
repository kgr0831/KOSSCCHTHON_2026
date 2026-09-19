"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu, Sparkles, Terminal } from "lucide-react";
import { api, jsonBody } from "@/lib/api";
import { AuthGate, ErrorMessage, Field, Loading, PageHeading } from "@/components/ui";

type Settings = { transport: string; easy_model: string; hard_model: string; revision: number };
type Providers = { api: { configured: boolean; models: string[]; error?: string }; cli: { allowed?: boolean; claude_installed: boolean; gemini_installed: boolean }; consent_text: string };
export default function AISettingsPage() { return <AuthGate><SettingsPage /></AuthGate>; }
function SettingsPage() {
  const settings = useQuery({ queryKey: ["ai-settings"], queryFn: () => api<Settings>("/me/ai-settings") });
  const providers = useQuery({ queryKey: ["ai-providers"], queryFn: () => api<Providers>("/ai/providers"), retry: false });
  return <><PageHeading eyebrow="CONNECTED INTELLIGENCE" title="AI 연결 설정" description="가벼운 초안은 현재 Claude Haiku, 깊이 있는 문서와 커리어 설계는 Claude Sonnet이 맡아요." /><div className="ai-routing"><article className="panel"><Sparkles /><h2>Claude Haiku · Gemini Flash</h2><p>자기소개 · 경험 정리 · 모집 문구<br />검색 조건 · 커피챗 질문 · 자료 분석</p></article><article className="panel"><Cpu /><h2>Claude</h2><p>포트폴리오 · 자기 PR · CV · 자기소개서<br />HTML/CSS/JS 생성 · 커리어 계획</p></article></div>{settings.isPending ? <Loading /> : settings.data && <SettingsForm initial={settings.data} providers={providers.data} />}<ErrorMessage error={settings.error || providers.error} /></>;
}
function SettingsForm({ initial, providers }: { initial: Settings; providers?: Providers }) {
  const [form, setForm] = useState(initial), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(), [saved, setSaved] = useState(false);
  const client = useQueryClient();
  async function save() { setBusy(true); setSaved(false); setError(null); try { const result = await api<Settings>("/me/ai-settings", { method: "PUT", body: jsonBody(form) }); setForm(result); await client.invalidateQueries({ queryKey: ["ai-settings"] }); setSaved(true); } catch (e) { setError(e); } finally { setBusy(false); } }
  return <section className="panel stack"><Field label="연결 방식"><select value={form.transport} onChange={e => { setSaved(false); setForm({ ...form, transport: e.target.value }); }}><option value="api">국민대 AI API · .env 키 사용</option><option disabled={providers?.cli.allowed === false} value="cli">공식 CLI · 각 제공자의 구독 로그인</option><option disabled={providers?.cli.allowed === false} value="hybrid">쉬운 기능은 API · 복잡한 기능은 Claude CLI</option></select></Field>{form.transport !== "cli" && <><p className="notice">{providers?.api.configured ? ".env의 API 키가 설정돼 있어요. 키는 화면에 표시하거나 브라우저로 전송하지 않습니다." : "루트 .env에 DUDRI_AI_API_KEY를 입력한 뒤 터미널을 다시 실행해 주세요."}</p>{providers?.api.error && <p className="notice error">{providers.api.error}</p>}{(["easy_model", "hard_model"] as const).filter(name => form.transport !== "hybrid" || name === "easy_model").map(name => <Field key={name} label={name === "easy_model" ? "가벼운 작업 모델" : "복잡한 작업 모델"}><select value={form[name]} onChange={e => setForm({ ...form, [name]: e.target.value })}><option value="">사용 가능한 모델 자동 선택</option>{providers?.api.models.filter(x => name === "easy_model" ? (/gemini/i.test(x) && /flash/i.test(x)) || /haiku/i.test(x) : /claude/i.test(x)).map(x => <option key={x} value={x}>{x}</option>)}</select></Field>)}</>}{form.transport !== "api" && <div className="cli-guide"><Terminal size={22} /><h2>실행 중인 터미널에서 연결해 주세요</h2><p>Claude: {providers?.cli.claude_installed ? "설치 확인됨" : "공식 Claude Code CLI 설치 필요"}<br />Gemini: {providers?.cli.gemini_installed ? "설치 확인됨" : "공식 Gemini CLI 설치 필요"}</p><ol><li>두드리를 켜 둔 터미널을 선택합니다.</li><li><kbd>C</kbd>를 눌러 Claude에 로그인합니다.</li>{form.transport === "cli" && <li><kbd>G</kbd>를 눌러 Gemini에 Google 계정으로 로그인합니다. 로그인 후 <code>/quit</code>으로 두드리로 돌아옵니다.</li>}<li>이 화면에서 연결 방식을 저장하고 생성을 실행합니다.</li></ol><p className="muted">Gemini는 두드리 전용 로그인 공간을 사용해 처음 한 번 다시 로그인해야 해요. 앱은 다른 프로그램의 인증 파일을 읽거나 복사하지 않습니다. 구독의 모델 접근 권한과 사용량 제한이 적용됩니다.</p></div>}<button className="button primary" disabled={busy} onClick={save}>{busy ? "저장 중…" : "연결 설정 저장"}</button><ErrorMessage error={error} />{saved && <p className="notice" role="status">설정을 저장했어요.</p>}<p className="muted">{providers?.consent_text}</p></section>;
}

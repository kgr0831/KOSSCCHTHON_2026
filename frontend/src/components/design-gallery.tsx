"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, Eye, FilePlus2, LoaderCircle, X } from "lucide-react";
import { api, jsonBody } from "@/lib/api";
import type { Style } from "@/lib/studio";
import { ErrorMessage, Field } from "./ui";
import { useFeedback } from "./feedback";
import StyleBuilder from "./style-builder";

export default function DesignGallery({ styles, selected, onSelect }: { styles: Style[]; selected: string; onSelect: (id: string) => void }) {
  const client = useQueryClient(), feedback = useFeedback();
  const [referenceId, setReferenceId] = useState(""), [markdown, setMarkdown] = useState("");
  const [detailError, setDetailError] = useState<unknown>();
  const detailRequest = useRef(0);
  const reference = styles.find(style => style.id === referenceId);
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(), [file, setFile] = useState<File | null>(null), [consent, setConsent] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null), fileInput = useRef<HTMLInputElement>(null);
  async function upload(event: React.FormEvent) {
    event.preventDefault(); if (!file || !consent) return;
    setBusy(true); setError(null);
    try {
      const data = new FormData(); data.append("file", file); data.append("consent", "true");
      const style = await api<Style>("/portfolio-styles/upload", { method: "POST", body: data });
      await client.invalidateQueries({ queryKey: ["portfolio-styles"] }); onSelect(style.id); setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    } catch (error) { setError(error); } finally { setBusy(false); }
  }
  async function createReference(style: Style) {
    if (!await feedback({ title: "디자인 예시 만들기", message: "디자인 MD를 선택한 AI 제공자에게 보내 PC·모바일 예시 이미지를 만듭니다. 가상 인물을 사용하며 내 프로필은 전송하지 않아요.", confirmLabel: "동의하고 만들기", cancelLabel: "취소" })) return;
    setBusy(true); setError(null);
    try { await api(`/portfolio-styles/${style.id}/preview`, { method: "POST", body: jsonBody({ consent: true }) }); await client.invalidateQueries({ queryKey: ["portfolio-styles"] }); } catch (error) { setError(error); } finally { setBusy(false); }
  }
  async function openReference(style: Style) {
    const request = ++detailRequest.current;
    setReferenceId(style.id); setMarkdown(""); setDetailError(null); if (!dialog.current?.open) dialog.current?.showModal();
    try { const detail = await api<Style & { markdown: string }>(`/portfolio-styles/${style.id}`); if (request === detailRequest.current) setMarkdown(detail.markdown || ""); } catch (error) { if (request === detailRequest.current) setDetailError(error); }
  }
  return <><StyleBuilder styles={styles} onSelect={onSelect} /><div className="style-gallery">{styles.filter(style => style.id !== "editorial").map(style => <article className={`style-card ${selected === style.id ? "selected" : ""}`} key={style.id}>
    <button className="style-select" aria-pressed={selected === style.id} onClick={() => onSelect(style.id)}>{style.reference_image ? <img src={style.reference_image} alt={`${style.name} 스타일의 포트폴리오 예시`} /> : <div className="style-placeholder">{style.status === "queued" || style.status === "running" ? <><LoaderCircle className="spin" size={22} />예시 이미지 생성 중</> : "디자인 MD 저장됨"}</div>}<span><strong>{style.name}</strong>{selected === style.id && <Check size={18} />}</span><small>{style.description}</small></button>
    <button className="text-link" onClick={() => openReference(style)}>{style.reference_image ? "PC · 모바일 예시 크게 보기" : "디자인 문서 보기"}<Eye size={14} /></button>
    {(style.status === "failed" || style.status === "missing") && <button className="text-link" disabled={busy} onClick={() => createReference(style)}>예시 이미지 {style.status === "failed" ? "다시 만들기" : "만들기"}</button>}
    {style.error && <p className="notice error">{style.error}</p>}
  </article>)}</div><form className="style-upload stack tight" onSubmit={upload}><div className="section-title"><h3><FilePlus2 size={17} /> 내 디자인 MD 추가</h3><span className="badge gray">개인 라이브러리</span></div><p className="muted">색상·서체·배치가 적힌 MD를 올리면 저장 후 예시 이미지를 만들어요. Design 폴더에 추가한 스타일도 목록에서 확인할 수 있어요.</p><Field label="디자인 MD 파일" hint="UTF-8 · 최대 64KB. 제목은 display_name, 설명은 gui_summary로 지정할 수 있어요."><input aria-label="디자인 MD 파일" ref={fileInput} disabled={busy} type="file" accept=".md,text/markdown" required onChange={event => setFile(event.target.files?.[0] || null)} /></Field><label className="check-row"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} />디자인 MD를 AI에 전송해 가상 인물의 예시 이미지를 만드는 데 동의합니다.</label><button className="button subtle" disabled={busy || !file || !consent}>{busy ? "디자인 저장 중…" : "디자인 저장 · 예시 만들기"}</button><ErrorMessage error={error} /></form>
    <dialog ref={dialog} className="reference-dialog" aria-labelledby="reference-title" onClose={() => { detailRequest.current++; }} onClick={event => { if (event.target === event.currentTarget) dialog.current?.close(); }}><div className="section-title"><h2 id="reference-title">{reference?.name} 디자인 예시</h2><button className="icon-button" autoFocus aria-label="예시 닫기" onClick={() => dialog.current?.close()}><X /></button></div>{reference?.reference_image ? <div className="reference-pair"><figure><img src={reference.reference_image} alt={`${reference.name} PC 전체 예시`} /><figcaption>PC · 가상 인물의 웹 포트폴리오</figcaption></figure>{reference.mobile_reference_image && <figure><img src={reference.mobile_reference_image} alt={`${reference.name} 모바일 전체 예시`} /><figcaption>모바일</figcaption></figure>}</div> : <p className="notice">{reference?.status === "missing" ? "아직 예시 이미지를 만들지 않았어요. 디자인 카드에서 예시 만들기를 눌러 주세요." : reference?.status === "failed" ? "예시 생성에 실패했어요. 저장된 디자인으로 다시 시도할 수 있어요." : "예시 이미지를 준비하고 있어요. 완료되면 자동으로 표시됩니다."}</p>}<ErrorMessage error={detailError} />{!!detailError && reference && <button className="button subtle" onClick={() => openReference(reference)}>문서 다시 불러오기</button>}{markdown && <details><summary>디자인 MD 원문</summary><pre className="style-markdown">{markdown}</pre></details>}</dialog>
  </>;
}

"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FilePlus2, Trash2 } from "lucide-react";
import { api, type DocumentReference } from "@/lib/api";
import { useFeedback } from "./feedback";
import { ErrorMessage } from "./ui";

export type DocumentKind = "portfolio" | "profile_pr" | "cv" | "cover_letter";

const formatNames: Record<DocumentReference["reference_format"], string> = {
  pdf: "PDF", png: "PNG", jpg: "JPG", txt: "TXT", html: "HTML", docx: "DOCX",
};

function fileSize(value: number) {
  return value < 1024 * 1024 ? `${Math.max(1, Math.ceil(value / 1024))}KB` : `${(value / 1024 / 1024).toFixed(1)}MB`;
}

function isImageFile(file: File) {
  return /\.(png|jpe?g)$/i.test(file.name) || ["image/png", "image/jpeg"].includes(file.type);
}

export default function DocumentReferencePicker({ kind, value, onChange, disabled = false, canUpload = true, selectionEnabled = true, imageInputsEnabled = false, imageInputsChecking = false }: {
  kind: DocumentKind;
  value: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  canUpload?: boolean;
  selectionEnabled?: boolean;
  imageInputsEnabled?: boolean;
  imageInputsChecking?: boolean;
}) {
  const client = useQueryClient();
  const feedback = useFeedback();
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const references = useQuery({
    queryKey: ["document-references", kind],
    queryFn: () => api<{ items: DocumentReference[] }>(`/me/document-references?kind=${encodeURIComponent(kind)}`),
  });
  const items = references.data?.items || [];

  async function upload(file: File) {
    if (!canUpload) return;
    if (isImageFile(file) && !imageInputsEnabled) {
      setError(new Error(imageInputsChecking
        ? "Codex CLI 이미지 입력 연결을 확인하는 중이에요. 잠시 후 다시 선택해 주세요."
        : "PNG/JPG 참고 자료는 이 PC에서 연결한 Codex CLI로 AI 문서를 만들 때만 사용할 수 있어요."));
      if (fileInput.current) fileInput.current.value = "";
      return;
    }
    if (value.length >= 5) {
      setError(new Error("이번 생성에는 참고 파일을 최대 5개까지 선택할 수 있어요."));
      if (fileInput.current) fileInput.current.value = "";
      return;
    }
    setBusy(true); setError(null);
    try {
      const form = new FormData(); form.append("file", file);
      const created = await api<DocumentReference>(`/me/document-references/${kind}`, { method: "POST", body: form });
      onChange([...new Set([...value, created.id])]);
      await client.invalidateQueries({ queryKey: ["document-references", kind] });
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function remove(reference: DocumentReference) {
    if (!await feedback({ title: "참고 파일 삭제", message: "원문은 복구할 수 없어요. 생성이 이미 시작됐다면 삭제할 수 없고, 대기 중인 생성은 중단돼요.", confirmLabel: "삭제", cancelLabel: "취소" })) return;
    setBusy(true); setError(null);
    try {
      await api(`/me/document-references/${reference.id}`, { method: "DELETE" });
      onChange(value.filter(id => id !== reference.id));
      await client.invalidateQueries({ queryKey: ["document-references", kind] });
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }

  return <section className="document-reference-picker stack tight" aria-labelledby="document-reference-title">
    <div className="section-title"><h3 id="document-reference-title"><FilePlus2 size={17} /> 생성 메모리 · 참고 파일</h3><span className="badge gray">선택</span></div>
    <p className="muted">이 {kind === "portfolio" ? "포트폴리오" : kind === "profile_pr" ? "자기 PR 프로필" : kind === "cv" ? "CV" : "자기소개서"} 생성에만 참고할 개인 자료예요. 텍스트는 생성 입력으로, PNG/JPG는 Codex CLI 이미지 입력으로만 전달되며 다른 사용자에게 공개되지 않아요.</p>
    {canUpload ? <><label className="document-reference-upload">
      <span>{imageInputsEnabled ? "PDF · PNG · JPG · TXT · DOCX · HTML" : "PDF · TXT · DOCX · HTML"} (파일당 10MB, 최대 5개 선택)</span>
      <input ref={fileInput} aria-label="문서 참고 파일" type="file" disabled={disabled || busy || imageInputsChecking} accept={imageInputsEnabled ? ".pdf,.png,.jpg,.jpeg,.txt,.docx,.html,.htm,application/pdf,image/png,image/jpeg,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/html" : ".pdf,.txt,.docx,.html,.htm,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/html"} onChange={event => {
        const file = event.target.files?.[0];
        if (file) void upload(file);
      }} />
    </label>
    {!imageInputsEnabled && <p className="muted">{imageInputsChecking ? "Codex CLI 이미지 입력 연결을 확인하고 있어요." : "PNG/JPG를 참고하려면 AI 연결 설정에서 이 PC의 Codex CLI를 연결한 뒤 CLI 또는 혼합 연결을 선택해 주세요."}</p>}</> : <p className="muted">저장한 참고 파일은 삭제할 수 있어요. 새 파일 추가와 AI 생성에 사용하려면 Premium 요금제가 필요해요.</p>}
    {busy && <p className="muted" role="status">참고 파일을 준비하는 중이에요.</p>}
    {references.isPending ? <p className="muted">저장한 참고 자료를 불러오는 중이에요.</p> : items.length > 0 && <div className="stack tight" role="group" aria-label="생성에 사용할 참고 파일">
      {items.map(reference => <div className="material-row document-reference-row" key={reference.id}>
        {selectionEnabled ? <label className="check-row"><input aria-label={`${reference.display_name} 참고에 사용`} type="checkbox" disabled={disabled || busy || (!value.includes(reference.id) && value.length >= 5)} checked={value.includes(reference.id)} onChange={event => onChange(event.target.checked ? [...value, reference.id] : value.filter(id => id !== reference.id))} />
          <span><strong>{reference.display_name}</strong><small>{formatNames[reference.reference_format]} · {fileSize(reference.byte_size)}</small></span>
        </label> : <span className="document-reference-summary"><strong>{reference.display_name}</strong><small>{formatNames[reference.reference_format]} · {fileSize(reference.byte_size)}</small></span>}
        <button className="icon-button" type="button" aria-label={`${reference.display_name} 참고 파일 삭제`} disabled={disabled || busy} onClick={() => void remove(reference)}><Trash2 size={15} /></button>
      </div>)}
    </div>}
    {!references.isPending && !items.length && <p className="muted">참고할 파일을 선택하면 여기에서 이번 생성에 사용할 자료를 고를 수 있어요.</p>}
    <ErrorMessage error={error || references.error} />
  </section>;
}

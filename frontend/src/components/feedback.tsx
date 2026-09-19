"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { CircleAlert, X } from "lucide-react";

type Notice = { title: string; message: string; confirmLabel?: string; cancelLabel?: string };
const Context = createContext<(notice: Notice) => Promise<boolean>>(async () => false);
export const useFeedback = () => useContext(Context);
export function FeedbackProvider({ children }: { children: React.ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null), resolve = useRef<((value: boolean) => void) | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const finish = useCallback((value: boolean) => { resolve.current?.(value); resolve.current = null; dialog.current?.close(); setNotice(null); }, []);
  const show = useCallback((next: Notice) => { if (resolve.current) return Promise.resolve(false); setNotice(next); return new Promise<boolean>(done => { resolve.current = done; }); }, []);
  useEffect(() => { if (notice && !dialog.current?.open) dialog.current?.showModal(); }, [notice]);
  return <Context.Provider value={show}><div className="feedback-scope" onInvalidCapture={event => {
    event.preventDefault();
    const input = event.target as HTMLInputElement;
    const label = input.closest("label")?.querySelector("span")?.textContent || input.getAttribute("aria-label") || "입력 항목";
    const issue = input.validity.valueMissing ? "필수 항목을 입력해 주세요." : input.validity.typeMismatch ? "올바른 형식으로 입력해 주세요." : input.validity.rangeUnderflow || input.validity.rangeOverflow ? "허용 범위 안의 값을 입력해 주세요." : "입력 형식을 확인해 주세요.";
    if (!resolve.current) void show({ title: "입력 내용을 확인해 주세요", message: `${label}: ${issue}` }).then(() => { if (input.isConnected) input.focus(); });
  }}>{children}</div><dialog ref={dialog} className="feedback-dialog" aria-labelledby="feedback-title" aria-describedby="feedback-message" onCancel={event => { event.preventDefault(); finish(false); }} onClick={event => { if (event.target === event.currentTarget) finish(false); }}>
    <div className="feedback-symbol"><CircleAlert size={26} /></div><button className="icon-button feedback-close" aria-label="안내 닫기" onClick={() => finish(false)}><X size={19} /></button><h2 id="feedback-title">{notice?.title}</h2><p id="feedback-message">{notice?.message}</p><div className="card-actions">{notice?.cancelLabel && <button className="button subtle" onClick={() => finish(false)}>{notice.cancelLabel}</button>}<button className="button primary" autoFocus onClick={() => finish(true)}>{notice?.confirmLabel || "확인"}</button></div>
  </dialog></Context.Provider>;
}

"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sparkles, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Style } from "@/lib/studio";
import { ErrorMessage, Field } from "./ui";

export default function StyleBuilder({ styles, onSelect }: { styles: Style[]; onSelect: (id: string) => void }) {
  const dialog = useRef<HTMLDialogElement>(null), client = useQueryClient();
  const [name, setName] = useState(""), [base, setBase] = useState("");
  const [mood, setMood] = useState("차분하고 전문적인"), [layout, setLayout] = useState("큰 소개와 프로젝트 카드 그리드");
  const [font, setFont] = useState("깔끔한 고딕"), [space, setSpace] = useState("여유로운 여백");
  const [background, setBackground] = useState("#faf8ff"), [accent, setAccent] = useState("#7553b6");
  const [request, setRequest] = useState(""), [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || !consent || busy) return;
    setBusy(true); setError(null);
    try {
      const reference = base ? await api<Style & { markdown: string }>(`/portfolio-styles/${base}`) : null;
      const title = name.replace(/[\r\n"]/g, " ").trim();
      const markdown = `display_name: ${title}\ngui_summary: ${mood} · ${font} · ${space}\n\n# 사용자 선택 디자인\n` +
        `- 분위기: ${mood}\n- 레이아웃: ${layout}\n- 서체: ${font}\n- 밀도: ${space}\n- 배경색: ${background}\n- 강조색: ${accent}\n` +
        `- PC와 모바일에 같은 디자인 언어를 적용하고 화면 크기에 맞게 재배치합니다.\n- 글자와 배경의 대비를 충분히 확보합니다.\n\n## 추가 요청\n${request.trim() || "선택한 설정에 어울리게 구성해 주세요."}\n` +
        (reference ? `\n## 참고 디자인\n아래 원문의 설정과 다르면 위 사용자 선택을 우선합니다.\n${reference.markdown}\n` : "");
      const data = new FormData();
      data.append("file", new File([markdown], "custom-design.md", { type: "text/markdown" }));
      data.append("consent", "true");
      const created = await api<Style>("/portfolio-styles/upload", { method: "POST", body: data });
      await client.invalidateQueries({ queryKey: ["portfolio-styles"] });
      onSelect(created.id); dialog.current?.close(); setName(""); setRequest(""); setConsent(false);
    } catch (error) { setError(error); } finally { setBusy(false); }
  }

  return <><button type="button" className="style-builder-launch" onClick={() => { setError(null); dialog.current?.showModal(); }}><Sparkles size={24} /><span><strong>원하는 스타일 만들기</strong><small>색상·서체·배치를 고르고 원하는 느낌을 알려 주세요.</small></span><span aria-hidden="true">＋</span></button>
    <dialog ref={dialog} className="style-builder-dialog" aria-labelledby="style-builder-title" onCancel={event => { if (busy) event.preventDefault(); }} onClick={event => { if (!busy && event.target === event.currentTarget) dialog.current?.close(); }}>
      <div className="section-title"><div><h2 id="style-builder-title">나만의 디자인 스타일</h2><p className="muted">선택한 내용을 저장하고 AI가 PC·모바일 예시를 만들어요.</p></div><button type="button" className="icon-button" aria-label="스타일 만들기 닫기" disabled={busy} onClick={() => dialog.current?.close()}><X /></button></div>
      <form className="stack" onSubmit={submit}><fieldset disabled={busy} className="style-builder-fields">
        <Field label="스타일 이름"><input autoFocus required maxLength={80} value={name} onChange={event => setName(event.target.value)} placeholder="예: 나의 첫 프로젝트 갤러리" /></Field>
        <Field label="참고할 디자인"><select value={base} onChange={event => setBase(event.target.value)}><option value="">새롭게 시작하기</option>{styles.filter(style => style.id !== "editorial").map(style => <option value={style.id} key={style.id}>{style.name}</option>)}</select></Field>
        <div className="style-builder-grid"><Field label="분위기"><select aria-label="분위기" value={mood} onChange={event => setMood(event.target.value)}>{["차분하고 전문적인", "밝고 친근한", "대담하고 창의적인", "따뜻하고 자연스러운", "미니멀하고 절제된"].map(value => <option key={value}>{value}</option>)}</select></Field>
          <Field label="화면 배치"><select aria-label="화면 배치" value={layout} onChange={event => setLayout(event.target.value)}>{["큰 소개와 프로젝트 카드 그리드", "이미지 중심 갤러리와 작업 상세", "잡지처럼 큰 제목과 비대칭 영역", "간결한 소개와 세로 작업 목록"].map(value => <option key={value}>{value}</option>)}</select></Field>
          <Field label="서체 느낌"><select aria-label="서체 느낌" value={font} onChange={event => setFont(event.target.value)}>{["깔끔한 고딕", "고전적인 명조 제목과 고딕 본문", "굵고 개성 있는 고딕", "코드 느낌의 고정폭 강조"].map(value => <option key={value}>{value}</option>)}</select></Field>
          <Field label="여백"><select aria-label="여백" value={space} onChange={event => setSpace(event.target.value)}>{["여유로운 여백", "균형 잡힌 여백", "내용을 많이 보여주는 밀도"].map(value => <option key={value}>{value}</option>)}</select></Field>
          <Field label="배경색"><input type="color" value={background} onChange={event => setBackground(event.target.value)} /></Field><Field label="강조색"><input type="color" value={accent} onChange={event => setAccent(event.target.value)} /></Field></div>
        <div className="style-draft-preview" style={{ background, borderColor: accent }} aria-label="선택한 색상 미리보기"><span style={{ background: accent }} /><strong>{name || "나의 이야기, 나의 디자인"}</strong><small>{mood} · {font}</small></div>
        <Field label="추가로 원하는 점" hint="예: 둥근 카드와 넓은 여백, 대표 작업 3개를 강조해 주세요."><textarea rows={3} maxLength={4000} value={request} onChange={event => setRequest(event.target.value)} /></Field>
        <label className="check-row"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} />선택과 요청을 AI에 전송해 가상 인물의 예시 이미지를 만드는 데 동의합니다.</label>
      </fieldset><ErrorMessage error={error} /><div className="card-actions"><button type="button" className="button subtle" disabled={busy} onClick={() => dialog.current?.close()}>취소</button><button className="button primary" disabled={busy || !name.trim() || !consent}>{busy ? "스타일 저장 중…" : "스타일 저장 · 예시 만들기"}</button></div></form>
    </dialog></>;
}

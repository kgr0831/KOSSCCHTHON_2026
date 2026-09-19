"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Page } from "@/lib/api";
import { useCommand } from "@/lib/hooks";
import { ErrorMessage, Field, Submit } from "./ui";

export function SchoolVerification() {
  const [school, setSchool] = useState("");
  const universities = useQuery({ queryKey: ["universities"], queryFn: () => api<Page<{ id: string; name: string }>>("/universities") });
  const domains = useQuery({ queryKey: ["domains", school], queryFn: () => api<Page<{ domain: string }>>(`/universities/${school}/domains`), enabled: !!school });
  const command = useCommand();
  return <form className="stack" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); command.mutate({ path: "/me/school-email-verifications", body: { university_id: school, email: form.get("email"), department: form.get("department"), enrollment_status: form.get("status") } }); }}>
    <h3>학교 이메일 확인</h3><p className="muted">지금 로그인한 계정에 학교 인증을 추가합니다. Google 로그인 이메일은 바뀌지 않아요.</p>
    <Field label="인증할 학교"><select value={school} onChange={event => { setSchool(event.target.value); command.reset(); }} required><option value="">학교를 선택해 주세요</option>{universities.data?.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
    <Field label="학교 이메일" hint={domains.data ? `허용 도메인: ${domains.data.items.map(item => item.domain).join(", ")}` : "학교를 선택해 주세요."}><input type="email" name="email" required autoComplete="email" /></Field>
    <Field label="학과"><input name="department" maxLength={150} /></Field>
    <Field label="학적 상태 (본인 입력)"><select name="status"><option value="student">재학 중</option><option value="graduate">졸업</option><option value="leave">휴학 중</option><option value="other">기타</option></select></Field>
    <ErrorMessage error={command.error || universities.error || domains.error} />
    {command.isSuccess && <p className="notice" role="status">이메일을 보냈어요. 현재 계정으로 로그인한 상태에서 15분 안에 링크를 열어 주세요.</p>}
    <Submit pending={command.isPending}>학교 인증 링크 받기</Submit>
  </form>;
}

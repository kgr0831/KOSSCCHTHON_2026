"use client";

import { ArrowRight, Sprout } from "lucide-react";
import Link from "next/link";
import { GoogleSignIn } from "@/components/google-sign-in";
import { useAuth } from "@/components/providers";
import { ErrorMessage, Field, PageHeading, Submit } from "@/components/ui";
import { useCommand } from "@/lib/hooks";

export default function AuthPage() {
  const { user } = useAuth();
  const command = useCommand();
  if (user) return <><PageHeading title="다시 만나 반가워요" description={`${user.profile.display_name}님으로 로그인되어 있어요.`} /><Link href="/profile" className="button primary">내 프로필 완성하기 <ArrowRight size={17} /></Link></>;
  return <div className="auth-container">
    <PageHeading eyebrow="YOUR NEXT CHAPTER" title="연결의 시작은, 나의 학교에서" description="Google로 시작하고, 프로필에서 학교 이메일을 별도로 확인해 주세요." />
    <div className="grid-2"><div className="auth-story"><Sprout size={49} /><h2>작은 연결 하나가<br />다음 가능성을<br />열어줄 거예요.</h2><p>국민대학교 · 숭실대학교 · 순천향대학교<br />함께 시작하는 동문 커뮤니티, 두드리.</p></div>
      <section className="panel stack"><h2>나의 계정으로 시작하기</h2><GoogleSignIn /><p className="muted">학교 인증은 이메일 접근 여부만 확인해요. 재학·졸업 상태는 직접 입력한 정보로 표시됩니다.</p><a href="/privacy.html" target="_blank" rel="noreferrer">개인정보처리방침</a>
        <details><summary>기존 이메일 계정 연결</summary><form className="stack" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); command.mutate({ path: "/auth/login-links", body: { email: form.get("email") } }); }}>
          <p className="muted">이전에 이메일로 만든 계정이 있다면 먼저 로그인해 주세요. 프로필에서 Google 계정을 연결하면 저장한 자료를 그대로 사용할 수 있어요.</p>
          <Field label="기존 로그인 이메일"><input type="email" name="email" required autoComplete="email" /></Field><ErrorMessage error={command.error} />
          {command.isSuccess && <p className="notice" role="status">등록된 계정이면 이메일의 링크로 로그인할 수 있어요. 이미 Google을 연결했다면 위 버튼을 이용해 주세요.</p>}
          <Submit pending={command.isPending}>기존 계정 로그인 링크 받기</Submit>
        </form></details>
      </section>
    </div>
  </div>;
}

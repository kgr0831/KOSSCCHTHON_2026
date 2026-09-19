"use client";

import { useState } from "react";
import Link from "next/link";
import { Trash2 } from "lucide-react";
import { useParams, useRouter } from "@/components/app-navigation";
import { useQuery } from "@tanstack/react-query";
import { api, statusText, type Page, type Project, type Recruitment } from "@/lib/api";
import { useCommand } from "@/lib/hooks";
import { useAuth } from "@/components/providers";
import { useFeedback } from "@/components/feedback";
import { AuthGate, ErrorMessage, Field, Loading, PageHeading } from "@/components/ui";

export default function ProjectPage() { const { id } = useParams<{ id: string }>(); return <AuthGate><Detail id={id} /></AuthGate>; }

function Detail({ id }: { id: string }) {
  const { user } = useAuth();
  const router = useRouter();
  const command = useCommand();
  const feedback = useFeedback();
  const [message, setMessage] = useState("");
  const [opening, setOpening] = useState("");
  const project = useQuery({ queryKey: ["project", id], queryFn: () => api<Project>(`/projects/${id}`) });
  const mine = project.data?.creator_id === user?.id;
  const posts = useQuery({
    queryKey: ["project-posts", id, mine],
    queryFn: () => api<Page<Recruitment>>(`/recruitment-posts?limit=100${mine ? "&mine=true" : ""}`),
    enabled: !!project.data,
  });

  if (project.isPending) return <Loading />;
  if (!project.data) return <ErrorMessage error={project.error} />;

  const p = project.data;
  const list = posts.data?.items.filter(post => post.project_id === id) || [];
  const canApply = !p.viewer_is_member && p.viewer_request_status !== "pending";

  async function remove() {
    const confirmed = await feedback({
      title: "프로젝트를 삭제할까요?",
      message: "프로젝트와 모집 글은 숨겨지고, 아직 처리되지 않은 참여 요청은 취소돼요. 이 작업은 되돌릴 수 없어요.",
      confirmLabel: "프로젝트 삭제",
      cancelLabel: "취소",
    });
    if (!confirmed) return;
    try {
      await command.mutateAsync({ path: `/projects/${id}?revision=${p.revision}`, method: "DELETE" });
      router.replace("/projects");
    } catch {
      // The shared command exposes the request error below.
    }
  }

  return <>
    <PageHeading eyebrow="PROJECT STORY" title={p.title} description={p.summary} action={<Link className="button subtle" href="/projects">프로젝트 목록</Link>} />
    <div className="grid-2">
      <section className="panel stack">
        <div className="tag-list">
          <span className="badge purple">{statusText[p.project_status]}</span>
          <span className="badge gray">{statusText[p.visibility]}</span>
          <span className="badge">팀원 {p.member_count || 1}명</span>
          {p.viewer_is_member && <span className="badge">참여 중</span>}
        </div>
        <h2>함께 이루고 싶은 목표</h2>
        <p>{p.goal || "함께 목표를 구체화하고 있어요."}</p>
        {mine && <>
          <h2>공개 범위</h2>
          <p className="muted">모집 글을 게시하려면 프로젝트를 먼저 공개해 주세요. 비공개로 전환하면 모집 게시도 중지됩니다.</p>
          <div className="card-actions">
            <button className="button subtle" disabled={command.isPending} onClick={() => command.mutate({ path: `/projects/${id}`, method: "PATCH", body: { revision: p.revision, title: p.title, summary: p.summary, goal: p.goal, project_status: p.project_status, visibility: p.visibility === "public" ? "private" : "public" } })}>{p.visibility === "public" ? "비공개로 전환" : "프로젝트 공개"}</button>
            <button className="button danger" disabled={command.isPending} onClick={() => void remove()}><Trash2 size={15} />프로젝트 삭제</button>
          </div>
        </>}
      </section>

      <div className="stack">
        {list.map(post => {
          const hasOpenings = post.role_openings.some(role => role.filled < role.capacity);
          return <section className="panel stack" key={post.id}>
            <div className="section-title"><h2>동료를 찾고 있어요</h2><span className="badge purple">{statusText[post.status]}</span></div>
            <p className="card-description">{post.description}</p>
            <p className="muted">{statusText[post.collaboration_mode]} · {post.duration || "기간 협의"}{post.hours_per_week ? ` · 주 ${post.hours_per_week}시간` : ""}</p>
            {post.role_openings.map(role => <div className="role-summary" key={role.id}><strong>{role.role}</strong><span>{role.filled}/{role.capacity}명</span><small>{role.skills.join(" · ")}</small></div>)}
            {mine ? <div className="card-actions">{hasOpenings ? (post.status !== "published"
              ? <button className="button primary" disabled={command.isPending || p.visibility !== "public"} onClick={() => command.mutate({ path: `/recruitment-posts/${post.id}/publish`, body: { revision: post.revision } })}>이 모집 글 게시</button>
              : <button className="button subtle" disabled={command.isPending} onClick={() => command.mutate({ path: `/recruitment-posts/${post.id}`, method: "PATCH", body: { revision: post.revision, description: post.description, hours_per_week: post.hours_per_week, collaboration_mode: post.collaboration_mode, duration: post.duration, status: "closed" } })}>모집 마감</button>)
              : <span className="muted">모든 역할의 모집이 마감됐어요.</span>}</div>
              : !canApply ? <p className="notice">{p.viewer_is_member ? "이미 이 프로젝트에 참여 중이에요." : "참여 요청을 검토 중이에요."}</p>
              : post.status === "published" && hasOpenings && <form className="stack" onSubmit={event => { event.preventDefault(); command.mutate({ path: `/recruitment-posts/${post.id}/applications`, idempotent: true, body: { opening_id: opening, message } }); }}>
                <Field label="참여하고 싶은 역할"><select required value={opening} onChange={event => setOpening(event.target.value)}><option value="">역할 선택</option>{post.role_openings.filter(role => role.filled < role.capacity).map(role => <option key={role.id} value={role.id}>{role.role}</option>)}</select></Field>
                <Field label="팀에게 전할 이야기"><textarea required rows={4} value={message} maxLength={5000} onChange={event => setMessage(event.target.value)} /></Field>
                <button className="button primary" disabled={command.isPending}>참여 신청</button>
              </form>}
          </section>;
        })}
        {!list.length && <section className="panel"><p className="muted">{p.viewer_is_member ? "이미 참여 중인 프로젝트예요." : "현재 표시할 모집 글이 없습니다."}</p></section>}
      </div>
    </div>
    <ErrorMessage error={posts.error || command.error} />
    {command.isSuccess && <p className="notice" role="status">변경 사항을 저장했어요.</p>}
  </>;
}

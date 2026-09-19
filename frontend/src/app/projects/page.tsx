"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Plus, Trash2, Users } from "lucide-react";
import { api, statusText, type Page, type Project, type Recruitment } from "@/lib/api";
import { useCommand } from "@/lib/hooks";
import { useAuth } from "@/components/providers";
import { useFeedback } from "@/components/feedback";
import { AuthGate, ErrorMessage, Loading, PageHeading } from "@/components/ui";

type Request = {
  id: string;
  project_id: string;
  project_is_active?: boolean;
  recipient_id: string;
  message: string;
  status: string;
  revision: number;
};

export default function ProjectsPage() { return <AuthGate><Projects /></AuthGate>; }

function Projects() {
  const { user } = useAuth();
  const command = useCommand();
  const feedback = useFeedback();
  const projects = useQuery({ queryKey: ["projects", "mine"], queryFn: () => api<Page<Project>>("/projects?mine=true&limit=100") });
  const posts = useQuery({ queryKey: ["recruitment-posts"], queryFn: () => api<Page<Recruitment>>("/recruitment-posts?limit=100") });
  const requests = useQuery({ queryKey: ["project-requests"], queryFn: () => api<Page<Request>>("/me/project-requests?limit=100") });

  async function remove(project: Project) {
    const confirmed = await feedback({
      title: "프로젝트를 삭제할까요?",
      message: "프로젝트와 모집 글은 숨겨지고, 아직 처리되지 않은 참여 요청은 취소돼요. 이 작업은 되돌릴 수 없어요.",
      confirmLabel: "프로젝트 삭제",
      cancelLabel: "취소",
    });
    if (!confirmed) return;
    try {
      await command.mutateAsync({ path: `/projects/${project.id}?revision=${project.revision}`, method: "DELETE" });
    } catch {
      // The shared command exposes the request error below.
    }
  }

  return <div className="projects-page">
    <PageHeading eyebrow="BUILD SOMETHING TOGETHER" title="함께 만드는 프로젝트" description="작은 아이디어도 팀을 만나면 다음 경험이 돼요." action={<Link className="button primary" href="/projects/new"><Plus size={17} />프로젝트 만들기</Link>} />

    <section className="dashboard-section projects-section">
      <h2>내가 만든 프로젝트</h2>
      {projects.isPending && <Loading />}
      <div className="grid-2">{projects.data?.items.map(project => <article className="panel" key={project.id}>
        <Link className="project-tile" href={`/projects/${project.id}`}>
          <span className="badge purple">{statusText[project.project_status]}</span>
          <h3>{project.title}</h3>
          <p>{project.summary}</p>
          <small>{statusText[project.visibility]} · {project.member_count || 1}명</small>
        </Link>
        <div className="card-actions"><button className="button danger" disabled={command.isPending} onClick={() => void remove(project)}><Trash2 size={15} />프로젝트 삭제</button></div>
      </article>)}</div>
      {projects.isSuccess && !projects.data.items.length && <p className="muted">첫 프로젝트를 등록하고 모집 초안을 만들어 보세요.</p>}
    </section>

    <section className="dashboard-section projects-section">
      <h2>함께할 동료를 찾고 있어요</h2>
      {posts.isPending && <Loading />}
      <div className="grid-2">{posts.data?.items.map(post => <Link className="panel project-tile" key={post.id} href={`/projects/${post.project_id}`}>
        <span className="badge"><Users size={12} />모집 중</span>
        <h3>{post.project_title}</h3>
        <p>{post.description}</p>
        <div className="tag-list">{post.role_openings.map(role => <span key={role.id} className="badge gray">{role.role} {role.filled}/{role.capacity}</span>)}</div>
      </Link>)}</div>
    </section>

    <section className="dashboard-section projects-section" id="requests">
      <h2>내 지원 · 받은 참여 요청</h2>
      {requests.isPending && <Loading />}
      <div className="stack">{requests.data?.items.map(request => {
        const activeProject = request.project_is_active !== false;
        return <article className="panel" key={request.id}>
          <div className="section-title">
            {activeProject ? <Link href={`/projects/${request.project_id}`} className="text-link">프로젝트 보기 ↗</Link> : <span className="muted">삭제된 프로젝트</span>}
            <span className="badge purple">{statusText[request.status]}</span>
          </div>
          <p className="card-description">{request.message}</p>
          {activeProject && request.recipient_id === user?.id && request.status === "pending" && <div className="card-actions">
            <button className="button primary" disabled={command.isPending} onClick={() => command.mutate({ path: `/project-requests/${request.id}/decision`, body: { decision: "accepted", revision: request.revision } })}>참여 수락</button>
            <button className="button subtle" disabled={command.isPending} onClick={() => command.mutate({ path: `/project-requests/${request.id}/decision`, body: { decision: "rejected", revision: request.revision } })}>거절</button>
          </div>}
        </article>;
      })}</div>
      {requests.isSuccess && !requests.data.items.length && <p className="muted">참여 요청을 보내거나 받으면 여기에 표시돼요.</p>}
    </section>

    <ErrorMessage error={projects.error || posts.error || requests.error || command.error} />
  </div>;
}

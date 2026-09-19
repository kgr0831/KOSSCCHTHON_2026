"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Plus, Users } from "lucide-react";
import { api, statusText, type Page, type Project, type Recruitment } from "@/lib/api";
import { useCommand } from "@/lib/hooks";
import { useAuth } from "@/components/providers";
import { AuthGate, ErrorMessage, Loading, PageHeading } from "@/components/ui";

type Request = { id: string; project_id: string; recipient_id: string; message: string; status: string; revision: number };
export default function ProjectsPage() { return <AuthGate><Projects /></AuthGate>; }
function Projects() {
  const { user } = useAuth(), command = useCommand();
  const projects = useQuery({ queryKey: ["projects", "mine"], queryFn: () => api<Page<Project>>("/projects?mine=true&limit=100") });
  const posts = useQuery({ queryKey: ["recruitment-posts"], queryFn: () => api<Page<Recruitment>>("/recruitment-posts?limit=100") });
  const requests = useQuery({ queryKey: ["project-requests"], queryFn: () => api<Page<Request>>("/me/project-requests?limit=100") });
  return <div className="projects-page"><PageHeading eyebrow="BUILD SOMETHING TOGETHER" title="함께 만드는 프로젝트" description="작은 아이디어도 팀을 만나면 다음 경험이 돼요." action={<Link className="button primary" href="/projects/new"><Plus size={17} />프로젝트 만들기</Link>} /><section className="dashboard-section projects-section"><h2>내가 만든 프로젝트</h2>{projects.isPending && <Loading />}<div className="grid-2">{projects.data?.items.map(x => <Link className="panel project-tile" key={x.id} href={`/projects/${x.id}`}><span className="badge purple">{statusText[x.project_status]}</span><h3>{x.title}</h3><p>{x.summary}</p><small>{statusText[x.visibility]} · {x.member_count || 1}명</small></Link>)}</div>{projects.isSuccess && !projects.data.items.length && <p className="muted">첫 프로젝트를 등록하고 모집 초안을 만들어 보세요.</p>}</section><section className="dashboard-section projects-section"><h2>함께할 동료를 찾고 있어요</h2>{posts.isPending && <Loading />}<div className="grid-2">{posts.data?.items.map(x => <Link className="panel project-tile" key={x.id} href={`/projects/${x.project_id}`}><span className="badge"><Users size={12} />모집 중</span><h3>{x.project_title}</h3><p>{x.description}</p><div className="tag-list">{x.role_openings.map(role => <span key={role.id} className="badge gray">{role.role} {role.filled}/{role.capacity}</span>)}</div></Link>)}</div></section><section className="dashboard-section projects-section" id="requests"><h2>내 지원 · 받은 참여 요청</h2>{requests.isPending && <Loading />}<div className="stack">{requests.data?.items.map(x => <article className="panel" key={x.id}><div className="section-title"><Link href={`/projects/${x.project_id}`} className="text-link">프로젝트 보기 ↗</Link><span className="badge purple">{statusText[x.status]}</span></div><p className="card-description">{x.message}</p>{x.recipient_id === user?.id && x.status === "pending" && <div className="card-actions"><button className="button primary" disabled={command.isPending} onClick={() => command.mutate({ path: `/project-requests/${x.id}/decision`, body: { decision: "accepted", revision: x.revision } })}>참여 수락</button><button className="button subtle" disabled={command.isPending} onClick={() => command.mutate({ path: `/project-requests/${x.id}/decision`, body: { decision: "rejected", revision: x.revision } })}>거절</button></div>}</article>)}{requests.isSuccess && !requests.data.items.length && <p className="muted">참여 요청을 보내거나 받으면 여기에 표시돼요.</p>}</div></section><ErrorMessage error={projects.error || posts.error || requests.error || command.error} /></div>;
}

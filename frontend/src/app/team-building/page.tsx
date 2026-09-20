"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Plus, UsersRound } from "lucide-react";
import { useAuth } from "@/components/providers";
import { AuthGate, Badge, Empty, ErrorMessage, Loading, PageHeading } from "@/components/ui";
import { useCommand } from "@/lib/hooks";
import { api, statusText, type Page, type Project, type ProjectRequest, type Recruitment } from "@/lib/api";

export default function TeamBuildingPage() { return <AuthGate><TeamBuilding /></AuthGate>; }

function TeamBuilding() {
  const { user } = useAuth();
  const command = useCommand();
  const posts = useQuery({ queryKey: ["team-building", "posts"], queryFn: () => api<Page<Recruitment>>("/recruitment-posts?limit=100") });
  const projects = useQuery({ queryKey: ["team-building", "projects"], queryFn: () => api<Page<Project>>("/projects?mine=true&limit=100") });
  const requests = useQuery({ queryKey: ["team-building", "requests"], queryFn: () => api<Page<ProjectRequest>>("/me/project-requests?limit=100") });
  const received = requests.data?.items.filter(request => request.recipient_id === user?.id) || [];
  const applications = requests.data?.items.filter(request => request.initiator_id === user?.id && request.request_kind === "application") || [];

  return <div className="projects-page">
    <PageHeading eyebrow="TEAM BUILDING" title="팀빌딩" description="모집 중인 팀을 찾고, 내 팀에 들어온 참여 신청을 바로 처리하세요." action={<Link className="button primary" href="/projects/new"><Plus size={17} />팀원 모집하기</Link>} />

    <section className="dashboard-section projects-section" aria-labelledby="recruitment-heading">
      <div className="section-title"><div><h2 id="recruitment-heading">모집 중인 팀</h2><p className="muted">관심 있는 공고를 열어 역할을 선택하고 참여 신청을 보낼 수 있어요.</p></div></div>
      {posts.isPending && <Loading />}
      {posts.isSuccess && !posts.data.items.length && <Empty title="현재 모집 중인 팀이 없어요" description="새로운 팀이 만들어지면 이곳에서 바로 확인할 수 있어요." action={<Link className="button primary" href="/projects/new">첫 팀 모집하기</Link>} />}
      <div className="grid-2">{posts.data?.items.map(post => <article className="panel project-tile" key={post.id}>
        <span className="badge"><UsersRound size={12} />모집 중</span><h3>{post.project_title}</h3><p>{post.description}</p>
        <div className="tag-list">{post.role_openings.map(role => <span key={role.id} className="badge gray">{role.role} {role.filled}/{role.capacity}</span>)}</div>
        <Link className="text-link" href={`/projects/${post.project_id}`}>공고 보기 · 참여 신청 <ArrowUpRight size={16} /></Link>
      </article>)}</div>
    </section>

    <section className="dashboard-section projects-section" id="requests" aria-labelledby="received-requests-heading">
      <div className="section-title"><div><h2 id="received-requests-heading">받은 팀 참여 신청</h2><p className="muted">수락하면 신청자가 선택한 역할의 팀원으로 바로 추가돼요.</p></div>{received.filter(request => request.status === "pending").length > 0 && <Badge color="purple">처리할 신청 {received.filter(request => request.status === "pending").length}건</Badge>}</div>
      {requests.isPending && <Loading />}
      {requests.isSuccess && !received.length && <Empty title="받은 참여 신청이 없어요" description="모집 글을 게시하면 새 신청이 이곳에 도착해요." />}
      <div className="stack">{received.map(request => <RequestCard key={request.id} request={request} userId={user?.id} pending={command.isPending} onDecision={decision => command.mutate({ path: `/project-requests/${request.id}/decision`, body: { decision, revision: request.revision } })} />)}</div>
    </section>

    <section className="dashboard-section projects-section" id="my-projects" aria-labelledby="my-projects-heading">
      <div className="section-title"><div><h2 id="my-projects-heading">내 프로젝트와 모집 관리</h2><p className="muted">프로젝트 공개, 모집 글 게시와 마감은 프로젝트 상세에서 관리해요.</p></div></div>
      {projects.isPending && <Loading />}
      {projects.isSuccess && !projects.data.items.length && <Empty title="아직 만든 프로젝트가 없어요" description="아이디어와 필요한 역할을 적어 첫 팀을 만들어 보세요." action={<Link className="button primary" href="/projects/new">프로젝트 만들기</Link>} />}
      <div className="grid-2">{projects.data?.items.map(project => <Link className="panel project-tile" key={project.id} href={`/projects/${project.id}`}><span className="badge purple">{statusText[project.project_status]}</span><h3>{project.title}</h3><p>{project.summary || "함께 만들 프로젝트를 소개해 보세요."}</p><small>{statusText[project.visibility]} · 팀원 {project.member_count || 1}명</small></Link>)}</div>
    </section>

    <section className="dashboard-section projects-section" aria-labelledby="my-applications-heading">
      <div className="section-title"><div><h2 id="my-applications-heading">내 참여 신청</h2><p className="muted">보낸 신청의 처리 상태를 확인할 수 있어요.</p></div></div>
      {requests.isPending && <Loading />}
      {requests.isSuccess && !applications.length && <p className="muted">아직 보낸 팀 참여 신청이 없어요.</p>}
      <div className="stack">{applications.map(request => <article className="panel" key={request.id}><div className="section-title"><Link href={`/projects/${request.project_id}`} className="text-link">신청한 프로젝트 보기 <ArrowUpRight size={16} /></Link><Badge color={request.status === "pending" ? "peach" : request.status === "accepted" ? "green" : "gray"}>{statusText[request.status]}</Badge></div><p className="card-description">{request.message}</p></article>)}</div>
    </section>

    <ErrorMessage error={posts.error || projects.error || requests.error || command.error} />
    {command.isSuccess && <p className="notice" role="status">참여 신청을 처리했어요.</p>}
  </div>;
}

function RequestCard({ request, userId, pending, onDecision }: { request: ProjectRequest; userId?: string; pending: boolean; onDecision: (decision: "accepted" | "rejected") => void }) {
  const isApplication = request.request_kind === "application";
  const canDecide = request.recipient_id === userId && request.status === "pending";
  return <article className="panel stack"><div className="section-title"><div><h3>{isApplication ? "새 팀 참여 신청" : "팀 초대 응답"}</h3><Link href={`/projects/${request.project_id}`} className="text-link">프로젝트 보기 <ArrowUpRight size={16} /></Link></div><Badge color={request.status === "pending" ? "peach" : request.status === "accepted" ? "green" : "gray"}>{statusText[request.status]}</Badge></div>{isApplication && <Link className="text-link" href={`/users/${request.candidate_id}`}>신청자 프로필 보기 <ArrowUpRight size={16} /></Link>}<p className="card-description">{request.message}</p>{canDecide && <div className="card-actions"><button className="button primary" disabled={pending} onClick={() => onDecision("accepted")}>참여 수락</button><button className="button subtle" disabled={pending} onClick={() => onDecision("rejected")}>거절</button></div>}</article>;
}

"use client";

import Link from "next/link";
import { kinds } from "@/lib/studio";
import { useParams, useSearchParams } from "@/components/app-navigation";
import { useQuery } from "@tanstack/react-query";
import { Coffee, ShieldCheck } from "lucide-react";
import { Avatar } from "@/components/avatar";
import { api, type UserPublic } from "@/lib/api";
import { AuthGate, Badge, Empty, ErrorMessage, Loading, PageHeading } from "@/components/ui";

type PublishedSite = { kind: string; url: string };

function PublicSiteViewer({ id, user, site }: { id: string; user: UserPublic; site: PublishedSite }) {
  const kind = kinds[site.kind] || "공개 문서";
  return <><PageHeading eyebrow="PUBLIC STORY" title={`${user.display_name}님의 ${kind}`} description="공개된 문서는 별도 보안 영역에서 표시돼요." action={<Link href={`/users/${id}`} className="button subtle">동문 프로필로 돌아가기</Link>} />
    <section className="public-site-viewer" aria-label={`${kind} 보기`}><iframe title={`${kind} 공개 문서`} sandbox="allow-scripts" referrerPolicy="no-referrer" src={site.url} /></section>
  </>;
}

function Content({ id }: { id: string }) {
  const params = useSearchParams();
  const query = useQuery({ queryKey: ["user", id], queryFn: () => api<UserPublic>(`/users/${id}`), staleTime: 0 });
  const graph = useQuery({ queryKey: ["graph", id], queryFn: () => api<{ nodes: { id: string; title: string; date: string | null; kind: string }[] }>(`/users/${id}/career-path-graph`) });
  const sites = useQuery({ queryKey: ["user-sites", id], queryFn: () => api<{ items: PublishedSite[] }>(`/users/${id}/sites`) });
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorMessage error={query.error} />;
  const user = query.data;
  const selectedKind = params.get("site");

  if (selectedKind) {
    if (sites.isPending) return <Loading />;
    if (sites.error) return <ErrorMessage error={sites.error} />;
    const selectedSite = sites.data?.items.find(site => site.kind === selectedKind);
    return selectedSite ? <PublicSiteViewer id={id} user={user} site={selectedSite} /> : <><PageHeading eyebrow="PUBLIC STORY" title="공개 문서를 찾을 수 없어요" action={<Link href={`/users/${id}`} className="button subtle">동문 프로필로 돌아가기</Link>} /><Empty title="현재 볼 수 없는 문서예요" description="게시가 중지되었거나 공개 정보가 바뀌었을 수 있어요." /></>;
  }

  return <><PageHeading eyebrow="A STORY TO SHARE" title={`${user.display_name}님의 이야기`} action={user.can_request_coffee_chat ? <Link className="button primary" href={`/coffee/new?recipient=${id}`}><Coffee size={17} /> 커피챗 요청</Link> : <Badge color="gray">커피챗 요청 불가</Badge>} /><div className="split"><div className="stack"><section className="panel"><div className="person-header"><Avatar src={user.avatar_url} name={user.display_name} /><div><h2 style={{ marginBottom: 4 }}>{user.display_name}</h2><p className="muted">{user.school_affiliations.map(x => `${x.university_name} ${x.department}`).join(" · ")}</p></div></div><p className="card-description" style={{ marginTop: 20 }}>{user.bio || "아직 공개한 자기소개가 없어요."}</p><div className="card-meta">{user.tags.map(x => <Badge key={x.id}>{x.name}</Badge>)}</div></section>{!!sites.data?.items.length && <section className="panel stack"><h2>이력서 · 나를 소개하는 이야기</h2>{sites.data.items.map(site => <div key={site.kind}><Link className="text-link" href={`/users/${id}?site=${encodeURIComponent(site.kind)}`}>{kinds[site.kind] || "공개 문서"} 전체 보기 ↗</Link></div>)}</section>}<ErrorMessage error={sites.error} /><section className="panel"><h2>직접 쌓아온 경험</h2>{user.career_events.length === 0 && <p className="muted">공개한 경력이 아직 없어요.</p>}{user.career_events.map(x => <div className="list-row" key={x.id}><div><h3>{x.title}</h3><small className="muted">{x.organization_name} · {x.started_on || "기간 미입력"}</small><p className="card-description">{x.description}</p></div></div>)}{user.project_members.map(x => <div className="list-row" key={x.id}><div><Badge>프로젝트</Badge><h3>{x.project_title}</h3><p>{x.role}</p><p className="card-description">{x.contribution}</p></div></div>)}</section></div><div className="stack"><section className="panel"><h2>걸어온 길</h2><ErrorMessage error={graph.error} /><div className="timeline">{graph.data?.nodes.map(x => <div key={x.id} className="timeline-event"><small>{x.date || "기간 미입력"}</small><h3>{x.title}</h3></div>)}</div>{graph.data?.nodes.length === 0 && <Empty title="이야기를 채워가는 중이에요" description="공개하고 승인한 경험이 생기면 이곳에 연결됩니다." />}<p className="muted">실제 입력·승인한 경험만 시간순으로 표시합니다.</p></section><section className="panel"><h2>확인된 이메일</h2>{user.verifications.map((x, i) => <div className="inline" key={i}><ShieldCheck size={16} /><span>{x.kind === "school" ? "학교" : "회사"} {x.meaning}</span></div>)}<p className="muted" style={{ marginTop: 12 }}>이메일 접근 확인이며, 학적·직무·실력에 대한 인증은 아닙니다.</p></section></div></div></>;
}

export default function UserPage() {
  const { id } = useParams<{ id: string }>();
  return <AuthGate><Content id={id} /></AuthGate>;
}

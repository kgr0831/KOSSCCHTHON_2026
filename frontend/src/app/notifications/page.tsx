"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, localDate, type Page } from "@/lib/api";
import { useCommand } from "@/lib/hooks";
import { AuthGate, Badge, Empty, ErrorMessage, PageHeading } from "@/components/ui";

function Content() {
  const query = useQuery({ queryKey: ["notifications"], queryFn: () => api<Page<{ id: string; title: string; href: string; created_at: string; read_at: string | null }>>("/me/notifications") });
  const command = useCommand();
  return <><ErrorMessage error={query.error || command.error} />{query.data?.items.length === 0 && <Empty title="새로운 소식이 아직 없어요" description="커피챗과 프로젝트의 새 요청, 일정 변경을 이곳에서 확인할 수 있어요." />}<div className="panel">{query.data?.items.map(x => <div className="list-row" key={x.id}><Link href={x.href}><h3>{x.title}</h3><small className="muted">{localDate(x.created_at)}</small></Link>{x.read_at ? <Badge color="gray">읽음</Badge> : <button className="button subtle" onClick={() => command.mutate({ path: `/me/notifications/${x.id}`, method: "PATCH" })}>읽음으로 표시</button>}</div>)}</div></>;
}
export default function Notifications() { return <><PageHeading eyebrow="WHAT'S NEW" title="새로운 소식" description="놓치고 싶지 않은 연결의 순간들." /><AuthGate><Content /></AuthGate></>; }

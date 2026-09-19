"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { api, type UserPublic } from "@/lib/api";
import { useAuth } from "./providers";
import { ErrorMessage } from "./ui";

export default function Recommendations() {
  const { user } = useAuth();
  const query = useQuery({ queryKey: ["recommendations"], queryFn: () => api<{ items: UserPublic[]; label: string }>("/recommendations"), enabled: !!user });
  if (!user) return null;
  return <section className="dashboard-section"><div className="section-title"><h2>오늘 만나볼 동문</h2><Link className="text-link" href="/explore">더 보기 <ArrowRight size={14} /></Link></div><p className="recommendation-note">임시 추천 · 적합도 순위가 아닌 임의 순서예요</p><div className="recommendation-grid">{query.data?.items.slice(0, 3).map(person => <Link className="panel recommendation-card" href={`/users/${person.id}`} key={person.id}><div className="avatar">{person.display_name.slice(0, 1)}</div><h3>{person.display_name}</h3><small>{person.school_affiliations[0]?.university_name || "학교 비공개"}</small><p>{person.bio || "공개 프로필에서 이야기를 살펴보세요."}</p><span className="text-link">프로필 보기 ↗</span></Link>)}</div><ErrorMessage error={query.error} /></section>;
}

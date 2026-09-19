"use client";

import Link from "next/link";
import { ArrowRight, LoaderCircle } from "lucide-react";
import { useAuth } from "./providers";

export function PageHeading({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: React.ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
}
export function ErrorMessage({ error }: { error: unknown }) { return error ? <p className="notice error" role="alert">{error instanceof Error ? error.message : "잠시 후 다시 시도해 주세요."}</p> : null; }
export function Loading() { return <div className="loading" role="status"><LoaderCircle className="spin" size={22} /> 불러오는 중이에요</div>; }
export function Empty({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) { return <div className="empty"><img className="empty-brand" src="/figma/logo.png" alt="" width="48" height="48" /><h3>{title}</h3><p>{description}</p>{action}</div>; }
export function AuthGate({ children }: { children: React.ReactNode }) { const { ready, user } = useAuth(); if (!ready) return <Loading />; if (!user) return <Empty title="당신의 다음 이야기를 시작해 보세요" description="Google로 로그인하고 학교 이메일을 확인해 동문들과 경험을 나눠요." action={<Link className="button primary" href="/auth">Google로 시작하기 <ArrowRight size={16} /></Link>} />; return <>{children}</>; }
export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) { return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>; }
export function Badge({ children, color = "green" }: { children: React.ReactNode; color?: string }) { return <span className={`badge ${color}`}>{children}</span>; }
export function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) { return <label className="toggle-row"><span>{label}</span><input type="checkbox" role="switch" checked={checked} onChange={e => onChange(e.target.checked)} /></label>; }
export function Submit({ pending, children }: { pending?: boolean; children: React.ReactNode }) { return <button className="button primary" type="submit" disabled={pending}>{pending && <LoaderCircle size={16} className="spin" />}{pending ? "저장 중…" : children}</button>; }

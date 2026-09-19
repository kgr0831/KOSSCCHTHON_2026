export type Style = { id: string; name: string; description: string; reference_image: string | null; mobile_reference_image: string | null; source_file: string; status?: string; error?: string };
export type Section = { id: string; heading: string; body: string; items: string[] };
export type Document = { title: string; headline: string; summary: string; sections: Section[]; accent: string; font: string; spacing: number };
export type Code = { html: string; css: string; javascript: string };
export type Version = { id: string; site_id: string; version_number: number; status: string; style_id: string; instruction: string; error?: string; gui: Document; code: Code; preview_html?: string; site_revision: number; facts_current: boolean; validation: { model?: string; transport?: string }; created_at: string };
export type Site = { id: string; site_kind: string; revision: number; versions: Version[]; published_version_id?: string; public_url?: string };
export const kinds: Record<string, string> = { portfolio: "포트폴리오", profile_pr: "자기 PR 프로필", cv: "CV · 이력서", cover_letter: "자기소개서" };
export const versionStatus: Record<string, string> = { queued: "생성 대기", running: "AI가 작성 중", preview_ready: "저장 완료", failed: "생성 실패", stale: "공개 정보 변경", conflicted: "다른 수정과 충돌", invalid: "코드 수정 필요" };
export const pending = (status: string) => status === "queued" || status === "running";

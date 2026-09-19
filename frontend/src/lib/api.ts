export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;
let authGeneration = 0;

export function setAccessToken(value: string | null) { accessToken = value; authGeneration++; }

export async function refreshSession(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  const generation = authGeneration;
  refreshPromise = (async () => {
    try {
      const response = await fetch("/api/v1/auth/refresh", { method: "POST", credentials: "same-origin", cache: "no-store" });
      if (!response.ok) { if (generation === authGeneration) accessToken = null; return false; }
      const result = await response.json();
      if (generation !== authGeneration) return false;
      accessToken = result.access_token;
      return true;
    } catch { return false; }
    finally { refreshPromise = null; }
  })();
  return refreshPromise;
}

export async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: "same-origin", cache: "no-store" });
  } catch { throw new ApiError(0, "연결이 끊어졌습니다. 입력 내용을 유지하고 있어요. 연결 후 다시 시도해 주세요."); }
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (await refreshSession()) return api<T>(path, options, false);
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "요청을 처리하지 못했습니다." }));
    const message = Array.isArray(error.detail) ? error.detail.map((x: { msg: string }) => x.msg).join(" · ") : error.detail;
    throw new ApiError(response.status, message || "요청을 처리하지 못했습니다.");
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const jsonBody = (data: unknown) => JSON.stringify(data);
export type Page<T> = { items: T[]; next_cursor: string | null };
export type Profile = { user_id: string; display_name: string; bio: string; avatar_url: string | null; name_is_public: boolean; bio_is_public: boolean; avatar_is_public: boolean; revision: number };
export type Affiliation = { id: string; university_id: string; university_name: string; department: string; enrollment_status: string; entry_year: number | null; graduation_year: number | null; is_public: boolean; revision: number };
export type Preference = { coffee_chat_available: boolean; project_available: boolean; learning_stage: string; activity_goal: string; hours_per_week: number | null; collaboration_mode: string; is_public: boolean; revision: number };
export type UserSelf = { id: string; login_email: string; profile: Profile; school_affiliations: Affiliation[]; preferences: Preference; tags: UserTag[] };
export type UserTag = { id: string; tag_id: string; name: string; kind: string; usage: string; is_public: boolean };
export type Career = { id: string; event_kind: string; title: string; organization_name: string; description: string; started_on: string | null; ended_on: string | null; is_public: boolean; revision: number };
export type UserPublic = { id: string; display_name: string; bio?: string; avatar_url?: string; school_affiliations: Affiliation[]; career_events: Career[]; preferences?: Preference; tags: UserTag[]; verifications: { kind: string; meaning: string }[]; project_members: { id: string; project_title: string; role: string; contribution: string }[] };
export type Project = { id: string; creator_id: string; title: string; summary: string; goal: string; visibility: string; project_status: string; revision: number; member_count?: number };
export type Opening = { id: string; role: string; capacity: number; filled: number; skills: string[]; experience: string };
export type Recruitment = { id: string; project_id: string; project_title: string; creator_id: string; description: string; status: string; hours_per_week: number | null; collaboration_mode: string; duration: string; revision: number; role_openings: Opening[] };
export type Coffee = { id: string; requester_id: string; recipient_id: string; purpose: string; introduction: string; questions: string; revision: number; status: string; booking_id: string | null; proposed_slots: { id: string; starts_at: string; ends_at: string }[] };
export type Booking = { id: string; request_id: string; requester_id?: string; recipient_id?: string; starts_at: string; ends_at: string; meeting_mode: string; meeting_location: string; status: string; revision: number; changes?: { id: string; proposer_id: string; change_kind: string; status: string; proposed_value?: { slot?: { starts_at: string; ends_at: string }; meeting_mode?: string; meeting_location?: string } }[] };
export const localDate = (value: string) => new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
export const timezone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
export const statusText: Record<string, string> = { pending: "응답 대기", accepted: "수락", rejected: "거절", confirmed: "일정 확정", cancelled: "취소", completed: "완료", draft: "초안", published: "모집 중", closed: "모집 마감", public: "공개", private: "비공개", planning: "기획 중", building: "진행 중", paused: "잠시 쉬는 중", online: "온라인", offline: "오프라인", hybrid: "온·오프라인", flexible: "협의 가능" };

export class ApiError extends Error {
  constructor(public status: number, message: string, public code = "") { super(message); }
}

const localBrowser = typeof window !== "undefined" && ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
const connectionMessage = localBrowser ? "백엔드 서버에 연결하지 못했어요. start-local.bat 실행 창을 확인한 뒤 다시 연결해 주세요." : "서버에 연결하지 못했어요. 잠시 후 다시 연결해 주세요.";

async function responseError(response: Response): Promise<ApiError> {
  const error = await response.json().catch(() => null);
  if (!error && response.status >= 500) return new ApiError(response.status, connectionMessage, "BACKEND_UNAVAILABLE");
  const detail = error?.detail;
  const message = Array.isArray(detail) ? detail.map((x: { msg: string }) => x.msg).join(" · ") : detail;
  return new ApiError(response.status, typeof message === "string" ? message : "요청을 처리하지 못했습니다.", error?.code || "");
}

let accessToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;
let authGeneration = 0;
let accessUserId: string | null = null;

export function setAccessToken(value: string | null, userId: string | null = null) { accessToken = value; accessUserId = userId; authGeneration++; }
export function setSessionIdentity(userId: string) { accessUserId = userId; }

export async function refreshSession(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  const generation = authGeneration;
  refreshPromise = (async () => {
    try {
      const response = await fetch("/api/v1/auth/refresh", { method: "POST", credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(localBrowser ? 10_000 : 60_000) });
      if (response.status === 401) { if (generation === authGeneration) accessToken = null; return false; }
      if (!response.ok) throw await responseError(response);
      const result = await response.json();
      if (generation !== authGeneration) return false;
      if (accessUserId && result.user_id && accessUserId !== result.user_id) {
        accessToken = null; accessUserId = null; authGeneration++;
        if (typeof window !== "undefined") window.dispatchEvent(new Event("dudri:session-changed"));
        throw new ApiError(401, "다른 화면에서 로그인 계정이 변경되었어요. 현재 계정에서 다시 요청해 주세요.", "SESSION_CHANGED");
      }
      accessToken = result.access_token;
      accessUserId = result.user_id || accessUserId;
      return true;
    } catch (error) { throw error instanceof ApiError ? error : new ApiError(0, connectionMessage, "BACKEND_UNAVAILABLE"); }
    finally { refreshPromise = null; }
  })();
  return refreshPromise;
}

export async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const generation = authGeneration;
  const headers = new Headers(options.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: "same-origin", cache: "no-store" });
  } catch { throw new ApiError(0, connectionMessage, "BACKEND_UNAVAILABLE"); }
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (generation !== authGeneration) throw new ApiError(401, "로그인 계정이 변경되었어요. 현재 계정에서 다시 요청해 주세요.", "SESSION_CHANGED");
    const refreshed = await refreshSession();
    if (generation !== authGeneration) throw new ApiError(401, "로그인 계정이 변경되었어요. 현재 계정에서 다시 요청해 주세요.", "SESSION_CHANGED");
    if (refreshed) return api<T>(path, options, false);
  }
  if (!response.ok) {
    throw await responseError(response);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const jsonBody = (data: unknown) => JSON.stringify(data);
export type Page<T> = { items: T[]; next_cursor: string | null };
export type Profile = { user_id: string; display_name: string; bio: string; avatar_url: string | null; name_is_public: boolean; bio_is_public: boolean; avatar_is_public: boolean; revision: number };
export type Affiliation = { id: string; university_id: string; university_name: string; department: string; enrollment_status: string; entry_year: number | null; graduation_year: number | null; is_public: boolean; revision: number };
export type Preference = { coffee_chat_available: boolean; project_available: boolean; learning_stage: string; activity_goal: string; hours_per_week: number | null; collaboration_mode: string; is_public: boolean; revision: number };
export type UserSelf = { id: string; login_email: string; google_connected?: boolean; profile: Profile; school_affiliations: Affiliation[]; preferences: Preference; tags: UserTag[] };
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

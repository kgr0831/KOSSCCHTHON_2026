import { expect, test, type Page } from "@playwright/test";

async function fixtures(page: Page) {
  const user = { id: "owner", profile: { user_id: "owner", display_name: "팀장", bio: "", revision: 1, name_is_public: true, bio_is_public: true, avatar_is_public: false }, school_affiliations: [], tags: [], preferences: { coffee_chat_available: true, project_available: true, learning_stage: "building", activity_goal: "팀 프로젝트", hours_per_week: 6, collaboration_mode: "online", is_public: true, revision: 1 } };
  const request = { id: "request-1", project_id: "project-1", opening_id: "opening-1", candidate_id: "applicant", initiator_id: "applicant", recipient_id: "owner", request_kind: "application", message: "프론트엔드 역할로 함께하고 싶습니다.", status: "pending", revision: 1 };
  const decisions: unknown[] = [];
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    if (path === "/auth/refresh") return route.fulfill({ json: { access_token: "fixture", user_id: user.id } });
    if (path === "/me") return route.fulfill({ json: user });
    if (path === "/recruitment-posts") return route.fulfill({ json: { items: [{ id: "post-1", project_id: "project-1", project_title: "동문 멘토링 서비스", creator_id: "owner", description: "학교 선후배를 연결하는 서비스를 만들어요.", status: "published", hours_per_week: 6, collaboration_mode: "online", duration: "이번 학기", revision: 1, role_openings: [{ id: "opening-1", role: "프론트엔드", capacity: 2, filled: 0, skills: ["React"], experience: "" }] }], next_cursor: null } });
    if (path === "/projects") return route.fulfill({ json: { items: [{ id: "project-1", creator_id: "owner", title: "동문 멘토링 서비스", summary: "관계를 연결해요.", goal: "첫 서비스 출시", visibility: "public", project_status: "building", revision: 1, member_count: 1 }], next_cursor: null } });
    if (path === "/me/project-requests") return route.fulfill({ json: { items: [request], next_cursor: null } });
    if (path === "/project-requests/request-1/decision") {
      const body = route.request().postDataJSON();
      decisions.push(body);
      Object.assign(request, { status: body.decision, revision: request.revision + 1 });
      return route.fulfill({ json: request });
    }
    return route.fulfill({ json: { items: [], next_cursor: null } });
  });
  return decisions;
}

test("team building exposes published recruitment and lets an owner accept an application", async ({ page }) => {
  const decisions = await fixtures(page);
  await page.goto("/team-building");

  await expect(page.getByRole("heading", { name: "팀빌딩" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "주요 메뉴" }).getByRole("link", { name: "팀빌딩", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "모집 중인 팀" })).toBeVisible();
  await expect(page.getByRole("link", { name: "공고 보기 · 참여 신청" })).toHaveAttribute("href", "/projects/project-1");
  const received = page.getByRole("region", { name: "받은 팀 참여 신청" });
  await expect(received.getByText("프론트엔드 역할로 함께하고 싶습니다.")).toBeVisible();
  await received.getByRole("button", { name: "참여 수락" }).click();

  await expect.poll(() => decisions).toEqual([{ decision: "accepted", revision: 1 }]);
  await expect(received.getByText("수락", { exact: true })).toBeVisible();
  await expect(received.getByRole("button", { name: "참여 수락" })).toHaveCount(0);
});

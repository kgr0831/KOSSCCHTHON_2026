import { expect, test, type Page } from "@playwright/test";

const project = {
  id: "project-1",
  creator_id: "owner",
  title: "테스트 프로젝트",
  summary: "함께 만드는 작은 서비스",
  goal: "프로젝트 흐름 확인",
  project_status: "planning",
  visibility: "public",
  revision: 1,
  member_count: 2,
};

async function fixture(page: Page, userId: string, deleted: { value: boolean }) {
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    if (path === "/auth/refresh") return route.fulfill({ json: { access_token: "fixture", user_id: userId } });
    if (path === "/me") return route.fulfill({ json: { id: userId, profile: { display_name: "Fixture" }, school_affiliations: [], tags: [], preferences: {} } });
    if (path === "/projects/project-1" && request.method() === "DELETE") {
      deleted.value = true;
      return route.fulfill({ status: 204 });
    }
    if (path === "/projects/project-1") return route.fulfill({ json: { ...project, viewer_is_member: userId !== "owner", viewer_request_status: userId !== "owner" ? "accepted" : null } });
    if (path === "/projects") return route.fulfill({ json: { items: deleted.value ? [] : [{ ...project, viewer_is_member: userId === "owner" }], next_cursor: null } });
    if (path === "/recruitment-posts") return route.fulfill({ json: { items: [], next_cursor: null } });
    if (path === "/me/project-requests") return route.fulfill({ json: { items: [], next_cursor: null } });
    return route.fulfill({ json: { items: [], next_cursor: null } });
  });
}

test("a creator confirms a soft-delete from the project list", async ({ page }) => {
  const deleted = { value: false };
  await fixture(page, "owner", deleted);
  await page.goto("/projects");
  await expect(page.getByText(project.title)).toBeVisible();
  await page.getByRole("button", { name: "프로젝트 삭제" }).click();
  const dialog = page.getByRole("dialog", { name: "프로젝트를 삭제할까요?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "프로젝트 삭제" }).click();
  await expect(page.getByText(project.title)).toHaveCount(0);
  expect(deleted.value).toBe(true);
});

test("a participating member never sees the application form", async ({ page }) => {
  const deleted = { value: false };
  await fixture(page, "member", deleted);
  await page.goto("/projects/project-1");
  await expect(page.getByText("참여 중", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "참여 신청" })).toHaveCount(0);
});

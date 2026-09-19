import { expect, test, type Page } from "@playwright/test";

const session = {
  id: "viewer",
  profile: { user_id: "viewer", display_name: "테스트 사용자", bio: "", revision: 1, name_is_public: true, bio_is_public: true, avatar_is_public: false },
  school_affiliations: [],
  tags: [],
  preferences: { user_id: "viewer", activity_goal: "프로젝트 완성", collaboration_mode: "online", learning_stage: "learning", revision: 1 },
};
const person = {
  id: "other", display_name: "공개 동문", bio: "공개된 경험", can_request_coffee_chat: true,
  school_affiliations: [], tags: [], verifications: [], career_events: [], project_members: [],
};
const publicSite = { kind: "profile_pr", url: "http://127.0.0.1:8001/s/profile-pr-fixture" };

async function fixtures(page: Page) {
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    let result: unknown = { items: [], next_cursor: null };
    if (path === "/auth/refresh") result = { access_token: "fixture-only" };
    else if (path === "/me") result = session;
    else if (path === "/users/other") result = person;
    else if (path === "/users/other/career-path-graph") result = { nodes: [] };
    else if (path === "/users/other/sites") result = { items: [publicSite] };
    await route.fulfill({ status: 200, json: result });
  });
  await page.route(publicSite.url, route => route.fulfill({ contentType: "text/html", body: "<!doctype html><title>fixture public profile</title><main>isolated profile</main>" }));
}

test("published custom profile opens in the app shell, survives reload, and returns with Back", async ({ page }) => {
  await fixtures(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/users/other?site=profile_pr");

  const frame = page.locator(".public-site-viewer iframe");
  await expect(frame).toHaveAttribute("src", publicSite.url);
  await expect(frame).toHaveAttribute("sandbox", "allow-scripts");
  await expect(frame).toHaveAttribute("referrerpolicy", "no-referrer");
  await expect(page.locator(".sidebar")).toBeVisible();
  await page.reload();
  await expect(frame).toBeVisible();

  await page.goto("/users/other");
  await expect(page.locator(".public-site-viewer")).toHaveCount(0);
  await page.getByRole("link", { name: "자기 PR 프로필 전체 보기 ↗" }).click();
  await expect(frame).toBeVisible();
  await page.goBack();
  await expect(page.locator(".public-site-viewer")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "자기 PR 프로필 전체 보기 ↗" })).toBeVisible();
});

test("custom profile viewer keeps the mobile bottom navigation visible", async ({ page }) => {
  await fixtures(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/users/other?site=profile_pr");

  await expect(page.locator(".public-site-viewer iframe")).toBeVisible();
  await expect(page.locator(".bottom-nav")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

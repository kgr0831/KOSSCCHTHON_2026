import { expect, test, type Page } from "@playwright/test";

const user = { id: "google-fixture", google_connected: true, login_email: "fixture@example.com", profile: { user_id: "google-fixture", display_name: "Google Fixture", bio: "", revision: 1, name_is_public: true, bio_is_public: true, avatar_is_public: false }, school_affiliations: [], tags: [], preferences: { activity_goal: "", collaboration_mode: "online", learning_stage: "learning", revision: 1 } };

async function fixtures(page: Page, guest = false) {
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  const confirmations: { path: string; body: unknown }[] = [];
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/refresh")) { await pending; await route.fulfill({ status: guest ? 401 : 200, json: guest ? {} : { access_token: "fixture-session", user_id: user.id } }); return; }
    if (path.endsWith("/auth/google/callback") || path.endsWith("/auth/github/callback") || path.endsWith("/school-email-verifications/confirm")) {
      confirmations.push({ path, body: route.request().postDataJSON() });
      await route.fulfill({ json: path.endsWith("/auth/google/callback") ? { access_token: "fixture-google-session", user_id: user.id } : path.endsWith("/auth/github/callback") ? { id: "github-fixture", provider: "github", login: "fixture" } : { status: "verified", user_id: user.id } }); return;
    }
    await route.fulfill({ json: path.endsWith("/me") ? user : { items: [], next_cursor: null } });
  });
  return { release, confirmations };
}

test("Google code is removed from the URL before session restoration and exchanged once", async ({ page }) => {
  const state = await fixtures(page, true);
  await page.goto("/auth/callback?code=fixture-private-code");
  await expect(page).toHaveURL(/\/auth\/callback$/);
  expect(state.confirmations).toHaveLength(0);
  state.release();
  await expect(page.getByRole("heading", { name: "내 프로필", exact: true })).toBeVisible();
  expect(state.confirmations).toEqual([{ path: "/api/v1/auth/google/callback", body: { code: "fixture-private-code" } }]);
  const storage = await page.evaluate(() => JSON.stringify({ history: history.state, local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(storage).not.toContain("fixture-private-code");
  expect(storage).not.toContain("fixture-google-session");
});

test("GitHub code and state are removed before one same-origin exchange", async ({ page }) => {
  const state = await fixtures(page);
  await page.goto("/github/callback?code=fixture-github-code&state=fixture-github-state");
  await expect(page).toHaveURL(/\/github\/callback$/);
  expect(state.confirmations).toHaveLength(0);
  state.release();
  await expect(page.getByRole("heading", { name: "내 자료와 AI 검토" })).toBeVisible();
  expect(await page.evaluate(() => history.state?.dudriView)).toBe("/materials");
  expect(state.confirmations).toEqual([{ path: "/api/v1/auth/github/callback", body: { code: "fixture-github-code", state: "fixture-github-state" } }]);
  const storage = await page.evaluate(() => JSON.stringify({ history: history.state, local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(storage).not.toContain("fixture-github-code");
  expect(storage).not.toContain("fixture-github-state");
});

test("GitHub callback keeps provider errors out of the page and offers a safe retry", async ({ page }) => {
  const state = await fixtures(page);
  await page.goto("/github/callback?error=access_denied&error_description=fixture-provider-detail");
  await expect(page).toHaveURL(/\/github\/callback$/);
  state.release();
  await expect(page.getByRole("button", { name: "다시 시도" })).toBeVisible();
  expect(state.confirmations).toEqual([]);
  await expect(page.getByRole("main").getByRole("alert")).not.toContainText("fixture-provider-detail");
  const storage = await page.evaluate(() => JSON.stringify({ history: history.state, local: { ...localStorage }, session: { ...sessionStorage } }));
  expect(storage).not.toContain("fixture-provider-detail");
});

test("school link waits for restored identity and retains the original token only in memory", async ({ page }) => {
  const state = await fixtures(page);
  await page.goto("/auth/confirm#purpose=school_attach&token=fixture-school-token");
  await expect(page).toHaveURL(/\/auth\/confirm$/);
  expect(state.confirmations).toHaveLength(0);
  state.release();
  await expect(page.getByRole("heading", { name: "내 프로필", exact: true })).toBeVisible();
  expect(state.confirmations).toEqual([{ path: "/api/v1/me/school-email-verifications/confirm", body: { token: "fixture-school-token" } }]);
});

test("school link does not consume a challenge while signed out", async ({ page }) => {
  const state = await fixtures(page, true);
  await page.goto("/auth/confirm#purpose=school_attach&token=fixture-school-token");
  state.release();
  await expect(page.getByRole("link", { name: "로그인하기", exact: true })).toBeVisible();
  expect(state.confirmations).toHaveLength(0);
});

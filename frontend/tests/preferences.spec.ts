import { expect, test, type Page } from "@playwright/test";

async function fixtures(page: Page) {
  const preferences = { coffee_chat_available: true, project_available: true, learning_stage: "learning", activity_goal: "", hours_per_week: 2, collaboration_mode: "online", is_public: false, revision: 1 };
  const user = { id: "owner", google_connected: true, profile: { user_id: "owner", display_name: "Fixture", bio: "", avatar_url: null, revision: 1, name_is_public: true, bio_is_public: true, avatar_is_public: false }, school_affiliations: [], tags: [], preferences };
  const state = { user, failReads: false, failSave: false, release: undefined as undefined | (() => void), revisions: [] as number[] };
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    if (path === "/auth/refresh") return route.fulfill({ json: { access_token: "fixture", user_id: user.id } });
    if (path === "/me") return route.fulfill({ status: state.failReads ? 503 : 200, json: state.failReads ? { detail: "Fixture refetch unavailable" } : user });
    if (path === "/me/preferences") {
      const body = route.request().postDataJSON();
      state.revisions.push(body.revision);
      await new Promise<void>(resolve => { state.release = resolve; });
      if (state.failSave) return route.fulfill({ status: 503, json: { detail: "Fixture save failed" } });
      Object.assign(preferences, body, { revision: preferences.revision + 1 });
      return route.fulfill({ json: preferences });
    }
    if (path === "/users/recipient") return route.fulfill({ json: { id: "recipient", display_name: "Recipient", can_request_coffee_chat: false, school_affiliations: [], tags: [], career_events: [], project_members: [], verifications: [] } });
    await route.fulfill({ json: { items: [], nodes: [] } });
  });
  return state;
}

test("saved coffee availability and revision survive a failed refetch", async ({ page }) => {
  const state = await fixtures(page);
  await page.goto("/profile");
  const panel = page.locator("#preferences"), toggle = panel.getByRole("switch", { name: "커피챗 요청을 받을게요" });
  await toggle.uncheck();
  await expect(panel.getByRole("status")).toHaveText("아직 저장하지 않았어요");
  await panel.getByRole("button", { name: "활동 조건 저장" }).click();
  await expect(toggle).toBeDisabled();
  await expect.poll(() => !!state.release).toBe(true);
  state.failReads = true; state.release!();
  await expect(panel.getByRole("status")).toHaveText("저장했어요");
  await expect(toggle).not.toBeChecked();
  await toggle.check();
  state.release = undefined;
  await panel.getByRole("button", { name: "활동 조건 저장" }).click();
  await expect.poll(() => !!state.release).toBe(true);
  state.release!();
  await expect(panel.getByRole("status")).toHaveText("저장했어요");
  expect(state.revisions).toEqual([1, 2]);
});

test("failed save keeps the draft and never reports success", async ({ page }) => {
  const state = await fixtures(page);
  await page.goto("/profile");
  const panel = page.locator("#preferences"), toggle = panel.getByRole("switch", { name: "커피챗 요청을 받을게요" });
  await toggle.uncheck();
  state.failSave = true;
  await panel.getByRole("button", { name: "활동 조건 저장" }).click();
  await expect.poll(() => !!state.release).toBe(true);
  state.release!();
  await expect(panel.getByRole("alert")).toHaveText("Fixture save failed");
  await expect(toggle).not.toBeChecked();
  await expect(toggle).toBeEnabled();
  await expect(panel.getByRole("status")).toHaveText("아직 저장하지 않았어요");
});

test("closed coffee requests have no action or direct-link form", async ({ page }) => {
  await fixtures(page);
  await page.goto("/users/recipient");
  await expect(page.getByText("커피챗 요청 불가", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "커피챗 요청", exact: true })).toHaveCount(0);
  await page.goto("/coffee/new?recipient=recipient");
  await expect(page.getByText("지금은 이 동문에게 커피챗을 요청할 수 없어요.")).toBeVisible();
  await expect(page.getByRole("button", { name: "커피챗 요청 보내기" })).toHaveCount(0);
});

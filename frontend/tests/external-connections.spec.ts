import { expect, test, type Page } from "@playwright/test";

const github = { id: "github-account", provider: "github", login: "dudri-fixture" };
const repositories = [
  { repository_id: 101, display_name: "public-repo", full_name: "campus/public-repo", private: false, canonical_url: "https://github.com/campus/public-repo", description: "Public fixture" },
  { repository_id: 202, display_name: "private-repo", full_name: "campus/private-repo", private: true, canonical_url: "https://github.com/campus/private-repo", description: "Private fixture" },
];

async function fixture(page: Page, options: { linkedIn?: boolean; githubConnected?: boolean } = {}) {
  let githubConnected = options.githubConnected ?? true;
  let sourceItems: Record<string, unknown>[] = options.linkedIn ? [{
    id: "linkedin-material", display_name: "LinkedIn profile", material_kind: "linkedin", access_status: "available",
    canonical_url: "https://www.linkedin.com/in/fixture", is_private: true, revision: 1, created_at: "2026-09-20T00:00:00Z",
  }] : [];
  const calls = { synced: undefined as unknown, linkedIn: undefined as unknown, deleted: [] as string[], analysisStarts: 0 };
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    if (path === "/auth/refresh") return route.fulfill({ json: { access_token: "fixture", user_id: "viewer" } });
    if (path === "/me") return route.fulfill({ json: { id: "viewer", profile: { display_name: "Fixture" }, school_affiliations: [], tags: [], preferences: {} } });
    if (path === "/me/subscription") return route.fulfill({ json: { plan: "free" } });
    if (path === "/me/external-accounts") return route.fulfill({ json: { items: githubConnected ? [github] : [] } });
    if (path === "/me/external-accounts/github/repositories") return route.fulfill({ json: { items: repositories } });
    if (path === "/me/external-accounts/github/sync" && request.method() === "POST") {
      calls.synced = request.postDataJSON();
      sourceItems = [...sourceItems, { id: "github-material", display_name: "campus/private-repo", material_kind: "github_repository", access_status: "available", canonical_url: "https://github.com/campus/private-repo", is_private: true, revision: 1, created_at: "2026-09-20T00:00:00Z" }];
      return route.fulfill({ json: { items: [] } });
    }
    if (path === "/me/external-accounts/github/connect" && request.method() === "POST") return route.fulfill({ json: { url: "https://github.com/login/oauth/authorize?state=fixture" } });
    if (path === `/me/external-accounts/${github.id}` && request.method() === "DELETE") {
      githubConnected = false;
      calls.deleted.push(path);
      return route.fulfill({ status: 204 });
    }
    if (path === "/me/source-materials/linkedin" && request.method() === "POST") {
      calls.linkedIn = request.postDataJSON();
      sourceItems = [{ id: "linkedin-material", display_name: "LinkedIn profile", material_kind: "linkedin", access_status: "available", canonical_url: (calls.linkedIn as { url: string }).url, is_private: true, revision: 1, created_at: "2026-09-20T00:00:00Z" }, ...sourceItems.filter(item => item.material_kind !== "linkedin")];
      return route.fulfill({ status: 201, json: sourceItems[0] });
    }
    if (path === "/me/source-materials/linkedin-material" && request.method() === "DELETE") {
      calls.deleted.push(path);
      sourceItems = sourceItems.map(item => item.id === "linkedin-material" ? { ...item, access_status: "withdrawn" } : item);
      return route.fulfill({ status: 204 });
    }
    if (path === "/me/source-materials") return route.fulfill({ json: { items: sourceItems } });
    if (path === "/me/analysis-runs") {
      if (request.method() === "POST") calls.analysisStarts++;
      return route.fulfill({ json: { items: [] } });
    }
    if (path === "/me/suggestions") return route.fulfill({ json: { items: [] } });
    return route.fulfill({ json: { items: [] } });
  });
  return calls;
}

test("GitHub repositories stay opt-in and are not automatically analyzed", async ({ page }) => {
  const calls = await fixture(page);
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/materials");
  await expect(page.getByRole("heading", { name: "GitHub 연결" })).toBeVisible();
  await expect(page.getByRole("link", { name: "AI 분석 플랜 보기" })).toHaveAttribute("href", "/pricing");
  await expect(page.getByLabel("campus/public-repo (공개)")).toBeVisible();
  const sync = page.getByRole("button", { name: /선택한 저장소.*가져오기/ });
  await expect(sync).toBeDisabled();
  await page.getByLabel("campus/private-repo (비공개)").check();
  await expect(sync).toBeEnabled();
  await sync.click();
  await expect.poll(() => calls.synced).toEqual({ repository_ids: [202] });
  expect(calls.analysisStarts).toBe(0);
  await expect(page.getByRole("status")).toContainText("AI 분석은 시작하지 않았어요");
  await expect(page.getByRole("link", { name: /저장소 열기/ }).first()).toHaveAttribute("rel", "noopener noreferrer");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("LinkedIn only stores and opens a profile URL", async ({ page }) => {
  const calls = await fixture(page, { linkedIn: false });
  await page.goto("/materials");
  const input = page.getByLabel("LinkedIn 프로필 URL");
  await input.fill("https://www.linkedin.com/in/fixture");
  await page.getByRole("button", { name: "LinkedIn 링크 저장" }).click();
  await expect.poll(() => calls.linkedIn).toEqual({ url: "https://www.linkedin.com/in/fixture" });
  const profile = page.getByRole("link", { name: /LinkedIn 프로필 열기/ });
  await expect(profile).toHaveAttribute("target", "_blank");
  await expect(profile).toHaveAttribute("rel", "noopener noreferrer");
  await page.getByRole("button", { name: "LinkedIn 연결 해제" }).click();
  await expect.poll(() => calls.deleted).toContain("/me/source-materials/linkedin-material");
  await expect(page.getByLabel("LinkedIn 프로필 URL")).toBeVisible();
});

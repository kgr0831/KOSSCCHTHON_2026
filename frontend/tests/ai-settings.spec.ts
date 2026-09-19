import { test, expect } from "@playwright/test";

for (const allowed of [true, false]) {
  test(`CLI metadata and PC-only controls: local=${allowed}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    let settings = { transport: "api", easy_model: "", hard_model: "", cli_provider: "codex", cli_model: "", revision: 2,
      cli_connections: [{ provider: "codex", device_id: "fixture", device_name: "my-pc", executable_path: "C:/Users/fixture/AppData/Roaming/npm/node_modules/@openai/codex/bin/codex.js", account_email: "fixture@example.com", status: "connected", models: ["fixture-model"], default_model: "fixture-model", checked_at: "2026-09-20T00:00:00Z", current_pc: allowed }] };
    let saved: Record<string, unknown> | undefined;
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
      let result: unknown = { items: [] };
      if (path === "/auth/refresh") result = { access_token: "fixture-only" };
      else if (path === "/me") result = { id: "viewer", profile: { display_name: "Fixture" }, school_affiliations: [], tags: [], preferences: {} };
      else if (path === "/ai/providers") result = { api: { configured: true, models: [] }, cli: { allowed, codex_installed: true, claude_installed: false } };
      else if (path === "/me/ai-settings") {
        if (route.request().method() === "PUT") {
          saved = route.request().postDataJSON();
          settings = { ...settings, ...saved, revision: settings.revision + 1 };
        }
        result = settings;
      }
      await route.fulfill({ json: result });
    });
    await page.goto("/settings/ai");
    await expect(page.getByText("CLI는 PC 실행 전용입니다.", { exact: true })).toBeVisible();
    await expect(page.getByText(/계정: fixture@example.com/)).toBeVisible();
    if (allowed) {
      await expect(page.getByRole("button", { name: "Codex 연결 확인" })).toBeVisible();
      await expect(page.getByLabel("PC CLI 제공자")).toHaveValue("codex");
      await page.getByRole("combobox", { name: "연결 방식", exact: true }).selectOption("cli");
      await page.getByLabel("PC CLI 모델").selectOption("fixture-model");
      await page.getByRole("button", { name: "연결 설정 저장", exact: true }).click();
      await expect(page.getByRole("status").filter({ hasText: "설정을 저장했어요." })).toBeVisible();
      expect(saved).toMatchObject({ transport: "cli", cli_provider: "codex", cli_model: "fixture-model" });
      expect(saved).not.toHaveProperty("cli_connections");
    } else {
      await expect(page.getByRole("button", { name: "Codex 연결 확인" })).toHaveCount(0);
      await expect(page.getByRole("combobox", { name: "연결 방식", exact: true }).locator('option[value="cli"]')).toHaveJSProperty("disabled", true);
      await expect(page.getByRole("combobox", { name: "연결 방식", exact: true }).locator('option[value="hybrid"]')).toHaveJSProperty("disabled", true);
      await expect(page.getByText("배포 웹에서는 저장된 기록만 볼 수 있어요.", { exact: false })).toBeVisible();
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

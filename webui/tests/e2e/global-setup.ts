import { test as setup, expect } from "@playwright/test";

setup("authenticate as admin", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[id="username"]', "admin");
  await page.fill('input[id="password"]', "changeme");
  await page.click('button[type="submit"]');
  await page.waitForURL("/", { timeout: 15000 });
  await page.context().storageState({ path: "./tests/e2e/.auth/state.json" });
});

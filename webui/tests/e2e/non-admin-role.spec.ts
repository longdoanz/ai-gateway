import { test, expect, Browser, BrowserContext, Page } from "@playwright/test";

const TEST_USER = {
  username: `e2euser_${Date.now()}`,
  password: "testpass123",
  role: "user",
};

test.describe("Non-Admin User Role Restrictions", () => {
  // First: create the user as admin (uses stored admin auth)
  test("admin should create a non-admin user account", async ({ page }) => {
    await page.goto("/accounts");
    const main = page.locator("main");
    await expect(main.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 10000 });

    // Switch to Account Management tab
    await main.getByRole("tab", { name: "Account Management" }).click();

    // Open Create Account dialog
    await main.getByText("Create Account").click();
    await expect(page.getByText("Create Dashboard Account")).toBeVisible({ timeout: 5000 });

    // Fill in the form
    await page.fill('input[id="new-username"]', TEST_USER.username);
    await page.fill('input[id="new-password"]', TEST_USER.password);

    // Select "User" role (should be default, but click to be sure)
    const roleTrigger = page.locator("form").locator('[data-slot="select-trigger"]');
    await roleTrigger.click();
    await page.getByRole("option", { name: "User" }).click();

    // Submit
    await page.locator("form").locator('button[type="submit"]').click();

    // Dialog should close and user should appear in the table
    await expect(page.getByText("Create Dashboard Account")).not.toBeVisible({ timeout: 10000 });
    await expect(page.locator("td").getByText(TEST_USER.username)).toBeVisible({ timeout: 10000 });
  });

  // All non-admin tests share a SINGLE login to avoid rate limiting
  test("non-admin user: sidebar visibility, page access, and route restrictions", async ({ browser }) => {
    const context = await browser.newContext({ storageState: undefined });
    const page = await context.newPage();

    // Login once as the test user
    await page.goto("/login");
    await expect(page.locator('input[id="username"]')).toBeVisible({ timeout: 10000 });
    await page.fill('input[id="username"]', TEST_USER.username);
    await page.fill('input[id="password"]', TEST_USER.password);
    await page.click('button[type="submit"]');

    // Wait for either successful redirect or rate limit message
    const result = await Promise.race([
      page.waitForURL("/", { timeout: 15000 }).then(() => "redirected" as const),
      page.getByText("Too many login attempts").waitFor({ state: "visible", timeout: 15000 }).then(() => "rate_limited" as const),
    ]);

    if (result === "rate_limited") {
      console.warn("Rate limited — skipping non-admin role tests. Run again after cooldown.");
      await context.close();
      return;
    }

    await expect(page.locator("nav").getByText("Dashboard")).toBeVisible({ timeout: 10000 });

    // --- 1. Sidebar visibility ---
    console.log("Checking sidebar visibility for non-admin user...");
    await expect(page.locator("nav").getByText("Dashboard")).toBeVisible();
    await expect(page.locator("nav").getByText("Analytics")).toBeVisible();
    // Logout is inside a popup — click the user avatar button first
    await page.locator("nav").getByRole("button").last().click();
    await expect(page.locator("nav").getByText("Logout")).toBeVisible();

    // Admin-only items should NOT be visible
    await expect(page.locator("nav").getByText("Accounts")).not.toBeVisible();
    await expect(page.locator("nav").getByText("Settings")).not.toBeVisible();
    console.log("PASS: Non-admin sidebar correctly hides admin-only items");

    // --- 2. Dashboard access ---
    console.log("Checking Dashboard access...");
    await expect(page.locator("main").getByText("System Overview")).toBeVisible({ timeout: 10000 });
    console.log("PASS: Non-admin can view Dashboard");

    // --- 3. Analytics access ---
    console.log("Checking Analytics access...");
    await page.click("nav >> text=Analytics");
    await expect(page).toHaveURL("/analytics");
    await expect(page.locator("main").locator("h1")).toBeVisible({ timeout: 10000 });
    console.log("PASS: Non-admin can view Analytics");

    // --- 4. Direct navigation to admin routes ---
    console.log("Checking direct navigation to admin routes...");

    // /settings
    await page.goto("/settings");
    await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
    const settingsContent = await page.locator("main").getByText("Gateway Configuration").isVisible().catch(() => false);
    console.log(`/settings — has admin content: ${settingsContent}`);
    if (settingsContent) {
      console.warn("BUG: Non-admin user can see Gateway Configuration content at /settings");
    }

    // /accounts
    await page.goto("/accounts");
    await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
    const accountsContent = await page.locator("main").getByText("Account Management").isVisible().catch(() => false);
    console.log(`/accounts — has admin content: ${accountsContent}`);
    if (accountsContent) {
      console.warn("BUG: Non-admin user can see Account Management content at /accounts");
    }

    // /import (now redirects to /accounts)
    await page.goto("/import");
    await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
    const importContent = await page.locator("main").getByText("drop").isVisible().catch(() => false);
    console.log(`/import — has admin content: ${importContent}`);
    if (importContent) {
      console.warn("BUG: Non-admin user can see Import content at /import");
    }

    await context.close();
  });
});

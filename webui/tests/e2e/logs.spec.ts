import { test, expect } from "@playwright/test";

// The logs screen is admin-only and streams from the live backend. With no
// backend/DB running in CI the stream simply won't connect, so this spec
// verifies the UI shell (nav + page render + empty state) rather than live
// events — the SSE behaviour is covered by backend unit tests.
test.describe("System Logs screen", () => {
  test("admin sees the Logs nav item and the page shell", async ({ page }) => {
    await page.goto("/logs");

    // Page shell renders (topbar also shows "System Logs", scope to main).
    const main = page.locator("main");
    await expect(main.getByRole("heading", { level: 2 }).getByText("System Logs")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Live WARNING / ERROR stream")).toBeVisible();

    // Controls are present.
    await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reconnect" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Clear" })).toBeVisible();

    // Level filter chips.
    await expect(page.getByRole("button", { name: "All", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "ERROR" })).toBeVisible();
    await expect(page.getByRole("button", { name: "WARNING" })).toBeVisible();

    // Search input.
    await expect(page.getByPlaceholder("Search message, module, function...")).toBeVisible();

    // Sidebar nav item exists (admin).
    const sidebar = page.locator("nav");
    await expect(sidebar.getByRole("link", { name: "Logs" })).toBeVisible();
  });

  test("connection status badge renders a state", async ({ page }) => {
    await page.goto("/logs");
    // Either Connected or Disconnected is fine; the badge must be visible.
    const badge = page.getByText(/Connected|Disconnected/);
    await expect(badge.first()).toBeVisible({ timeout: 10000 });
  });
});

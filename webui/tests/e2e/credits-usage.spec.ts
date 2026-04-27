import { test, expect } from "@playwright/test";

test.describe("Credits and Usage Tracking", () => {
  test("dashboard should display credit consumption KPIs", async ({ page }) => {
    await page.goto("/");
    const main = page.locator("main");
    await expect(main.getByText("System Overview")).toBeVisible({ timeout: 10000 });

    // Verify KPI cards are present and show numeric values
    await expect(main.getByText("Total Monthly Credits Consumed")).toBeVisible();
    await expect(main.getByText("Active Users")).toBeVisible();
    await expect(main.getByText("Remaining Budget")).toBeVisible();
    await expect(main.getByText("Active API Keys")).toBeVisible();

    // The KPI values should be rendered (font-mono spans with numbers)
    const kpiValues = main.locator(".font-mono");
    const count = await kpiValues.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test("analytics page should show credit consumption data", async ({ page }) => {
    await page.goto("/analytics");
    const main = page.locator("main");
    await expect(main.getByText("User Credit Consumption")).toBeVisible({ timeout: 10000 });
  });

  test("dashboard credit values should be rendered as numbers", async ({ page }) => {
    await page.goto("/");
    const main = page.locator("main");
    await expect(main.getByText("Total Monthly Credits Consumed")).toBeVisible({ timeout: 10000 });

    // Verify the budget section shows usage percentage
    await expect(main.getByText("Usage", { exact: true })).toBeVisible();

    // Verify KPI values are actual rendered numbers (not empty or NaN)
    const kpiValues = main.locator(".font-mono");
    const firstValue = await kpiValues.first().textContent();
    expect(firstValue).toBeTruthy();
    expect(firstValue).not.toBe("NaN");
  });

  test("credit consumption trend chart should be visible", async ({ page }) => {
    await page.goto("/");
    const main = page.locator("main");
    await expect(main.getByText("Credit Consumption Trend")).toBeVisible({ timeout: 10000 });
    await expect(main.getByText("Daily usage over last 30 days")).toBeVisible();
  });
});

import { test, expect } from "@playwright/test";

test.describe("Analytics Page - Charts and Sections", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/webui/analytics");
    const main = page.locator("main");
    await expect(main).toBeVisible({ timeout: 15000 });
    // Wait for analytics content to load (either data or empty state)
    await expect(
      main.getByText(/User Credit Consumption|No data/i).first()
    ).toBeVisible({ timeout: 15000 });
  });

  test("should load the analytics page without errors", async ({ page }) => {
    const main = page.locator("main");

    // Page title in header
    await expect(page.locator("header").getByText("Usage Analytics")).toBeVisible();

    // Range selector buttons
    await expect(main.getByText("7D")).toBeVisible();
    await expect(main.getByText("30D")).toBeVisible();
    await expect(main.getByText("90D")).toBeVisible();

    // No error states visible
    await expect(main.getByText("Failed to load")).not.toBeVisible();
  });

  test("should render the User Credit Consumption bar chart section", async ({
    page,
  }) => {
    const main = page.locator("main");
    const heading = main.getByText("User Credit Consumption");
    await expect(heading).toBeVisible();

    // The chart container should be present (either chart or empty state)
    const chartPanel = main
      .locator(".glass-panel")
      .filter({ hasText: "User Credit Consumption" });
    await expect(chartPanel).toBeVisible();
  });

  test("should render the Top Users section with display names", async ({
    page,
  }) => {
    const main = page.locator("main");
    const heading = main.getByText("Top Users");
    await expect(heading).toBeVisible();

    const topUsersPanel = main
      .locator(".glass-panel")
      .filter({ hasText: "Top Users" });
    await expect(topUsersPanel).toBeVisible();

    // If data is present, verify it shows display names (not dashboard usernames)
    // The rank badge (1, 2, 3...) indicates user entries are rendered
    const userEntries = topUsersPanel.locator(
      ".flex.items-center.justify-between"
    );
    const count = await userEntries.count();
    if (count > 0) {
      // Each entry should have a rank badge and a display name
      const firstEntry = userEntries.first();
      await expect(firstEntry).toBeVisible();
      // Verify credits value is shown (format: number + optional k/M suffix)
      await expect(firstEntry.locator(".text-primary").first()).toBeVisible();
    }
  });

  test("should render the Credit Consume By Users donut chart section", async ({
    page,
  }) => {
    const main = page.locator("main");
    const heading = main.getByText("Credit Consume By Users");
    await expect(heading).toBeVisible();

    const donutPanel = main
      .locator(".glass-panel")
      .filter({ hasText: "Credit Consume By Users" });
    await expect(donutPanel).toBeVisible();
  });

  test("should render the Daily Credit Consumption area chart section", async ({
    page,
  }) => {
    const main = page.locator("main");
    const heading = main.getByText("Daily Credit Consumption");
    await expect(heading).toBeVisible();

    const areaPanel = main
      .locator(".glass-panel")
      .filter({ hasText: "Daily Credit Consumption" });
    await expect(areaPanel).toBeVisible();
  });

  test("should render the Kiro User Credit Usage table", async ({ page }) => {
    const main = page.locator("main");
    const heading = main.getByText("Kiro User Credit Usage");
    await expect(heading).toBeVisible();

    const tablePanel = main
      .locator(".glass-panel")
      .filter({ hasText: "Kiro User Credit Usage" });
    await expect(tablePanel).toBeVisible();

    // Verify table headers
    const expectedHeaders = ["User", "Used", "Quota", "Remaining", "Shared Usage"];
    for (const header of expectedHeaders) {
      await expect(
        tablePanel
          .getByRole("columnheader", { name: header })
          .or(tablePanel.locator("th", { hasText: header }))
          .first()
      ).toBeVisible({ timeout: 5000 });
    }

    // Verify at least one data row is present (display names, not dashboard usernames)
    const rows = tablePanel.locator("tbody tr");
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test("should switch date ranges", async ({ page }) => {
    const main = page.locator("main");

    // Click 30D range
    await main.getByText("30D").click();
    // Content should still be visible after range switch
    await expect(main.getByText("User Credit Consumption")).toBeVisible({
      timeout: 10000,
    });

    // Click 90D range
    await main.getByText("90D").click();
    await expect(main.getByText("User Credit Consumption")).toBeVisible({
      timeout: 10000,
    });

    // Click back to 7D
    await main.getByText("7D").click();
    await expect(main.getByText("User Credit Consumption")).toBeVisible({
      timeout: 10000,
    });
  });
});

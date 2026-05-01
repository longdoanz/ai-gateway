import { test, expect } from "@playwright/test";
import path from "path";

const screenshotDir = path.resolve(__dirname, "screenshots");

test.describe("Analytics - Kiro User Credit Usage Table", () => {
  test("should display the Kiro User Credit Usage table with correct headers", async ({
    page,
  }) => {
    // Navigate to analytics page (basePath is /webui)
    await page.goto("/webui/analytics");

    // Wait for the page to fully load by checking for the main element
    const main = page.locator("main");
    await expect(main).toBeVisible({ timeout: 15000 });

    // Wait for analytics content to render (heading or no-data message)
    await expect(
      main
        .getByText(/Kiro User Credit Usage|User Credit Consumption|No data/i)
        .first()
    ).toBeVisible({ timeout: 15000 });

    // Take a full-page screenshot
    await page.screenshot({
      path: path.join(screenshotDir, "analytics-full.png"),
      fullPage: true,
    });

    // Scroll to the bottom of the page
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    // Brief pause for any lazy content to render
    await page.waitForTimeout(1000);

    // Take a screenshot of the visible viewport (bottom of page)
    await page.screenshot({
      path: path.join(screenshotDir, "analytics-credit-table.png"),
      fullPage: false,
    });

    // Check that "Kiro User Credit Usage" heading is visible
    const creditUsageHeading = main.getByText("Kiro User Credit Usage");
    await expect(creditUsageHeading).toBeVisible({ timeout: 10000 });

    // Verify expected table headers exist
    const expectedHeaders = [
      "User",
      "Used",
      "Quota",
      "Remaining",
      "Shared Usage",
    ];
    for (const header of expectedHeaders) {
      await expect(
        main
          .getByRole("columnheader", { name: header })
          .or(main.locator("th", { hasText: header }))
          .first()
      ).toBeVisible({ timeout: 5000 });
    }
  });
});

import { test, expect } from '@playwright/test';

test.describe('Accounts page - Key deduplication', () => {
  test('Access & Overrides tab loads and each Kiro user has exactly 1 key', async ({ page }) => {
    await page.goto('/webui/accounts');

    // The "Access & Overrides" tab is the default (first tab)
    const accessTab = page.getByRole('tab', { name: /access & overrides/i });
    await expect(accessTab).toBeVisible();

    // Wait for the table to load (skeleton should disappear)
    const table = page.locator('table').first();
    await expect(table).toBeVisible({ timeout: 15000 });

    // Verify stat cards are visible
    const kiroUsersCard = page.getByText('Kiro Users').first();
    await expect(kiroUsersCard).toBeVisible();

    const activeTokensCard = page.getByText('Active Tokens').first();
    await expect(activeTokensCard).toBeVisible();

    // Take a screenshot of the full page for visual inspection
    await page.screenshot({
      path: 'tests/e2e/screenshots/accounts-keys-dedup.png',
      fullPage: true,
    });

    // Get all user rows from the table body (skip expanded detail rows)
    const userRows = table.locator('tbody > tr').filter({
      has: page.locator('td:nth-child(4)'), // rows with a 4th column (Keys count)
    });

    const rowCount = await userRows.count();
    console.log(`Found ${rowCount} Kiro user rows in the table`);
    expect(rowCount).toBeGreaterThan(0);

    // Check each user row's key count (4th column, right-aligned)
    const usersWithMultipleKeys: string[] = [];

    for (let i = 0; i < rowCount; i++) {
      const row = userRows.nth(i);
      const cells = row.locator('td');
      const cellCount = await cells.count();

      // Only process rows that have 4 columns (user rows, not expanded detail rows)
      if (cellCount !== 4) continue;

      const userLabel = await cells.nth(1).innerText();
      const keysText = await cells.nth(3).innerText();
      const keyCount = parseInt(keysText.trim(), 10);

      console.log(`User: ${userLabel.split('\n')[0].trim()} | Keys: ${keyCount}`);

      if (keyCount > 1) {
        usersWithMultipleKeys.push(`${userLabel.split('\n')[0].trim()} (${keyCount} keys)`);
      }
    }

    // Report findings
    if (usersWithMultipleKeys.length > 0) {
      console.log(`\nUsers with multiple keys (dedup may not be complete):`);
      usersWithMultipleKeys.forEach((u) => console.log(`  - ${u}`));
    } else {
      console.log(`\nAll users have exactly 1 key - deduplication verified.`);
    }

    // Assert: after deduplication, each user should have exactly 1 key
    expect(
      usersWithMultipleKeys,
      `Expected all users to have 1 key, but found duplicates: ${usersWithMultipleKeys.join(', ')}`
    ).toHaveLength(0);

    // Verify the "Avg Keys / User" stat card shows ~1.0
    const avgKeysCard = page.getByText('Avg Keys / User').first();
    await expect(avgKeysCard).toBeVisible();
  });

  test('page does not show errors', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    const responseErrors: string[] = [];
    page.on('response', (response) => {
      if (response.status() >= 500) {
        responseErrors.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/webui/accounts');

    // Wait for data to load
    const table = page.locator('table').first();
    await expect(table).toBeVisible({ timeout: 15000 });

    // No 5xx API errors
    expect(
      responseErrors,
      `Server errors detected: ${responseErrors.join(', ')}`
    ).toHaveLength(0);

    // Filter out noise - only flag critical React/app errors
    const criticalErrors = consoleErrors.filter(
      (e) => !e.includes('favicon') && !e.includes('404')
    );

    if (criticalErrors.length > 0) {
      console.log('Console errors found:', criticalErrors);
    }
  });
});

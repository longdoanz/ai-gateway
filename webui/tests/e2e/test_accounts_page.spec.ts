import { test, expect } from '@playwright/test';

test('check accounts page kiro users tab', async ({ page }) => {
  await page.goto('/accounts');
  
  // Click on Kiro Users tab if it's not already active
  const kiroUsersTab = page.getByRole('tab', { name: /kiro users/i });
  await kiroUsersTab.click();
  
  // Check if Kiro Users tab has a table
  const table = page.locator('table');
  await expect(table.first()).toBeVisible();
  
  // Check if there are rows
  const rows = table.first().locator('tbody tr');
  const count = await rows.count();
  console.log(`Table has ${count} rows.`);
  const rowText = await rows.first().innerText();
  console.log(`First row data: ${rowText}`);
  expect(count).toBeGreaterThan(0);
  
  // Check if the "Button edit import" is available
  // It could be just "Edit Import"
  const importButton = page.getByRole('button', { name: /edit import/i });
  await expect(importButton.first()).toBeVisible();
  
  console.log('All checks passed: table visible, rows exist, import button available.');
});

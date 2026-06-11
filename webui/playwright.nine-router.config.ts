import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: /nine-router.*\.spec\.ts/,
  timeout: 60000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://localhost:3002",
    headless: true,
    screenshot: "on",
    // No storageState — tests log in directly
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});

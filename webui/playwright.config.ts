import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30000,
  retries: 1,
  workers: 1,
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    screenshot: "only-on-failure",
    storageState: "./tests/e2e/.auth/state.json",
  },
  projects: [
    {
      name: "setup",
      testMatch: /global-setup\.ts/,
      use: { storageState: undefined },
    },
    {
      name: "chromium",
      use: {
        browserName: "chromium",
        launchOptions: {
          args: [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--memory-pressure-off",
          ],
        },
      },
      dependencies: ["setup"],
    },
  ],
});

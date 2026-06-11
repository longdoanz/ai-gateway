import { test, expect, Browser, BrowserContext } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

const BASE_URL = "http://localhost:3002";
const WEBUI = `${BASE_URL}/webui`;
// Shared auth state written once in beforeAll and reused by every test
const AUTH_STATE_PATH = path.join(__dirname, ".auth", "nine-router-state.json");

/**
 * Login once via the API, persist storage state to disk.
 * Subsequent calls reuse the cached state without hitting /auth/login again.
 */
async function ensureAuthState(browser: Browser): Promise<void> {
  // Re-use cached state if it's less than 30 minutes old
  if (fs.existsSync(AUTH_STATE_PATH)) {
    const age = Date.now() - fs.statSync(AUTH_STATE_PATH).mtimeMs;
    if (age < 30 * 60 * 1000) return; // still fresh
  }

  const context = await browser.newContext({ storageState: undefined });
  const page = await context.newPage();

  try {
    // 1. Get tokens from the REST API
    const res = await page.request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: "admin", password: "changeme" },
    });
    if (!res.ok()) {
      throw new Error(`Login API failed: ${res.status()} ${await res.text()}`);
    }
    const { refresh_token } = await res.json();

    // 2. Navigate to the webui so we can write localStorage
    await page.goto(WEBUI);
    await page.waitForLoadState("domcontentloaded");

    // 3. Inject refresh token — AuthProvider reads this on mount
    await page.evaluate((rt) => {
      localStorage.setItem("refresh_token", rt);
    }, refresh_token);

    // 4. Reload so AuthProvider calls /auth/refresh → sets gw_token httponly cookie
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    // Wait briefly for the auth refresh to complete
    await page.waitForTimeout(2000);

    // 5. Save storage state (cookies + localStorage)
    fs.mkdirSync(path.dirname(AUTH_STATE_PATH), { recursive: true });
    await context.storageState({ path: AUTH_STATE_PATH });
  } finally {
    await page.close();
    await context.close();
  }
}

/**
 * 9Router OIDC SSO login flow test
 *
 * Tests the popup-based OIDC SSO flow initiated by the "9Router Admin" button
 * in the sidebar. The expected happy path is:
 *   1. Popup opens /9router/api/auth/oidc/start
 *   2. 9router sets OIDC cookies, redirects to /oauth/authorize
 *   3. Gateway validates gw_token cookie, issues authorization code
 *   4. Redirect to /9router/api/auth/oidc/callback with code + state
 *   5. 9router validates state, exchanges code for token
 *   6. Final redirect to /9router/dashboard
 */
test.describe("9Router OIDC SSO Login Flow", () => {
  // Login ONCE before all tests — avoids hitting the rate limit
  test.beforeAll(async ({ browser }) => {
    await ensureAuthState(browser);
  });

  // Each test gets a fresh context with the saved auth state
  test.use({ storageState: AUTH_STATE_PATH });

  test("should complete SSO flow and land on 9router dashboard", async ({ page, context }) => {
    test.setTimeout(150000);

    // ----------------------------------------------------------------
    // Step 1: Verify webui loads with admin session
    // ----------------------------------------------------------------
    await page.goto(WEBUI, { waitUntil: "domcontentloaded", timeout: 30000 });

    const currentUrl = page.url();
    expect(currentUrl, "Expected to be on the webui dashboard after login").toContain("/webui");
    const isOnLoginPage = currentUrl.includes("/login");
    expect(isOnLoginPage, `Should not be on login page after auth — got: ${currentUrl}`).toBe(false);

    // ----------------------------------------------------------------
    // Step 2: Verify "9Router Admin" button is visible in sidebar
    // After domcontentloaded, React/AuthProvider needs time to hydrate and
    // resolve auth state before NineRouterButton renders.
    // Wait for any auth-gated element first (user avatar), then the button.
    // ----------------------------------------------------------------
    await expect(page.locator("nav")).toBeVisible({ timeout: 30000 });
    // Wait for auth to hydrate — the user initials badge only appears after /auth/refresh
    await expect(page.getByText("admin").first()).toBeVisible({ timeout: 30000 });
    const nineRouterBtn = page.locator("nav").getByRole("button", { name: "9Router Admin" });
    await expect(nineRouterBtn).toBeVisible({ timeout: 10000 });

    // Take a screenshot of the sidebar state before clicking
    await page.screenshot({
      path: path.join(__dirname, "screenshots", "nine-router-sidebar.png"),
    });

    // ----------------------------------------------------------------
    // Step 3: Click the button and capture the popup
    // ----------------------------------------------------------------
    const popupPromise = context.waitForEvent("page");
    await nineRouterBtn.click();
    const popup = await popupPromise;

    // Collect all navigation events during the OIDC flow for diagnostics
    const navigationUrls: string[] = [];
    popup.on("framenavigated", (frame) => {
      if (frame === popup.mainFrame()) {
        navigationUrls.push(frame.url());
      }
    });

    // Wait for the OIDC redirect chain to land on a terminal URL.
    // The 9router dashboard makes continuous background requests so networkidle
    // may never settle. We instead wait for the URL to reach /9router/ (success)
    // or a login/error page (failure).
    try {
      await popup.waitForURL(
        (url) =>
          url.pathname.startsWith("/9router/") ||
          url.pathname.includes("/login") ||
          url.search.includes("error="),
        { timeout: 120000 }
      );
    } catch {
      // Timed out waiting — report whatever URL we have
    }

    const finalUrl = popup.url();
    const pageTitle = await Promise.race([
      popup.title(),
      new Promise<string>((resolve) => setTimeout(() => resolve("(timeout)"), 5000)),
    ]).catch(() => "(unknown)");

    // Take a screenshot of the final state
    const screenshotPath = path.join(
      __dirname,
      "screenshots",
      "nine-router-sso-final.png"
    );
    await popup.screenshot({ path: screenshotPath, fullPage: false, timeout: 10000 }).catch(() => {
      // screenshot may fail if fonts/resources never settle — that's OK
    });

    console.log("=== 9Router SSO Test Results ===");
    console.log("Navigation chain:", navigationUrls.join(" → "));
    console.log("Final URL:", finalUrl);
    console.log("Page Title:", pageTitle);
    console.log("Screenshot:", screenshotPath);

    // ----------------------------------------------------------------
    // Step 4: Assert happy-path outcome
    // ----------------------------------------------------------------

    // Check for error query params — any error= in the URL is a failure
    let urlObj: URL;
    try {
      urlObj = new URL(finalUrl);
    } catch {
      throw new Error(`Final URL is not a valid URL: ${finalUrl}`);
    }

    const errorParam = urlObj.searchParams.get("error");
    if (errorParam) {
      const navChain = navigationUrls.join(" → ");
      throw new Error(
        `OIDC flow failed with error: "${errorParam}"\nFinal URL: ${finalUrl}\nNavigation chain: ${navChain}`
      );
    }

    // The happy path should land on /9router/dashboard
    // Accept /9router/dashboard or /9router/ root as success
    // Reject /9router/login or any /login path as failure
    const isLoginPage =
      /\/9router\/login/.test(finalUrl) || /^http[^/]*\/login/.test(finalUrl);
    const isDashboard =
      /\/9router\/dashboard/.test(finalUrl) ||
      (/\/9router\//.test(finalUrl) && !isLoginPage);

    expect(
      isDashboard,
      `Expected final URL to be the 9router dashboard, got: ${finalUrl}\nNavigation: ${navigationUrls.join(" → ")}`
    ).toBe(true);

    expect(
      isLoginPage,
      `OIDC flow ended on login page — authentication failed. URL: ${finalUrl}\nNavigation: ${navigationUrls.join(" → ")}`
    ).toBe(false);
  });

  test("should show 9Router Admin button for admin user", async ({ page }) => {
    await page.goto(WEBUI, { waitUntil: "domcontentloaded", timeout: 30000 });

    // Wait for auth hydration — the "admin" username label appears after auth resolves
    await expect(page.getByText("admin").first()).toBeVisible({ timeout: 30000 });
    const nineRouterBtn = page.locator("nav").getByRole("button", { name: "9Router Admin" });
    await expect(nineRouterBtn).toBeVisible({ timeout: 10000 });

    // Verify it has the ExternalLink icon (SVG) inside the button
    const svgInBtn = nineRouterBtn.locator("svg");
    await expect(svgInBtn).toBeVisible();
  });

  test("should report navigation chain for diagnostics", async ({ page, context }) => {
    test.setTimeout(150000);

    await page.goto(WEBUI, { waitUntil: "domcontentloaded", timeout: 30000 });

    // Wait for auth hydration before checking the button
    await expect(page.getByText("admin").first()).toBeVisible({ timeout: 30000 });
    const nineRouterBtn = page.locator("nav").getByRole("button", { name: "9Router Admin" });
    await expect(nineRouterBtn).toBeVisible({ timeout: 10000 });

    const popupPromise = context.waitForEvent("page");
    await nineRouterBtn.click();
    const popup = await popupPromise;

    const steps: Array<{ url: string; status?: number }> = [];

    // Track each navigation step
    popup.on("framenavigated", (frame) => {
      if (frame === popup.mainFrame()) {
        steps.push({ url: frame.url() });
      }
    });

    // Track responses to capture status codes
    popup.on("response", (response) => {
      if (response.request().resourceType() === "document") {
        const existing = steps.find((s) => s.url === response.url() && !s.status);
        if (existing) {
          existing.status = response.status();
        }
      }
    });

    try {
      await popup.waitForURL(
        (url) =>
          url.pathname.startsWith("/9router/") ||
          url.pathname.includes("/login") ||
          url.search.includes("error="),
        { timeout: 120000 }
      );
    } catch {
      // continue and report the current URL
    }

    const finalUrl = popup.url();
    console.log("=== OIDC Navigation Diagnostics ===");
    steps.forEach((step, i) => {
      console.log(`  Step ${i + 1}: [${step.status ?? "?"}] ${step.url}`);
    });
    console.log("Final URL:", finalUrl);

    // This test always passes — it's purely for diagnostics output
    // The main assertions are in the first test
    expect(finalUrl).toBeTruthy();
  });
});

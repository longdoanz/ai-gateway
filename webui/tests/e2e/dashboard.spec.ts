import { test, expect } from "@playwright/test";

// ============================================================
// Screen: Login (no auth state needed)
// ============================================================
test.describe("Login Screen", () => {
  test.use({ storageState: undefined });

  test("should display login form with Glacier AI branding", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("text=Glacier AI")).toBeVisible();
    await expect(page.locator("text=Credit Manager Dashboard")).toBeVisible();
    await expect(page.locator('input[id="username"]')).toBeVisible();
    await expect(page.locator('input[id="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });
});

// ============================================================
// Dashboard Layout (Sidebar, Topbar, Auth Guard)
// ============================================================
test.describe("Dashboard Layout", () => {
  test("should display sidebar with navigation items", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("nav >> text=Dashboard")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("nav >> text=Directory")).toBeVisible();
  });

  test("admin should see all nav items including admin-only screens", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("nav >> text=Import")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("nav >> text=Accounts")).toBeVisible();
    await expect(page.locator("nav >> text=Settings")).toBeVisible();
  });

  test("should display topbar with page title", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("header >> text=System Overview")).toBeVisible({ timeout: 10000 });
  });

  test("should have logout button in sidebar", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("nav >> text=Logout")).toBeVisible({ timeout: 10000 });
  });

  test("should redirect to login when not authenticated", async ({ browser }) => {
    const context = await browser.newContext({ storageState: undefined });
    const page = await context.newPage();
    await page.goto("/");
    await page.waitForURL(/\/login/, { timeout: 15000 });
    await context.close();
  });
});

// ============================================================
// Screen 1: Monthly Overview Dashboard
// ============================================================
test.describe("Screen 1: Monthly Overview Dashboard", () => {
  test("should display System Overview heading", async ({ page }) => {
    await page.goto("/");
    const main = page.locator("main");
    await expect(main.locator("text=System Overview")).toBeVisible({ timeout: 10000 });
    await expect(main.locator("text=Real-time credit consumption metrics")).toBeVisible();
  });

  test("should display KPI cards", async ({ page }) => {
    await page.goto("/");
    const main = page.locator("main");
    await expect(main.locator("text=Total Monthly Credits Consumed")).toBeVisible({ timeout: 10000 });
    await expect(main.locator("text=Active Users")).toBeVisible();
    await expect(main.locator("text=Remaining Budget")).toBeVisible();
  });

  test("should display consumption trend chart section", async ({ page }) => {
    await page.goto("/");
    const main = page.locator("main");
    await expect(main.locator("text=Credit Consumption Trend")).toBeVisible({ timeout: 10000 });
    await expect(main.locator("text=Daily usage over last 30 days")).toBeVisible();
  });

  test("should display Active API Keys card", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("main").locator("text=Active API Keys")).toBeVisible({ timeout: 10000 });
  });

  test("should NOT display Buy Credits button (per BRD constraint)", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(2000);
    await expect(page.locator("text=Buy Credits")).not.toBeVisible();
  });
});

// ============================================================
// Screen 2: User & API Key Management Hub
// ============================================================
test.describe("Screen 2: User & API Key Management Hub", () => {
  test("should display page heading and tabs", async ({ page }) => {
    await page.goto("/users");
    const main = page.locator("main");
    await expect(main.locator("h1")).toBeVisible({ timeout: 10000 });
    await expect(main.getByRole("tab", { name: /Access/ })).toBeVisible();
    await expect(main.getByText("Usage Analytics")).toBeVisible();
  });

  test("should display user data table with correct columns", async ({ page }) => {
    await page.goto("/users");
    await expect(page.locator("th >> text=USER DETAILS")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("th >> text=ROLE")).toBeVisible();
    await expect(page.locator("th >> text=STATUS")).toBeVisible();
    await expect(page.locator("th >> text=KEYS")).toBeVisible();
  });

  test("should have Register Key button", async ({ page }) => {
    await page.goto("/users");
    await expect(page.getByText("Register Key")).toBeVisible({ timeout: 10000 });
  });

  test("should open Register Key dialog on click", async ({ page }) => {
    await page.goto("/users");
    await page.getByText("Register Key").click({ timeout: 10000 });
    await expect(page.getByText("Register API Key")).toBeVisible({ timeout: 5000 });
  });

  test("should switch to Usage Analytics tab", async ({ page }) => {
    await page.goto("/users");
    await page.getByText("Usage Analytics").click({ timeout: 10000 });
    await expect(page.getByText("User Credit Consumption")).toBeVisible({ timeout: 5000 });
  });

  test("should show admin user in the table", async ({ page }) => {
    await page.goto("/users");
    await expect(page.locator("td >> text=admin").first()).toBeVisible({ timeout: 10000 });
  });
});

// ============================================================
// Screen 3: User Mapping Import
// ============================================================
test.describe("Screen 3: User Mapping Import", () => {
  test("should display import page with drag-and-drop zone", async ({ page }) => {
    await page.goto("/import");
    const main = page.locator("main");
    await expect(main.locator("h1")).toBeVisible({ timeout: 10000 });
    await expect(main.getByText("drop")).toBeVisible();
    await expect(main.getByText("kiro_user_id").first()).toBeVisible();
    await expect(main.getByText("or click to browse")).toBeVisible();
  });

  test("should accept CSV file and show preview", async ({ page }) => {
    await page.goto("/import");
    const csvContent = "kiro_user_id,email,username\nuser-001,test@example.com,testuser\nuser-002,test2@example.com,testuser2";
    const buffer = Buffer.from(csvContent, "utf-8");

    const fileChooserPromise = page.waitForEvent("filechooser");
    await page.getByText("or click to browse").click({ timeout: 10000 });
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles({
      name: "users.csv",
      mimeType: "text/csv",
      buffer,
    });

    await expect(page.getByText("2 valid", { exact: true }).first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("user-001")).toBeVisible();
    await expect(page.getByText("user-002")).toBeVisible();
    await expect(page.getByText("Import 2 rows")).toBeVisible();
  });
});

// ============================================================
// Screen 4: Account Management
// ============================================================
test.describe("Screen 4: Account Management", () => {
  test("should display account management page", async ({ page }) => {
    await page.goto("/accounts");
    const main = page.locator("main");
    await expect(main.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 10000 });
    await expect(main.getByText("Create Account")).toBeVisible();
  });

  test("should display accounts table with correct columns", async ({ page }) => {
    await page.goto("/accounts");
    await expect(page.locator("th >> text=ACCOUNT")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("th >> text=ROLE")).toBeVisible();
    await expect(page.locator("th >> text=ACTIVE")).toBeVisible();
    await expect(page.locator("th >> text=ACTIONS")).toBeVisible();
  });

  test("should show admin user with Reset Password button", async ({ page }) => {
    await page.goto("/accounts");
    await expect(page.locator("td >> text=admin").first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Reset Password").first()).toBeVisible();
  });

  test("should have active toggle switch per account row", async ({ page }) => {
    await page.goto("/accounts");
    const switches = page.locator('[data-slot="switch"]');
    await expect(switches.first()).toBeVisible({ timeout: 10000 });
  });

  test("should open Create Account dialog", async ({ page }) => {
    await page.goto("/accounts");
    await page.locator("main").getByText("Create Account").click({ timeout: 10000 });
    await expect(page.getByText("Create Dashboard Account")).toBeVisible({ timeout: 5000 });
  });
});

// ============================================================
// Screen 5: Gateway Configuration
// ============================================================
test.describe("Screen 5: Gateway Configuration", () => {
  test("should display settings page with sections", async ({ page }) => {
    await page.goto("/settings");
    const main = page.locator("main");
    await expect(main.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 10000 });
    await expect(main.getByText("Global Model Enforcement")).toBeVisible();
    await expect(main.getByText("Usage Sharing")).toBeVisible();
  });

  test("should have Reload and Apply Changes buttons", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("main").getByText("Reload")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("main").getByText("Apply Changes")).toBeVisible();
  });

  test("Apply Changes should be disabled when no changes made", async ({ page }) => {
    await page.goto("/settings");
    const applyBtn = page.locator("main").locator("button", { hasText: "Apply Changes" });
    await expect(applyBtn).toBeVisible({ timeout: 10000 });
    await expect(applyBtn).toBeDisabled();
  });

  test("should enable Apply Changes after toggling a switch", async ({ page }) => {
    await page.goto("/settings");
    const toggle = page.locator("main").locator('[data-slot="switch"]').first();
    await expect(toggle).toBeVisible({ timeout: 10000 });
    await toggle.click();

    const applyBtn = page.locator("main").locator("button", { hasText: "Apply Changes" });
    await expect(applyBtn).toBeEnabled({ timeout: 5000 });
  });
});

// ============================================================
// Navigation
// ============================================================
test.describe("Navigation", () => {
  test("should navigate between all screens via sidebar", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("main").locator("text=System Overview")).toBeVisible({ timeout: 10000 });

    await page.click("nav >> text=Directory");
    await expect(page).toHaveURL("/users");

    await page.click("nav >> text=Import");
    await expect(page).toHaveURL("/import");

    await page.click("nav >> text=Accounts");
    await expect(page).toHaveURL("/accounts");

    await page.click("nav >> text=Settings");
    await expect(page).toHaveURL("/settings");

    await page.click("nav >> text=Dashboard");
    await expect(page).toHaveURL("/");
    await expect(page.locator("main").locator("text=System Overview")).toBeVisible({ timeout: 10000 });
  });

  test("topbar should update title on navigation", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("header >> text=System Overview")).toBeVisible({ timeout: 10000 });

    await page.click("nav >> text=Directory");
    await expect(page.locator("header").getByText(/User/)).toBeVisible({ timeout: 10000 });

    await page.click("nav >> text=Settings");
    await expect(page.locator("header >> text=Gateway Configuration")).toBeVisible({ timeout: 10000 });
  });
});

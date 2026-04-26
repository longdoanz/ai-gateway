# Glacier AI Credit Management Dashboard - Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Next.js dashboard UI that consumes the existing FastAPI backend (`/api/*` endpoints) for managing AI credit usage, users, API keys, and gateway configuration.

**Architecture:** Next.js App Router with client-side data fetching via TanStack Query. All API calls go to the FastAPI backend (same origin, proxied via Next.js rewrites). JWT auth with access/refresh tokens stored in memory + localStorage. Role-based UI gating (admin vs user) driven by JWT claims.

**Tech Stack:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Shadcn UI, TanStack Query v5, Recharts, Lucide React, next/font (Inter + JetBrains Mono)

---

## File Structure

```text
webui/
├── package.json
├── tsconfig.json
├── next.config.js                    # API rewrites to FastAPI backend
├── tailwind.config.ts                # Glacier Light design tokens
├── postcss.config.js
├── components.json                   # Shadcn UI config
├── app/
│   ├── layout.tsx                    # Root layout: fonts, QueryClientProvider, AuthProvider
│   ├── globals.css                   # Tailwind directives + glassmorphism utilities
│   ├── (auth)/
│   │   └── login/
│   │       └── page.tsx              # Login screen
│   ├── (dashboard)/
│   │   ├── layout.tsx                # Sidebar + Topbar shell, auth guard
│   │   ├── page.tsx                  # Screen 1: Monthly Overview Dashboard
│   │   ├── users/
│   │   │   └── page.tsx              # Screen 2: User & API Key Management Hub
│   │   ├── import/
│   │   │   └── page.tsx              # Screen 3: User Mapping Import
│   │   ├── accounts/
│   │   │   └── page.tsx              # Screen 4: Account Management (admin)
│   │   └── settings/
│   │       └── page.tsx              # Screen 5: Gateway Configuration (admin)
├── components/
│   ├── ui/                           # Shadcn UI primitives (button, table, tabs, dialog, switch, input, select, badge, card, dropdown-menu, toast, skeleton)
│   ├── layout/
│   │   ├── sidebar.tsx               # Glass sidebar nav with role-based menu items
│   │   └── topbar.tsx                # Top header bar
│   └── charts/
│       ├── area-chart-usage.tsx      # 30-day consumption trend (Recharts AreaChart)
│       └── bar-chart-users.tsx       # Per-user burn rate comparison (Recharts BarChart)
├── lib/
│   ├── api-client.ts                 # Axios instance with JWT interceptor (attach token, auto-refresh on 401)
│   ├── auth.ts                       # AuthContext: login, logout, refresh, token storage, user state
│   ├── types.ts                      # TypeScript types mirroring backend Pydantic schemas
│   └── utils.ts                      # Helpers: maskKey, formatCredits, formatDate, cn()
├── hooks/
│   ├── use-auth.ts                   # useAuth() hook consuming AuthContext
│   ├── use-overview.ts               # useOverview() - TanStack Query hook, 60s polling
│   ├── use-users.ts                  # useUsers(), useCreateUser(), useUpdateUser()
│   ├── use-keys.ts                   # useKeys(), useCreateKey(), useToggleKey(), useDeleteKey(), useKeyUsage()
│   ├── use-config.ts                 # useConfig(), useUpdateConfig()
│   └── use-import.ts                 # useImportUsers()
```

**Key decisions:**
- Shadcn UI components go in `components/ui/` — installed via `npx shadcn-ui@latest add <component>`
- All API types in one `lib/types.ts` file mirroring the backend schemas exactly
- One hook file per API domain (users, keys, config, etc.) — each exports query + mutation hooks
- Auth state in React Context, not in TanStack Query — simpler lifecycle for token refresh
- Next.js `rewrites` in `next.config.js` proxy `/api/*` to the FastAPI backend — avoids CORS entirely

---

## Tasks

### Task 1: Project Scaffolding & Design System

**Files:**
- Create: `webui/package.json`
- Create: `webui/tsconfig.json`
- Create: `webui/next.config.js`
- Create: `webui/tailwind.config.ts`
- Create: `webui/postcss.config.js`
- Create: `webui/app/globals.css`
- Create: `webui/app/layout.tsx`
- Create: `webui/lib/utils.ts`
- Create: `webui/components.json`

- [ ] **Step 1: Initialize Next.js project**

```bash
cd /data/longdt/kiro-gateway
npx create-next-app@latest webui --typescript --tailwind --eslint --app --src-dir=false --import-alias="@/*" --use-npm
```

Expected: `webui/` directory created with Next.js boilerplate.

- [ ] **Step 2: Install dependencies**

```bash
cd /data/longdt/kiro-gateway/webui
npm install @tanstack/react-query@5 axios recharts lucide-react class-variance-authority clsx tailwind-merge
npm install -D @types/node
```

- [ ] **Step 3: Install fonts**

```bash
cd /data/longdt/kiro-gateway/webui
npm install @fontsource/inter @fontsource/jetbrains-mono
```

- [ ] **Step 4: Initialize Shadcn UI**

```bash
cd /data/longdt/kiro-gateway/webui
npx shadcn-ui@latest init
```

When prompted:
- Style: Default
- Base color: Slate
- CSS variables: Yes

- [ ] **Step 5: Install Shadcn UI components**

```bash
cd /data/longdt/kiro-gateway/webui
npx shadcn-ui@latest add button table tabs dialog switch input select badge card dropdown-menu toast skeleton separator label
```

- [ ] **Step 6: Configure Tailwind with Glacier Light design tokens**

Replace `webui/tailwind.config.ts`:

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#fcf8ff",
        "on-surface": "#1b1b24",
        "on-surface-variant": "#464555",
        primary: {
          DEFAULT: "#3525cd",
          container: "#4f46e5",
          fixed: "#e2dfff",
          "fixed-dim": "#c3c0ff",
        },
        secondary: {
          DEFAULT: "#565e74",
          container: "#dae2fd",
        },
        tertiary: {
          DEFAULT: "#7e3000",
          container: "#a44100",
        },
        surface: {
          DEFAULT: "#fcf8ff",
          dim: "#dcd8e5",
          bright: "#fcf8ff",
          variant: "#e4e1ee",
          "container-lowest": "#ffffff",
          "container-low": "#f5f2ff",
          container: "#f0ecf9",
          "container-high": "#eae6f4",
          "container-highest": "#e4e1ee",
        },
        outline: {
          DEFAULT: "#777587",
          variant: "#c7c4d8",
        },
        error: {
          DEFAULT: "#ba1a1a",
          container: "#ffdad6",
        },
        sky: {
          DEFAULT: "#0ea5e9",
        },
        indigo: {
          DEFAULT: "#6366f1",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      fontSize: {
        display: ["48px", { lineHeight: "1.1", letterSpacing: "-0.02em", fontWeight: "600" }],
        h1: ["30px", { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600" }],
        h2: ["24px", { lineHeight: "1.3", letterSpacing: "-0.01em", fontWeight: "600" }],
        "body-base": ["14px", { lineHeight: "1.5", letterSpacing: "0", fontWeight: "400" }],
        "body-sm": ["13px", { lineHeight: "1.5", letterSpacing: "0", fontWeight: "400" }],
        "mono-label": ["12px", { lineHeight: "1", letterSpacing: "-0.01em", fontWeight: "500" }],
        "label-caps": ["11px", { lineHeight: "1", letterSpacing: "0.05em", fontWeight: "600" }],
      },
      spacing: {
        "bento-gap": "16px",
        "container-padding": "24px",
        gutter: "24px",
        margin: "32px",
      },
      borderRadius: {
        DEFAULT: "0.25rem",
        lg: "0.5rem",
        xl: "0.75rem",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
```

- [ ] **Step 7: Set up global CSS with glassmorphism utilities**

Replace `webui/app/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  body {
    @apply bg-background text-on-surface font-sans antialiased;
    background-image:
      radial-gradient(at 0% 0%, hsla(210, 100%, 95%, 1) 0px, transparent 50%),
      radial-gradient(at 100% 0%, hsla(190, 100%, 95%, 1) 0px, transparent 50%),
      radial-gradient(at 100% 100%, hsla(230, 100%, 95%, 1) 0px, transparent 50%),
      radial-gradient(at 0% 100%, hsla(200, 100%, 95%, 1) 0px, transparent 50%);
    background-attachment: fixed;
  }
}

@layer components {
  .glass-panel {
    @apply bg-white/60 backdrop-blur-2xl border border-white/80;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
  }
  .glass-panel-elevated {
    @apply bg-white/75 backdrop-blur-3xl border border-white/90;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.05);
  }
}
```

- [ ] **Step 8: Configure Next.js API rewrites**

Replace `webui/next.config.js`:

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
```

- [ ] **Step 9: Set up root layout with fonts and providers**

Replace `webui/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/lib/providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Glacier AI - Credit Manager",
  description: "AI Credit Management Dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

- [ ] **Step 10: Create Providers wrapper (QueryClient only — AuthProvider added in Task 3)**

Create `webui/lib/providers.tsx`:

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
```

- [ ] **Step 11: Create utility helpers**

Create `webui/lib/utils.ts`:

```typescript
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function maskKey(prefix: string, suffix: string): string {
  return `${prefix}...${suffix}`;
}

export function formatCredits(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toString();
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
```

- [ ] **Step 12: Verify setup compiles**

```bash
cd /data/longdt/kiro-gateway/webui
npm run build
```

Expected: Build succeeds (may warn about missing pages, that's fine).

- [ ] **Step 13: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/
git commit -m "feat(webui): scaffold Next.js project with Glacier Light design system

- Next.js 14 App Router + TypeScript
- Tailwind CSS with Glacier Light color tokens and glassmorphism utilities
- Shadcn UI components installed
- TanStack Query, Recharts, Axios, Lucide React
- Inter + JetBrains Mono fonts via next/font
- API rewrites to FastAPI backend"
```

---

### Task 2: TypeScript Types & API Client

**Files:**
- Create: `webui/lib/types.ts`
- Create: `webui/lib/api-client.ts`

- [ ] **Step 1: Define TypeScript types mirroring backend Pydantic schemas**

Create `webui/lib/types.ts`:

```typescript
// --- Auth ---

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface JwtPayload {
  sub: string;
  role: "admin" | "user";
  exp: number;
  type: "access" | "refresh";
}

// --- User ---

export interface UserCreate {
  username: string;
  password: string;
  role?: "admin" | "user";
}

export interface UserUpdate {
  is_active?: boolean;
  password?: string;
  role?: "admin" | "user";
}

export interface UserResponse {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface UserDetailResponse extends UserResponse {
  api_keys: ApiKeyResponse[];
}

// --- ApiKey ---

export interface ApiKeyCreate {
  raw_key: string;
}

export interface ApiKeyResponse {
  id: number;
  user_id: number;
  kiro_user_id: string | null;
  key_prefix: string;
  key_suffix: string;
  is_active: boolean;
  created_at: string;
}

export interface ApiKeyToggle {
  is_active: boolean;
}

// --- KeyUsage ---

export interface KeyUsageResponse {
  month: string;
  current_usage: number;
  usage_limit: number;
  last_synced_at: string | null;
  last_used_at: string | null;
}

// --- Overview ---

export interface DailyUsage {
  date: string;
  credits: number;
}

export interface OverviewResponse {
  total_credits_used: number;
  total_credits_limit: number;
  active_users: number;
  active_keys: number;
  daily_usage: DailyUsage[];
}

// --- Config ---

export interface SystemConfigResponse {
  enable_model_override: boolean;
  enforced_global_model: string;
  enable_usage_sharing: boolean;
}

export interface SystemConfigUpdate {
  enable_model_override?: boolean;
  enforced_global_model?: string;
  enable_usage_sharing?: boolean;
}

// --- Import ---

export interface ImportResult {
  imported: number;
  updated: number;
  errors: string[];
}
```

- [ ] **Step 2: Create Axios API client with JWT interceptor**

Create `webui/lib/api-client.ts`:

```typescript
import axios from "axios";

const apiClient = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

let accessToken: string | null = null;
let refreshToken: string | null = null;
let refreshPromise: Promise<string> | null = null;

export function setTokens(access: string, refresh: string) {
  accessToken = access;
  refreshToken = refresh;
  localStorage.setItem("refresh_token", refresh);
}

export function clearTokens() {
  accessToken = null;
  refreshToken = null;
  localStorage.removeItem("refresh_token");
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem("refresh_token");
}

export function getAccessToken(): string | null {
  return accessToken;
}

async function doRefresh(): Promise<string> {
  const rt = refreshToken || getStoredRefreshToken();
  if (!rt) throw new Error("No refresh token");
  const res = await axios.post("/api/auth/refresh", { refresh_token: rt });
  const { access_token, refresh_token: newRt } = res.data;
  setTokens(access_token, newRt);
  return access_token;
}

// Attach access token to every request
apiClient.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

// Auto-refresh on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      try {
        // Deduplicate concurrent refresh calls
        if (!refreshPromise) {
          refreshPromise = doRefresh().finally(() => {
            refreshPromise = null;
          });
        }
        const newToken = await refreshPromise;
        original.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(original);
      } catch {
        clearTokens();
        window.location.href = "/login";
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

- [ ] **Step 3: Verify types compile**

```bash
cd /data/longdt/kiro-gateway/webui
npx tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/lib/types.ts webui/lib/api-client.ts
git commit -m "feat(webui): add TypeScript types and Axios API client with JWT auto-refresh"
```

---

### Task 3: Auth Context & Login Screen

**Files:**
- Create: `webui/lib/auth.tsx`
- Create: `webui/hooks/use-auth.ts`
- Create: `webui/app/(auth)/login/page.tsx`

- [ ] **Step 1: Create AuthContext with login/logout/refresh logic**

Create `webui/lib/auth.tsx`:

```tsx
"use client";

import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import type { JwtPayload, LoginRequest, TokenResponse } from "@/lib/types";
import apiClient, { clearTokens, getStoredRefreshToken, setTokens } from "@/lib/api-client";

export interface AuthUser {
  id: number;
  role: "admin" | "user";
}

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  isLoading: true,
  login: async () => {},
  logout: () => {},
});

function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const base64 = token.split(".")[1];
    const json = atob(base64.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function userFromToken(token: string): AuthUser | null {
  const payload = decodeJwtPayload(token);
  if (!payload || payload.type !== "access") return null;
  if (payload.exp * 1000 < Date.now()) return null;
  return { id: parseInt(payload.sub), role: payload.role };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Try to restore session from stored refresh token on mount
  useEffect(() => {
    const rt = getStoredRefreshToken();
    if (!rt) {
      setIsLoading(false);
      return;
    }
    apiClient
      .post<TokenResponse>("/auth/refresh", { refresh_token: rt })
      .then((res) => {
        setTokens(res.data.access_token, res.data.refresh_token);
        setUser(userFromToken(res.data.access_token));
      })
      .catch(() => {
        clearTokens();
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (credentials: LoginRequest) => {
    const res = await apiClient.post<TokenResponse>("/auth/login", credentials);
    setTokens(res.data.access_token, res.data.refresh_token);
    setUser(userFromToken(res.data.access_token));
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, login, logout }),
    [user, isLoading, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
```

- [ ] **Step 2: Create useAuth hook**

Create `webui/hooks/use-auth.ts`:

```typescript
"use client";

import { useContext } from "react";
import { AuthContext } from "@/lib/auth";

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
```

- [ ] **Step 3: Build Login page**

Create `webui/app/(auth)/login/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login({ username, password });
      router.push("/");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="glass-panel-elevated rounded-3xl p-10 w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-h1 font-bold text-primary tracking-tight">Glacier AI</h1>
          <p className="text-on-surface-variant mt-2">Credit Manager Dashboard</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter username"
              required
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              required
            />
          </div>
          {error && (
            <p className="text-sm text-error">{error}</p>
          )}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "Signing in..." : "Sign In"}
          </Button>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Update Providers to wrap with AuthProvider**

Replace `webui/lib/providers.tsx`:

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { AuthProvider } from "@/lib/auth";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 5: Verify login page renders**

```bash
cd /data/longdt/kiro-gateway/webui
npm run dev &
# Open http://localhost:3000/login in browser — should see glassmorphism login form
```

Kill the dev server after verifying.

- [ ] **Step 6: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/lib/auth.tsx webui/lib/providers.tsx webui/hooks/use-auth.ts webui/app/\(auth\)/login/page.tsx
git commit -m "feat(webui): add auth context with JWT management and login screen"
```

---

### Task 4: Dashboard Layout — Sidebar, Topbar & Auth Guard

**Files:**
- Create: `webui/components/layout/sidebar.tsx`
- Create: `webui/components/layout/topbar.tsx`
- Create: `webui/app/(dashboard)/layout.tsx`

- [ ] **Step 1: Build Sidebar component with role-based navigation**

Create `webui/components/layout/sidebar.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, Upload, UserCog, Settings, LogOut } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, adminOnly: false },
  { href: "/users", label: "Directory", icon: Users, adminOnly: false },
  { href: "/import", label: "Import", icon: Upload, adminOnly: true },
  { href: "/accounts", label: "Accounts", icon: UserCog, adminOnly: true },
  { href: "/settings", label: "Settings", icon: Settings, adminOnly: true },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const visibleItems = navItems.filter(
    (item) => !item.adminOnly || user?.role === "admin"
  );

  return (
    <nav className="hidden md:flex flex-col fixed left-0 top-0 h-screen w-64 border-r border-white/60 bg-white/40 backdrop-blur-2xl shadow-[4px_0_24px_rgba(0,0,0,0.02)] z-40">
      <div className="p-6">
        <h1 className="text-xl font-bold tracking-tight text-primary">Glacier AI</h1>
        <p className="text-xs text-on-surface-variant mt-1 font-medium">Credit Manager</p>
      </div>

      <div className="flex-1 px-4 space-y-1">
        {visibleItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-4 py-3 rounded-xl transition-colors duration-200 font-medium",
                isActive
                  ? "text-primary bg-white/80 shadow-sm border border-white"
                  : "text-on-surface-variant hover:bg-white/60 hover:text-primary"
              )}
            >
              <item.icon className="w-5 h-5" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>

      <div className="p-4 mt-auto border-t border-white/60">
        <button
          onClick={logout}
          className="flex items-center gap-3 px-4 py-3 w-full rounded-xl text-on-surface-variant hover:bg-white/60 hover:text-error transition-colors font-medium"
        >
          <LogOut className="w-5 h-5" />
          <span>Logout</span>
        </button>
        {user && (
          <div className="mt-3 px-4 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs border border-primary/20">
              {user.role === "admin" ? "A" : "U"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-on-surface truncate capitalize">{user.role} User</p>
              <p className="text-xs text-on-surface-variant truncate">ID: {user.id}</p>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Build Topbar component**

Create `webui/components/layout/topbar.tsx`:

```tsx
"use client";

import { usePathname } from "next/navigation";
import { Bell } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";

const pageTitles: Record<string, string> = {
  "/": "System Overview",
  "/users": "User & Tokens",
  "/import": "Import Mappings",
  "/accounts": "Account Management",
  "/settings": "Gateway Configuration",
};

export function Topbar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const title = pageTitles[pathname] || "Dashboard";

  return (
    <header className="sticky top-0 z-30 w-full border-b border-white/20 bg-white/60 backdrop-blur-2xl shadow-[0_8px_32px_0_rgba(31,38,135,0.07)] flex justify-between items-center px-8 h-16">
      <div className="flex items-center gap-4">
        <h2 className="text-lg font-bold text-on-surface">{title}</h2>
      </div>
      <div className="flex items-center gap-4">
        <button className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-surface-container rounded-full transition-colors relative">
          <Bell className="w-5 h-5" />
        </button>
        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs border border-primary/20">
          {user?.role === "admin" ? "A" : "U"}
        </div>
      </div>
    </header>
  );
}
```

- [ ] **Step 3: Build dashboard layout with auth guard**

Create `webui/app/(dashboard)/layout.tsx`:

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/hooks/use-auth";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="glass-panel rounded-2xl p-8 text-center">
          <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto" />
          <p className="text-on-surface-variant mt-4 text-sm">Loading...</p>
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <div className="flex-1 md:ml-64 flex flex-col min-h-screen">
        <Topbar />
        <main className="flex-1 p-6 md:p-10 lg:p-12 max-w-7xl mx-auto w-full">
          {children}
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create placeholder dashboard page**

Create `webui/app/(dashboard)/page.tsx`:

```tsx
export default function DashboardPage() {
  return (
    <div className="glass-panel rounded-2xl p-8">
      <h1 className="text-h2 font-bold text-on-surface">Monthly Overview</h1>
      <p className="text-on-surface-variant mt-2">Dashboard content coming next.</p>
    </div>
  );
}
```

- [ ] **Step 5: Verify layout renders with sidebar and topbar**

```bash
cd /data/longdt/kiro-gateway/webui
npm run dev &
# Open http://localhost:3000 — should redirect to /login
# After login, should see sidebar + topbar + placeholder content
```

Kill the dev server after verifying.

- [ ] **Step 6: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/components/layout/ webui/app/\(dashboard\)/
git commit -m "feat(webui): add dashboard layout with glassmorphism sidebar, topbar, and auth guard"
```

---

### Task 5: TanStack Query Hooks for All API Domains

**Files:**
- Create: `webui/hooks/use-overview.ts`
- Create: `webui/hooks/use-users.ts`
- Create: `webui/hooks/use-keys.ts`
- Create: `webui/hooks/use-config.ts`
- Create: `webui/hooks/use-import.ts`

- [ ] **Step 1: Create overview hook with 60s polling**

Create `webui/hooks/use-overview.ts`:

```typescript
import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { OverviewResponse } from "@/lib/types";

export function useOverview() {
  return useQuery({
    queryKey: ["overview"],
    queryFn: async () => {
      const res = await apiClient.get<OverviewResponse>("/overview");
      return res.data;
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}
```

- [ ] **Step 2: Create users hooks (list, create, update, detail)**

Create `webui/hooks/use-users.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { UserCreate, UserDetailResponse, UserResponse, UserUpdate } from "@/lib/types";

export function useUsers(limit = 50, offset = 0) {
  return useQuery({
    queryKey: ["users", limit, offset],
    queryFn: async () => {
      const res = await apiClient.get<UserResponse[]>("/users", {
        params: { limit, offset },
      });
      return res.data;
    },
  });
}

export function useUserDetail(userId: number | null) {
  return useQuery({
    queryKey: ["users", userId],
    queryFn: async () => {
      const res = await apiClient.get<UserDetailResponse>(`/users/${userId}`);
      return res.data;
    },
    enabled: userId !== null,
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: UserCreate) => {
      const res = await apiClient.post<UserResponse>("/users", data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, data }: { userId: number; data: UserUpdate }) => {
      const res = await apiClient.put<UserResponse>(`/users/${userId}`, data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}
```

- [ ] **Step 3: Create keys hooks (list, create, toggle, delete, usage)**

Create `webui/hooks/use-keys.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { ApiKeyCreate, ApiKeyResponse, KeyUsageResponse } from "@/lib/types";

export function useKeys(limit = 50, offset = 0) {
  return useQuery({
    queryKey: ["keys", limit, offset],
    queryFn: async () => {
      const res = await apiClient.get<ApiKeyResponse[]>("/keys", {
        params: { limit, offset },
      });
      return res.data;
    },
    refetchInterval: 60_000,
  });
}

export function useKeyUsage(keyId: number | null) {
  return useQuery({
    queryKey: ["keys", keyId, "usage"],
    queryFn: async () => {
      const res = await apiClient.get<KeyUsageResponse[]>(`/keys/${keyId}/usage`);
      return res.data;
    },
    enabled: keyId !== null,
  });
}

export function useCreateKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: ApiKeyCreate) => {
      const res = await apiClient.post<ApiKeyResponse>("/keys", data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
  });
}

export function useToggleKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ keyId, isActive }: { keyId: number; isActive: boolean }) => {
      const res = await apiClient.put<ApiKeyResponse>(`/keys/${keyId}`, { is_active: isActive });
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
  });
}

export function useDeleteKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (keyId: number) => {
      await apiClient.delete(`/keys/${keyId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
  });
}
```

- [ ] **Step 4: Create config hooks**

Create `webui/hooks/use-config.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { SystemConfigResponse, SystemConfigUpdate } from "@/lib/types";

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: async () => {
      const res = await apiClient.get<SystemConfigResponse>("/config");
      return res.data;
    },
  });
}

export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: SystemConfigUpdate) => {
      const res = await apiClient.put<SystemConfigResponse>("/config", data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["config"] }),
  });
}
```

- [ ] **Step 5: Create import hook**

Create `webui/hooks/use-import.ts`:

```typescript
import { useMutation } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { ImportResult } from "@/lib/types";

export function useImportUsers() {
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const res = await apiClient.post<ImportResult>("/import/users", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return res.data;
    },
  });
}
```

- [ ] **Step 6: Verify hooks compile**

```bash
cd /data/longdt/kiro-gateway/webui
npx tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 7: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/hooks/
git commit -m "feat(webui): add TanStack Query hooks for all API domains (overview, users, keys, config, import)"
```

---

### Task 6: Screen 1 — Monthly Overview Dashboard

**Files:**
- Create: `webui/components/charts/area-chart-usage.tsx`
- Modify: `webui/app/(dashboard)/page.tsx`

- [ ] **Step 1: Create the 30-day consumption trend AreaChart**

Create `webui/components/charts/area-chart-usage.tsx`:

```tsx
"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DailyUsage } from "@/lib/types";
import { formatCredits } from "@/lib/utils";

interface Props {
  data: DailyUsage[];
}

export function AreaChartUsage({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="creditGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e4e1ee" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 12, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 12, fill: "#464555" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => formatCredits(v)}
        />
        <Tooltip
          contentStyle={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.9)",
            borderRadius: "12px",
            boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
          }}
          formatter={(value: number) => [formatCredits(value), "Credits"]}
        />
        <Area
          type="monotone"
          dataKey="credits"
          stroke="#0ea5e9"
          strokeWidth={2}
          fill="url(#creditGradient)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 2: Build the full Monthly Overview Dashboard page**

Replace `webui/app/(dashboard)/page.tsx`:

```tsx
"use client";

import { TrendingUp, Users, Key, Wallet } from "lucide-react";
import { useOverview } from "@/hooks/use-overview";
import { formatCredits } from "@/lib/utils";
import { AreaChartUsage } from "@/components/charts/area-chart-usage";
import { Skeleton } from "@/components/ui/skeleton";

function KpiCard({
  title,
  value,
  subtitle,
  icon: Icon,
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ElementType;
}) {
  return (
    <div className="glass-panel rounded-2xl p-6 relative overflow-hidden group">
      <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
        <Icon className="w-16 h-16 text-primary" />
      </div>
      <h3 className="text-sm font-medium text-on-surface-variant mb-1">{title}</h3>
      <div className="flex items-end gap-3 mt-4">
        <span className="text-4xl font-bold text-on-surface tracking-tight font-mono">{value}</span>
      </div>
      <p className="text-xs text-on-surface-variant mt-2">{subtitle}</p>
    </div>
  );
}

function BudgetCard({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.round((used / limit) * 100) : 0;
  const remaining = limit - used;

  return (
    <div className="glass-panel-elevated rounded-2xl p-6 relative overflow-hidden group border-primary/20">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-50" />
      <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
        <Wallet className="w-16 h-16 text-primary" />
      </div>
      <h3 className="text-sm font-medium text-primary mb-1 relative z-10">Remaining Budget</h3>
      <div className="flex items-end gap-3 mt-4 relative z-10">
        <span className="text-4xl font-bold text-on-surface tracking-tight font-mono">
          {formatCredits(remaining)}
        </span>
        <span className="text-sm text-on-surface-variant mb-1">Credits</span>
      </div>
      <div className="mt-4 relative z-10">
        <div className="flex justify-between text-xs mb-1 text-on-surface-variant">
          <span>Usage</span>
          <span>{pct}%</span>
        </div>
        <div className="w-full bg-surface-container-high rounded-full h-1.5 overflow-hidden">
          <div
            className="bg-primary h-1.5 rounded-full shadow-[0_0_8px_rgba(14,165,233,0.4)]"
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { data, isLoading } = useOverview();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-40 rounded-2xl" />
          ))}
        </div>
        <Skeleton className="h-[400px] rounded-2xl" />
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-h1 font-bold text-on-surface tracking-tight">System Overview</h2>
        <p className="text-on-surface-variant mt-1 text-sm">Real-time credit consumption metrics</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <KpiCard
          title="Total Monthly Credits Consumed"
          value={formatCredits(data.total_credits_used)}
          subtitle="current billing cycle"
          icon={TrendingUp}
        />
        <KpiCard
          title="Active Users"
          value={data.active_users.toString()}
          subtitle="unique users this month"
          icon={Users}
        />
        <BudgetCard used={data.total_credits_used} limit={data.total_credits_limit} />
      </div>

      {/* Consumption Trend Chart */}
      <div className="glass-panel rounded-2xl p-6 flex flex-col h-[400px]">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h3 className="text-lg font-semibold text-on-surface">Credit Consumption Trend</h3>
            <p className="text-xs text-on-surface-variant mt-1">Daily usage over last 30 days</p>
          </div>
        </div>
        <div className="flex-1">
          <AreaChartUsage data={data.daily_usage} />
        </div>
      </div>

      {/* Active Keys stat */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <KpiCard
          title="Active API Keys"
          value={data.active_keys.toString()}
          subtitle="keys currently enabled"
          icon={Key}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify dashboard renders with mock/real data**

```bash
cd /data/longdt/kiro-gateway/webui
npm run dev &
# Login and verify the dashboard shows KPI cards, budget bar, and chart area
```

Kill the dev server after verifying.

- [ ] **Step 4: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/components/charts/area-chart-usage.tsx webui/app/\(dashboard\)/page.tsx
git commit -m "feat(webui): implement Monthly Overview Dashboard with KPI cards and consumption chart"
```

---

### Task 7: Screen 2 — User & API Key Management Hub (Tab 1: Access & Overrides)

**Files:**
- Create: `webui/app/(dashboard)/users/page.tsx`
- Create: `webui/components/charts/bar-chart-users.tsx`

This is the most complex screen. It has two tabs: "Access & Overrides" (data table with row expansion showing nested API keys) and "Usage Analytics" (bar chart). We build Tab 1 first, then Tab 2 in the same file.

- [ ] **Step 1: Build the Users page with Tabs, Data Table, and Row Expansion**

Create `webui/app/(dashboard)/users/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ChevronRight, ChevronDown, Plus, Key } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useKeys, useCreateKey, useToggleKey } from "@/hooks/use-keys";
import { useUsers } from "@/hooks/use-users";
import { useAuth } from "@/hooks/use-auth";
import { maskKey, formatCredits } from "@/lib/utils";
import { BarChartUsers } from "@/components/charts/bar-chart-users";
import type { ApiKeyResponse, UserResponse } from "@/lib/types";

function AddKeyDialog() {
  const [rawKey, setRawKey] = useState("");
  const [open, setOpen] = useState(false);
  const createKey = useCreateKey();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await createKey.mutateAsync({ raw_key: rawKey });
    setRawKey("");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="w-4 h-4" /> Register Key
        </Button>
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated">
        <DialogHeader>
          <DialogTitle>Register API Key</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="raw_key">Kiro API Key</Label>
            <Input
              id="raw_key"
              value={rawKey}
              onChange={(e) => setRawKey(e.target.value)}
              placeholder="sk-proj-..."
              className="font-mono text-sm"
              required
              minLength={10}
            />
            <p className="text-xs text-on-surface-variant">
              The key will be encrypted. Only prefix and suffix are stored visibly.
            </p>
          </div>
          <Button type="submit" disabled={createKey.isPending} className="w-full">
            {createKey.isPending ? "Registering..." : "Register Key"}
          </Button>
          {createKey.isError && (
            <p className="text-sm text-error">
              {(createKey.error as any)?.response?.data?.detail || "Failed to register key"}
            </p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}

function KeyRow({ apiKey }: { apiKey: ApiKeyResponse }) {
  const toggleKey = useToggleKey();

  return (
    <tr className="border-b border-outline-variant/20">
      <td className="py-3 px-4 text-on-surface font-medium text-xs">{apiKey.kiro_user_id || "—"}</td>
      <td className="py-3 px-4 font-mono text-on-surface-variant text-xs">
        {maskKey(apiKey.key_prefix, apiKey.key_suffix)}
      </td>
      <td className="py-3 px-4 text-on-surface-variant text-xs">
        {new Date(apiKey.created_at).toLocaleDateString()}
      </td>
      <td className="py-3 px-4 text-right">
        <Switch
          checked={apiKey.is_active}
          onCheckedChange={(checked) =>
            toggleKey.mutate({ keyId: apiKey.id, isActive: checked })
          }
          disabled={toggleKey.isPending}
        />
      </td>
    </tr>
  );
}

function UserRow({
  user,
  keys,
  isExpanded,
  onToggle,
}: {
  user: UserResponse;
  keys: ApiKeyResponse[];
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const userKeys = keys.filter((k) => k.user_id === user.id);

  return (
    <>
      <tr
        className={`hover:bg-surface-container-lowest transition-colors cursor-pointer group ${
          isExpanded ? "bg-sky-50/30" : ""
        }`}
        onClick={onToggle}
      >
        <td className="py-4 px-6 text-center">
          <button className="text-outline group-hover:text-primary hover:bg-surface-container rounded-full p-0.5 transition-colors">
            {isExpanded ? (
              <ChevronDown className="w-5 h-5" />
            ) : (
              <ChevronRight className="w-5 h-5" />
            )}
          </button>
        </td>
        <td className="py-4 px-6">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">
              {user.username.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <div className="font-medium text-on-surface">{user.username}</div>
            </div>
          </div>
        </td>
        <td className="py-4 px-6">
          <Badge variant={user.role === "admin" ? "default" : "secondary"} className="text-[10px]">
            {user.role}
          </Badge>
        </td>
        <td className="py-4 px-6">
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
              user.is_active
                ? "bg-emerald-100/50 text-emerald-800 border-emerald-200/50"
                : "bg-surface-variant text-on-surface-variant border-outline-variant/50"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                user.is_active ? "bg-emerald-500" : "bg-outline"
              }`}
            />
            {user.is_active ? "Active" : "Inactive"}
          </span>
        </td>
        <td className="py-4 px-6 text-right font-mono text-sm">{userKeys.length}</td>
      </tr>
      {/* Expanded: nested API keys sub-table */}
      {isExpanded && (
        <tr className="bg-surface-container-lowest border-b-2 border-primary/10">
          <td colSpan={5} className="p-0">
            <div className="px-12 py-6 pl-20 bg-gradient-to-b from-sky-50/20 to-transparent">
              <div className="flex justify-between items-center mb-4">
                <h4 className="font-mono text-mono-label text-on-surface font-semibold flex items-center gap-2">
                  <Key className="w-4 h-4 text-sky-600" />
                  API Keys ({userKeys.length})
                </h4>
              </div>
              {userKeys.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No API keys registered.</p>
              ) : (
                <div className="border border-outline-variant/40 rounded-lg overflow-hidden bg-white">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-surface-container-low/50">
                      <tr>
                        <th className="py-2 px-4 font-medium text-on-surface-variant">Kiro User ID</th>
                        <th className="py-2 px-4 font-medium text-on-surface-variant font-mono">Token Secret</th>
                        <th className="py-2 px-4 font-medium text-on-surface-variant">Created</th>
                        <th className="py-2 px-4 font-medium text-on-surface-variant text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-outline-variant/20">
                      {userKeys.map((key) => (
                        <KeyRow key={key.id} apiKey={key} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function UsersPage() {
  const { user: authUser } = useAuth();
  const { data: users, isLoading: usersLoading } = useUsers();
  const { data: keys, isLoading: keysLoading } = useKeys();
  const [expandedUserId, setExpandedUserId] = useState<number | null>(null);

  const isLoading = usersLoading || keysLoading;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-h1 font-bold text-on-surface tracking-tight">User & Tokens</h1>
          <p className="text-on-surface-variant mt-1 text-sm max-w-2xl">
            Manage users, their access roles, and API key registration.
          </p>
        </div>
        <AddKeyDialog />
      </div>

      <Tabs defaultValue="access" className="w-full">
        <TabsList>
          <TabsTrigger value="access">Access & Overrides</TabsTrigger>
          <TabsTrigger value="analytics">Usage Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="access" className="mt-6">
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16 rounded-xl" />
              ))}
            </div>
          ) : (
            <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] overflow-hidden">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-surface-container-low/50 border-b border-outline-variant/30">
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider w-12" />
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                      User Details
                    </th>
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                      Role
                    </th>
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                      Status
                    </th>
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider text-right">
                      Keys
                    </th>
                  </tr>
                </thead>
                <tbody className="text-body-sm divide-y divide-outline-variant/20">
                  {(users || []).map((u) => (
                    <UserRow
                      key={u.id}
                      user={u}
                      keys={keys || []}
                      isExpanded={expandedUserId === u.id}
                      onToggle={() =>
                        setExpandedUserId(expandedUserId === u.id ? null : u.id)
                      }
                    />
                  ))}
                </tbody>
              </table>
              {(!users || users.length === 0) && (
                <div className="p-8 text-center text-on-surface-variant">No users found.</div>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="analytics" className="mt-6">
          <div className="glass-panel rounded-2xl p-6 h-[400px]">
            <h3 className="text-lg font-semibold text-on-surface mb-4">User Credit Consumption</h3>
            <div className="h-[320px]">
              <BarChartUsers users={users || []} keys={keys || []} />
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

- [ ] **Step 2: Create the per-user BarChart component for Usage Analytics tab**

Create `webui/components/charts/bar-chart-users.tsx`:

```tsx
"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ApiKeyResponse, UserResponse } from "@/lib/types";

interface Props {
  users: UserResponse[];
  keys: ApiKeyResponse[];
}

export function BarChartUsers({ users, keys }: Props) {
  const data = users.map((u) => ({
    name: u.username,
    keys: keys.filter((k) => k.user_id === u.id && k.is_active).length,
  }));

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-on-surface-variant">
        No user data available.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e4e1ee" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#464555" }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fontSize: 12, fill: "#464555" }} tickLine={false} axisLine={false} />
        <Tooltip
          contentStyle={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(16px)",
            border: "1px solid rgba(255,255,255,0.9)",
            borderRadius: "12px",
            boxShadow: "0 8px 30px rgba(0,0,0,0.05)",
          }}
        />
        <Bar dataKey="keys" fill="#6366f1" radius={[6, 6, 0, 0]} barSize={40} />
      </BarChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 3: Verify the Users page renders both tabs**

```bash
cd /data/longdt/kiro-gateway/webui
npm run dev &
# Navigate to /users — verify data table with row expansion and Usage Analytics tab
```

Kill the dev server after verifying.

- [ ] **Step 4: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/app/\(dashboard\)/users/ webui/components/charts/bar-chart-users.tsx
git commit -m "feat(webui): implement User & API Key Management Hub with row expansion and usage analytics"
```

---

### Task 8: Screen 3 — User Mapping Import

**Files:**
- Create: `webui/app/(dashboard)/import/page.tsx`

- [ ] **Step 1: Build the Import page with drag-and-drop file upload and preview table**

Create `webui/app/(dashboard)/import/page.tsx`:

```tsx
"use client";

import { useCallback, useState } from "react";
import { Upload, FileText, AlertCircle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useImportUsers } from "@/hooks/use-import";
import type { ImportResult } from "@/lib/types";

interface PreviewRow {
  kiro_user_id: string;
  email?: string;
  username?: string;
  error?: string;
}

function parseCSV(text: string): PreviewRow[] {
  const lines = text.trim().split("\n");
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const idIdx = headers.indexOf("kiro_user_id");
  const emailIdx = headers.indexOf("email");
  const usernameIdx = headers.indexOf("username");

  return lines.slice(1).map((line, i) => {
    const cols = line.split(",").map((c) => c.trim());
    if (idIdx === -1 || !cols[idIdx]) {
      return { kiro_user_id: "", error: `Row ${i + 1}: missing kiro_user_id` };
    }
    return {
      kiro_user_id: cols[idIdx],
      email: emailIdx >= 0 ? cols[emailIdx] : undefined,
      username: usernameIdx >= 0 ? cols[usernameIdx] : undefined,
    };
  });
}

function parseJSON(text: string): PreviewRow[] {
  try {
    const data = JSON.parse(text);
    if (!Array.isArray(data)) return [{ kiro_user_id: "", error: "JSON must be an array" }];
    return data.map((row: any, i: number) => {
      if (!row.kiro_user_id) {
        return { kiro_user_id: "", error: `Row ${i}: missing kiro_user_id` };
      }
      return {
        kiro_user_id: row.kiro_user_id,
        email: row.email,
        username: row.username,
      };
    });
  } catch {
    return [{ kiro_user_id: "", error: "Invalid JSON" }];
  }
}

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewRow[]>([]);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const importUsers = useImportUsers();

  const handleFile = useCallback((f: File) => {
    setFile(f);
    setResult(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const rows = f.name.endsWith(".json") ? parseJSON(text) : parseCSV(text);
      setPreview(rows);
    };
    reader.readAsText(f);
  }, []);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  }

  async function handleImport() {
    if (!file) return;
    const res = await importUsers.mutateAsync(file);
    setResult(res);
  }

  const validRows = preview.filter((r) => !r.error);
  const errorRows = preview.filter((r) => r.error);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-h1 font-bold text-on-surface tracking-tight">Import User Mappings</h1>
        <p className="text-on-surface-variant mt-1 text-sm max-w-2xl">
          Map kiro_user_id (AWS identity) to username or email for meaningful reports.
          Upload a CSV or JSON file.
        </p>
      </div>

      {/* Drop Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`glass-panel rounded-2xl p-12 text-center border-2 border-dashed transition-colors ${
          dragOver ? "border-primary bg-primary/5" : "border-outline-variant/50"
        }`}
      >
        <Upload className="w-12 h-12 text-on-surface-variant mx-auto mb-4" />
        <p className="text-on-surface font-medium">
          Drag & drop your CSV or JSON file here
        </p>
        <p className="text-on-surface-variant text-sm mt-1">
          Required: <code className="font-mono text-xs bg-surface-container px-1 py-0.5 rounded">kiro_user_id</code>.
          Optional: <code className="font-mono text-xs bg-surface-container px-1 py-0.5 rounded">email</code>,{" "}
          <code className="font-mono text-xs bg-surface-container px-1 py-0.5 rounded">username</code>.
        </p>
        <label className="mt-4 inline-block">
          <input
            type="file"
            accept=".csv,.json"
            onChange={handleFileInput}
            className="hidden"
          />
          <span className="cursor-pointer text-sm text-primary hover:underline">
            or click to browse
          </span>
        </label>
        {file && (
          <div className="mt-4 flex items-center justify-center gap-2 text-sm text-on-surface">
            <FileText className="w-4 h-4" />
            {file.name} ({(file.size / 1024).toFixed(1)} KB)
          </div>
        )}
      </div>

      {/* Preview Table */}
      {preview.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Badge variant="secondary">{validRows.length} valid</Badge>
              {errorRows.length > 0 && (
                <Badge variant="destructive">{errorRows.length} errors</Badge>
              )}
            </div>
            <Button onClick={handleImport} disabled={validRows.length === 0 || importUsers.isPending}>
              {importUsers.isPending ? "Importing..." : `Import ${validRows.length} rows`}
            </Button>
          </div>

          <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-container-low/50 border-b border-outline-variant/30">
                <tr>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                    #
                  </th>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                    Kiro User ID
                  </th>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                    Email
                  </th>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                    Username
                  </th>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/20">
                {preview.slice(0, 50).map((row, i) => (
                  <tr key={i} className={row.error ? "bg-error/5" : ""}>
                    <td className="py-2 px-4 text-on-surface-variant text-xs">{i + 1}</td>
                    <td className="py-2 px-4 font-mono text-xs">{row.kiro_user_id || "—"}</td>
                    <td className="py-2 px-4 text-xs">{row.email || "—"}</td>
                    <td className="py-2 px-4 text-xs">{row.username || "—"}</td>
                    <td className="py-2 px-4">
                      {row.error ? (
                        <span className="text-error text-xs flex items-center gap-1">
                          <AlertCircle className="w-3 h-3" /> {row.error}
                        </span>
                      ) : (
                        <span className="text-emerald-600 text-xs flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" /> Valid
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {preview.length > 50 && (
              <div className="p-3 text-center text-xs text-on-surface-variant border-t border-outline-variant/30">
                Showing first 50 of {preview.length} rows
              </div>
            )}
          </div>
        </div>
      )}

      {/* Import Result */}
      {result && (
        <div className="glass-panel-elevated rounded-2xl p-6">
          <h3 className="text-lg font-semibold text-on-surface flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-600" /> Import Complete
          </h3>
          <div className="mt-3 grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-on-surface-variant">Imported:</span>{" "}
              <span className="font-semibold text-on-surface">{result.imported}</span>
            </div>
            <div>
              <span className="text-on-surface-variant">Updated:</span>{" "}
              <span className="font-semibold text-on-surface">{result.updated}</span>
            </div>
            <div>
              <span className="text-on-surface-variant">Errors:</span>{" "}
              <span className="font-semibold text-error">{result.errors.length}</span>
            </div>
          </div>
          {result.errors.length > 0 && (
            <ul className="mt-3 text-xs text-error space-y-1">
              {result.errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify import page renders with drag-and-drop**

```bash
cd /data/longdt/kiro-gateway/webui
npm run dev &
# Navigate to /import — verify drop zone, file selection, preview table
```

Kill the dev server after verifying.

- [ ] **Step 3: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/app/\(dashboard\)/import/
git commit -m "feat(webui): implement User Mapping Import with drag-drop, preview table, and result display"
```

---

### Task 9: Screen 4 — Account Management (Admin Only)

**Files:**
- Create: `webui/app/(dashboard)/accounts/page.tsx`

- [ ] **Step 1: Build the Account Management page with CRUD operations**

Create `webui/app/(dashboard)/accounts/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { Plus, UserCog } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useUsers, useCreateUser, useUpdateUser } from "@/hooks/use-users";
import type { UserResponse } from "@/lib/types";

function CreateUserDialog() {
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "user">("user");
  const createUser = useCreateUser();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await createUser.mutateAsync({ username, password, role });
    setUsername("");
    setPassword("");
    setRole("user");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="gap-2">
          <Plus className="w-4 h-4" /> Create Account
        </Button>
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated">
        <DialogHeader>
          <DialogTitle>Create Dashboard Account</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="new-username">Username</Label>
            <Input
              id="new-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter username"
              required
              minLength={3}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-password">Password</Label>
            <Input
              id="new-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              required
              minLength={6}
            />
          </div>
          <div className="space-y-2">
            <Label>Role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as "admin" | "user")}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="user">User</SelectItem>
                <SelectItem value="admin">Admin</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={createUser.isPending} className="w-full">
            {createUser.isPending ? "Creating..." : "Create Account"}
          </Button>
          {createUser.isError && (
            <p className="text-sm text-error">
              {(createUser.error as any)?.response?.data?.detail || "Failed to create account"}
            </p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ResetPasswordDialog({ user }: { user: UserResponse }) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const updateUser = useUpdateUser();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await updateUser.mutateAsync({ userId: user.id, data: { password } });
    setPassword("");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          Reset Password
        </Button>
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated">
        <DialogHeader>
          <DialogTitle>Reset Password for {user.username}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="reset-pw">New Password</Label>
            <Input
              id="reset-pw"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter new password"
              required
              minLength={6}
            />
          </div>
          <Button type="submit" disabled={updateUser.isPending} className="w-full">
            {updateUser.isPending ? "Updating..." : "Update Password"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ChangeRoleSelect({ user }: { user: UserResponse }) {
  const updateUser = useUpdateUser();

  return (
    <Select
      value={user.role}
      onValueChange={(newRole) =>
        updateUser.mutate({ userId: user.id, data: { role: newRole as "admin" | "user" } })
      }
      disabled={updateUser.isPending}
    >
      <SelectTrigger className="w-24 h-8 text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="user">User</SelectItem>
        <SelectItem value="admin">Admin</SelectItem>
      </SelectContent>
    </Select>
  );
}

function AccountRow({ user }: { user: UserResponse }) {
  const updateUser = useUpdateUser();

  return (
    <tr className="hover:bg-surface-container-lowest transition-colors">
      <td className="py-4 px-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">
            {user.username.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <div className="font-medium text-on-surface">{user.username}</div>
            <div className="text-on-surface-variant text-xs mt-0.5">
              ID: {user.id} · Created: {new Date(user.created_at).toLocaleDateString()}
            </div>
          </div>
        </div>
      </td>
      <td className="py-4 px-6">
        <ChangeRoleSelect user={user} />
      </td>
      <td className="py-4 px-6">
        <Switch
          checked={user.is_active}
          onCheckedChange={(checked) =>
            updateUser.mutate({ userId: user.id, data: { is_active: checked } })
          }
          disabled={updateUser.isPending}
        />
      </td>
      <td className="py-4 px-6 text-right">
        <ResetPasswordDialog user={user} />
      </td>
    </tr>
  );
}

export default function AccountsPage() {
  const { data: users, isLoading } = useUsers();

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-h1 font-bold text-on-surface tracking-tight">Account Management</h1>
          <p className="text-on-surface-variant mt-1 text-sm max-w-2xl">
            Manage dashboard accounts. Create, deactivate, reset passwords, and assign roles.
          </p>
        </div>
        <CreateUserDialog />
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container-low/50 border-b border-outline-variant/30">
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                  Account
                </th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                  Role
                </th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">
                  Active
                </th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="text-body-sm divide-y divide-outline-variant/20">
              {(users || []).map((u) => (
                <AccountRow key={u.id} user={u} />
              ))}
            </tbody>
          </table>
          {(!users || users.length === 0) && (
            <div className="p-8 text-center text-on-surface-variant">No accounts found.</div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify accounts page renders with CRUD operations**

```bash
cd /data/longdt/kiro-gateway/webui
npm run dev &
# Navigate to /accounts — verify create dialog, role select, active toggle, reset password
```

Kill the dev server after verifying.

- [ ] **Step 3: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/app/\(dashboard\)/accounts/
git commit -m "feat(webui): implement Account Management with create, role change, toggle active, and password reset"
```

---

### Task 10: Screen 5 — Gateway Configuration (Admin Only)

**Files:**
- Create: `webui/app/(dashboard)/settings/page.tsx`

- [ ] **Step 1: Build the Gateway Configuration page with form controls**

Create `webui/app/(dashboard)/settings/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Save, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfig, useUpdateConfig } from "@/hooks/use-config";

export default function SettingsPage() {
  const { data: config, isLoading, refetch } = useConfig();
  const updateConfig = useUpdateConfig();

  const [enableModelOverride, setEnableModelOverride] = useState(false);
  const [enforcedModel, setEnforcedModel] = useState("auto");
  const [enableUsageSharing, setEnableUsageSharing] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (config) {
      setEnableModelOverride(config.enable_model_override);
      setEnforcedModel(config.enforced_global_model);
      setEnableUsageSharing(config.enable_usage_sharing);
      setDirty(false);
    }
  }, [config]);

  function handleChange<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setDirty(true);
    };
  }

  async function handleSave() {
    await updateConfig.mutateAsync({
      enable_model_override: enableModelOverride,
      enforced_global_model: enforcedModel,
      enable_usage_sharing: enableUsageSharing,
    });
    setDirty(false);
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-32 rounded-2xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-h1 font-bold text-on-surface tracking-tight">Gateway Configuration</h1>
          <p className="text-on-surface-variant mt-1 text-sm max-w-2xl">
            Configure dynamic gateway parameters. Changes apply immediately without server restart.
          </p>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-2">
            <RefreshCw className="w-4 h-4" /> Reload
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!dirty || updateConfig.isPending}
            className="gap-2"
          >
            <Save className="w-4 h-4" />
            {updateConfig.isPending ? "Saving..." : "Apply Changes"}
          </Button>
        </div>
      </div>

      {/* Model Override Section */}
      <div className="glass-panel rounded-2xl p-8">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-on-surface">Global Model Enforcement</h3>
            <p className="text-sm text-on-surface-variant mt-1 max-w-lg">
              When enabled, all API requests will be forced to use the specified model,
              regardless of what the client requests.
            </p>
          </div>
          <Switch
            checked={enableModelOverride}
            onCheckedChange={handleChange(setEnableModelOverride)}
          />
        </div>
        {enableModelOverride && (
          <div className="mt-6 space-y-2">
            <Label htmlFor="enforced-model">Enforced Model</Label>
            <Input
              id="enforced-model"
              value={enforcedModel}
              onChange={(e) => handleChange(setEnforcedModel)(e.target.value)}
              placeholder="e.g. auto, claude-haiku-4.5, claude-sonnet-4.6"
              className="max-w-md font-mono text-sm"
            />
            <p className="text-xs text-on-surface-variant">
              Use "auto" for automatic model selection, or specify an exact model ID.
            </p>
          </div>
        )}
      </div>

      {/* Usage Sharing / Fallback Section */}
      <div className="glass-panel rounded-2xl p-8">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold text-on-surface">Usage Sharing (Fallback)</h3>
            <p className="text-sm text-on-surface-variant mt-1 max-w-lg">
              When enabled, the gateway will automatically use round-robin fallback to borrow
              a backup key when the primary key is below 1% of its usage limit.
            </p>
          </div>
          <Switch
            checked={enableUsageSharing}
            onCheckedChange={handleChange(setEnableUsageSharing)}
          />
        </div>
      </div>

      {/* Save confirmation */}
      {updateConfig.isSuccess && !dirty && (
        <div className="glass-panel-elevated rounded-2xl p-4 text-center text-sm text-emerald-700 bg-emerald-50/50">
          Configuration saved and applied successfully. Backend cache has been refreshed.
        </div>
      )}
      {updateConfig.isError && (
        <div className="glass-panel-elevated rounded-2xl p-4 text-center text-sm text-error bg-error/5">
          {(updateConfig.error as any)?.response?.data?.detail || "Failed to save configuration"}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify settings page renders and toggles work**

```bash
cd /data/longdt/kiro-gateway/webui
npm run dev &
# Navigate to /settings — verify switches, model input, save/reload buttons
```

Kill the dev server after verifying.

- [ ] **Step 3: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/app/\(dashboard\)/settings/
git commit -m "feat(webui): implement Gateway Configuration with model override and usage sharing toggles"
```

---

### Task 11: Docker Integration & Production Build

**Files:**
- Create: `webui/Dockerfile`
- Create: `webui/.env.example`
- Modify: `docker-compose.apikey.yml` (add webui service)

- [ ] **Step 1: Create environment example file**

Create `webui/.env.example`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 2: Create Dockerfile for the webui**

Create `webui/Dockerfile`:

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
CMD ["node", "server.js"]
```

- [ ] **Step 3: Update next.config.js for standalone output**

Add `output: "standalone"` to `webui/next.config.js`:

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
```

- [ ] **Step 4: Add webui service to docker-compose.apikey.yml**

Append to the `services` section in `docker-compose.apikey.yml`:

```yaml
  webui:
    build:
      context: ./webui
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://kiro-gateway-apikey:8000
    depends_on:
      - kiro-gateway-apikey
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "1"
          memory: 512M
```

- [ ] **Step 5: Verify production build succeeds**

```bash
cd /data/longdt/kiro-gateway/webui
npm run build
```

Expected: Build completes with no errors. `.next/` directory created.

- [ ] **Step 6: Create .gitignore for webui**

Create `webui/.gitignore`:

```
node_modules/
.next/
out/
.env.local
.env
```

- [ ] **Step 7: Commit**

```bash
cd /data/longdt/kiro-gateway
git add webui/Dockerfile webui/.env.example webui/.gitignore webui/next.config.js docker-compose.apikey.yml
git commit -m "feat(webui): add Docker build, standalone output, and docker-compose integration"
```

---

## Summary

| Task | Screen / Component | Estimated Time |
|------|--------------------|---------------|
| 1 | Project Scaffolding & Design System | 30 min |
| 2 | TypeScript Types & API Client | 15 min |
| 3 | Auth Context & Login Screen | 20 min |
| 4 | Dashboard Layout (Sidebar, Topbar, Auth Guard) | 20 min |
| 5 | TanStack Query Hooks | 15 min |
| 6 | Screen 1: Monthly Overview Dashboard | 25 min |
| 7 | Screen 2: User & API Key Management Hub | 35 min |
| 8 | Screen 3: User Mapping Import | 25 min |
| 9 | Screen 4: Account Management | 25 min |
| 10 | Screen 5: Gateway Configuration | 20 min |
| 11 | Docker Integration & Production Build | 15 min |

**Total estimated: ~4 hours**

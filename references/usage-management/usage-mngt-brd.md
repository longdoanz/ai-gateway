# Project Brief: AI Credit Management System (Integrated Gateway)

## 1. Product Concept
A high-fidelity administrative command center for enterprise governance of AI credit consumption. The system is designed for organizations that use an external API Gateway where individual users provide their own keys. This platform synchronizes that usage data to provide a centralized audit and management hub.

**Design Philosophy:** *Minimalism Glassmorphism Light (2026).* High-transparency frosted glass surfaces, soft Sky Blue accents, and high-information density presented with breathable layouts.

**Locked Architectural Decisions:**
- **System access & Accounts:** Management of "Accounts" (Create/Deactivate) is strictly for controlling access to this Gateway management dashboard.
- **External API Keys (BYOK):** Users bring their own external API keys. Gateway purely tracks usage. Users completely own their external API keys. 
- **Gateway Enforcement (Global):** Gateway enforces allowed models globally across the entire gateway. Requests hitting unauthorized models are blocked at the gateway level.
- **Usage Sharing (Fallback):** System allows configuring sharing. When a user's `currentUsage` reaches the `usageLimit` returned by Kiro API (`getUsageLimits`), the gateway automatically shifts requests to use a shared fallback key according to the sharing configuration.
- **Monitoring vs Blocking:** Gateway does not actively block requests based on generic budget logic; it only monitors. Rate lifting or `429` enforcement comes from the backend limitations. 
- **Telemetry SLA:** Usage metrics are cached and periodically persisted, ensuring dashboard data freshness within 1 minute of a request.

---

## 2. Core Functional Requirements

### A. Credit-Based Governance
- **Strictly "Credits":** All usage is abstracted into "Credits". No monetary values ($/VND) or technical token counts are shown to maintain focus on organizational resource allocation.
- **Monthly Budgeting:** Aggregated and per-user burn rate monitoring against monthly organizational limits.
- **Model Enforcement (Global):** Maintain a system-wide allow/deny list of AI models. Requests strictly adhere to this list with clear Gateway error messaging upon denial.

### B. User & API Key Management (Integrated Logic)
- **Account Management:** Master list of company personnel with rapid management actions (Create, Deactivate, Reset Dashboard Password).
- **User-Provided Keys & Auto-Sharing:** Users provide keys via the API Gateway. System triggers mapping requests to fallback pool shared-keys when `currentUsage` approaches `usageLimit`. 
- **Key Display & Security:** 
    - **Masking:** Keys are masked showing only the start and end (e.g., `sk-proj-ax...8f92`).
    - **Status:** Real-time toggle for Active/Inactive states.
    - **Telemetry:** Tracking "Last Used" timestamps pushed from the gateway (under 1-minute freshness).

### C. Unified Management Hub (Tabbed Architecture)
- **Consolidated View:** Merging Dashboard Account Management and deep-dive Analytics into a single dual-tab interface to reduce navigation friction.
- **Bento Grid Layout:** Organizing KPIs and charts into logical, high-visibility blocks.

---

## 3. Screen Inventory & Specifications

### 1. Monthly Overview Dashboard
- **Purpose:** Executive summary of burn rates and system health.
- **Key Features:** Total Credits Burned KPI, User Growth, Remaining Budget, and a 30-day "This Month" consumption trend.
- **Navigation:** Sidebar with **no "Buy Credits" button** to emphasize internal governance.

### 2. User & Token Management Hub (Primary)
- **Tab 1: Access & Overrides:** Interactive table. Row expansion reveals a sub-table of the user's mapped API keys along with their active/fallback sharing status.
- **Tab 2: Usage Analytics:** Comparative charts showing per-user and daily credit burn trends.

---

## 4. Visual Identity (Glacier Light System)
- **Background:** `#F8FAFC` (Pure white with a faint blue tint).
- **Surfaces:** `rgba(255, 255, 255, 0.7)` with `backdrop-filter: blur(16px)`.
- **Typography:** 
    - **Structural:** Inter (Sans-Serif).
    - **Data/Technical:** JetBrains Mono (Monospace) for keys and credit counts.
- **Accents:** Indigo (`#6366F1`) and Sky Blue (`#0EA5E9`).
- **Borders:** Refined `1px solid rgba(226, 232, 240, 0.8)`.
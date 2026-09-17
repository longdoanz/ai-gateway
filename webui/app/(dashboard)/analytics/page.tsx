"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalytics, type AnalyticsRange } from "@/hooks/use-analytics";
import { useGatewayKeyAnalytics } from "@/hooks/use-gateway-key-analytics";
import { BarChartTokens } from "@/components/charts/bar-chart-credits";
import { DonutChartShare } from "@/components/charts/donut-chart-share";
import { GatewayKeyUsageTable } from "@/components/charts/gateway-key-usage-table";
import { LineChartUserDaily } from "@/components/charts/line-chart-user-daily";

// DEPRECATED: Kiro credit usage reporting has moved to 9router. See NineRouterUsageBanner
// below, which replaces the old KiroCreditUsageTable section. Kept the hook/component
// (hooks/use-kiro-credit-usage.ts, components/charts/kiro-credit-usage-table.tsx) intact
// for the cleanup PR to remove once nothing references them.
const NINE_ROUTER_ENABLED = process.env.NEXT_PUBLIC_NINE_ROUTER_ENABLED === "true";
const NINE_ROUTER_URL = (process.env.NEXT_PUBLIC_NINE_ROUTER_URL || "").replace(/\/+$/, "");

function NineRouterUsageBanner() {
  const hasLink = NINE_ROUTER_ENABLED && NINE_ROUTER_URL;

  function handleClick() {
    window.open(`${NINE_ROUTER_URL}/api/auth/oidc/start`, "_blank", "noopener");
  }

  return (
    <div className="glass-panel rounded-3xl px-6 py-5 flex items-center justify-between gap-4 flex-wrap">
      <div className="flex items-start gap-3">
        <span className="material-symbols-outlined text-sky-600 text-xl mt-0.5">open_in_new</span>
        <div>
          <p className="text-sm font-semibold text-on-surface">Kiro credit usage reporting has moved to 9router</p>
          <p className="text-xs text-on-surface-variant mt-0.5">
            Kiro credit/token usage per user is now tracked in 9router. This dashboard no longer shows it here.
          </p>
        </div>
      </div>
      {hasLink && (
        <button
          onClick={handleClick}
          className="cursor-pointer shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg border border-outline-variant/60 bg-white/70 text-on-surface hover:bg-white/90 hover:-translate-y-[1px] transition-all shadow-[0_1px_3px_rgba(0,0,0,0.05)] flex items-center gap-1.5"
        >
          Open 9router
          <span className="material-symbols-outlined text-[14px]">arrow_outward</span>
        </button>
      )}
    </div>
  );
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

const RANGES: AnalyticsRange[] = ["7d", "30d", "90d"];

export default function AnalyticsPage() {
  const [range, setRange] = useState<AnalyticsRange>("7d");
  const { data, isLoading, isError } = useAnalytics(range);
  const { data: gwData, isLoading: gwLoading, isError: gwError } = useGatewayKeyAnalytics(range);

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <div className="glass-panel flex items-center rounded-xl p-1 gap-0.5">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`cursor-pointer px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                range === r
                  ? "bg-primary-container text-white shadow-sm"
                  : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container"
              }`}
            >
              {r.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Row 1: Top Users + Token Usage By Users */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel rounded-3xl p-0 overflow-hidden">
          <div className="px-6 py-4 border-b border-outline-variant/30">
            <h3 className="text-base font-semibold text-on-surface">Top Users</h3>
          </div>
          <div className="p-2">
            {isLoading ? (
              <div className="p-4 space-y-3">
                {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
              </div>
            ) : isError ? (
              <div className="p-6"><ErrorState /></div>
            ) : !data?.top_users?.length ? (
              <EmptyState />
            ) : (
              data.top_users.map((u) => (
                <div key={u.kiro_user_id} className="flex items-center justify-between p-3 rounded-xl hover:bg-surface-container transition-colors">
                  <div className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded-full bg-primary-container flex items-center justify-center text-[10px] font-bold text-on-primary-container">
                      {u.rank}
                    </span>
                    <div>
                      <div className="text-sm font-medium text-on-surface">{u.username ?? u.display_name}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-primary">{formatTokens(u.input_tokens + u.output_tokens)}</div>
                    <div className="text-[10px] text-on-surface-variant">{u.share_pct}%</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <h3 className="text-base font-semibold text-on-surface mb-4">Token Usage By Users</h3>
          <div className="h-[280px]">
            {isLoading ? (
              <Skeleton className="h-full w-full rounded-xl" />
            ) : isError ? (
              <ErrorState />
            ) : !data?.token_share?.length ? (
              <EmptyState />
            ) : (
              <DonutChartShare data={data.token_share} />
            )}
          </div>
        </div>
      </div>

      {/* Row 2: User Token Usage — full width */}
      <div className="glass-panel rounded-3xl p-6">
        <h3 className="text-base font-semibold text-on-surface mb-4">User Token Usage</h3>
        <div className="h-[300px]">
          {isLoading ? (
            <Skeleton className="h-full w-full rounded-xl" />
          ) : isError ? (
            <ErrorState />
          ) : !data?.user_tokens?.length ? (
            <EmptyState />
          ) : (
            <BarChartTokens data={data.user_tokens} />
          )}
        </div>
      </div>

      {/* Row 3: Daily Token Usage per User — full width */}
      <div className="glass-panel rounded-3xl p-6">
        <h3 className="text-base font-semibold text-on-surface mb-4">Daily Token Usage per User</h3>
        <div className="h-[300px]">
          {isLoading ? (
            <Skeleton className="h-full w-full rounded-xl" />
          ) : isError ? (
            <ErrorState />
          ) : !data?.user_daily_series?.length ? (
            <EmptyState />
          ) : (
            <LineChartUserDaily data={data.user_daily_series} />
          )}
        </div>
      </div>

      {/* Row 4: Kiro User Credit Usage — DEPRECATED, replaced by NineRouterUsageBanner (see top of file) */}
      <NineRouterUsageBanner />

      {/* Row 5: Gateway Key Usage */}
      <div className="grid grid-cols-1 gap-6">
        <div className="glass-panel rounded-3xl p-0 overflow-hidden">
          <div className="px-6 py-4 border-b border-outline-variant/30 flex items-center justify-between">
            <h3 className="text-base font-semibold text-on-surface">Gateway Key Users</h3>
            {gwData && (
              <span className="text-xs text-on-surface-variant">
                {gwData.active_gateway_users} active / {gwData.total_gateway_users} total
              </span>
            )}
          </div>
          <div className="p-2">
            {gwLoading ? (
              <div className="p-4 space-y-3">
                {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
              </div>
            ) : gwError ? (
              <div className="p-6"><ErrorState /></div>
            ) : !gwData?.user_usages?.length ? (
              <div className="p-6"><EmptyState /></div>
            ) : (
              <GatewayKeyUsageTable data={gwData.user_usages} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex items-center justify-center h-full text-on-surface-variant text-sm">
      No data for this period.
    </div>
  );
}

function ErrorState() {
  return (
    <div className="flex items-center justify-center h-full text-error text-sm">
      Failed to load. Please refresh.
    </div>
  );
}
